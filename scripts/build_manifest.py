#!/usr/bin/env python3 -I
"""Normalize every raw image identically and write the public manifest.

Real and fake go through the exact same transform (center crop to square, same size,
same JPEG quality, metadata stripped) to reduce clues from file formatting.
"""
import argparse, json, os, subprocess, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from filters import plausible
from fetch_fake import pretty_model
from fetch_real import get as get_json
from categories import categorize

def normalize(src, dst, size):
    vf = f"scale='if(gt(iw,ih),-2,{size})':'if(gt(iw,ih),{size},-2)',crop={size}:{size},format=yuv420p"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", vf, "-map_metadata", "-1", "-q:v", "4", dst],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("ffmpeg failed", src, r.stderr[:200], file=sys.stderr)
        return False
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default="public/media")
    ap.add_argument("--size", type=int, default=768)
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, "img"), exist_ok=True)
    # Start from the existing pool (CI runs have an empty raw dir), keeping items whose image still exists.
    bpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blocklist.txt")
    blocked = {l.strip() for l in open(bpath) if l.strip() and not l.startswith("#")} if os.path.exists(bpath) else set()
    mpath = os.path.join(a.out, "manifest.json"); items = []
    if os.path.exists(mpath):
        try:
            for it in json.load(open(mpath))["items"]:
                if not os.path.exists(os.path.join(a.out, "img", it["id"] + ".jpg")): continue
                if it["id"] in blocked: continue
                if it["label"] == "ai":
                    if it.get("model_raw"): it["model"] = pretty_model(it["model_raw"])
                    if not plausible(it.get("prompt"), it.get("model")): continue
                items.append(it)
        except Exception as e: print("could not read existing manifest:", e, file=sys.stderr)
    seen = {it["id"] for it in items}
    for kind in ("real", "fake"):
        d = os.path.join(a.raw, kind)
        if not os.path.isdir(d): continue
        # oldest first, so the manifest order is age order and prune_pool drops the oldest
        for fn in sorted((f for f in os.listdir(d) if f.endswith(".json")), key=lambda f: os.path.getmtime(os.path.join(d, f))):
            with open(os.path.join(d, fn)) as f: meta = json.load(f)
            if meta["id"] in seen or meta["id"] in blocked: continue
            if meta["label"] == "ai":
                if meta.get("model_raw"): meta["model"] = pretty_model(meta["model_raw"])
                if not plausible(meta.get("prompt"), meta.get("model")): continue
            seen.add(meta["id"])
            src = os.path.join(d, meta["file"]); dst = os.path.join(a.out, "img", meta["id"] + ".jpg")
            if not os.path.exists(dst) and not normalize(src, dst, a.size): continue
            item = {"id": meta["id"], "kind": "image", "label": meta["label"], "src": f"/media/img/{meta['id']}.jpg"}
            if meta["label"] == "ai":
                item.update({"model": meta["model"], "model_raw": meta.get("model_raw"), "prompt": meta.get("prompt")})
            else:
                item.update({"credit": meta.get("credit"), "license": meta.get("license"), "page": meta.get("page")})
            items.append(item)
    categorize(items, get_json)  # subject tag for category rounds; existing tags are kept
    real = sum(1 for i in items if i["label"] == "real"); ai = len(items) - real
    manifest = {"version": datetime.datetime.utcnow().strftime("%Y%m%d%H%M"), "generated": datetime.datetime.utcnow().isoformat() + "Z",
                "counts": {"real": real, "ai": ai}, "items": items}
    with open(os.path.join(a.out, "manifest.json"), "w") as f: json.dump(manifest, f, separators=(",", ":"))
    print(f"manifest: {real} real, {ai} ai -> {a.out}/manifest.json")

if __name__ == "__main__":
    main()
