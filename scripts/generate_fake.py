#!/usr/bin/env python3 -I
"""Generate fresh AI images with current models through fal.ai so the pool tracks the state of the art.

Runs only when FAL_KEY is set. Prompts are mundane photo captions built from templates so the subject
never gives the answer away. Cost is roughly a cent per image.
"""
import argparse, hashlib, json, os, random, sys, time, urllib.request

MODELS = {  # fal endpoint -> display name
    "fal-ai/flux-pro/v1.1-ultra": "FLUX 1.1 Pro Ultra",
    "fal-ai/imagen4/preview": "Imagen 4 (Google)",
    "fal-ai/ideogram/v3": "Ideogram 3",
    "fal-ai/recraft/v3/text-to-image": "Recraft V3",
    "fal-ai/hidream-i1-full": "HiDream-I1",
}
SUBJECTS = ["a man reading a newspaper at a bus stop", "a woman pouring coffee in a small kitchen", "two kids playing football in a park",
            "a cat asleep on a windowsill", "a crowded farmers market in the morning", "a delivery cyclist waiting at a red light",
            "an old fishing boat tied to a wooden pier", "a dog shaking off water at a beach", "commuters on a rainy train platform",
            "a mechanic working under a car", "a family dinner table with plates and glasses", "a street vendor grilling corn",
            "a hiker resting on a rock with a view of mountains", "a cluttered desk with a laptop and papers", "a barista steaming milk",
            "a school bus on a suburban street in autumn", "pigeons on a cathedral square", "a woman jogging along a river path",
            "a wedding guest taking a photo on a phone", "an elderly couple on a park bench", "a child blowing out birthday candles"]
STYLES = ["candid photo, natural light", "smartphone photo", "35mm film photo, slight grain", "documentary photograph", "snapshot, slightly overexposed",
          "photo taken at dusk", "overcast daylight photo", "indoor photo with window light"]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--count", type=int, default=30); ap.add_argument("--out", default="data/raw/fake")
    a = ap.parse_args()
    key = os.environ.get("FAL_KEY")
    if not key: sys.exit("FAL_KEY not set; skipping generation")
    os.makedirs(a.out, exist_ok=True); rng = random.Random()
    endpoints = list(MODELS); got = 0
    for i in range(a.count):
        ep = endpoints[i % len(endpoints)]; prompt = f"{rng.choice(SUBJECTS)}, {rng.choice(STYLES)}"
        body = json.dumps({"prompt": prompt, "num_images": 1, "aspect_ratio": "1:1", "image_size": "square_hd", "safety_tolerance": "2"}).encode()
        try:
            req = urllib.request.Request(f"https://fal.run/{ep}", body, {"Authorization": f"Key {key}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r: res = json.loads(r.read())
            url = res["images"][0]["url"]
            with urllib.request.urlopen(url, timeout=120) as r: data = r.read()
        except Exception as e:
            print("gen failed", ep, repr(e)[:200], file=sys.stderr); time.sleep(2); continue
        rid = "a_" + hashlib.sha1(f"fal:{ep}:{prompt}:{time.time()}".encode()).hexdigest()[:10]
        ext = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
        open(os.path.join(a.out, rid + ext), "wb").write(data)
        json.dump({"id": rid, "label": "ai", "model": MODELS[ep], "model_raw": ep, "prompt": prompt, "source": "generated via fal.ai", "license": "own", "file": rid + ext},
                  open(os.path.join(a.out, rid + ".json"), "w"))
        got += 1
    print(f"generated {got} images")

if __name__ == "__main__":
    main()
