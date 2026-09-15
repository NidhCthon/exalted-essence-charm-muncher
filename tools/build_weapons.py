"""Turn an antagonist's printed weapon line into weapon Items on its sheet.

The books give an antagonist's weapons as a run of text in its stat block:

    Weapons: <name> (<n> Accuracy, <n> Damage, <n> Defense,
    <n> Overwhelming. Tags: <tag>, <tag>), <name> (...)

Every number the sheet wants is in there, so unlike an artifact nothing has
to be derived - these are read, not computed. Embedding them is right here in
a way it would not be for charms: a weapon is printed as part of the
antagonist rather than matched to it by name.
"""
import hashlib
import re

from build_artifacts import WEAPON_TAGS, attack_effect_preset, tag_key

# "Name (+1 Accuracy, +3 Damage, ... Tags: a, b)". The name runs up to the
# bracket; everything inside it is the statistics.
WEAPON_RE = re.compile(r"([^(),]{2,60}?)\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)")
# The draft manuscript once drops the opening bracket and prints a colon
# instead: "Name: +3 Accuracy, ... Tags: a, b)". Only a colon followed by a
# number and a closing bracket with no opening one before it is read as that,
# and the bracket is put back so the weapon is found like any other. Not
# inside a bracket that is already open: "(<weight>: <stats>; <weight>:
# <stats>)" is one weapon's stats at two weights, not a weapon named for one.
BRACKETLESS_RE = re.compile(
    r"([^():;,.]{2,60}?)\s*:\s*([+-]?\d[^()]{0,200}?\))")


def restore_bracket(match):
    before = match.string[:match.start()]
    if (before.count("(") != before.count(")")
            or not WEAPON_STAT_RE.search(match.group(2))):
        return match.group(0)
    return "{} ({}".format(match.group(1), match.group(2))


# Both orders are printed: "+1 Accuracy, 3 Overwhelming" and "Accuracy +1,
# Overwhelming 3", sometimes mixed in one bracket. Matching left to right,
# a number is taken by the word after it before the word in front of it, and
# a word-first number is refused when a stat word follows it, so neither
# "+3 Damage 2 Overwhelming" nor "Damage 12 Overwhelming" reads as Damage 2
# or 1.
STAT_WORDS = r"Accuracy|Acc|Damage|Dam|Defense|Defence|Def|Overwhelming"
STAT_RE = re.compile(
    r"([+-]?\d+)\s*({0})"
    r"|\b({0})\b\s*:?\s*([+-]?\d+)(?!\d|\s*(?:Acc|Dam|Def|Overwhelm))".format(
        STAT_WORDS),
    re.I)
TAGS_RE = re.compile(r"Tags?\s*:\s*(.+)$", re.I | re.S)
# "<band> range", "Range: <band>" and "Range <band>" are all printed.
RANGE_RE = re.compile(
    r"\b(?:(short|medium|long|extreme)\s+range"
    r"|range\s*:?\s*(short|medium|long|extreme))\b", re.I)
# The weapon line runs on into the qualities after it, so the text before a
# bracket can end a sentence of prose: "<prose>. Weapons: <name> (...)". The
# name is what follows the last full stop, colon or semicolon.
NAME_BREAK_RE = re.compile(r"[.:;]\s+")
# "<Name>. <a sentence about it> (<stats>)": a short title-case name first.
LEADING_NAME_RE = re.compile(
    r"^\s*([A-Z][\w'-]*(?:\s+(?:of|the|and|[A-Z][\w'-]*)){0,5})\.\s")
# "<Name> (<kind>): (<stats>)": the bracket before the stats belongs to the
# name, leaving only the colon between it and the stats.
KIND_NAME_RE = re.compile(r"([A-Z][^(),.:;]{0,60}?\s*\([^()]*\))\s*:\s*$")
# A weapon line whose "Weapons" heading lost its colon keeps it on the name.
WEAPON_LABEL_RE = re.compile(r"^weapons?\b\s*:?\s*", re.I)
# A weapon prints Accuracy or Overwhelming. An environmental hazard in the
# prose prints only damage and a difficulty, and is not a weapon.
WEAPON_STAT_RE = re.compile(r"\bAcc|Overwhelm", re.I)
# A bow or sling that prints neither a range nor the ranged tag still shoots.
SHOOTS_RE = re.compile(r"\b(?:long|short|cross|power)?bows?\b|sling", re.I)

FIELD = {
    "acc": "accuracy", "accuracy": "accuracy",
    "dam": "damage", "damage": "damage",
    "def": "defense", "defence": "defense", "defense": "defense",
    "overwhelming": "overwhelming",
}

ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def item_id(owner, name, index):
    key = "weapon:{}:{}:{}".format(owner, index, name)
    number = int(hashlib.sha1(key.encode("utf-8")).hexdigest(), 16)
    out = []
    for _ in range(16):
        number, rem = divmod(number, len(ALPHABET))
        out.append(ALPHABET[rem])
    return "".join(out)


