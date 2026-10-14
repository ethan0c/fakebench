#!/usr/bin/env python3 -I
"""Pull AI images with a known generating model from Rapidata's per-model preference datasets.

License: CDLA-Permissive-2.0 (commercial use allowed). Prompts are mundane COCO-style captions,
so the subject matter doesn't give the answer away. Each row pairs two models on the same prompt
with crowd coherence votes; we keep the images humans rated as more coherent (the convincing ones).
"""
import argparse, json, os, re, sys, time, hashlib, urllib.request, urllib.parse, urllib.error

DATASETS = [
    "Rapidata/OpenAI-4o_t2i_human_preference",
    "Rapidata/Imagen4_t2i_human_preference",
    "Rapidata/Seedream-3_t2i_human_preference",
    "Rapidata/Hidream_t2i_human_preference",
    "Rapidata/Imagen-4-ultra-24-7-25_t2i_human_preference",
    "Rapidata/Recraft-v3-24-7-25_t2i_human_preference",
]
ROWS = "https://datasets-server.huggingface.co/rows"
UA = "fakebench-pipeline/0.1 (https://github.com/fakebench)"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from filters import plausible

MODEL_NAMES = {
    "4o": "GPT-4o image (OpenAI)", "imagen-3": "Imagen 3 (Google)", "imagen-4": "Imagen 4 (Google)", "imagen-4-ultra": "Imagen 4 Ultra (Google)",
    "midjourney-5.2": "Midjourney 5.2", "midjourney-7": "Midjourney 7", "flux-1.1-pro": "FLUX 1.1 Pro", "flux-1-pro": "FLUX.1 Pro", "flux-1-dev": "FLUX.1 Dev",
    "dalle-3": "DALL·E 3 (OpenAI)", "ideogram": "Ideogram", "ideogram-v2": "Ideogram 2", "ideogram-v3": "Ideogram 3", "aurora": "Aurora (xAI Grok)", "janus-7b": "Janus 7B (DeepSeek)",
    "frames": "Runway Frames", "seedream-3": "Seedream 3 (ByteDance)", "hidream": "HiDream-I1", "recraft-v3": "Recraft V3", "recraft-v2": "Recraft V2",
    "lumina": "Lumina (OpenGVLab)", "reve": "Reve Halfmoon", "stable-diffusion-3.5": "Stable Diffusion 3.5", "sd3.5": "Stable Diffusion 3.5",
}

SUBSTR = [("imagen-4.0-ultra", "Imagen 4 Ultra (Google)"), ("imagen-4-ultra", "Imagen 4 Ultra (Google)"), ("imagen-4", "Imagen 4 (Google)"), ("imagen4", "Imagen 4 (Google)"),
          ("seedream-3", "Seedream 3 (ByteDance)"), ("seedream", "Seedream (ByteDance)"), ("hidream", "HiDream-I1"), ("recraft-v3", "Recraft V3"), ("recraft", "Recraft"),
          ("ideogram-v3", "Ideogram 3"), ("ideogram-v2", "Ideogram 2"), ("midjourney-7", "Midjourney 7"), ("flux-1.1", "FLUX 1.1 Pro"), ("flux", "FLUX"), ("4o", "GPT-4o image (OpenAI)"),
          ("gpt-image", "GPT Image (OpenAI)"), ("dalle", "DALL·E 3 (OpenAI)"), ("aurora", "Aurora (xAI Grok)"), ("lumina", "Lumina (OpenGVLab)"), ("reve", "Reve Halfmoon"), ("halfmoon", "Reve Halfmoon"), ("janus", "Janus 7B (DeepSeek)"), ("frames", "Runway Frames")]
def pretty_model(raw):
    low = raw.lower()
    base = re.sub(r"-\d{1,2}-\d{1,2}-\d{2}$", "", low)   # strip date suffixes like -26-3-25
    if base in MODEL_NAMES: return MODEL_NAMES[base]
    if low in MODEL_NAMES: return MODEL_NAMES[low]
    for key, name in SUBSTR:
        if key in low: return name
    return raw.replace("-", " ").title()

def get(url, binary=False, tries=6):
    for attempt in range(tries):
        try:
            headers = {"User-Agent": UA}
            if os.environ.get("HF_TOKEN") and "huggingface.co" in url: headers["Authorization"] = "Bearer " + os.environ["HF_TOKEN"]
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read() if binary else json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504) and attempt < tries - 1:
                wait = 15 * (attempt + 1)
                print(f"HTTP {e.code}, backing off {wait}s", file=sys.stderr); time.sleep(wait); continue
            raise

