#!/usr/bin/env python3 -I
"""Primary AI-image source: read Rapidata per-model preference datasets straight from their parquet shards.

The HF CDN serves shards without the per-request limits of the rows API. Each shard (~230 MB) holds
~11 prompts x ~13 models. We read the small columns first, pick plausible prompts with the shared
filter, then decode only the row groups that contain picks. Shards are deleted after use unless --keep.
Needs pyarrow (pip install pyarrow).
"""
import argparse, hashlib, json, os, random, sys, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from filters import plausible
from fetch_fake import pretty_model, ext_of, UA
import pyarrow.parquet as pq

def list_shards(dataset):
    req = urllib.request.Request(f"https://huggingface.co/api/datasets/{dataset}/tree/main/data", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return sorted(x["path"] for x in json.load(r) if x["path"].endswith(".parquet"))

def download(dataset, path, cache):
    dst = os.path.join(cache, dataset.replace("/", "__") + "__" + os.path.basename(path))
    if os.path.exists(dst): return dst
    url = f"https://huggingface.co/datasets/{dataset}/resolve/main/{path}"
    headers = {"User-Agent": UA}
    if os.environ.get("HF_TOKEN"): headers["Authorization"] = "Bearer " + os.environ["HF_TOKEN"]
    t = time.time()
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=600) as r, open(dst + ".part", "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk: break
            f.write(chunk)
    os.rename(dst + ".part", dst)
    print(f"  downloaded {os.path.basename(path)} {os.path.getsize(dst)//(1<<20)} MB in {time.time()-t:.0f}s", file=sys.stderr)
    return dst

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", action="append", default=None, help="HF dataset id (repeatable)")
    ap.add_argument("--shards", default="all", help="'all', 'random:N', or comma-separated indexes")
    ap.add_argument("--count", type=int, default=400)
    ap.add_argument("--per-prompt", type=int, default=3)
    ap.add_argument("--per-model", type=int, default=60)
    ap.add_argument("--min-coherence", type=float, default=0.5)
    ap.add_argument("--out", default="data/raw/fake")
    ap.add_argument("--cache", default="data/shards")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    datasets = a.dataset or ["Rapidata/OpenAI-4o_t2i_human_preference", "Rapidata/Imagen4_t2i_human_preference", "Rapidata/Seedream-3_t2i_human_preference",
                             "Rapidata/Hidream_t2i_human_preference", "Rapidata/Imagen-4-ultra-24-7-25_t2i_human_preference", "Rapidata/Recraft-v3-24-7-25_t2i_human_preference"]
    os.makedirs(a.out, exist_ok=True); os.makedirs(a.cache, exist_ok=True)
    have = {f[:-5] for f in os.listdir(a.out) if f.endswith(".json")}
    try: have |= {i["id"] for i in json.load(open("public/media/manifest.json"))["items"]}
    except Exception: pass
    per_model, per_prompt, seen_pm = {}, {}, set()
    for f in os.listdir(a.out):
        if f.endswith(".json"):
            try:
                m = json.load(open(os.path.join(a.out, f)))
                per_model[m["model"]] = per_model.get(m["model"], 0) + 1; per_prompt[m["prompt"]] = per_prompt.get(m["prompt"], 0) + 1; seen_pm.add((m["prompt"], m["model"]))
            except Exception: pass
    got = 0
    for ds in datasets:
        if got >= a.count: break
        shards = list_shards(ds)
        if a.shards.startswith("random:"): shards = random.sample(shards, min(len(shards), int(a.shards.split(":")[1])))
        elif a.shards != "all": shards = [shards[int(i)] for i in a.shards.split(",") if int(i) < len(shards)]
        print(f"{ds}: {len(shards)} shard(s)", file=sys.stderr)
        for path in shards:
            if got >= a.count: break
            try: local = download(ds, path, a.cache)
            except Exception as e: print("download failed", path, e, file=sys.stderr); continue
            pf = pq.ParquetFile(local)
            picks = {}  # row group -> list of (row-in-group, side, prompt, raw_model, coh)
            for g in range(pf.metadata.num_row_groups):
                t = pf.read_row_group(g, columns=["prompt", "model1", "model2", "weighted_results_image1_coherence", "weighted_results_image2_coherence"]).to_pydict()
                for i, prompt in enumerate(t["prompt"]):
                    prompt = (prompt or "").strip()
                    if not plausible(prompt) or per_prompt.get(prompt, 0) >= a.per_prompt: continue
                    for side in ("1", "2"):
                        raw, coh = t["model" + side][i] or "", t[f"weighted_results_image{side}_coherence"][i]
                        model = pretty_model(raw)
                        if coh is None or coh < a.min_coherence or not plausible(prompt, model): continue
                        if per_model.get(model, 0) >= a.per_model or (prompt, model) in seen_pm or per_prompt.get(prompt, 0) >= a.per_prompt: continue
                        rid = "a_" + hashlib.sha1(f"{ds}:{prompt}:{raw}".encode()).hexdigest()[:10]
                        if rid in have: continue
                        picks.setdefault(g, []).append((i, side, prompt, raw, model, coh, rid))
                        have.add(rid); seen_pm.add((prompt, model)); per_model[model] = per_model.get(model, 0) + 1; per_prompt[prompt] = per_prompt.get(prompt, 0) + 1
            for g, rows in picks.items():
                imgs = pf.read_row_group(g, columns=["image1", "image2"]).to_pydict()
                for (i, side, prompt, raw, model, coh, rid) in rows:
                    data = imgs["image" + side][i]["bytes"]
                    ext = ext_of(data)
                    if ext == ".bin": continue
                    open(os.path.join(a.out, rid + ext), "wb").write(data)
                    json.dump({"id": rid, "label": "ai", "model": model, "model_raw": raw, "prompt": prompt, "coherence": round(float(coh), 3),
                               "source": f"https://huggingface.co/datasets/{ds}", "license": "CDLA-Permissive-2.0", "file": rid + ext},
                              open(os.path.join(a.out, rid + ".json"), "w"))
                    got += 1
            print(f"  {os.path.basename(path)}: +{sum(len(v) for v in picks.values())} (total {got})", file=sys.stderr)
            if not a.keep: os.remove(local)
    print(json.dumps(per_model, indent=1), file=sys.stderr)
    print(f"extracted {got} fake images into {a.out}")

if __name__ == "__main__":
    main()
