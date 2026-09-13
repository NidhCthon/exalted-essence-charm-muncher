"""Map warstriders onto Foundry Items, into the artifacts pack.

A warstrider is a chassis you wear and a set of weapons bolted to it, so it
becomes an armour for the chassis plus one weapon per gun. Every number is
read from the page: unlike an ordinary artifact, a warstrider prints its own
Soak and Hardness rather than taking them from a category.

The chassis also grants Defense, which no armour field holds, so that stays
in the description with the rest of the printed line.
"""
import hashlib
import html
import json
import re
from pathlib import Path

from build_artifacts import WEAPON_TAGS, tag_key

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "warstriders.raw.json"
OUT = ROOT / "data" / "packs" / "artifacts"

ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

STAT_RE = re.compile(
    r"([+-]?\s*\d+)\s*(Accuracy|Damage|Defense|Defence|Overwhelming)", re.I)
FIELD = {"accuracy": "accuracy", "damage": "damage", "defense": "defense",
         "defence": "defense", "overwhelming": "overwhelming"}


def doc_id(kind, owner, name):
    key = "warstrider:{}:{}:{}".format(kind, owner, name)
    number = int(hashlib.sha1(key.encode("utf-8")).hexdigest(), 16)
    out = []
    for _ in range(16):
        number, rem = divmod(number, len(ALPHABET))
        out.append(ALPHABET[rem])
    return "".join(out)


def to_html(paragraphs):
    return "".join("<p>{}</p>".format(html.escape(p)) for p in paragraphs if p)


def read_tags(text):
    known, custom = [], []
    for word in re.split(r"[,.]", text):
        word = word.strip()
        if not word or STAT_RE.search(word):
            continue
        key = tag_key(word)
        (known if key in WEAPON_TAGS else custom).append(
            key if key in WEAPON_TAGS else word)
    return known, custom


def build_chassis(entry):
    identifier = doc_id("chassis", entry["name"], entry["weight"])
    chassis = entry["chassis"]
    notes = [entry.get("form", ""), entry.get("description", "")]
    if entry.get("slots"):
        notes.append("Hearthstone slots: {}".format(entry["slots"]))
    notes.append(
        "A {} chassis: {} Defense, {} Soak, {} Hardness, {} Health Levels. "
        "The Defense bonus has no field on an armour sheet, so apply it by "
        "hand.".format(entry["weight"], chassis.get("defense", 0),
                       chassis.get("soak", 0), chassis.get("hardness", 0),
                       chassis.get("health levels", 0)))

    return {
        "_id": identifier,
        "_key": "!items!{}".format(identifier),
        "name": entry["name"],
        "type": "armor",
        "img": "systems/exaltedessence/assets/icons/breastplate.svg",
        "system": {
            "description": to_html(notes),
            "pagenum": str(entry["page"]),
            "soak": chassis.get("soak", 0),
            "penalty": 0,
            "hardness": chassis.get("hardness", 0),
            "poise": chassis.get("hardness", 0),
            "tags": "Artifact, Warstrider",
            "equipped": False,
            "weight": entry["weight"] if entry["weight"] in ("light", "heavy")
                      else "other",
            "traits": {"armortags": {"value": ["artifact"],
                                     "custom": "Warstrider"}},
        },
        "effects": [],
        "folder": None,
        "sort": 0,
        "ownership": {"default": 0},
        "flags": {},
    }


def build_weapon(entry, weapon):
    identifier = doc_id("weapon", entry["name"], weapon["name"])
    stats = {"accuracy": 0, "damage": 0, "defense": 0, "overwhelming": 0}
    for match in STAT_RE.finditer(weapon["printed"]):
        field = FIELD.get(match.group(2).lower())
        if field:
            stats[field] = int(match.group(1).replace(" ", ""))
    known, custom = read_tags(weapon["printed"].split(".", 1)[-1])
    # Thrown does not make it ranged; the melee tag settles it.
    ranged = "ranged" in known and "melee" not in known

    return {
        "_id": identifier,
        "_key": "!items!{}".format(identifier),
        # Named for the machine it is bolted to, so a compendium list does
        # not show three unattributed ballistae.
        "name": "{}: {}".format(entry["name"], weapon["name"]),
        "type": "weapon",
        "img": "icons/svg/sword.svg",
        "system": {
            "description": to_html([weapon["printed"]]),
            "pagenum": str(entry["page"]),
            "accuracy": stats["accuracy"],
            "damage": stats["damage"],
            "defence": stats["defense"],
            "defense": stats["defense"],
            "overwhelming": stats["overwhelming"],
            "equipped": False,
            "weapontype": "ranged" if ranged else "melee",
            "attackeffectpreset": "none",
            "attackeffect": "",
            "weight": "heavy",
            "traits": {"weapontags": {"value": known,
                                      "custom": ", ".join(custom)}},
        },
        "effects": [],
        "folder": None,
        "sort": 0,
        "ownership": {"default": 0},
        "flags": {},
    }


def main():
    if not SRC.exists():
        print("no warstriders extracted; nothing to build")
        return
    entries = json.loads(SRC.read_text(encoding="utf-8"))

    items = []
    for entry in entries:
        items.append(build_chassis(entry))
        for weapon in entry["weapons"]:
            items.append(build_weapon(entry, weapon))

    # Written alongside the artifacts rather than into a pack of their own:
    # four machines do not need their own compendium.
    OUT.mkdir(parents=True, exist_ok=True)
    for item in items:
        (OUT / "{}.json".format(item["_id"])).write_text(
            json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")

    print("warstriders written : {} chassis, {} weapons".format(
        sum(1 for i in items if i["type"] == "armor"),
        sum(1 for i in items if i["type"] == "weapon")))
    print("ids unique          : {}".format(
        len({i["_id"] for i in items}) == len(items)))
    for item in items:
        s = item["system"]
        if item["type"] == "armor":
            print("  {:38s} soak {} hardness {}".format(
                item["name"][:36], s["soak"], s["hardness"]))
        else:
            print("    {:36s} acc {} dmg {} def {} ovw {} [{}] {}".format(
                item["name"][:34], s["accuracy"], s["damage"], s["defense"],
                s["overwhelming"], s["weapontype"],
                ",".join(s["traits"]["weapontags"]["value"])))


if __name__ == "__main__":
    main()
