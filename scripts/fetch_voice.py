#!/usr/bin/env python3 -I
"""Voice test pool: real VCTK recordings vs. TTS clones of the same speakers, from DFADD.

Source: isjwdu/DFADD on Hugging Face (MIT). Real side is the VCTK corpus (CC BY 4.0,
CSTR, University of Edinburgh). Generators: Grad-TTS, Matcha-TTS, NaturalSpeech 2, P-Flow, StyleTTS 2.

Both sides go through one identical ffmpeg chain (trim silence, cap length, high-pass, loudness
normalize, faint noise floor, 16 kHz mono MP3) so recording format can't give the answer away.
Writes public/media/voice/<id>.mp3 and public/media/voice/manifest.json, keeping existing items.

  python3 -I scripts/fetch_voice.py --real 60 --fake 60
"""
import argparse, datetime, hashlib, json, os, random, subprocess, sys, tempfile, time, urllib.parse, urllib.request

DATASET = "isjwdu/DFADD"
ROWS = "https://datasets-server.huggingface.co/rows"
UA = "fakebench-pipeline/0.1 (https://github.com/fakebench; contact via repo)"
TOTAL_ROWS = 200465  # train split; refreshed from the API response when available
GENERATORS = {  # file-name suffix -> display name
    "GradTTS": "Grad-TTS", "matcha": "Matcha-TTS", "NaturalSpeech2": "NaturalSpeech 2",
    "pflow": "P-Flow TTS", "StyleTTS2": "StyleTTS 2",
}
VCTK = {"credit": "VCTK corpus, CSTR, University of Edinburgh", "license": "CC BY 4.0",
        "page": "https://datashare.ed.ac.uk/handle/10283/3443"}
MIN_SEC, MAX_SEC = 2.5, 7.0

def get(url, binary=False, tries=4):
    for t in range(tries):
        try:
            hdr = {"User-Agent": UA}
            if os.environ.get("HF_TOKEN"): hdr["Authorization"] = f"Bearer {os.environ['HF_TOKEN']}"
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=90) as r:
                data = r.read()
                return data if binary else json.loads(data)
        except Exception as e:
            if t == tries - 1: raise
            time.sleep(5 * (t + 1))

def generator(name):
    stem = os.path.splitext(name)[0]
    parts = stem.split("_")
    return GENERATORS.get(parts[-1]) if len(parts) >= 3 else None

def sample_rows(pages, pace, enough):
    """Metadata from random 100-row pages of the train split, until enough(rows) or `pages` pages.
    Rows are stored in long single-label runs, so one page is usually all one generator."""
    rows, total = [], TOTAL_ROWS
    for k in range(pages):
        if enough(rows): break
        off = random.randrange(0, max(1, total - 100))
        q = urllib.parse.urlencode({"dataset": DATASET, "config": "default", "split": "train", "offset": off, "length": 100})
        try: d = get(f"{ROWS}?{q}")
        except Exception as e:
            print("rows failed", off, e, file=sys.stderr); continue
        total = d.get("num_rows_total") or total
        for r in d.get("rows", []):
            row = r["row"]; audio = row.get("audio") or []
            if audio and audio[0].get("src"): rows.append({"name": row["audio_name"], "label": row["label"], "src": audio[0]["src"]})
        print(f"page {k + 1}/{pages}: {len(rows)} rows", file=sys.stderr)
        time.sleep(pace)
    return rows

