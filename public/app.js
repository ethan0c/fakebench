/* FakeBench test engine. One page per test; the body carries data-test. */
(() => {
  const TEST = document.body.dataset.test;
  if (!TEST) return;
  const NAMES = { image: "AI Image Test" };
  const $ = (s, r = document) => r.querySelector(s);
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const todayUTC = () => new Date().toISOString().slice(0, 10);
  const screens = { start: $("#start"), play: $("#play"), results: $("#results") };
  const show = (name) => { for (const k in screens) screens[k].classList.toggle("hidden", k !== name); window.scrollTo({ top: 0 }); };
  const toast = (msg) => { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 1800); };
  const store = { get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } }, set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} } };

  let prefetched = null; // next random round, fetched while results are on screen
  let seconds = 5;

  async function fetchRound(mode) {
    const r = await fetch(`/api/round?test=${TEST}&mode=${mode}`);
    if (!r.ok) throw new Error("round");
    return r.json();
  }
  function preload(items) {
    return Promise.all(items.map((it) => new Promise((res) => {
      const im = new Image(); im.onload = im.onerror = () => res(); im.src = it.src; setTimeout(res, 8000);
    })));
  }

  // ---------- live stat on start screen ----------
  async function loadStat() {
    const box = $("#stat"); if (!box) return;
    const num = $(".stat-num", box), txt = $(".stat-text", box);
    try {
      const s = await (await fetch(`/api/stats?test=${TEST}`)).json();
      const weekly = s.accuracy_week != null, acc = s.accuracy_week ?? s.accuracy;
      if (acc == null) { num.textContent = ""; txt.textContent = "No results yet. Take the first test."; return; }
      let delta = "";
      if (weekly && s.accuracy_prev != null && s.accuracy_prev !== acc) delta = `, ${acc > s.accuracy_prev ? "up" : "down"} from ${s.accuracy_prev}% in the previous 30 days`;
      num.textContent = `${acc}%`;
      txt.textContent = `of answers were correct ${weekly ? "over the past seven days" : "across all tests so far"}${delta}.`;
    } catch { txt.textContent = "Real or AI? 5 seconds per image."; }
  }

  // ---------- game ----------
  const game = { mode: "round", items: [], idx: 0, answers: [], t0: 0, timer: null, locked: false };

  async function start(mode) {
    game.mode = mode;
    const btns = [$("#btn-round"), $("#btn-daily")];
    btns.forEach((b) => b && (b.disabled = true));
    try {
      const data = mode === "round" && prefetched ? prefetched : await fetchRound(mode);
      prefetched = null;
      seconds = data.seconds || 5;
      game.items = data.items; game.idx = 0; game.answers = []; game.day = data.day;
      await preload(game.items);
      show("play");
      next();
    } catch (e) {
      toast("Couldn't load the test. Try again.");
    } finally { btns.forEach((b) => b && (b.disabled = false)); }
  }

  function next() {
    if (game.idx >= game.items.length) return finish();
    const it = game.items[game.idx];
    $("#img").src = it.src;
    $("#count").textContent = `${game.idx + 1} / ${game.items.length}`;
    $("#score-live").textContent = `Score ${game.answers.filter((a) => a.correct).length}`;
    const bar = $("#bar"); bar.classList.remove("run"); bar.style.transitionDuration = "0s"; bar.style.transform = "scaleX(1)";
    void bar.offsetWidth; bar.style.transitionDuration = `${seconds}s`; bar.classList.add("run");
    $("#fb").className = "fb"; game.locked = false; game.t0 = performance.now();
    game.timer = setTimeout(() => answer(null), seconds * 1000);
  }

  function answer(choice) {
    if (game.locked) return; game.locked = true; clearTimeout(game.timer);
    const it = game.items[game.idx];
    const ms = Math.round(performance.now() - game.t0);
    const correct = choice === it.label;
    game.answers.push({ id: it.id, correct, choice, ms });
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
        body: JSON.stringify({ test: TEST, mode: game.mode, score, total, avg_ms, items: game.answers.map((a) => ({ id: a.id, correct: a.correct })) }) });
      const d = await r.json(); pct = d.percentile; rounds = d.rounds;
    } catch {}
    if (pct == null) { $("#r-pct").textContent = "–"; $("#r-pct-line").textContent = "Your score is ready, but we couldn't load your percentile."; }
    else {
      $("#r-pct").textContent = `${pct}%`;
      $("#r-pct-line").innerHTML = `Your score ranks above roughly <span class="score-pct">${pct}%</span> of scores.<span class="muted small"> Estimated from ${rounds.toLocaleString()} completed ${rounds === 1 ? "round" : "rounds"} and a starting baseline. <a href="/about">How it's calculated</a></span>`;
    }
    if (game.mode === "daily") saveDaily(score, total, pct);
    renderShare(score, total, pct);
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
  $("#btn-again").onclick = () => start("round");
  $("#btn-home").onclick = () => { show("start"); updateDailyButton(); };
  $("#c-real").onclick = () => answer("real");
  $("#c-ai").onclick = () => answer("ai");
  document.addEventListener("keydown", (e) => {
    if (screens.play.classList.contains("hidden")) return;
    if (e.key === "ArrowLeft" || e.key.toLowerCase() === "r") answer("real");
    if (e.key === "ArrowRight" || e.key.toLowerCase() === "a") answer("ai");
  });
  loadStat(); updateDailyButton();
  fetchRound("round").then((d) => (prefetched = d)).catch(() => {});
})();
