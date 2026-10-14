import { ImageResponse, loadGoogleFont } from "workers-og";

// ---------- config ----------
const TESTS = {
  image: { name: "AI Image Test", roundSize: 20, dailySize: 10, seconds: 5, noun: "images" },
};
const PRIOR_P = 0.62;      // assumed accuracy for the starting score distribution
const PRIOR_WEIGHT = 40;   // pseudo-rounds blended into the histogram until real data dominates
const MANIFEST_TTL = 5 * 60 * 1000;

// ---------- small utils ----------
const json = (data, status = 200, extra = {}) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...extra } });
const bad = (msg, status = 400) => json({ error: msg }, status);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const todayUTC = () => new Date().toISOString().slice(0, 10);

function hashStr(s) { let h = 2166136261 >>> 0; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; } return h; }
function mulberry32(a) { return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function shuffle(arr, rng) { const a = arr.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rng() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }
const sample = (arr, n, rng) => shuffle(arr, rng).slice(0, n);

function binomialPrior(total, p, weight) {
  const out = []; let c = 1;
  for (let k = 0; k <= total; k++) { out[k] = c * Math.pow(p, k) * Math.pow(1 - p, total - k) * weight; c = (c * (total - k)) / (k + 1); }
  return out;
}

// ---------- manifest ----------
let manifestCache = { at: 0, data: null };
async function loadManifest(env, reqUrl) {
  if (manifestCache.data && Date.now() - manifestCache.at < MANIFEST_TTL) return manifestCache.data;
  const res = await env.ASSETS.fetch(new URL("/media/manifest.json", reqUrl));
  if (!res.ok) throw new Error("manifest missing");
  const data = await res.json();
  manifestCache = { at: Date.now(), data };
  return data;
}

function pickRound(manifest, n, rng) {
  const real = manifest.items.filter((i) => i.label === "real");
  const ai = manifest.items.filter((i) => i.label === "ai");
  const half = Math.floor(n / 2);
  return shuffle([...sample(real, half, rng), ...sample(ai, n - half, rng)], rng);
}

// ---------- API ----------
async function apiRound(req, env, url) {
  const test = url.searchParams.get("test") || "image";
  const mode = url.searchParams.get("mode") || "round";
  const cfg = TESTS[test];
  if (!cfg) return bad("unknown test", 404);
  if (!["round", "daily"].includes(mode)) return bad("unknown mode");
  const manifest = await loadManifest(env, url);
  const day = todayUTC();
  const rng = mode === "daily" ? mulberry32(hashStr(`daily:${test}:${day}`)) : mulberry32(hashStr(crypto.randomUUID()));
  const n = mode === "daily" ? cfg.dailySize : cfg.roundSize;
  const items = pickRound(manifest, n, rng);
  return json({ test, mode, day, seconds: cfg.seconds, version: manifest.version, items }, 200,
    mode === "daily" ? { "cache-control": "public, max-age=300" } : {});
}

async function percentile(env, histKey, total, score) {
  const { results } = await env.DB.prepare("SELECT score, n FROM score_hist WHERE test = ?").bind(histKey).all();
  const prior = binomialPrior(total, PRIOR_P, PRIOR_WEIGHT);
  const counts = prior.slice();
  let real = 0;
  for (const r of results) { if (r.score >= 0 && r.score <= total) { counts[r.score] += r.n; real += r.n; } }
  let below = 0, sum = 0;
  for (let k = 0; k <= total; k++) { if (k < score) below += counts[k]; sum += counts[k]; }
  const pct = Math.round((100 * (below + 0.5 * counts[score])) / sum);
  return { percentile: Math.max(1, Math.min(99, pct)), rounds: real };
}

async function apiResult(req, env) {
  if (req.method !== "POST") return bad("POST only", 405);
  if (env.RL) {  // per-IP rate limit so a script can't skew the public stat; binding is optional
    const ip = req.headers.get("cf-connecting-ip") || "unknown";
    const { success } = await env.RL.limit({ key: ip });
    if (!success) return bad("slow down", 429);
  }
  if (Number(req.headers.get("content-length") || 0) > 8192) return bad("too large", 413);
  let b; try { b = await req.json(); } catch { return bad("bad json"); }
  const cfg = TESTS[b.test];
  if (!cfg) return bad("unknown test");
  if (!["round", "daily"].includes(b.mode)) return bad("unknown mode");
  const total = b.mode === "daily" ? cfg.dailySize : cfg.roundSize;
  if (!Number.isInteger(b.score) || b.score < 0 || b.score > total || b.total !== total) return bad("bad score");
  const avgMs = Number.isFinite(b.avg_ms) ? Math.max(0, Math.min(60000, Math.round(b.avg_ms))) : null;
  const items = Array.isArray(b.items) ? b.items.slice(0, total).filter((i) => typeof i.id === "string" && i.id.length <= 24) : [];
  const day = b.mode === "daily" ? todayUTC() : null;
  const histKey = b.mode === "daily" ? `${b.test}:daily` : b.test;

  const stmts = [
    env.DB.prepare("INSERT INTO results (test, mode, day, score, total, avg_ms) VALUES (?, ?, ?, ?, ?, ?)").bind(b.test, b.mode, day, b.score, total, avgMs),
    env.DB.prepare("INSERT INTO score_hist (test, score, n) VALUES (?, ?, 1) ON CONFLICT(test, score) DO UPDATE SET n = n + 1").bind(histKey, b.score),
    ...items.map((i) => env.DB.prepare("INSERT INTO item_stats (item_id, shown, wrong) VALUES (?, 1, ?) ON CONFLICT(item_id) DO UPDATE SET shown = shown + 1, wrong = wrong + excluded.wrong").bind(i.id, i.correct ? 0 : 1)),
  ];
  await env.DB.batch(stmts);
  const p = await percentile(env, histKey, total, b.score);
  return json({ ok: true, ...p });
}

async function apiStats(req, env, url) {
  const test = url.searchParams.get("test") || "image";
  if (!TESTS[test]) return bad("unknown test", 404);
  const cache = caches.default;
  const key = new Request(new URL(`/api/stats?test=${test}`, url).toString());
  const hit = await cache.match(key);
  if (hit) return hit;
  const q = (where) => env.DB.prepare(`SELECT COUNT(*) c, COALESCE(SUM(score),0) s, COALESCE(SUM(total),0) t FROM results WHERE test = ? ${where}`).bind(test).first();
  const [all, week, prev, hard] = await Promise.all([
    q(""),
    q("AND created_at >= datetime('now','-7 days')"),
    q("AND created_at < datetime('now','-7 days') AND created_at >= datetime('now','-37 days')"),
    env.DB.prepare("SELECT item_id, shown, wrong FROM item_stats WHERE shown >= 20 ORDER BY wrong * 1.0 / shown DESC LIMIT 6").all(),
  ]);
  const acc = (r) => (r.t ? Math.round((100 * r.s) / r.t) : null);
  const body = {
    test, rounds: all.c, accuracy: acc(all), accuracy_week: acc(week), rounds_week: week.c, accuracy_prev: acc(prev),
    hardest: hard.results.map((r) => ({ id: r.item_id, fooled: Math.round((100 * r.wrong) / r.shown) })),
    updated: new Date().toISOString(),
  };
  const res = json(body, 200, { "cache-control": "public, max-age=300" });
  await cache.put(key, res.clone());
  return res;
}

// ---------- share card ----------
let fontCache = null;
async function fonts() {
  if (!fontCache) fontCache = Promise.all([loadGoogleFont({ family: "Figtree", weight: 800 }), loadGoogleFont({ family: "Figtree", weight: 500 })])
    .then(([b, m]) => [{ name: "Figtree", data: b, weight: 800, style: "normal" }, { name: "Figtree", data: m, weight: 500, style: "normal" }]);
  return fontCache;
}

// Brand palette and logo, kept in sync with public/app.css and public/favicon.svg.
const C = { brand: "#1f5eff", ink: "#16181d", muted: "#5f6670", line: "#e5e5e5", real: "#1d9a55", ai: "#ea5a0c" };
const MARK = (fill, glyph) => `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="${fill}"/><path d="M15.25 7a9 9 0 0 0 0 18z" fill="${glyph}"/><path d="M16.75 7h3v3h3v3h3v6h-3v3h-3v3h-3z" fill="${glyph}"/></svg>`)}`;
const logo = (size, color, fill = C.brand, glyph = "#fff") => `<div style="display:flex;align-items:center;font-size:${size}px;font-weight:800;letter-spacing:-1px;color:${color}"><img src="${MARK(fill, glyph)}" width="${Math.round(size * 1.3)}" height="${Math.round(size * 1.3)}" style="margin-right:${Math.round(size * 0.4)}px"/>fakebench</div>`;

async function ogCard(req, env, url, test) {
  const cfg = TESTS[test];
  if (!cfg) return bad("unknown test", 404);
  const s = Math.max(0, Math.min(99, parseInt(url.searchParams.get("s") ?? "-1", 10)));
  const t = Math.max(1, Math.min(99, parseInt(url.searchParams.get("t") ?? cfg.roundSize, 10)));
  const p = Math.max(0, Math.min(99, parseInt(url.searchParams.get("p") ?? "0", 10)));
  const generic = !(s >= 0);
  const cache = caches.default;
  const key = new Request(new URL(`/og/${test}.png?s=${s}&t=${t}&p=${p}`, url).toString());
  const hit = await cache.match(key);
  if (hit) return hit;
  const host = esc(url.host);
  const headline = generic ? `Can you spot the AI ${cfg.noun}?` : `${s}/${t}`;
  const sub = generic ? `${cfg.roundSize} ${cfg.noun}. ${cfg.seconds} seconds each. How many can you get right?` : `Ahead of roughly ${p}% of scores on the ${cfg.name}`;
  const html = `
  <div style="display:flex;flex-direction:column;justify-content:space-between;width:1200px;height:630px;padding:60px 72px;background:#fff;color:${C.ink};font-family:Figtree;border-bottom:16px solid ${C.brand}">
    ${logo(34, C.ink)}
    <div style="display:flex;flex-direction:column">
      <div style="display:flex;font-size:${generic ? 84 : 176}px;font-weight:800;line-height:1;letter-spacing:${generic ? -3 : -7}px;color:${generic ? C.ink : C.brand}">${headline}</div>
      <div style="display:flex;font-size:40px;font-weight:500;color:${C.muted};margin-top:24px">${esc(sub)}</div>
    </div>
    <div style="display:flex;justify-content:space-between;font-size:26px;color:${C.muted};font-weight:500"><div style="display:flex">${host}/${test}</div><div style="display:flex;font-weight:800;color:${C.brand}">${generic ? "" : "Think you can beat it?"}</div></div>
  </div>`;
  const img = new ImageResponse(html, { width: 1200, height: 630, fonts: await fonts() });
  const res = new Response(img.body, { headers: { "content-type": "image/png", "cache-control": "public, max-age=604800, immutable" } });
  await cache.put(key, res.clone());
  return res;
}

// Transparent 1080x1920 overlays for the daily vertical video, so ffmpeg needs no font or drawtext.
async function overlayCard(req, env, url) {
  const q = url.searchParams;
  const kind = q.get("kind") || "question";
  const txt = (k, max = 60) => esc((q.get(k) || "").slice(0, max));
  const cache = caches.default;
  const key = new Request(url.toString());
  const hit = await cache.match(key);
  if (hit) return hit;
  const wrap = (inner) => `<div style="display:flex;flex-direction:column;align-items:center;justify-content:space-between;width:1080px;height:1920px;padding:220px 60px 300px;color:#fff;font-family:Figtree;text-align:center">${inner}</div>`;
  let html;
  if (kind === "question") {
    html = wrap(`<div style="display:flex;flex-direction:column;align-items:center"><div style="display:flex;font-size:104px;font-weight:800;letter-spacing:-3px;text-shadow:0 4px 24px rgba(0,0,0,.6)">REAL or AI?</div><div style="display:flex;font-size:48px;font-weight:500;color:#dfe3ef;margin-top:16px;text-shadow:0 2px 12px rgba(0,0,0,.6)">${txt("n", 8)}</div></div><div style="display:flex;font-size:260px;font-weight:800;line-height:1;text-shadow:0 6px 30px rgba(0,0,0,.7)">${txt("count", 2)}</div>`);
  } else if (kind === "reveal") {
    const ai = q.get("label") === "AI";
    html = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;width:1080px;height:1920px;padding:0 60px;background:${ai ? "rgba(234,90,12,.82)" : "rgba(29,154,85,.82)"};color:#fff;font-family:Figtree;text-align:center"><div style="display:flex;font-size:240px;font-weight:800;letter-spacing:-8px;line-height:1">${ai ? "AI" : "REAL"}</div><div style="display:flex;font-size:60px;font-weight:500;margin-top:40px;line-height:1.2">${txt("detail", 70)}</div></div>`;
  } else if (kind === "end") {
    html = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;width:1080px;height:1920px;padding:0 80px;background:${C.brand};color:#fff;font-family:Figtree;text-align:center"><div style="display:flex;margin-bottom:120px">${logo(48, "#fff", "#fff", C.brand)}</div><div style="display:flex;font-size:112px;font-weight:800;letter-spacing:-4px;line-height:1.05">How did you do?</div><div style="display:flex;font-size:58px;font-weight:500;color:#dbe5ff;margin-top:60px;line-height:1.25">${txt("stat", 90)}</div><div style="display:flex;font-size:64px;font-weight:500;margin-top:160px">Get your score at</div><div style="display:flex;font-size:92px;font-weight:800;color:#fff;margin-top:10px;letter-spacing:-2px">${txt("host", 40)}</div></div>`;
  } else return bad("unknown kind");
  const img = new ImageResponse(html, { width: 1080, height: 1920, fonts: await fonts() });
  const res = new Response(img.body, { headers: { "content-type": "image/png", "cache-control": "public, max-age=86400" } });
  await cache.put(key, res.clone());
  return res;
}

