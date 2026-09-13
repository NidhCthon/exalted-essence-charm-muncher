"""Turn an antagonist's printed weapon line into weapon Items on its sheet.

The books give an antagonist's weapons as a run of text in its stat block:

    Weapons: Bloodspike Spear (+1 Accuracy, +3 Damage, +2 Defense,
    3 Overwhelming. Tags: Artifact, Piercing, Reaching), Glad-of-War Bow
    (+2 Accuracy, +2 Damage, 2 Overwhelming. Tags: Artifact, Ranged)

Every number the sheet wants is in there, so unlike an artifact nothing has
to be derived - these are read, not computed. Embedding them is right here in
a way it would not be for charms: a weapon is printed as part of the
antagonist rather than matched to it by name.
"""
import hashlib
import re

from build_artifacts import WEAPON_TAGS, tag_key

# "Name (+1 Accuracy, +3 Damage, ... Tags: a, b)". The name runs up to the
# bracket; everything inside it is the statistics.
WEAPON_RE = re.compile(r"([^(),]{2,60}?)\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)")
STAT_RE = re.compile(
    r"([+-]?\d+)\s*(Accuracy|Acc|Damage|Dam|Defense|Defence|Def|Overwhelming)",
    re.I)
OVERWHELMING_RE = re.compile(r"(\d+)\s*Overwhelming", re.I)
TAGS_RE = re.compile(r"Tags?\s*:\s*(.+)$", re.I | re.S)
RANGE_RE = re.compile(r"\b(short|medium|long|extreme)\s+range\b", re.I)

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
    found = []
    for match in WEAPON_RE.finditer(text or ""):
        name = match.group(1).strip(" .,;:&").lstrip("and ").strip()
        body = match.group(2)
        if len(name) < 2 or not STAT_RE.search(body):
            continue

        stats = {"accuracy": 0, "damage": 0, "defense": 0, "overwhelming": 0}
        for stat in STAT_RE.finditer(body):
            field = FIELD.get(stat.group(2).lower())
            if field:
                stats[field] = int(stat.group(1))
        # Overwhelming is written after its number without a sign, which the
        # signed pattern above also catches - but only when it is not the
        # first thing in the bracket, so read it directly too.
        overwhelming = OVERWHELMING_RE.search(body)
        if overwhelming:
            stats["overwhelming"] = int(overwhelming.group(1))

        known, custom = [], []
        tags = TAGS_RE.search(body)
        if tags:
            for tag in tags.group(1).split(","):
                tag = tag.strip(" .;)")
                if not tag:
                    continue
                key = tag_key(tag)
                (known if key in WEAPON_TAGS else custom).append(
                    key if key in WEAPON_TAGS else tag)

        # Not every weapon is given a Tags clause. Where one is written
        # "+2 Accuracy, +2 Damage, 2 Overwhelming, Long range", the range is
        # the book saying it shoots, so read that rather than leaving a bow
        # filed as a melee weapon.
        ranged = bool(RANGE_RE.search(body))

        found.append({"name": name, "stats": stats, "tags": known,
                      "custom": custom, "ranged": ranged,
                      "printed": match.group(0).strip()})
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
                "attackeffectpreset": "none",
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