def ext_of(data):
    if data[:3] == b"\xff\xd8\xff": return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n": return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP": return ".webp"
    return ".bin"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=220)
    ap.add_argument("--per-model", type=int, default=24)
    ap.add_argument("--min-coherence", type=float, default=0.5)
    ap.add_argument("--out", default="data/raw/fake")
    ap.add_argument("--per-prompt", type=int, default=2)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    have = {f[:-5] for f in os.listdir(a.out) if f.endswith(".json")}
    try: have |= {i["id"] for i in json.load(open("public/media/manifest.json"))["items"]}   # already in the pool
    except Exception: pass
    seen_prompt_model = set()
    per_model = {}
    for f in have:
        try:
            m = json.load(open(os.path.join(a.out, f + ".json")))
            per_model[m["model"]] = per_model.get(m["model"], 0) + 1
            seen_prompt_model.add((m.get("prompt"), m["model"]))
        except Exception: pass
    prompt_count = {}
    for f in have:
        try: m = json.load(open(os.path.join(a.out, f + ".json"))); prompt_count[m["prompt"]] = prompt_count.get(m["prompt"], 0) + 1
        except Exception: pass
    got = 0
    for di, ds in enumerate(DATASETS):
        if got >= a.count: break
        # Rows are grouped by prompt (about 40 per prompt). Stride through groups with small pages so we
        # see every prompt. The first dataset carries a dozen models; later ones only add their new model.
        # Rate limits are per request, not per byte, so take full pages: 100 rows covers 2-3 prompts.
        stride, length = (100, 100) if di == 0 else (400, 100)
        for offset in range(0, 13500, stride):
            if got >= a.count: break
            q = urllib.parse.urlencode({"dataset": ds, "config": "default", "split": "train", "offset": offset, "length": length})
            try:
                d = get(f"{ROWS}?{q}")
            except Exception as e:
                print("page error", ds, offset, e, file=sys.stderr); time.sleep(3); continue
            rows = d.get("rows", [])
            if not rows: break
            for r in rows:
                r = r["row"]; prompt = (r.get("prompt") or "").strip()
                if not prompt or not plausible(prompt): continue  # model check happens per side below
                if prompt_count.get(prompt, 0) >= a.per_prompt: continue
                for side in ("1", "2"):
                    img, raw_model = r.get("image" + side), r.get("model" + side) or ""
                    coh = r.get(f"weighted_results_image{side}_coherence")
                    if not img or not img.get("src") or coh is None or coh < a.min_coherence: continue
                    model = pretty_model(raw_model)
                    if not plausible(prompt, model): continue
                    if per_model.get(model, 0) >= a.per_model or (prompt, model) in seen_prompt_model: continue
                    rid = "a_" + hashlib.sha1(f"{ds}:{prompt}:{raw_model}".encode()).hexdigest()[:10]
                    if rid in have: continue
                    try:
                        data = get(img["src"], binary=True)
                    except Exception as e:
                        print("img error", rid, e, file=sys.stderr); continue
                    ext = ext_of(data)
                    if ext == ".bin": continue
                    with open(os.path.join(a.out, rid + ext), "wb") as f: f.write(data)
                    meta = {"id": rid, "label": "ai", "model": model, "model_raw": raw_model, "prompt": prompt, "coherence": round(coh, 3),
                            "source": f"https://huggingface.co/datasets/{ds}", "license": "CDLA-Permissive-2.0", "file": rid + ext}
                    with open(os.path.join(a.out, rid + ".json"), "w") as f: json.dump(meta, f)
                    have.add(rid); seen_prompt_model.add((prompt, model)); per_model[model] = per_model.get(model, 0) + 1; prompt_count[prompt] = prompt_count.get(prompt, 0) + 1
                    got += 1
                    if got >= a.count: break
                if got >= a.count: break
            if offset % (stride * 20) == 0: print(f"{ds.split('/')[1][:28]} offset {offset} total {got}", file=sys.stderr)
            time.sleep(7.0)
    print(json.dumps(per_model, indent=1), file=sys.stderr)
    print(f"fetched {got} fake images into {a.out}")

if __name__ == "__main__":
    main()
