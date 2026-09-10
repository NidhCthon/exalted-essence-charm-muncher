"""Extract Exalted Essence spells and shaping rituals from the core rulebook.

Sorcery entries look like charms - 12pt all-caps names in the same two-column
layout - but carry no "Prerequisite:" line, which is precisely why the charm
extractor skips them. They need their own pass, and they map to the system's
`spell` and `ritual` item types rather than `charm`.

Structure of the chapter:

    SORCERY AND NECROMANCY          (30pt banner, p300)
      <shaping rituals>             (12pt names, no circle heading yet)
      First Circle Spells           (13.9pt)   -> universal spells
      Second Circle Spells
      Third Circle Spells
      First Circle Spells           (cycle restarts) -> sorcery spells
      ...
      First Circle Spells           (cycle restarts) -> necromancy spells
      ...
    SORCEROUS WORKINGS              (30pt banner, p311 - stop here)

The circle heading cycling back to "First" is the only marker separating the
three spell groups, so that reset is what advances the spell type.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pymupdf

from books import add_pdf_argument, open_book
from extract import (ALLCAPS, FOOTER, XREF, clean, dedupe_doubled,
                     is_doubled, order_page, page_units, titlecase)

OUT = Path(__file__).resolve().parent.parent / "data" / "sorcery.raw.json"

FIRST_PAGE, LAST_PAGE = 300, 310  # 1-indexed inclusive; p311 starts Workings

NAME_SIZE = (11.5, 12.6)
CIRCLE_SIZE = (13.5, 14.5)
BANNER_SIZE = 18.0
CIRCLE_RE = re.compile(r"^(First|Second|Third) Circle Spells", re.I)
SPELL_TYPES = ["universal", "sorcery", "necromancy"]
WILL_RE = re.compile(r"\bSpend\s+(\d+)\s+Will\b", re.I)


def extract(doc):
    entries = []
    circle = None          # None until the first circle heading -> rituals
    group = -1             # index into SPELL_TYPES
    current = None

    def close():
        if current and current["body"]:
            entries.append(current)

    for pno in range(FIRST_PAGE - 1, LAST_PAGE):
        units = order_page(list(page_units(doc[pno])))
        for _, _, size, text in units:
            if FOOTER.search(text) or is_doubled(text):
                continue
            if size >= BANNER_SIZE:
                continue
            if CIRCLE_SIZE[0] <= size <= CIRCLE_SIZE[1]:
                match = CIRCLE_RE.match(text)
                if match:
                    name = match.group(1).lower()
                    if name == "first":
                        group += 1     # the cycle restarting means a new type
                    close()
                    current = None
                    circle = name
                continue
            if NAME_SIZE[0] <= size <= NAME_SIZE[1] and ALLCAPS.match(text):
                close()
                current = {
                    "name": titlecase(dedupe_doubled(text)),
                    "kind": "spell" if circle else "ritual",
                    "circle": circle,
                    "spelltype": SPELL_TYPES[group] if circle and 0 <= group < 3
                                 else "universal",
                    "page": pno,
                    "body": [],
                }
                continue
            if current is not None:
                if XREF.match(text):
                    current = None     # a cross-reference, not a real entry
                    continue
                current["body"].append(text)
    close()
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_pdf_argument(parser, "core")
    args = parser.parse_args()
    doc, path = open_book("core", args.pdf)
    print("reading: {}".format(path.name))
    entries = extract(doc)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(entries, indent=2, ensure_ascii=False),
                   encoding="utf-8")

    rituals = [e for e in entries if e["kind"] == "ritual"]
    spells = [e for e in entries if e["kind"] == "spell"]
    print("entries      : {}".format(len(entries)))
    print("  rituals    : {}".format(len(rituals)))
    print("  spells     : {}".format(len(spells)))
    print("written to   : {}".format(OUT))
    print("empty body   : {}".format(sum(1 for e in entries if not e["body"])))
    dupes = [n for n, k in Counter(e["name"] for e in entries).items() if k > 1]
    print("duplicates   : {}  {}".format(len(dupes), dupes[:4]))
    print()
    print("spells by type and circle:")
    for spelltype in SPELL_TYPES:
        counts = Counter(e["circle"] for e in spells if e["spelltype"] == spelltype)
        total = sum(counts.values())
        print("  {:11s} {:3d}   {}".format(spelltype, total, dict(counts)))
    costed = sum(1 for e in spells if WILL_RE.search(" ".join(e["body"])))
    print()
    print("spells with a parsable Will cost: {}/{}".format(costed, len(spells)))
    print()
    print("rituals:", ", ".join(e["name"] for e in rituals))


if __name__ == "__main__":
    main()
