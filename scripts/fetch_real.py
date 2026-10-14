#!/usr/bin/env python3 -I
"""Pull real photographs from Wikimedia Commons, matched to the subjects of the AI prompts.

Queries are derived from the fake set's prompts (data/raw/fake/*.json) so real and AI images cover the
same kinds of subjects. Falls back to a generic subject list. Only CC0 / public domain / CC BY / CC BY-SA
JPEGs with camera EXIF dates are kept; the credit and license are shown in the reveal panel.
"""
import argparse, json, os, re, sys, time, hashlib, glob, random, urllib.request, urllib.parse

API = "https://commons.wikimedia.org/w/api.php"
UA = "fakebench-pipeline/0.1 (https://github.com/fakebench; contact via repo)"
FALLBACK = ["street", "portrait", "landscape", "food", "dog", "cat", "bird", "market", "kitchen", "beach", "forest", "mountain",
            "city night", "car", "bicycle", "cafe", "flower", "train", "river", "bridge", "snow", "sunset", "people walking", "boat", "farm"]
OK_LICENSE = re.compile(r"^(CC0|Public domain|CC BY(-SA)? \d(\.\d)?)", re.I)
BAD_CATS = re.compile(r"AI-generated|Computer-generated|Renders|Screenshots|Maps|Diagrams|Panoram|Logos|Scans|Drawings|Paintings|Illustrations|Posters|Stamps|Coins|Banknotes|Book covers|Charts|Retouched|Photomontage|Collages|HDR|Infrared|Stitched|Focus stack", re.I)
BAD_TITLE = re.compile(r"\b(map|diagram|logo|chart|scan|panorama|montage|collage|screenshot|crop|detail|drawing|poster)\b", re.I)
STOP = set("a an the of in on at with and or to from is are was were next by for his her their its this that these those two three four some near under over into onto up down out very".split())

def get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read() if binary else json.loads(r.read().decode())

def strip_html(s): return re.sub(r"<[^>]+>", "", s or "").strip()

def query_from_prompt(p):
    words = [w for w in re.findall(r"[a-zA-Z]+", p.lower()) if w not in STOP and len(w) > 2]
    return " ".join(words[:4])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=220)
    ap.add_argument("--out", default="data/raw/real")
    ap.add_argument("--fake-dir", default="data/raw/fake")
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--per-query", type=int, default=2)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    have = {f[:-5] for f in os.listdir(a.out) if f.endswith(".json")}
    try: have |= {i["id"] for i in json.load(open("public/media/manifest.json"))["items"]}   # already in the pool
    except Exception: pass
    prompts = []
    for f in glob.glob(os.path.join(a.fake_dir, "*.json")):
        try: prompts.append(json.load(open(f)).get("prompt") or "")
        except Exception: pass
    queries = list(dict.fromkeys(q for q in (query_from_prompt(p) for p in prompts) if q))
    random.shuffle(queries)
    queries += FALLBACK * 3
    got, qi = 0, 0
    while got < a.count and qi < len(queries):
        subject = queries[qi]; qi += 1
        for strict in (True, False):
            if got >= a.count: break
            search = (f'incategory:"Quality images" ' if strict else "") + f"filetype:bitmap {subject}"
            q = urllib.parse.urlencode({"action": "query", "generator": "search", "gsrnamespace": 6, "gsrlimit": 30, "gsrsort": "random",
                                        "gsrsearch": search, "prop": "imageinfo|categories", "cllimit": 50,
                                        "iiprop": "url|extmetadata|size|mime", "iiurlwidth": a.width, "format": "json"})
            try:
                d = get(f"{API}?{q}")
            except Exception as e:
                print("search error", subject, e, file=sys.stderr); time.sleep(5); continue
            n = 0
            for p in d.get("query", {}).get("pages", {}).values():
                if n >= a.per_query or got >= a.count: break
                ii = (p.get("imageinfo") or [{}])[0]; em = ii.get("extmetadata", {})
                lic = em.get("LicenseShortName", {}).get("value", "")
                cats = " ".join(c["title"] for c in p.get("categories", []))
                if ii.get("mime") != "image/jpeg" or ii.get("width", 0) < 1000 or ii.get("height", 0) < 700: continue
                if not OK_LICENSE.match(lic) or BAD_CATS.search(cats) or BAD_TITLE.search(p["title"]) or not ii.get("thumburl"): continue
                if not strict and not em.get("DateTimeOriginal", {}).get("value"): continue   # no camera date: probably not a photo
                rid = "r_" + hashlib.sha1(p["title"].encode()).hexdigest()[:10]
                if rid in have: continue
                try: data = get(ii["thumburl"], binary=True)
                except Exception as e: print("img error", rid, e, file=sys.stderr); continue
                with open(os.path.join(a.out, rid + ".jpg"), "wb") as f: f.write(data)
                meta = {"id": rid, "label": "real", "title": p["title"], "page": ii.get("descriptionurl"),
                        "credit": strip_html(em.get("Artist", {}).get("value")) or "Wikimedia Commons",
                        "license": lic, "licenseUrl": em.get("LicenseUrl", {}).get("value"),
                        "date": em.get("DateTimeOriginal", {}).get("value"), "subject": subject, "strict": strict, "file": rid + ".jpg"}
                with open(os.path.join(a.out, rid + ".json"), "w") as f: json.dump(meta, f)
                have.add(rid); got += 1; n += 1
                time.sleep(0.15)
            if n: print(f"{subject!r} {'QI' if strict else 'any'}: +{n} (total {got})", file=sys.stderr)
            if n >= a.per_query: break
            time.sleep(0.3)
    print(f"fetched {got} real photos into {a.out}")

if __name__ == "__main__":
    main()
