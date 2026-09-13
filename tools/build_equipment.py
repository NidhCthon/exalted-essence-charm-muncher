"""Map the mundane weapons onto Foundry `weapon` Items, plus the two armours.

Statistics come from the equipment chapter's table for the weapon's
category, the same table the artifact builder uses - without the artifact
bonus, because these are not artifacts.

    Light   accuracy +2  damage +0  defense +1  overwhelming 1
    Medium  accuracy +1  damage +1  defense +1  overwhelming 1
    Heavy   accuracy +0  damage +2  defense +1  overwhelming 1

Tags need more care here than they did for artifacts. An artifact prints a
plain list; an example weapon often prints a choice - "smashing, improvised,
or balanced" is one of three, not all three - or a condition, as in
"sometimes mounted". Ticking every box in those cases would give a weapon
tags the book does not give it, and the tags carry mechanics, so only the
unconditional ones are set. The rest are named in the description for a
player to pick from.

The book prints no example armour, only the two categories with their
statistics, so those two are built from the table and described as what they
are: the category rather than a named piece of kit.
"""
import hashlib
import html
import json
import re
from pathlib import Path

from build_artifacts import WEAPON_BASE, WEAPON_TAGS, tag_key

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "equipment.raw.json"
OUT = ROOT / "data" / "packs" / "equipment"

ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

# Words that make a tag conditional rather than given.
HEDGE_RE = re.compile(r"^(sometimes|usually|often|may be|can be)\s+", re.I)

ARMOUR = [
    ("Light Armor", "light", 1, 0, 0,
     "The light armour category from the equipment chapter. The book gives "
     "the category its statistics but prints no named examples, so this is "
     "the category itself, ready to rename for whatever the character is "
     "actually wearing."),
    ("Heavy Armor", "heavy", 2, -1, 0,
     "The heavy armour category from the equipment chapter. The book gives "
     "the category its statistics but prints no named examples, so this is "
     "the category itself, ready to rename for whatever the character is "
     "actually wearing."),
]


def doc_id(name, book, page):
    key = "equipment:{}:{}:{}".format(book, page, name)
    number = int(hashlib.sha1(key.encode("utf-8")).hexdigest(), 16)
    out = []
    for _ in range(16):
        number, rem = divmod(number, len(ALPHABET))
        out.append(ALPHABET[rem])
    return "".join(out)


def to_html(paragraphs):
    return "".join("<p>{}</p>".format(html.escape(p)) for p in paragraphs if p)


def read_tags(clause, weapontype):
    """Tags the book gives outright, and the ones it leaves to the player.

    A clause reads either as a list ("thrown, concealable, paired") or as a
    choice ("smashing, improvised, or balanced"), and a single tag can be
    hedged ("sometimes mounted"). Only what is given outright is ticked.
    """
    given, optional = [], []
    # Close combat weapons always have melee; ranged weapons always ranged.
    given.append(weapontype)

    parts = [p.strip() for p in clause.rstrip(".").split(",") if p.strip()]
    # "Smashing, improvised, or balanced" is one of three. "Balanced,
    # chopping or piercing, off-hand" gives two and offers a choice between
    # the other two. What separates them is whether the last item opens with
    # "or", which makes the whole list the set of alternatives.
    whole_list = bool(parts) and bool(re.match(r"^or\b", parts[-1], re.I))

    for part in parts:
        alternatives = [p.strip() for p in re.split(r"\bor\b", part)]
        hedged = bool(HEDGE_RE.match(part))
        if whole_list:
            alternatives = [re.sub(r"^or\b", "", part, flags=re.I).strip()]
            hedged = True
        for alternative in alternatives:
            name = HEDGE_RE.sub("", alternative).strip(" .")
            if not name:
                continue
            key = tag_key(name)
            if key not in WEAPON_TAGS:
                optional.append(name)
            elif hedged or len(alternatives) > 1:
                optional.append(name)
            elif key not in given:
                given.append(key)
    return given, optional


def build(entry):
    identifier = doc_id(entry["name"], entry["book"], entry["page"])
    accuracy, damage, defense, overwhelming = WEAPON_BASE[entry["weight"]]
    given, optional = read_tags(entry["tags"], entry["weapontype"])

    parts = [entry["description"]]
    parts.append("Tags: {}".format(entry["tags"]))
    if optional:
        parts.append(
            "The book leaves these to the wielder rather than giving them "
            "outright, so they are not ticked: {}.".format(", ".join(optional)))
    parts.append(
        "Statistics are the {} weapon category from the equipment chapter."
        .format(entry["weight"]))

    return {
        "_id": identifier,
        "_key": "!items!{}".format(identifier),
        "name": entry["name"],
        "type": "weapon",
        "img": "icons/svg/sword.svg",
        "system": {
            "description": to_html(parts),
            "pagenum": str(entry["page"]),
            "accuracy": accuracy,
            "damage": damage,
            "defence": defense,
            "defense": defense,
            "overwhelming": overwhelming,
            "equipped": False,
            "weapontype": entry["weapontype"],
            "attackeffectpreset": "none",
            "attackeffect": "",
            "weight": entry["weight"],
            "traits": {"weapontags": {"value": given,
                                      "custom": ", ".join(optional)}},
        },
        "effects": [],
        "folder": None,
        "sort": 0,
        "ownership": {"default": 0},
        "flags": {},
    }


def build_armour(name, weight, soak, penalty, hardness, note):
    identifier = doc_id(name, "core", 342)
    return {
        "_id": identifier,
        "_key": "!items!{}".format(identifier),
        "name": name,
        "type": "armor",
        "img": "systems/exaltedessence/assets/icons/breastplate.svg",
        "system": {
            "description": to_html([note]),
            "pagenum": "342",
            "soak": soak,
            "penalty": penalty,
            "hardness": hardness,
            # As above: Hardness is Poise under Combat Reforged. Mundane
            # armour grants no Hardness, so this is zero either way - it is
            # set from the same place so the two cannot drift apart.
            "poise": hardness,
            "tags": "",
            "equipped": False,
            "weight": weight,
            "traits": {"armortags": {"value": [], "custom": ""}},
        },
        "effects": [],
        "folder": None,
        "sort": 0,
        "ownership": {"default": 0},
        "flags": {},
    }


def main():
    if not SRC.exists():
        print("no equipment extracted; nothing to build")
        return
    entries = json.loads(SRC.read_text(encoding="utf-8"))
    items = [build(e) for e in entries]
    items += [build_armour(*row) for row in ARMOUR]

    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.json"):
        stale.unlink()
    for item in items:
        (OUT / "{}.json".format(item["_id"])).write_text(
            json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")

    weapons = [i for i in items if i["type"] == "weapon"]
    print("equipment written : {}".format(len(items)))
    print("  weapons {}, armour {}".format(len(weapons), len(items) - len(weapons)))
    print("  ids unique      : {}".format(
        len({i["_id"] for i in items}) == len(items)))
    print("  with a choice   : {}".format(sum(
        1 for i in weapons if i["system"]["traits"]["weapontags"]["custom"])))
    print()
    for item in weapons[:10]:
        s = item["system"]
        print("  {:26s} {:6s} acc {} dmg {} def {} ovw {}  {}".format(
            item["name"][:24], s["weight"], s["accuracy"], s["damage"],
            s["defense"], s["overwhelming"],
            ",".join(s["traits"]["weapontags"]["value"])))


if __name__ == "__main__":
    main()