function sharePage(url, test, s, p) {
  const cfg = TESTS[test];
  if (!cfg) return new Response("not found", { status: 404 });
  const origin = url.origin;
  const img = `${origin}/og/${test}.png?s=${s}&t=${cfg.roundSize}&p=${p}`;
  const title = `I scored ${s}/${cfg.roundSize} on the ${cfg.name}`;
  const desc = `Ahead of roughly ${p}% of scores on this test. Think you can beat it?`;
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)} · FakeBench</title><meta name="description" content="${esc(desc)}"><meta name="robots" content="noindex">
<meta property="og:title" content="${esc(title)}"><meta property="og:description" content="${esc(desc)}"><meta property="og:image" content="${img}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta property="og:type" content="website"><meta property="og:url" content="${origin}/share/${test}/${s}-${p}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="${esc(title)}"><meta name="twitter:description" content="${esc(desc)}"><meta name="twitter:image" content="${img}">
<link rel="stylesheet" href="/app.css"></head><body><main class="wrap share"><a class="brand" href="/">FakeBench</a>
<img class="card" src="${img}" alt="${esc(title)}" width="1200" height="630"><h1>${esc(title)}</h1><p class="lede">${esc(desc)}</p>
<a class="btn primary big" href="/${test}">Take the test</a><p class="muted">${cfg.roundSize} ${cfg.noun}, ${cfg.seconds} seconds each. No sign-up.</p><p class="muted small">Rankings are estimates based on completed rounds and a starting baseline. <a href="/about">How they're calculated</a></p></main></body></html>`;
  return new Response(html, { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "public, max-age=86400" } });
}

