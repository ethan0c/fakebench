// Headless play-through of the image test against a running `wrangler dev` (http://localhost:8787).
// Loads the real page + app.js in jsdom, stubs timers/images, answers every item, checks the results screen.
import { JSDOM } from "jsdom";
const BASE = process.env.BASE || "http://localhost:8787";
const html = await (await fetch(`${BASE}/image`)).text();
const dom = new JSDOM(html, { url: `${BASE}/image`, runScripts: "outside-only", pretendToBeVisual: true });
const { window } = dom;
window.fetch = (u, o) => fetch(new URL(u, BASE), o);            // route page fetches to the dev server
window.Image = class { set src(v) { setTimeout(() => this.onload && this.onload(), 0); } };
window.performance = { now: () => Date.now() };
window.scrollTo = () => {};
Object.defineProperty(window.navigator, "clipboard", { value: { writeText: async () => {} } });
const js = await (await fetch(`${BASE}/app.js`)).text();
window.eval(js);
const $ = (s) => window.document.querySelector(s);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const until = async (fn, ms = 8000) => { const t = Date.now(); while (!fn()) { if (Date.now() - t > ms) throw new Error("timeout waiting"); await sleep(25); } };

$("#btn-round").click();
await until(() => !$("#play").classList.contains("hidden"));
console.log("play screen shown, first counter:", $("#count").textContent);
let answered = 0;
for (let i = 0; i < 20; i++) {
  await until(() => $("#count").textContent.startsWith(`${i + 1} /`));
  const src = $("#img").src; if (!src.includes("/media/img/")) throw new Error("no image src");
  (i % 2 ? $("#c-real") : $("#c-ai")).click(); answered++;
  await until(() => $("#fb").classList.contains("show"));
}
await until(() => !$("#results").classList.contains("hidden"));
await until(() => /\d+%/.test($("#r-pct").textContent), 10000);
const score = $("#r-score").textContent, pct = $("#r-pct").textContent, misses = $("#misses").children.length;
console.log({ answered, score, pct, misses, pctLine: $("#r-pct-line").textContent.slice(0, 80), xHref: $("#btn-x").href.slice(0, 60) });
const [s, t] = score.split("/").map(Number);
if (t !== 20 || s + misses !== 20) throw new Error("score/misses mismatch");
if (!decodeURIComponent($("#btn-x").href).includes("/share/image/")) throw new Error("share link missing");
// daily: play, then button must lock
$("#btn-home").click(); $("#btn-daily").click();
await until(() => !$("#play").classList.contains("hidden"));
for (let i = 0; i < 10; i++) { await until(() => $("#count").textContent.startsWith(`${i + 1} /`)); $("#c-ai").click(); await until(() => $("#fb").classList.contains("show")); }
await until(() => !$("#results").classList.contains("hidden"));
await until(() => /\d+%/.test($("#r-pct").textContent), 10000);
console.log("daily grid:", $("#share-grid").textContent.split("\n")[2], "| stored:", window.localStorage.getItem("fb:daily:image").slice(0, 60));
$("#btn-home").click();
if (!$("#btn-daily").disabled) throw new Error("daily button should lock after playing");
console.log("daily locked:", $("#btn-daily").textContent, "|", $("#daily-note").textContent);
console.log("PASS");
process.exit(0);
