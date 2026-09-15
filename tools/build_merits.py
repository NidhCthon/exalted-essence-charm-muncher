"""Map extracted Merits onto Foundry `merit` Items.

The system's merit has a free-text `merittype`, left at the system's own
default of story, and a `rating` that has to be primary, secondary, tertiary
or blank. The dice roller adds CONFIG.EXALTEDESSENCE.meritDiceBonuses[rating]
to any roll the Merit is added to, and a value outside those turns the roll's
dice modifier into NaN.

These are Merits a character buys at a rating of their choosing, so the
rating is left for the player to set - except where the book allows only
one. The ratings a Merit may take have no field of their own, so they lead
the description.
"""
import hashlib
import html
import json
import re
from pathlib import Path

from extract_antagonists import join_spans

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "merits.raw.json"
OUT = ROOT / "data" / "packs" / "merits"

ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

ONLY_RE = re.compile(r"^(primary|secondary|tertiary) only$", re.I)
# The book leads each rating's paragraph with its name.
RATING_LABEL_RE = re.compile(r"^(Tertiary|Secondary|Primary):\s*")


def doc_id(name, book, page):
    key = "merit:{}:{}:{}".format(book, page, name)
    number = int(hashlib.sha1(key.encode("utf-8")).hexdigest(), 16)
    out = []
    for _ in range(16):
        number, rem = divmod(number, len(ALPHABET))
        out.append(ALPHABET[rem])
    return "".join(out)


def restriction_note(restriction):
    if restriction.lower() == "any":
        return "Any rating."
    return "{}.".format(restriction[0].upper() + restriction[1:].lower())


def paragraph(text):
    label = RATING_LABEL_RE.match(text)
    if label:
        return "<p><strong>{}:</strong> {}</p>".format(
            label.group(1), html.escape(text[label.end():]))
    return "<p>{}</p>".format(html.escape(text))


def description(entry):
    parts = ["<p><em>{}</em></p>".format(
        html.escape(restriction_note(entry["restriction"])))]
    parts.extend(paragraph(join_spans(p)) for p in entry["paragraphs"])
    box = entry.get("sidebar")
    if box:
        parts.append("<p><strong>{}</strong></p>".format(
            html.escape(box["title"])))
        parts.extend("<p>{}</p>".format(html.escape(join_spans(line)))
                     for line in box["lines"])
    return "".join(parts)


def build(entry):
    identifier = doc_id(entry["name"], entry["book"], entry["page"])
    only = ONLY_RE.match(entry["restriction"])
    return {
        "_id": identifier,
        "_key": "!items!{}".format(identifier),
        "name": entry["name"],
        "type": "merit",
        "img": "icons/svg/coins.svg",
        "system": {
            "description": description(entry),
            "pagenum": str(entry["page"]),
            "merittype": "story",
            "rating": only.group(1).lower() if only else "",
        },
        "effects": [],
        "folder": None,
        "sort": 0,
        "ownership": {"default": 0},
        "flags": {},
    }


def main():
    if not SRC.exists():
        print("no merits extracted; nothing to build")
        return
    entries = json.loads(SRC.read_text(encoding="utf-8"))
    items = [build(e) for e in entries]

    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.json"):
        stale.unlink()
    for item in items:
        (OUT / "{}.json".format(item["_id"])).write_text(
            json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")

    print("merits written  : {}".format(len(items)))
    print("ids unique      : {}".format(
        len({i["_id"] for i in items}) == len(items)))
    print("with a rating   : {}".format(
        sum(1 for i in items if i["system"]["rating"])))
    print()
    for item, entry in zip(items, entries):
        print("  {:14s} {:10s} p{:<4} {}".format(
            item["name"][:14], item["system"]["rating"] or "-",
            item["system"]["pagenum"], entry["restriction"]))


if __name__ == "__main__":
    main()
