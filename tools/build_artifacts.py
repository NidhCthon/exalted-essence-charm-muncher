"""Map extracted artifacts onto Foundry `weapon` and `armor` Items.

An artifact does not print its own numbers. The equipment chapter gives a
table by category, and the artifact tag says to "increase all weapon or
armor stats by one", so the numbers here are derived from the Type line
rather than read off the page. That derivation is stated in each item's
description, because a derived number should not look like a printed one.

    Weapons   accuracy  damage  defense  overwhelming
    Light        +2       +0      +1          1
    Medium       +1       +1      +1          1
    Heavy        +0       +2      +1          1

    Armor     soak  mobility penalty  hardness
    Light      +1          0             0
    Heavy      +2         -1             0

The mobility penalty is not improved by the artifact tag - the rule lists
Soak and Hardness only.

Only the artifact bonus is baked into the numbers. The other tags carry
mechanical effects too - balanced raises Overwhelming by one - but the
system's roller reads those tags and applies them itself, so adding them
here would count them twice. It does not do that for artifact, which is why
that one is applied here.
"""
import hashlib
import html
import json
import re
from pathlib import Path

from extract_antagonists import join_spans

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "artifacts.raw.json"
OUT = ROOT / "data" / "packs"

ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

WEAPON_BASE = {          # accuracy, damage, defense, overwhelming
    "light": (2, 0, 1, 1),
    "medium": (1, 1, 1, 1),
    "heavy": (0, 2, 1, 1),
}
ARMOR_BASE = {           # soak, penalty, hardness
    "light": (1, 0, 0),
    "heavy": (2, -1, 0),
}

# The system's own tag keys, from its config. A tag the book writes with a
# qualifier - "Ranged (Long)" - is that tag plus a detail worth keeping in
# the description, so the qualifier is stripped for matching and the whole
# phrase is kept as written.
WEAPON_TAGS = {
    "aggravated", "artifact", "balanced", "chopping", "concealable",
    "defensive", "disarming", "flame", "flexible", "improvised",
    "magicdamage", "melee", "mounted", "natural", "worn", "offhand",
    "onehanded", "paired", "piercing", "pulling", "powerful", "ranged",
    "reaching", "returning", "shield", "smashing", "thrown", "twohanded",
}
ARMOR_TAGS = {"artifact", "buoyant", "concealable", "silent", "towering"}

CATEGORY_RE = re.compile(r"\b(light|medium|heavy)\b", re.I)
RANGED_RE = re.compile(r"\branged\b", re.I)
ARMOR_RE = re.compile(r"\barmou?r\b", re.I)


def doc_id(name, book, page):
    key = "artifact:{}:{}:{}".format(book, page, name)
    number = int(hashlib.sha1(key.encode("utf-8")).hexdigest(), 16)
    out = []
    for _ in range(16):
        number, rem = divmod(number, len(ALPHABET))
        out.append(ALPHABET[rem])
    return "".join(out)


def tag_key(tag):
    """"Two-Handed" and "Ranged (Long)" are the twohanded and ranged tags."""
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", tag).lower())


def split_tags(text, vocabulary):
    """Known tags as system keys; anything else kept as written."""
    known, custom = [], []
    for tag in text.split(","):
        tag = tag.strip(" .;")
        if not tag:
            continue
        key = tag_key(tag)
        if key in vocabulary:
            known.append(key)
            if "(" in tag:          # the qualifier is not in the key
                custom.append(tag)
        else:
            custom.append(tag)
    return known, custom


def to_html(paragraphs):
    return "".join("<p>{}</p>".format(html.escape(p)) for p in paragraphs if p)


def description(entry, derived):
    parts = []
    if entry["form"]:
        parts.append(entry["form"])
    parts.append(join_spans(entry["body"]))
    if entry["slots"]:
        parts.append("Hearthstone slots: {}".format(entry["slots"]))
    parts.append("Type: {}. Tags: {}.".format(entry["type"], entry["tags"]))
    parts.append(
        "Statistics derived from the {} category plus the artifact tag, "
        "which increases each by one. The book prints the category, not the "
        "numbers.".format(derived))
    return to_html(parts)


