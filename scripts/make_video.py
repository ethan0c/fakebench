#!/usr/bin/env python3 -I
"""Render a vertical "Real or AI?" video from the public manifest.

Format: N images, each shown for about 3s with a countdown, followed by the model name
or photo credit. An end card shows the site's average accuracy and URL.
Text is rendered by the site's own /og/overlay.png endpoint (same font as the share cards), so ffmpeg
needs neither fonts nor the drawtext filter.
"""
import argparse, json, os, random, subprocess, sys, urllib.request, urllib.parse, tempfile, shutil

W, H = 1080, 1920
UA = "fakebench-video/0.1"

def fetch(url, dst):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f: f.write(r.read())
    return dst

def overlay(site, tmp, name, **params):
    return fetch(f"{site}/og/overlay.png?{urllib.parse.urlencode(params)}", os.path.join(tmp, name + ".png"))

def fetch_stat(site):
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{site}/api/stats?test=image", headers={"User-Agent": UA}), timeout=15) as r:
            s = json.load(r); return s.get("accuracy_week") if s.get("accuracy_week") is not None else s.get("accuracy")
    except Exception: return None

def run(args): subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="public/media/manifest.json")
    ap.add_argument("--media-root", default="public")
    ap.add_argument("--site", default="https://fakebench.com")
    ap.add_argument("--out", default="out/daily.mp4")
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--show", type=int, default=3)
    ap.add_argument("--reveal", type=float, default=1.6)
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    site = a.site.rstrip("/"); rng = random.Random(a.seed)
    m = json.load(open(a.manifest))
    real = [i for i in m["items"] if i["label"] == "real"]; ai = [i for i in m["items"] if i["label"] == "ai"]
    picks = rng.sample(real, a.n // 2) + rng.sample(ai, a.n - a.n // 2); rng.shuffle(picks)
    acc = fetch_stat(site)
    host = site.split("://", 1)[-1]
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    tmp = tempfile.mkdtemp(); segs = []
    try:
        for k, it in enumerate(picks):
            src = os.path.join(a.media_root, it["src"].lstrip("/"))
            label = "AI" if it["label"] == "ai" else "REAL"
            detail = (it.get("model") or "") if it["label"] == "ai" else ("Photo by " + it["credit"][:40] if it.get("credit") else "Photo from Wikimedia Commons")
            counts = [overlay(site, tmp, f"q{k}_{c}", kind="question", n=f"{k+1}/{len(picks)}", count=str(c)) for c in range(a.show, 0, -1)]
            rev = overlay(site, tmp, f"r{k}", kind="reveal", label=label, detail=detail)
            dur = a.show + a.reveal
            inputs = ["-loop", "1", "-t", str(dur), "-i", src]
            for p in counts + [rev]: inputs += ["-loop", "1", "-t", str(dur), "-i", p]
            fc = (f"[0:v]split[s0][s1];[s0]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:8,eq=brightness=-0.25[bg];"
                  f"[s1]scale={W}:{W}[fg];[bg][fg]overlay=0:(H-h)/2[v0]")
            for i in range(len(counts)):
                fc += f";[v{i}][{i+1}:v]overlay=0:0:enable='between(t,{i},{i+1})'[v{i+1}]"
            n = len(counts)
            fc += f";[v{n}][{n+1}:v]overlay=0:0:enable='gte(t,{a.show})'[v]"
            seg = os.path.join(tmp, f"seg{k}.mp4")
            run([*inputs, "-filter_complex", fc, "-map", "[v]", "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", seg])
            segs.append(seg)
        stat = f"Players on FakeBench get {acc}% of answers right" if acc is not None else "20 images. 5 seconds each. How many can you get right?"
        end_png = overlay(site, tmp, "end", kind="end", stat=stat, host=host)
        end = os.path.join(tmp, "end.mp4")
        run(["-loop", "1", "-t", "4", "-i", end_png, "-vf", f"scale={W}:{H},format=yuv420p", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", end])
        segs.append(end)
        lst = os.path.join(tmp, "list.txt")
        with open(lst, "w") as f:
            for s in segs: f.write(f"file '{s}'\n")
        # silent audio track: some platforms reject videos without one
        run(["-f", "concat", "-safe", "0", "-i", lst, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-shortest", "-c:v", "copy", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", a.out])
        json.dump({"items": [{"id": i["id"], "label": i["label"]} for i in picks], "accuracy": acc, "site": site}, open(os.path.splitext(a.out)[0] + ".json", "w"))
        print(f"wrote {a.out} ({os.path.getsize(a.out)//1024} KB), {len(picks)} items, stat={acc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    main()
