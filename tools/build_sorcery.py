"""Map extracted sorcery entries onto Foundry `spell` and `ritual` Items.

Runs after build_items.py, which clears data/packs/ - this only adds its own
two directories, so the order in the README matters.

Both books' sorcery chapters feed the same two packs. Core ids stay
unnamespaced so already-published packs keep them; supplement ids are
namespaced by book and page, because names are not unique across books.

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
OUT = ROOT / "data" / "packs"

SOURCES = [
    ("core", ROOT / "data" / "sorcery.raw.json"),
    ("pillars", ROOT / "data" / "sorcery_pillars.raw.json"),
]

WILL_RE = re.compile(r"\bSpend\s+(\d+)\s+Will\b", re.I)
RITUAL_WILL_RE = re.compile(r"\b(?:gain|generates?|grants?)\s+(\d+)\s+Will\b", re.I)


def build_spell(entry, book):
    identifier = doc_id(entry["name"], book, None, entry.get("page"))
    match = WILL_RE.search(" ".join(entry["body"]))
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


def build_ritual(entry, book):
    identifier = doc_id(entry["name"], book, None, entry.get("page"))
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
    packs = {"sorcery-spells": [], "shaping-rituals": []}
    seen_books = []
    for book, path in SOURCES:
        if not path.exists():
            print("  skipping missing source: {}".format(path.name))
            continue
        seen_books.append(book)
        for entry in json.loads(path.read_text(encoding="utf-8")):
            if entry["kind"] == "spell":
                packs["sorcery-spells"].append(build_spell(entry, book))
            else:
                packs["shaping-rituals"].append(build_ritual(entry, book))

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
    every = spells + packs["shaping-rituals"]
    print()
    print("books included : {}".format(", ".join(seen_books)))
    print("ids unique     : {}".format(
        len({i["_id"] for i in every}) == len(every)))
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