// ---------- router ----------
export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const path = url.pathname;
    try {
      if (path === "/api/round") return apiRound(req, env, url);
      if (path === "/api/result") return apiResult(req, env);
      if (path === "/api/stats") return apiStats(req, env, url);
      if (path === "/api/health") return json({ ok: true, time: new Date().toISOString() });
      let m;
      if (path === "/og/overlay.png") return overlayCard(req, env, url);
      if ((m = path.match(/^\/og\/([a-z]+)\.png$/))) return ogCard(req, env, url, m[1]);
      if ((m = path.match(/^\/share\/([a-z]+)\/(\d{1,2})-(\d{1,2})\/?$/))) return sharePage(url, m[1], +m[2], +m[3]);
      return env.ASSETS.fetch(req);
    } catch (e) {
      console.error(e);
      return json({ error: "server error" }, 500);
    }
  },

  // Nightly: roll yesterday into daily_rollup so the public stat page never scans the results table.
  async scheduled(event, env, ctx) {
    await env.DB.prepare(
      `INSERT OR REPLACE INTO daily_rollup (test, day, rounds, correct, total)
       SELECT test, date(created_at), COUNT(*), SUM(score), SUM(total) FROM results
       WHERE date(created_at) = date('now','-1 day') GROUP BY test`
    ).run();
  },
};