def parse_weapons(text):
    """Every weapon in a printed weapon line."""
    text = BRACKETLESS_RE.sub(restore_bracket, text or "")
    found = []
    for match in WEAPON_RE.finditer(text):
        body = match.group(2)
        if not STAT_RE.search(body) or not WEAPON_STAT_RE.search(body):
            continue
        raw = match.group(1)
        start = 0
        for brk in NAME_BREAK_RE.finditer(raw):
            start = brk.end()
        printed = text[match.start(1) + start:match.end()].strip()
        if start == 0 and match.start() > 0 and text[match.start() - 1].isalnum():
            # The name pattern hit its length limit mid-sentence, so prose
            # runs right up to this bracket. The one form that still names
            # the weapon gives the name first, then a sentence about it.
            leading = LEADING_NAME_RE.match(text)
            if found or not leading:
                continue
            raw, printed = leading.group(1), text[:match.end()].strip()
        name = re.sub(r"^and\s+", "", raw[start:].strip(" .,;:&")).strip()
        if not name:
            kinded = KIND_NAME_RE.search(text, 0, match.start(2) - 1)
            if kinded:
                name = kinded.group(1).strip()
                printed = text[kinded.start(1):match.end()].strip()
        name = WEAPON_LABEL_RE.sub("", name)
        printed = WEAPON_LABEL_RE.sub("", printed)
        if len(name) < 2:
            continue

        stats = {"accuracy": 0, "damage": 0, "defense": 0, "overwhelming": 0}
        overwhelming = None
        for stat in STAT_RE.finditer(body):
            field = FIELD[(stat.group(2) or stat.group(3)).lower()]
            value = int(stat.group(1) or stat.group(4))
            stats[field] = value
            if field == "overwhelming" and overwhelming is None:
                overwhelming = value
        # Overwhelming has no sign, and where it is printed twice the first
        # one is the weapon's own.
        if overwhelming is not None:
            stats["overwhelming"] = abs(overwhelming)

        known, custom = [], []
        tags = TAGS_RE.search(body)
        if not tags:
            # No "Tags:" label: the tags sit bare in the bracket, before or
            # after the stats ("<tag>, <tag>, <stats>" and "<stats>, <tag>").
            # Only a segment that is a known tag is taken; anything else in
            # there (a range, "Artifact <kind>") is not a tag, nor custom.
            bare = RANGE_RE.sub("", STAT_RE.sub(",", body))
            for piece in re.split(r"[,.;]", bare):
                key = tag_key(piece)
                if key in WEAPON_TAGS and key not in known:
                    known.append(key)
        else:
            # A range printed after the tags ("Tags: <tag>. Range: <band>")
            # is not a tag, and left in it swallowed the tag before it.
            for tag in RANGE_RE.sub("", tags.group(1)).split(","):
                tag = tag.strip(" .;)")
                if not tag:
                    continue
                key = tag_key(tag)
                (known if key in WEAPON_TAGS else custom).append(
                    key if key in WEAPON_TAGS else tag)

        # Not every weapon is given a Tags clause. Where one is written as
        # its stats followed by a range ("<n> Overwhelming, Long range"), the range is
        # the book saying it shoots, so read that rather than leaving a bow
        # filed as a melee weapon.
        ranged = bool(RANGE_RE.search(body) or SHOOTS_RE.search(name))

        found.append({"name": name, "stats": stats, "tags": known,
                      "custom": custom, "ranged": ranged,
                      "printed": printed})
    return found


def weapon_items(owner, text):
    """The weapon line as Foundry weapon Items, ready to embed on an actor."""
    items = []
    for index, weapon in enumerate(parse_weapons(text)):
        identifier = item_id(owner, weapon["name"], index)
        # The ranged tag, or a printed range, and not merely thrown: a
        # weapon tagged melee and thrown is a melee weapon you can throw.
        ranged = ((weapon["ranged"] or "ranged" in weapon["tags"])
                  and "melee" not in weapon["tags"])
        items.append({
            "_id": identifier,
            "name": weapon["name"],
            "type": "weapon",
            "img": "icons/svg/sword.svg",
            "system": {
                "description": "<p>{}</p>".format(weapon["printed"]),
                "pagenum": "",
                "accuracy": weapon["stats"]["accuracy"],
                "damage": weapon["stats"]["damage"],
                "defence": weapon["stats"]["defense"],
                "defense": weapon["stats"]["defense"],
                "overwhelming": weapon["stats"]["overwhelming"],
                "equipped": True,
                "weapontype": "ranged" if ranged else "melee",
                "attackeffectpreset": attack_effect_preset(
                    weapon["name"], "ranged" if ranged else "melee",
                    weapon["tags"]),
                "attackeffect": "",
                "weight": "medium",
                "traits": {"weapontags": {"value": weapon["tags"],
                                          "custom": ", ".join(weapon["custom"])}},
            },
            "effects": [],
            "folder": None,
            "sort": 0,
            "ownership": {"default": 0},
            "flags": {},
        })
    return items
