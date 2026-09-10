"""Map extracted sorcery entries onto Foundry `spell` and `ritual` Items.

Runs after build_items.py, which clears data/packs/ - this only adds its own
two directories, so the order in the README matters.

The two schemas are much smaller than the charm one. A spell carries circle,
spelltype and a numeric Will cost; a ritual carries only a description and a
Will figure.
"""
import json
import re
from collections import Counter
from pathlib import Path

from build_items import doc_id, to_html

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "sorcery.raw.json"
OUT = ROOT / "data" / "packs"

WILL_RE = re.compile(r"\bSpend\s+(\d+)\s+Will\b", re.I)
RITUAL_WILL_RE = re.compile(r"\b(?:gain|generates?|grants?)\s+(\d+)\s+Will\b", re.I)


def build_spell(entry):
    identifier = doc_id(entry["name"])
    body = " ".join(entry["body"])
    match = WILL_RE.search(body)
    return {
        "_id": identifier,
        "_key": "!items!{}".format(identifier),
        "name": entry["name"],
        "type": "spell",
        "img": "icons/svg/daze.svg",
        "system": {
            "description": to_html(entry["body"]),
            "pagenum": str(entry["page"]),
            "activatable": False,
            "active": False,
            "autoaddtorolls": "",
            "endtrigger": "none",
            "circle": entry["circle"] or "first",
            "cost": int(match.group(1)) if match else 0,
            "spelltype": entry["spelltype"],
            "listingname": "",
            "iscontrolspell": False,
            "modes": {},
            "triggers": {"dicerollertriggers": {}},
        },
        "effects": [],
        "folder": None,
        "sort": 0,
        "ownership": {"default": 0},
        "flags": {},
    }


def build_ritual(entry):
    identifier = doc_id(entry["name"])
    match = RITUAL_WILL_RE.search(" ".join(entry["body"]))
    return {
        "_id": identifier,
        "_key": "!items!{}".format(identifier),
        "name": entry["name"],
        "type": "ritual",
        "img": "icons/svg/book.svg",
        "system": {
            "description": to_html(entry["body"]),
            "pagenum": str(entry["page"]),
            "will": int(match.group(1)) if match else 0,
        },
        "effects": [],
        "folder": None,
        "sort": 0,
        "ownership": {"default": 0},
        "flags": {},
    }


def main():
    entries = json.loads(SRC.read_text(encoding="utf-8"))
    packs = {"sorcery-spells": [], "shaping-rituals": []}
    for entry in entries:
        if entry["kind"] == "spell":
            packs["sorcery-spells"].append(build_spell(entry))
        else:
            packs["shaping-rituals"].append(build_ritual(entry))

    for name, items in packs.items():
        directory = OUT / name
        directory.mkdir(parents=True, exist_ok=True)
        for stale in directory.glob("*.json"):
            stale.unlink()
        for item in items:
            (directory / "{}.json".format(item["_id"])).write_text(
                json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        print("  {:4d}  {}".format(len(items), name))

    spells = packs["sorcery-spells"]
    print()
    print("spell circles  : {}".format(
        dict(Counter(i["system"]["circle"] for i in spells))))
    print("spell types    : {}".format(
        dict(Counter(i["system"]["spelltype"] for i in spells))))
    print("zero Will cost : {}".format(
        sum(1 for i in spells if not i["system"]["cost"])))
    print("rituals w/ Will: {}".format(
        sum(1 for i in packs["shaping-rituals"] if i["system"]["will"])))


if __name__ == "__main__":
    main()
