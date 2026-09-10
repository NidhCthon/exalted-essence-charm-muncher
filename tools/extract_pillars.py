"""Extract charms from Exalted Essence: Pillars of Creation.

Pillars uses the same page geometry and type scale as the core rulebook, so it
reuses the core extractor wholesale - only the page range and the section
names differ. It adds six Exalt types the core book does not cover (Exigent,
Architect, Sovereign, Dragon King, Dream-Souled, Umbral), all of which already
exist in the system's CharmTypes enum.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pymupdf

from books import add_pdf_argument, open_book
from extract import build_stream, segment

OUT = Path(__file__).resolve().parent.parent / "data" / "pillars.raw.json"

FIRST_PAGE, LAST_PAGE = 51, 213

# Two banners need repair before they can be matched. "SOVEREIGNS OF ULUIRU"
# and "CHARMS" are set as separate lines, so the section arrives as bare
# "Charms"; and the Martial Arts banner is doubled with its subtitle run
# together. Both are keyed on what the extractor actually produces.
SECTION_FIXES = {
    "Charms": "Sovereign Charms",
    "Martial Arts: Martial Arts: Scattered Lotus Petalsscattered Lotus Petals":
        "Martial Arts: Scattered Lotus Petals",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_pdf_argument(parser, "pillars")
    args = parser.parse_args()
    doc, path = open_book("pillars", args.pdf)
    print("reading: {}".format(path.name))
    charms = segment(build_stream(doc, FIRST_PAGE, LAST_PAGE))
    for charm in charms:
        charm["section"] = SECTION_FIXES.get(charm["section"], charm["section"])
        charm["book"] = "pillars"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(charms, indent=2, ensure_ascii=False),
                   encoding="utf-8")

    print("charms extracted : {}".format(len(charms)))
    print("empty body       : {}".format(sum(1 for c in charms if not c["body"])))
    print("no section       : {}".format(sum(1 for c in charms if not c["section"])))
    dupes = [n for n, k in Counter(c["name"] for c in charms).items() if k > 1]
    print("duplicate names  : {}  {}".format(len(dupes), dupes[:5]))
    print("written to       : {}".format(OUT))
    print()
    print("sections:")
    for name, count in Counter(c["section"] for c in charms).items():
        print("  {:4d}  {}".format(count, name))


if __name__ == "__main__":
    main()
