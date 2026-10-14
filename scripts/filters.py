"""Shared plausibility rules for AI images. Used by fetch_fake.py (to avoid wasted downloads) and
build_manifest.py (as the final gate, so rules can tighten without re-downloading anything)."""
import re

NON_PHOTO = re.compile(r"paint|illustrat|anime|render|digital art|cartoon|drawing|sketch|\b3d\b|pixel|concept art|fantasy|manga|comic|artwork|stylized|surreal|dragon|robot|cyborg|astronaut|monster|creature|wizard|magic|neon|logo|poster|typography|emoji|clipart|vector|icon|sticker", re.I)
IMPLAUSIBLE = re.compile(r"written|says|\bsign\b|\btext\b|letter|\bword|quote|'|\"|a type of|a device|an inst|which grows|consisting|used for|bigger than|smaller than|larger than|under the sea|underwater|upside|in the shape|shaped|triangular|\bsquare\b|made of|made out of|in space|on the moon|flying|floating|vertical|without|with no|makes us feel|real scene|photojournalism|typically|\btimes\b|solaris|colored|coloured|scaring|smil|on top of|sticking|mirror|octopus|donkey|dolphin|tiger|giraffe|zebra|elephant|lion|kangaroo|penguin|dinosaur|unicorn", re.I)
UNNATURAL_COLOR = re.compile(r"\b(red|blue|green|yellow|purple|pink|orange|rainbow|golden|silver)\b[^.,]{0,12}\b(bunny|rabbit|bird|bear|cat|dog|horse|cow|sheep|fish|frog|duck|monkey|pig|goat|deer|wolf|fox|owl|mouse|squirrel|turtle|snake|kitten|puppy|banana|apple|lemon|bread|pizza|egg|milk|rice|grass|tree|cloud|sky|snow|sand)s?\b", re.I)
# "A blue cup and a green cell phone": object-pair prompts render as studio product shots.
OBJECT_PAIR = re.compile(r"^(a|an|the|two|three)\b[^.]{0,40}\b(and|next to|beside|on the right of|on the left of|above|below)\b[^.]{0,40}$", re.I)
# A scene needs an action or a place; bare nouns become catalogue images on plain backgrounds.
SCENE = re.compile(r"\b\w+ing\b|\b(in|on|at|near|along|through|inside|outside|across|under|behind|beside|down|along)\s+(a|an|the|some|his|her|their)\b", re.I)
WEAK_MODELS = {"Janus 7B (DeepSeek)", "Lumina (OpenGVLab)", "Recraft V2", "Stable Diffusion 3", "Midjourney 5.2"}

def plausible(prompt, model=None):
    p = (prompt or "").strip().rstrip(" .!")
    n = len(p.split())
    if n < 6 or n > 40: return False
    if model in WEAK_MODELS: return False
    if NON_PHOTO.search(p) or IMPLAUSIBLE.search(p) or UNNATURAL_COLOR.search(p): return False
    if OBJECT_PAIR.match(p) or not SCENE.search(p): return False
    return True
