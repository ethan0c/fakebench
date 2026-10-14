#!/usr/bin/env python3 -I
"""Keep the image pool bounded so the static asset bundle stays small. Drops the oldest items per class."""
import argparse, json, os
ap = argparse.ArgumentParser(); ap.add_argument("--manifest", default="public/media/manifest.json"); ap.add_argument("--max-per-class", type=int, default=600)
a = ap.parse_args()
m = json.load(open(a.manifest)); keep, dropped = [], 0
for label in ("real", "ai"):
    items = [i for i in m["items"] if i["label"] == label]
    for i in items[:-a.max_per_class] if len(items) > a.max_per_class else []:
        p = os.path.join(os.path.dirname(a.manifest), "img", i["id"] + ".jpg")
        if os.path.exists(p): os.remove(p)
        dropped += 1
    keep += items[-a.max_per_class:]
m["items"] = keep; m["counts"] = {"real": sum(i["label"] == "real" for i in keep), "ai": len(keep) - sum(i["label"] == "real" for i in keep)}
json.dump(m, open(a.manifest, "w"), separators=(",", ":")); print(f"pruned {dropped}, kept {len(keep)}")
