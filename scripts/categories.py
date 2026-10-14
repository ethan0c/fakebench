"""Subject categories for the image pool, inferred from the AI prompt or the Commons file name.

Keyword matching on whole words. The first category with the most hits wins; ties go to the
earlier entry in CATS, so a "woman holding a cat" counts as people. Items that match nothing
stay uncategorized and only appear in mixed rounds.
"""
import re, urllib.parse

CATS = {
    "people": "person people man men woman women girl girls boy boys child children kid kids baby family portrait "
              "face selfie crowd couple wedding bride groom student students worker workers farmer chef doctor nurse "
              "soldier police officer player players athlete runner cyclist dancer musician singer teacher friends "
              "grandmother grandfather mother father elderly teenager tourist tourists audience fans rider skier surfer",
    "animals": "animal animals dog dogs puppy cat cats kitten bird birds horse horses cow cows sheep goat goats pig "
               "chicken chickens duck ducks fish insect insects butterfly bee bees spider deer fox bear bears wolf lion "
               "tiger elephant giraffe zebra monkey squirrel rabbit owl eagle parrot penguin turtle frog lizard snake "
               "whale dolphin seal crab beetle ant dragonfly hedgehog otter raccoon swan goose pigeon gull heron "
               "hummingbird capybara camel llama alpaca koala panda kangaroo moth wildlife",
    "food": "food meal dish breakfast lunch dinner pizza burger sandwich salad soup bread cake cookie cookies "
            "dessert fruit fruits apple apples banana bananas orange oranges vegetables vegetable tomato tomatoes "
            "cheese coffee tea wine beer cocktail drink drinks pasta noodles sushi rice steak chicken meat egg eggs "
            "pancakes donut donuts chocolate ice cream bakery market restaurant kitchen plate bowl cup milk juice",
    "places": "landscape mountain mountains lake river sea ocean beach coast island forest woods field fields "
              "valley desert waterfall sunset sunrise sky city street streets town village building buildings "
              "church cathedral castle bridge tower skyline harbor harbour port park garden road square plaza "
              "station temple mosque palace house houses architecture ruins canyon cliff hill hills meadow snow "
              "night aerial view panorama interior room hall library museum",
    "objects": "car cars truck bus train tram bicycle bike motorcycle boat boats ship airplane plane aircraft "
               "clock watch phone laptop computer camera book books chair table lamp bottle bottles glass glasses "
               "shoe shoes bag hat guitar piano toy toys sign tool tools vase umbrella keyboard bench mug "
               "sculpture statue robot machine engine",
}
_WORDS = {c: set(ws.split()) for c, ws in CATS.items()}
_TOKEN = re.compile(r"[a-z]+")

def classify(text):
    words = _TOKEN.findall((text or "").lower())
    best, hits = None, 0
    for cat, vocab in _WORDS.items():
        n = sum(1 for w in words if w in vocab)
        if n > hits: best, hits = cat, n
    return best

def item_text(item):
    """Text to classify: the prompt for AI images, the decoded file name for real photos."""
    if item.get("label") == "ai": return item.get("prompt") or ""
    page = item.get("page") or ""
    name = urllib.parse.unquote(page.rsplit("File:", 1)[-1]) if "File:" in page else ""
    return re.sub(r"[_\-.,()]+", " ", re.sub(r"\.(jpe?g|png|tiff?)$", "", name, flags=re.I))

def _split_camel(s):
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)

def commons_categories(pages, get_json):
    """Visible Commons categories for real photos, keyed by page URL. get_json(url) -> parsed JSON."""
    titles = {urllib.parse.unquote(p.rsplit("/wiki/", 1)[-1]).replace("_", " "): p for p in pages if "/wiki/" in p}
    out, names = {}, list(titles)
    for i in range(0, len(names), 50):
        q = urllib.parse.urlencode({"action": "query", "format": "json", "prop": "categories", "clshow": "!hidden",
                                    "cllimit": "max", "titles": "|".join(names[i:i + 50])})
        data = get_json("https://commons.wikimedia.org/w/api.php?" + q)
        norm = {n["to"]: n["from"] for n in data.get("query", {}).get("normalized", [])}
        for pg in data.get("query", {}).get("pages", {}).values():
            t = norm.get(pg.get("title"), pg.get("title"))
            if t in titles:
                out[titles[t]] = [c["title"].split(":", 1)[-1] for c in pg.get("categories", [])]
    return out

def categorize(items, get_json=None):
    """Set item["cat"] on every item that lacks one. Real photos also use their Commons categories when get_json is given."""
    todo = [i for i in items if "cat" not in i]
    extra = {}
    if get_json:
        pages = [i["page"] for i in todo if i.get("label") == "real" and i.get("page")]
        try: extra = commons_categories(pages, get_json)
        except Exception as e: print("commons categories unavailable:", e)
    for i in todo:
        text = _split_camel(item_text(i))
        cats = extra.get(i.get("page"), [])
        # The file name is the strongest signal; categories break ties and fill gaps.
        i["cat"] = classify(text) or classify(_split_camel(" ".join(cats)))
