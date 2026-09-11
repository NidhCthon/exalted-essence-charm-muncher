"""Extract spells and shaping rituals from Pillars of Creation.

Pillars carries its own Sorcery and Necromancy chapter, and it is laid out
differently from the core book's, which is why it needs its own pass:

* The core book marks circles with clean 13.9pt headings. Pillars sets them at
  17.8pt and usually runs them onto the end of the preceding paragraph, as in
  "...usable by both sorcerers and necromancers.First Circle Spells". The text
  before the marker is the previous spell's, so each block is split at the
  marker rather than assigned whole.
* Group changes are prose, not headings: "usable by both sorcerers and
  necromancers", "available to sorcerers alone", "solely for necromancers".
  As in the core book, the circle cycling back to First is what advances the
  spell type, so the prose only has to confirm the order.
* Body paragraphs can report a larger font size than the body text, because a
  block's size is the largest span in it. Blocks are therefore classified by
  what they contain, not by size alone.

Everything before the first circle marker is a shaping ritual.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from books import add_pdf_argument, open_book
from extract import (ALLCAPS, FOOTER, dedupe_doubled, is_doubled, order_page,
                     page_units, titlecase)

OUT = Path(__file__).resolve().parent.parent / "data" / "sorcery_pillars.raw.json"

FIRST_PAGE, LAST_PAGE = 159, 167

NAME_SIZE = (11.4, 12.7)
HEADING_MIN = 13.0
CIRCLE_RE = re.compile(r"(First|Second|Third)\s*Circle\s*Spells", re.I)
SPELL_TYPES = ["universal", "sorcery", "necromancy"]


def extract(doc):
    entries = []
    circle = None      # None until the first circle marker: rituals come first
    group = -1         # index into SPELL_TYPES
    current = None

    def close():
        nonlocal current
        if current and current["body"]:
            entries.append(current)
        current = None

    for pno in range(FIRST_PAGE - 1, LAST_PAGE):
        for _, _, size, raw in order_page(list(page_units(doc[pno]))):
            if FOOTER.search(raw) or is_doubled(raw):
                continue
            text = dedupe_doubled(raw)

            # An entry name.
            if NAME_SIZE[0] <= size <= NAME_SIZE[1] and ALLCAPS.match(text):
                close()
                current = {
                    "name": titlecase(text),
                    "kind": "spell" if circle else "ritual",
                    "circle": circle,
                    "spelltype": (SPELL_TYPES[group] if circle and 0 <= group < 3
                                  else "universal"),
                    "page": pno,
                    "body": [],
                }
                continue

            # A circle marker, possibly welded to the end of a paragraph.
            match = CIRCLE_RE.search(text) if size >= HEADING_MIN else None
            if match:
                head = text[:match.start()].strip()
                if head and current is not None:
                    current["body"].append(head)   # belongs to the last spell
                close()
                name = match.group(1).lower()
                if name == "first":
                    group += 1
                circle = name
                continue

            if current is not None:
                current["body"].append(text)

    close()
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_pdf_argument(parser, "pillars")
    args = parser.parse_args()
    doc, path = open_book("pillars", args.pdf)
    print("reading: {}".format(path.name))

    entries = extract(doc)
    for entry in entries:
        entry["book"] = "pillars"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(entries, indent=2, ensure_ascii=False),
                   encoding="utf-8")

    rituals = [e for e in entries if e["kind"] == "ritual"]
    spells = [e for e in entries if e["kind"] == "spell"]
    print("entries      : {}".format(len(entries)))
    print("  rituals    : {}".format(len(rituals)))
    print("  spells     : {}".format(len(spells)))
    print("empty body   : {}".format(sum(1 for e in entries if not e["body"])))
    dupes = [n for n, k in Counter(e["name"] for e in entries).items() if k > 1]
    print("duplicates   : {}  {}".format(len(dupes), dupes[:4]))
    print("written to   : {}".format(OUT))
    print()
    print("spells by type and circle:")
    for spelltype in SPELL_TYPES:
        counts = Counter(e["circle"] for e in spells if e["spelltype"] == spelltype)
        print("  {:11s} {:3d}   {}".format(spelltype, sum(counts.values()),
                                           dict(counts)))
    print()
    print("rituals:", ", ".join(e["name"] for e in rituals))


if __name__ == "__main__":
    main()
