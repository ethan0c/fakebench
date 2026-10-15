/* FakeBench test engine. One page per test; the body carries data-test. */
(() => {
  const TEST = document.body.dataset.test;
  if (!TEST) return;
  const NAMES = { image: "AI Image Test" };
  const $ = (s, r = document) => r.querySelector(s);
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const todayUTC = () => new Date().toISOString().slice(0, 10);
  const screens = { start: $("#start"), ready: $("#ready"), play: $("#play"), results: $("#results") };
  const show = (name) => { for (const k in screens) screens[k].classList.toggle("hidden", k !== name); window.scrollTo({ top: 0 }); };
  const toast = (msg) => { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 1800); };
  const store = { get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } }, set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} } };

  // ---------- sound: tiny Web Audio synth, no files. Preference stays in this browser. ----------
  const sfx = (() => {
    let ctx = null, on = store.get("fb:sound", true);
    const ac = (create = true) => {
      const C = window.AudioContext || window.webkitAudioContext; if (!C) return null;
      if (!ctx && !create) return null;
      if (!ctx) ctx = new C();
      if (ctx.state === "suspended") ctx.resume();
      return ctx;
    };
    function tone(freq, at, dur, type = "triangle", vol = 0.12, slideTo) {
      const c = ac(); if (!c) return;
      const o = c.createOscillator(), g = c.createGain(), t = c.currentTime + at;
      o.type = type; o.frequency.setValueAtTime(freq, t);
      if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, t + dur);
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol, t + 0.012); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.connect(g).connect(c.destination); o.start(t); o.stop(t + dur + 0.03);
    }
    const play = (fn) => { if (on) try { fn(); } catch {} };
    return {
      ctx: ac,
      get on() { return on; },
      set(v) { on = v; store.set("fb:sound", v); },
      count: (n) => play(() => tone(n === 1 ? 784 : 587.33, 0, 0.11, "triangle", 0.1)),
      go: () => play(() => tone(1046.5, 0, 0.18, "triangle", 0.12)),
      good: (combo) => play(() => { const f = 523.25 * Math.pow(2, Math.min(combo, 10) / 12); tone(f, 0, 0.12); tone(f * 1.5, 0.07, 0.2); }),
      bad: () => play(() => tone(240, 0, 0.26, "sawtooth", 0.05, 120)),
      tick: () => play(() => tone(1250, 0, 0.035, "square", 0.025)),
      win: () => play(() => [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => tone(f, i * 0.09, 0.3))),
      end: () => play(() => [392, 523.25].forEach((f, i) => tone(f, i * 0.11, 0.24, "triangle", 0.09))),
    };
  })();
  // ---------- background music: off until the player turns it on; fetched only then ----------
  const music = (() => {
    const LEVEL = 0.22;
    let on = store.get("fb:music", false), buf = null, loading = null, src = null, gain = null;
    async function startLoop() {
      const c = sfx.ctx(); if (!c || src) return;
      try {
        loading ??= fetch("/media/music/lounge.mp3").then((r) => r.arrayBuffer())
          .then((a) => new Promise((res, rej) => c.decodeAudioData(a, res, rej)));
        buf ??= await loading;
        if (!on || src) return;
        gain = c.createGain(); gain.gain.value = 0.0001; gain.connect(c.destination);
        src = c.createBufferSource(); src.buffer = buf; src.loop = true; src.connect(gain); src.start();
        gain.gain.exponentialRampToValueAtTime(LEVEL, c.currentTime + 1.5);
      } catch { loading = null; }
    }
    function stopLoop() {
      if (!src) return;
      const c = sfx.ctx(), s = src, g = gain; src = gain = null;
      g.gain.setTargetAtTime(0.0001, c.currentTime, 0.15);
      setTimeout(() => { try { s.stop(); } catch {} g.disconnect(); }, 800);
    }
    return {
      get on() { return on; },
      set(v) { on = v; store.set("fb:music", v); v ? startLoop() : stopLoop(); },
      resume() { if (on) startLoop(); },
      duck(low) { if (gain) gain.gain.setTargetAtTime(low ? LEVEL * 0.35 : LEVEL, sfx.ctx().currentTime, 0.12); },
    };
  })();
  const musBtn = $("#mus");
  if (musBtn) {
    musBtn.setAttribute("aria-pressed", String(music.on));
    musBtn.onclick = () => { music.set(!music.on); musBtn.setAttribute("aria-pressed", String(music.on)); };
  }
  // browsers only allow audio after a gesture, so a saved "music on" starts on the first click or key
  const wake = () => { music.resume(); removeEventListener("pointerdown", wake); removeEventListener("keydown", wake); };
  addEventListener("pointerdown", wake); addEventListener("keydown", wake);
  document.addEventListener("visibilitychange", () => { const c = sfx.ctx(false); if (c) document.hidden ? c.suspend() : c.resume(); });

  const sndBtn = $("#snd");
  if (sndBtn) {
    sndBtn.setAttribute("aria-pressed", String(sfx.on));
    sndBtn.onclick = () => { sfx.set(!sfx.on); sndBtn.setAttribute("aria-pressed", String(sfx.on)); if (sfx.on) sfx.good(0); };
  }
  const calm = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  function confetti() {
    if (calm()) return;
    const box = el("div", "confetti"), cols = ["var(--brand)", "var(--real)", "var(--ai)", "#ffc53d"];
    for (let i = 0; i < 70; i++) {
      const c = el("i");
      c.style.cssText = `left:${Math.random() * 100}%;background:${cols[i % 4]};animation-delay:${Math.random() * 0.3}s;animation-duration:${1.6 + Math.random() * 1.2}s;--x:${(Math.random() - 0.5) * 220}px;--r:${Math.random() * 720 - 360}deg`;
      box.appendChild(c);
    }
    document.body.appendChild(box); setTimeout(() => box.remove(), 3500);
  }
  function countUp(node, to, suffix = "") {
    if (calm() || !window.requestAnimationFrame) { node.textContent = to + suffix; return; }
    const t0 = performance.now(), dur = 900;
    const step = (t) => { const k = Math.min(1, (t - t0) / dur); node.textContent = Math.round(to * (1 - Math.pow(1 - k, 3))) + suffix; if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }

  let prefetched = null; // next random round, fetched while results are on screen
  let seconds = 5;

  async function fetchRound(mode, opts = {}) {
    const r = await fetch(`/api/round?${new URLSearchParams({ test: TEST, mode, ...opts })}`);
    if (!r.ok) throw new Error("round");
    return r.json();
  }
  function preload(items, onEach = () => {}) {
    return Promise.all(items.map((it) => new Promise((res) => {
      let done = false; const fin = () => { if (!done) { done = true; onEach(); res(); } };
      const im = new Image(); im.onload = im.onerror = fin; im.src = it.src; setTimeout(fin, 8000);
    })));
  }
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  // 3-2-1 while the round's images load; if they're still loading after "1", the bar keeps showing progress
  async function getReady(items, label) {
    const num = $("#ready-num"), bar = $("#ready-bar"), lab = $("#ready-label");
    let loaded = 0, counting = true;
    const progress = () => {
      bar.style.transform = `scaleX(${loaded / items.length})`;
      if (!counting) lab.textContent = `Loading images ${loaded}/${items.length}`;
    };
    lab.textContent = label || "Get ready"; num.classList.remove("hidden"); progress();
    show("ready");
    const loading = preload(items, () => { loaded++; progress(); });
    for (const n of [3, 2, 1]) {
      num.textContent = n; num.classList.remove("beat"); void num.offsetWidth; num.classList.add("beat");
      sfx.count(n); await wait(calm() ? 250 : 550);
    }
    counting = false;
    if (loaded < items.length) { num.classList.add("hidden"); progress(); }
    await loading;
    sfx.go();
  }

  // ---------- live stat on start screen ----------
  const MIN_ROUNDS = 10; // a public average from a handful of rounds is noise
  async function loadStat() {
    const box = $("#stat"); if (!box) return;
    const num = $(".stat-num", box), txt = $(".stat-text", box);
    try {
      const s = await (await fetch(`/api/stats?test=${TEST}`)).json();
      const weekly = s.accuracy_week != null, acc = s.accuracy_week ?? s.accuracy;
      if (acc == null || s.rounds < MIN_ROUNDS) { num.textContent = ""; txt.textContent = "New benchmark. Early results are coming in, so take the test and help set the baseline."; return; }
      let delta = "";
      if (weekly && s.accuracy_prev != null && s.accuracy_prev !== acc) delta = `, ${acc > s.accuracy_prev ? "up" : "down"} from ${s.accuracy_prev}% in the previous 30 days`;
      countUp(num, acc, "%");
      txt.textContent = `of answers were correct ${weekly ? "over the past seven days" : "across all tests so far"}${delta}.`;
    } catch { txt.textContent = "Real or AI? 5 seconds per image."; }
  }

  // ---------- game ----------
  const game = { mode: "round", opts: {}, items: [], idx: 0, answers: [], t0: 0, timer: null, ticks: [], locked: false, combo: 0 };

  async function start(mode, opts = {}) {
    game.mode = mode;
    game.opts = opts;
    const btns = [$("#btn-round"), $("#btn-daily"), $("#btn-level"), $("#btn-again")];
    btns.forEach((b) => b && (b.disabled = true));
    try {
      const data = mode === "round" && prefetched ? prefetched : await fetchRound(mode, opts);
      prefetched = null;
      seconds = data.seconds || 5;
      game.items = data.items; game.idx = 0; game.answers = []; game.combo = 0; game.day = data.day; game.data = data;
      $("#round-label").textContent = mode === "level" ? `Level ${data.level} · ${data.level_name}` : mode === "cat" ? data.cat_name : mode === "daily" ? "Daily" : "";
      await getReady(game.items, $("#round-label").textContent);
      show("play");
      next();
    } catch (e) {
      show("start");
      toast("Couldn't load the test. Try again.");
    } finally { btns.forEach((b) => b && (b.disabled = false)); }
  }

  function next() {
    if (game.idx >= game.items.length) return finish();
    const it = game.items[game.idx];
    const img = $("#img"); img.src = it.src; img.classList.remove("enter"); void img.offsetWidth; img.classList.add("enter");
    $(".frame").classList.remove("good", "bad");
    $("#count").textContent = `${game.idx + 1} / ${game.items.length}`;
    renderLive();
    // the bar slides out of its track at a constant rate, so its rounded end stays round; it freezes on answer
    const bar = $("#bar"); game.barAnim?.cancel();
    game.barAnim = bar.animate?.([{ transform: "translateX(0)" }, { transform: "translateX(-100%)" }], { duration: seconds * 1000, easing: "linear", fill: "forwards" });
    $("#fb").className = "fb"; game.locked = false; game.t0 = performance.now();
    game.timer = setTimeout(() => answer(null), seconds * 1000);
    // last two seconds: bar turns red and ticks
    $(".timer").classList.remove("low"); music.duck(false);
    game.ticks = [2, 1].filter((s) => s < seconds).map((s) => setTimeout(() => { $(".timer").classList.add("low"); music.duck(true); sfx.tick(); }, (seconds - s) * 1000));
  }
  function renderLive(bump) {
    const live = $("#score-live");
    live.innerHTML = `Score <span>${game.answers.filter((a) => a.correct).length}</span>${game.combo >= 3 ? `<span class="combo">🔥 ${game.combo}</span>` : ""}`;
    if (bump) live.firstElementChild.className = "bump";
  }

  function answer(choice) {
    if (game.locked) return; game.locked = true; clearTimeout(game.timer); game.ticks.forEach(clearTimeout); game.barAnim?.pause();
    const it = game.items[game.idx];
    const ms = Math.round(performance.now() - game.t0);
    const correct = choice === it.label;
    game.answers.push({ id: it.id, correct, choice, ms });
    game.combo = correct ? game.combo + 1 : 0;
    correct ? sfx.good(game.combo) : sfx.bad();
    $(".frame").classList.add(correct ? "good" : "bad");
    renderLive(correct);
    const fb = $("#fb");
    const what = it.label === "ai" ? `AI <small>${esc(it.model || "")}</small>` : `Real photo <small>${esc(it.credit ? "by " + it.credit : "")}</small>`;
    fb.innerHTML = (choice === null ? "Time's up. " : correct ? "Correct! " : "Not quite. ") + what;
    fb.className = "fb show " + (correct ? "good" : "bad");
    game.idx++;
    setTimeout(next, correct ? 550 : 900);
  }

  async function finish() {
    const total = game.items.length, score = game.answers.filter((a) => a.correct).length;
    const avg_ms = Math.round(game.answers.reduce((s, a) => s + a.ms, 0) / Math.max(1, game.answers.length));
    show("results");
    $("#r-score").textContent = `${score}/${total}`;
    $("#r-acc").textContent = `${Math.round((100 * score) / total)}%`;
    $("#r-ms").textContent = `${(avg_ms / 1000).toFixed(1)}s`;
    $("#r-pct").innerHTML = `<span class="spin"></span>`;
    $("#r-pct-line").textContent = "Checking how your score compares…";
    renderMisses();
    let pct = null, rounds = 0;
    try {
      const r = await fetch("/api/result", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ test: TEST, mode: game.mode, ...game.opts, score, total, avg_ms, items: game.answers.map((a) => ({ id: a.id, correct: a.correct })) }) });
      const d = await r.json(); pct = d.percentile; rounds = d.rounds;
    } catch {}
    if (pct == null) { $("#r-pct").textContent = "–"; $("#r-pct-line").textContent = "Your score is ready, but we couldn't load your percentile."; }
    else {
      $("#r-pct").textContent = `${pct}%`;
      $("#r-pct-line").innerHTML = `Your score ranks above roughly <span class="score-pct">${pct}%</span> of scores.<span class="muted small"> Estimated from ${rounds.toLocaleString()} completed ${rounds === 1 ? "round" : "rounds"} and a starting baseline. <a href="/about">How it's calculated</a></span>`;
    }
    $("#r-outcome").className = "outcome hidden";
    $("#btn-again").textContent = "Play again";
    if (game.mode === "level") levelOutcome(score);
    if (game.mode === "daily") saveDaily(score, total, pct);
    renderShare(score, total, pct);
    const great = game.mode === "level" ? score >= game.data.pass : score / total >= 0.9;
    if (great) { sfx.win(); confetti(); } else sfx.end();
    if (game.mode === "round") fetchRound("round").then((d) => (prefetched = d)).catch(() => {});
    loadStat();
  }

  function renderMisses() {
    const wrap = $("#misses"); wrap.innerHTML = "";
    const missed = game.answers.map((a, i) => ({ a, it: game.items[i] })).filter((x) => !x.a.correct);
    $("#misses-h").textContent = missed.length ? `Images you missed (${missed.length})` : "You got every image right!";
    for (const { a, it } of missed) {
      const said = a.choice === null ? "time ran out" : `you chose ${a.choice === "ai" ? "AI" : "real"}`;
      const cap = it.label === "ai"
        ? `<span class="lab">AI image · ${said}</span><b>${esc(it.model || "Unknown model")}</b>`
        : `<span class="lab">Real photo · ${said}</span><b>${esc(it.credit || "Wikimedia Commons")}</b><a href="${esc(it.page || "#")}" target="_blank" rel="noopener">${esc(it.license || "Source")}</a>`;
      const d = el("div", `miss ${it.label}`, `<img src="${esc(it.src)}" alt="" loading="lazy"><div class="cap">${cap}</div>`);
      d.style.setProperty("--i", wrap.children.length);
      wrap.appendChild(d);
    }
  }

  function shareText(score, total, pct) {
    const name = NAMES[TEST] || "FakeBench";
    if (game.mode === "daily") {
      const grid = game.answers.map((a) => (a.correct ? "🟩" : "🟥")).join("");
      const streak = store.get(`fb:daily:${TEST}`, {}).streak || 1;
      return `FakeBench Daily ${game.day}\n${name}: ${score}/${total}${pct != null ? ` · ahead of roughly ${pct}% of scores` : ""}\n${grid}\n🔥 ${streak}-day streak\n`;
    }
    if (game.mode === "level") return `I ${score >= game.data.pass ? "passed" : "got"} level ${game.data.level} (${game.data.level_name}) on the FakeBench ${name}${score >= game.data.pass ? "" : ` ${score}/${total}`}. How far can you get?`;
    if (game.mode === "cat") return `I got ${score}/${total} on FakeBench's ${game.data.cat_name.toLowerCase()} round. Real photo or AI: how many can you get right?`;
    return `I got ${score}/${total} on the ${name}${pct != null ? ` (ahead of roughly ${pct}% of scores)` : ""}. How many can you get right?`;
  }

  function renderShare(score, total, pct) {
    const url = pct != null && game.mode === "round" ? `${location.origin}/share/${TEST}/${score}-${pct}` : `${location.origin}/${TEST}`;
    const text = shareText(score, total, pct);
    $("#share-grid").textContent = game.mode === "daily" ? text : "";
    $("#btn-copy").textContent = game.mode === "daily" ? "Copy results" : "Copy link";
    $("#btn-copy").onclick = async () => { try { await navigator.clipboard.writeText(game.mode === "daily" ? text + url : url); toast(game.mode === "daily" ? "Results copied" : "Link copied"); } catch { toast("Couldn't copy. Try again."); } };
    $("#btn-x").href = `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`;
    const nat = $("#btn-share");
    if (navigator.share) { nat.classList.remove("hidden"); nat.onclick = () => navigator.share({ title: "FakeBench", text, url }).catch(() => {}); }
    else nat.classList.add("hidden");
  }

  // ---------- levels ----------
  const catalog = { levels: [], pass: 8, cats: [] };
  let selected = 1;
  const levelState = () => store.get(`fb:levels:${TEST}`, { best: {} });
  const unlocked = () => { const b = levelState().best; let n = 1; while (catalog.levels[n] && b[n] >= catalog.pass) n++; return n; };
  const LOCK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';

  function levelOutcome(score) {
    const n = game.data.level, st = levelState(), passed = score >= game.data.pass;
    st.best[n] = Math.max(st.best[n] ?? 0, score); store.set(`fb:levels:${TEST}`, st);
    const last = !catalog.levels[n];
    const out = $("#r-outcome");
    out.className = `outcome ${passed ? "pass" : "fail"}`;
    out.textContent = passed ? (last ? `Level ${n} passed. That's the top of the ladder.` : `Level ${n} passed. Level ${n + 1} is unlocked.`)
      : `Level ${n} needs ${game.data.pass} out of ${game.items.length}. You got ${score}.`;
    selected = passed && !last ? n + 1 : n;
    $("#btn-again").textContent = passed ? (last ? "Play again" : `Play level ${n + 1}`) : `Retry level ${n}`;
    renderLadder();
  }

  function renderLadder() {
    const list = $("#ladder"); if (!list || !catalog.levels.length) return;
    const best = levelState().best, top = unlocked();
    if (selected > top) selected = top;
    list.innerHTML = "";
    for (const l of catalog.levels) {
      const state = best[l.n] >= catalog.pass ? "done" : l.n <= top ? "open" : "locked";
      const li = el("li", `${state}${l.n === selected ? " sel" : ""}`);
      const b = el("button", null, `<span class="node">${state === "locked" ? LOCK : l.n}</span><span class="lname">${esc(l.name)}</span><span class="lbest">${best[l.n] != null ? `${best[l.n]}/${l.size}` : ""}</span>`);
      b.type = "button"; b.disabled = state === "locked";
      b.setAttribute("aria-label", `Level ${l.n}, ${l.name}${state === "locked" ? ", locked" : ""}`);
      if (l.n === selected) b.setAttribute("aria-current", "step");
      b.onclick = () => { selected = l.n; renderLadder(); };
      li.appendChild(b); list.appendChild(li);
    }
    const l = catalog.levels[selected - 1];
    $("#ld-title").textContent = `Level ${l.n} · ${l.name}`;
    $("#ld-meta").textContent = `${l.size} images, ${l.seconds} seconds each${best[l.n] != null ? ` · best ${best[l.n]}/${l.size}` : ""}`;
    $("#btn-level").textContent = `Play level ${l.n}`;
  }

  function renderCats() {
    const list = $("#cat-list"); if (!list || !catalog.cats.length) return;
    list.innerHTML = "";
    for (const c of catalog.cats) {
      const li = el("li", null, `<a href="#"><span class="thumb">${c.thumb ? `<img src="${esc(c.thumb)}" alt="" loading="lazy">` : ""}</span><span class="t-name">${esc(c.name)}</span><span class="t-desc">${c.count} images</span></a>`);
      $("a", li).onclick = (e) => { e.preventDefault(); start("cat", { cat: c.id }); };
      list.appendChild(li);
    }
    $("#cats-sec").classList.remove("hidden");
  }

  async function loadCatalog() {
    if (!$("#ladder")) return;
    try {
      Object.assign(catalog, await (await fetch(`/api/catalog?test=${TEST}`)).json());
      selected = unlocked();
      renderLadder(); renderCats();
    } catch { $("#levels-sec").classList.add("hidden"); }
  }

  // ---------- daily ----------
  function dailyState() { return store.get(`fb:daily:${TEST}`, { last: null, streak: 0, results: {} }); }
  function saveDaily(score, total, pct) {
    const s = dailyState(), today = todayUTC();
    if (s.last !== today) {
      const y = new Date(Date.now() - 864e5).toISOString().slice(0, 10);
      s.streak = s.last === y ? s.streak + 1 : 1; s.last = today;
      s.results[today] = { score, total, pct, grid: game.answers.map((a) => a.correct) };
      store.set(`fb:daily:${TEST}`, s);
    }
    updateDailyButton();
  }
  function updateDailyButton() {
    const b = $("#btn-daily"); if (!b) return;
    const s = dailyState(), today = todayUTC();
    if (s.last === today) {
      const r = s.results[today];
      b.innerHTML = `Today's score: ${r.score}/${r.total} · 🔥 ${s.streak}`; b.disabled = true;
      const nextMid = new Date(); nextMid.setUTCHours(24, 0, 0, 0);
      const tick = () => { const ms = nextMid - Date.now(); if (ms <= 0) return location.reload(); const h = Math.floor(ms / 36e5), m = Math.floor((ms % 36e5) / 6e4); $("#daily-note").textContent = `Next challenge in ${h}h ${m}m`; };
      tick(); setInterval(tick, 30000);
    } else {
      b.innerHTML = `Daily challenge${s.streak ? ` · 🔥 ${s.streak}` : ""}`;
      $("#daily-note").textContent = "The same 10 images for everyone. A new challenge each day.";
    }
  }

  // ---------- wiring ----------
  $("#btn-round").onclick = () => start("round");
  $("#btn-daily").onclick = () => start("daily");
  $("#btn-again").onclick = () => game.mode === "level" ? start("level", { level: selected }) : start(game.mode === "cat" ? "cat" : "round", game.mode === "cat" ? game.opts : {});
  $("#btn-home").onclick = () => { show("start"); updateDailyButton(); renderLadder(); };
  const lvBtn = $("#btn-level"); if (lvBtn) lvBtn.onclick = () => start("level", { level: selected });
  $("#c-real").onclick = () => answer("real");
  $("#c-ai").onclick = () => answer("ai");
  document.addEventListener("keydown", (e) => {
    if (screens.play.classList.contains("hidden")) return;
    if (e.key === "ArrowLeft" || e.key.toLowerCase() === "r") answer("real");
    if (e.key === "ArrowRight" || e.key.toLowerCase() === "a") answer("ai");
  });
  loadStat(); updateDailyButton(); loadCatalog();
  fetchRound("round").then((d) => (prefetched = d)).catch(() => {});
})();
