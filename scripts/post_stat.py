#!/usr/bin/env python3 -I
"""Post the site's average accuracy and daily video to configured channels.

Channels, each enabled only when its secrets are present:
  Bluesky  (BSKY_HANDLE, BSKY_APP_PASSWORD)            text + link card
  X        (X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET)   text + link via API v2, OAuth 1.0a signed by hand
  Postiz   (POSTIZ_API_KEY, POSTIZ_INTEGRATIONS)       uploads the video and schedules it to TikTok / Reels / Shorts
Stdlib only.
"""
import argparse, base64, datetime, hashlib, hmac, json, os, sys, time, urllib.parse, urllib.request, uuid, mimetypes

UA = "fakebench-bot/0.1"

def http(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})}, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode() or "{}")

def compose(site):
    try: s = http(f"{site}/api/stats?test=image")
    except Exception as e: print("stats fetch failed", e, file=sys.stderr); s = {}
    weekly = s.get("accuracy_week") is not None
    acc = s.get("accuracy_week") if weekly else s.get("accuracy")
    prev, rounds = s.get("accuracy_prev"), s.get("rounds") or 0
    day = datetime.date.today().strftime("%b %-d")
    if acc is None:
        text = "Real photo or AI? You have 5 seconds to decide. Try 20 images and see how many you get right."
    else:
        trend = ""
        if weekly and prev is not None and prev != acc: trend = f" ({'up' if acc > prev else 'down'} from {prev}% in the previous 30 days)"
        period = "over the past 7 days" if weekly else "across all tests so far"
        text = f"FakeBench, {day}: {acc}% of answers were correct {period}{trend}. {rounds:,} rounds played. Can you beat the average?"
    return text, f"{site}/image", acc

# ---------- Bluesky ----------
def post_bluesky(text, link):
    handle, pw = os.environ.get("BSKY_HANDLE"), os.environ.get("BSKY_APP_PASSWORD")
    if not (handle and pw): return "bluesky: skipped (no creds)"
    pds = "https://bsky.social"
    sess = http(f"{pds}/xrpc/com.atproto.server.createSession", json.dumps({"identifier": handle, "password": pw}).encode(), {"content-type": "application/json"})
    auth = {"authorization": f"Bearer {sess['accessJwt']}", "content-type": "application/json"}
    # link card with the OG image as thumbnail
    thumb = None
    try:
        with urllib.request.urlopen(urllib.request.Request(link.rsplit("/", 1)[0] + "/og/image.png", headers={"User-Agent": UA}), timeout=60) as r: img = r.read()
        up = urllib.request.Request(f"{pds}/xrpc/com.atproto.repo.uploadBlob", img, {"authorization": auth["authorization"], "content-type": "image/png"})
        with urllib.request.urlopen(up, timeout=60) as r: thumb = json.loads(r.read())["blob"]
    except Exception as e: print("bsky thumb failed", e, file=sys.stderr)
    embed = {"$type": "app.bsky.embed.external", "external": {"uri": link, "title": "FakeBench: AI Image Test", "description": "Real or AI? 20 images, 5 seconds each. See your score and the images you missed."}}
    if thumb: embed["external"]["thumb"] = thumb
    record = {"$type": "app.bsky.feed.post", "text": text, "createdAt": datetime.datetime.utcnow().isoformat() + "Z", "embed": embed}
    http(f"{pds}/xrpc/com.atproto.repo.createRecord", json.dumps({"repo": sess["did"], "collection": "app.bsky.feed.post", "record": record}).encode(), auth)
    return "bluesky: posted"

# ---------- X (OAuth 1.0a, hand-rolled) ----------
def oauth1_header(method, url, ck, cs, tk, ts_):
    p = {"oauth_consumer_key": ck, "oauth_nonce": uuid.uuid4().hex, "oauth_signature_method": "HMAC-SHA1",
         "oauth_timestamp": str(int(time.time())), "oauth_token": tk, "oauth_version": "1.0"}
    enc = lambda s: urllib.parse.quote(str(s), safe="")
    base = "&".join([method.upper(), enc(url), enc("&".join(f"{enc(k)}={enc(v)}" for k, v in sorted(p.items())))])
    key = f"{enc(cs)}&{enc(ts_)}".encode()
    p["oauth_signature"] = base64.b64encode(hmac.new(key, base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{enc(k)}="{enc(v)}"' for k, v in sorted(p.items()))

def post_x(text, link):
    ck, cs, tk, ts_ = (os.environ.get(k) for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"))
    if not all((ck, cs, tk, ts_)): return "x: skipped (no creds)"
    url = "https://api.twitter.com/2/tweets"
    body = json.dumps({"text": f"{text} {link}"}).encode()
    http(url, body, {"authorization": oauth1_header("POST", url, ck, cs, tk, ts_), "content-type": "application/json"})
    return "x: posted"

# ---------- Postiz (TikTok / Instagram Reels / YouTube Shorts scheduler) ----------
def post_postiz(text, link, video):
    key, integrations = os.environ.get("POSTIZ_API_KEY"), os.environ.get("POSTIZ_INTEGRATIONS", "")
    if not (key and integrations and video and os.path.exists(video)): return "postiz: skipped (no creds or no video)"
    base = os.environ.get("POSTIZ_API_URL", "https://api.postiz.com/public/v1")
    boundary = uuid.uuid4().hex
    data = video and open(video, "rb").read()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{os.path.basename(video)}\"\r\n"
            f"Content-Type: {mimetypes.guess_type(video)[0] or 'video/mp4'}\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    up = http(f"{base}/upload", body, {"Authorization": key, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    caption = f"{text}\n\nTake the test: {link}\n#ai #realorfake #aiart #deepfake"
    when = (datetime.datetime.utcnow() + datetime.timedelta(minutes=10)).isoformat() + "Z"
    posts = [{"integration": {"id": i.strip()}, "value": [{"content": caption, "image": [{"id": up.get("id"), "path": up.get("path")}]}],
              "settings": {"title": "Real or AI? Can you tell?", "privacy_level": "PUBLIC_TO_EVERYONE", "type": "public"}} for i in integrations.split(",") if i.strip()]
    http(f"{base}/posts", json.dumps({"type": "schedule", "date": when, "shortLink": False, "posts": posts}).encode(), {"Authorization": key, "content-type": "application/json"})
    return f"postiz: scheduled to {len(posts)} channel(s)"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=os.environ.get("SITE_URL", "https://fakebench.pages.dev"))
    ap.add_argument("--video", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    text, link, acc = compose(a.site.rstrip("/"))
    print("TEXT:", text, link)
    if a.dry_run: return
    for fn in (lambda: post_bluesky(text, link), lambda: post_x(text, link), lambda: post_postiz(text, link, a.video)):
        try: print(fn())
        except Exception as e: print("channel failed:", repr(e)[:300], file=sys.stderr)

if __name__ == "__main__":
    main()