def build(entry):
    identifier = doc_id(entry["name"], entry["book"], entry["page"])
    kind = entry["type"]
    category_match = CATEGORY_RE.search(kind)
    category = category_match.group(1).lower() if category_match else "medium"
    is_armor = bool(ARMOR_RE.search(kind))
    artifact = "artifact" in entry["tags"].lower()

    common = {
        "_id": identifier,
        "_key": "!items!{}".format(identifier),
        "name": entry["name"],
        "folder": None,
        "sort": 0,
        "ownership": {"default": 0},
        "flags": {},
        "effects": [],
    }

    if is_armor:
        soak, penalty, hardness = ARMOR_BASE.get(category, ARMOR_BASE["light"])
        if artifact:
            soak += 1
            hardness += 1
        known, custom = split_tags(entry["tags"], ARMOR_TAGS)
        common.update({
            "type": "armor",
            "img": "systems/exaltedessence/assets/icons/breastplate.svg",
            "system": {
                "description": description(entry, category + " armor"),
                "pagenum": str(entry["page"]),
                "soak": soak,
                "penalty": penalty,
                "hardness": hardness,
                "poise": 0,
                "tags": entry["tags"],
                "equipped": False,
                "weight": category if category in ("light", "heavy") else "other",
                "traits": {"armortags": {"value": known,
                                         "custom": ", ".join(custom)}},
            },
        })
        return common

    accuracy, damage, defense, overwhelming = WEAPON_BASE.get(
        category, WEAPON_BASE["medium"])
    if artifact:
        accuracy += 1
        damage += 1
        defense += 1
        overwhelming += 1
    known, custom = split_tags(entry["tags"], WEAPON_TAGS)
    common.update({
        "type": "weapon",
        "img": "icons/svg/sword.svg",
        "system": {
            "description": description(entry, category + " weapon"),
            "pagenum": str(entry["page"]),
            "accuracy": accuracy,
            "damage": damage,
            "defence": defense,
            "defense": defense,
            "overwhelming": overwhelming,
            "equipped": False,
            "weapontype": "ranged" if RANGED_RE.search(kind) else "melee",
            "attackeffectpreset": "none",
            "attackeffect": "",
            "weight": category,
            "traits": {"weapontags": {"value": known,
                                      "custom": ", ".join(custom)}},
        },
    })
    return common


def main():
    if not SRC.exists():
        print("no artifacts extracted; nothing to build")
        return
    entries = json.loads(SRC.read_text(encoding="utf-8"))
    items = [build(e) for e in entries]

    target = OUT / "artifacts"
    target.mkdir(parents=True, exist_ok=True)
    for stale in target.glob("*.json"):
        stale.unlink()
    for item in items:
        (target / "{}.json".format(item["_id"])).write_text(
            json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")

    weapons = [i for i in items if i["type"] == "weapon"]
    armour = [i for i in items if i["type"] == "armor"]
    print("artifacts written : {}".format(len(items)))
    print("  weapons {}, armour {}".format(len(weapons), len(armour)))
    print("  ids unique      : {}".format(
        len({i["_id"] for i in items}) == len(items)))
    print()
    for item in items:
        s = item["system"]
        if item["type"] == "weapon":
            print("  {:32s} {:6s} acc {} dmg {} def {} ovw {}  {}".format(
                item["name"][:30], s["weight"], s["accuracy"], s["damage"],
                s["defense"], s["overwhelming"],
                ",".join(s["traits"]["weapontags"]["value"])))
        else:
            print("  {:32s} {:6s} soak {} pen {} hard {}  {}".format(
                item["name"][:30], s["weight"], s["soak"], s["penalty"],
                s["hardness"], ",".join(s["traits"]["armortags"]["value"])))


if __name__ == "__main__":
    main()
