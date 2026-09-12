"""Map extracted hearthstones onto Foundry `merit` Items.

A hearthstone is a Merit in Essence - the character creation chapter lists
Hearthstone among the merits a character buys - so that is the type used
here rather than a generic item. The system's merit carries a free-text
`rating`, which takes the Lesser or Greater the book prints in brackets, and
a `merittype`, which is a free string set to hearthstone so these can be
told apart from other merits at a glance.

Nothing about a hearthstone is numeric, so nothing here is derived. The
aspect and the manse description are kept as printed.
"""
import hashlib
import html
import json
import re
from pathlib import Path

from extract_antagonists import join_spans

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "hearthstones.raw.json"
OUT = ROOT / "data" / "packs" / "hearthstones"

ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def doc_id(name, book, page):
    key = "hearthstone:{}:{}:{}".format(book, page, name)
    number = int(hashlib.sha1(key.encode("utf-8")).hexdigest(), 16)
    out = []
    for _ in range(16):
        number, rem = divmod(number, len(ALPHABET))
        out.append(ALPHABET[rem])
    return "".join(out)


def to_html(paragraphs):
    return "".join("<p>{}</p>".format(html.escape(p)) for p in paragraphs if p)


# The spans are lines, not paragraphs, so one <p> per span gives a wall of
# one-line paragraphs. These are the headings the chapter actually uses, and
# a paragraph starts at each one.
SECTION_RE = re.compile(
    r"^(While in possession|While set in a weapon|Manse attributes"
    r"|Demesne attributes)\s*:?\s*$", re.I)


def paragraphs(body):
    """Reflow the lines into paragraphs led by the chapter's own headings."""
    out, current = [], []
    for line in body:
        if SECTION_RE.match(line.strip()):
            if current:
                out.append(join_spans(current))
            heading = line.strip().rstrip(":")
            current = ["{}:".format(heading)]
        else:
            current.append(line)
    if current:
        out.append(join_spans(current))
    return out


def build(entry):
    identifier = doc_id(entry["name"], entry["book"], entry["page"])
    parts = []
    if entry["aspect"]:
        parts.append("Aspect: {}. {} hearthstone.".format(
            entry["aspect"], entry["rating"] or "Standard"))
    parts.extend(paragraphs(entry["body"]))

    return {
        "_id": identifier,
        "_key": "!items!{}".format(identifier),
        "name": entry["name"],
        "type": "merit",
        "img": "icons/svg/coins.svg",
        "system": {
            "description": to_html(parts),
            "pagenum": str(entry["page"]),
            "merittype": "hearthstone",
            "rating": entry["rating"],
        },
        "effects": [],
        "folder": None,
        "sort": 0,
        "ownership": {"default": 0},
        "flags": {},
    }


def main():
    if not SRC.exists():
        print("no hearthstones extracted; nothing to build")
        return
    entries = json.loads(SRC.read_text(encoding="utf-8"))
    items = [build(e) for e in entries]

    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.json"):
        stale.unlink()
    for item in items:
        (OUT / "{}.json".format(item["_id"])).write_text(
            json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")

    print("hearthstones written : {}".format(len(items)))
    print("ids unique           : {}".format(
        len({i["_id"] for i in items}) == len(items)))
    print("with a rating        : {}".format(
        sum(1 for i in items if i["system"]["rating"])))
    print("empty description    : {}".format(
        sum(1 for i in items if not i["system"]["description"])))
    print()
    for item in items[:8]:
        print("  {:34s} {:10s} p{}".format(
            item["name"][:32], item["system"]["rating"],
            item["system"]["pagenum"]))


if __name__ == "__main__":
    main()