def process(src, dst):
    """Identical chain for both labels. Returns the output duration, or None if too short."""
    chain = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,"
             "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse,"
             f"atrim=0:{MAX_SEC},asetpts=N/SR/TB,aresample=16000,highpass=f=70,"
             "afade=t=in:d=0.02,areverse,afade=t=in:d=0.08,areverse,loudnorm=I=-20:TP=-2:LRA=11,aresample=16000")
    graph = f"[0:a]{chain}[v];anoisesrc=color=pink:sample_rate=16000:amplitude=0.0015[n];[v][n]amix=inputs=2:duration=first:normalize=0[o]"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-filter_complex", graph, "-map", "[o]", "-ac", "1",
                        "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "48k", "-map_metadata", "-1", dst], capture_output=True, text=True)
    if r.returncode != 0:
        print("ffmpeg failed", r.stderr[:200], file=sys.stderr); return None
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", dst], capture_output=True, text=True)
    try: dur = float(p.stdout.strip())
    except ValueError: return None
    if dur < MIN_SEC: os.remove(dst); return None
    return round(dur, 2)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", type=int, default=60)
    ap.add_argument("--fake", type=int, default=60)
    ap.add_argument("--pages", type=int, default=120, help="max pages to sample")
    ap.add_argument("--pace", type=float, default=3.0)
    ap.add_argument("--out", default="public/media/voice")
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    random.seed(a.seed)
    os.makedirs(a.out, exist_ok=True)
    mpath = os.path.join(a.out, "manifest.json")
    items = []
    if os.path.exists(mpath):
        items = [i for i in json.load(open(mpath))["items"] if os.path.exists(os.path.join(a.out, i["id"] + ".mp3"))]
    have = {i["id"] for i in items}

    def enough(rows):
        n_real = sum(1 for r in rows if r["label"] == "real")
        per_gen = {g: 0 for g in GENERATORS.values()}
        for r in rows:
            g = generator(r["name"]) if r["label"] != "real" else None
            if g: per_gen[g] += 1
        return n_real >= 2 * a.real and min(per_gen.values()) >= 2 * a.fake / len(GENERATORS)
    rows = sample_rows(a.pages, a.pace, enough)
    real = [r for r in rows if r["label"] == "real"]
    fake = [r for r in rows if r["label"] != "real" and generator(r["name"])]
    random.shuffle(real); random.shuffle(fake)

    def pick(pool, n, key):
        """Round-robin over groups (speaker for real, generator for fake) so no one group dominates."""
        groups = {}
        for r in pool: groups.setdefault(key(r), []).append(r)
        out, order = [], list(groups)
        random.shuffle(order)
        while len(out) < n and any(groups.values()):
            for g in order:
                if groups[g] and len(out) < n: out.append(groups[g].pop())
        return out

    speaker = lambda r: r["name"].split("_")[0]
    chosen = pick(real, a.real, speaker) + pick(fake, a.fake, lambda r: generator(r["name"]))
    added = 0
    with tempfile.TemporaryDirectory() as tmp:
        for r in chosen:
            iid = ("v_" if r["label"] == "real" else "s_") + hashlib.sha1(r["name"].encode()).hexdigest()[:10]
            if iid in have: continue
            raw = os.path.join(tmp, "in" + os.path.splitext(r["name"])[1])
            try:
                with open(raw, "wb") as f: f.write(get(r["src"], binary=True))
            except Exception as e:
                print("download failed", r["name"], e, file=sys.stderr); continue
            dur = process(raw, os.path.join(a.out, iid + ".mp3"))
            if not dur: continue
            item = {"id": iid, "kind": "audio", "label": "real" if r["label"] == "real" else "ai",
                    "src": f"/media/voice/{iid}.mp3", "seconds": dur, "speaker": speaker(r)}
            if item["label"] == "ai":
                item.update({"model": generator(r["name"]), "source": "DFADD (MIT)", "page": f"https://huggingface.co/datasets/{DATASET}"})
            else:
                item.update(VCTK)
            items.append(item); have.add(iid); added += 1
            time.sleep(0.3)
    real_n = sum(1 for i in items if i["label"] == "real")
    manifest = {"version": datetime.datetime.utcnow().strftime("%Y%m%d%H%M"), "generated": datetime.datetime.utcnow().isoformat() + "Z",
                "counts": {"real": real_n, "ai": len(items) - real_n}, "items": items}
    with open(mpath, "w") as f: json.dump(manifest, f, separators=(",", ":"))
    print(f"voice: +{added}, pool {real_n} real / {len(items) - real_n} ai -> {mpath}")

if __name__ == "__main__":
    main()
