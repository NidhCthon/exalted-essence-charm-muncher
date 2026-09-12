"""Extract charms from the Exalted Essence Player's Guide (draft manuscript).

The manuscript is a different animal from the published books: single column,
US Letter, and a clean type hierarchy rather than a designed layout.

    20pt  chapter title
    16pt  ability grouping (Athletics, Awareness, ...)
    14pt  charm name, Title Case rather than all-caps
    11pt  prerequisite line and body

The charm rule is the same as the core book's - a name followed by a
"Prerequisite:" line - just at a different size. Blocks are streamed
continuously across pages rather than page by page, because 31 charms have
their name at the foot of one page and their prerequisite at the head of the
next; iterating per page silently drops every one of them.

CHAPTERS maps page ranges to the system's charmtype. Ranges are used rather
than parsed chapter headings because several body paragraphs in the manuscript
are mis-styled at 20pt, and the Infernal chapter has no chapter heading at all.

This is a DRAFT manuscript. Its charms may differ from the published book.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pymupdf

from books import add_pdf_argument, open_book
from extract import PREREQ, clean

OUT = Path(__file__).resolve().parent.parent / "data" / "playersguide.raw.json"

INLINE_PREREQ = re.compile(r"^(.{3,80}?)\s+(Prerequisites?:.*)$", re.S)
NAME_SIZE = 14.0
GROUP_SIZE = 16.0
TOLERANCE = 0.15

# (first_page, last_page, section label) - 1-indexed, inclusive.
CHAPTERS = [
    (10, 45, "Dragon-Blooded Charms"),
    (46, 75, "Lunar Charms"),
    (76, 112, "Sidereal Charms"),
    (113, 145, "Solar Charms"),
    (146, 170, "Exigent Charms"),
    (171, 182, "Architect Charms"),
    (183, 197, "Sovereign Charms"),
    (198, 237, "Abyssal Charms"),
    (238, 273, "Alchemical Charms"),
    (274, 308, "Getimian Charms"),
    (309, 342, "Infernal Charms"),
    (343, 374, "Liminal Charms"),
]


def section_for(page):
    for first, last, label in CHAPTERS:
        if first <= page <= last:
            return label
    return None


def stream_blocks(doc):
    """Continuous [(size, text, page)] across the whole manuscript."""
    stream = []
    for pno in range(doc.page_count):
        for blk in doc[pno].get_text("dict")["blocks"]:
            if blk.get("type") != 0:
                continue
            size, parts = 0.0, []
            for line in blk.get("lines", []):
                for span in line.get("spans", []):
                    size = max(size, round(span["size"], 1))
                    parts.append(span["text"])
            text = clean("".join(parts))
            if text:
                stream.append((size, text, pno + 1))
    return stream


def extract(doc):
    stream = stream_blocks(doc)
    charms, group, i = [], None, 0
    while i < len(stream):
        size, text, page = stream[i]
        if abs(size - GROUP_SIZE) < TOLERANCE:
            group = text
            i += 1
            continue
        if abs(size - NAME_SIZE) < TOLERANCE and i + 1 < len(stream):
            # The manuscript is inconsistent: most chapters put the name and
            # the prerequisite in separate blocks, but the Dragon-Blooded,
            # Abyssal, Getimian and Liminal chapters run them together into a
            # single 14pt block (the name and its prerequisites run together).
            inline = INLINE_PREREQ.match(text)
            if inline:
                name, match, offset = inline.group(1).strip(), PREREQ.match(
                    inline.group(2)), 1
            else:
                name, match, offset = text, PREREQ.match(stream[i + 1][1]), 2
            if match:
                body, j = [], i + offset
                while j < len(stream):
                    body_size, body_text, _ = stream[j]
                    if abs(body_size - NAME_SIZE) < TOLERANCE or body_size >= GROUP_SIZE:
                        break
                    body.append(body_text)
                    j += 1
                section = section_for(page)
                if section:
                    charms.append({
                        "name": name,
                        "section": section,
                        "group": group,
                        "page": page,
                        "prerequisite": match.group(1).strip(),
                        "body": body,
                        "book": "playersguide",
                    })
                i = j
                continue
        i += 1
    return charms


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_pdf_argument(parser, "playersguide")
    args = parser.parse_args()
    doc, path = open_book("playersguide", args.pdf)
    print("reading: {}".format(path.name))
    charms = extract(doc)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(charms, indent=2, ensure_ascii=False),
                   encoding="utf-8")

    print("charms extracted : {}".format(len(charms)))
    print("empty body       : {}".format(sum(1 for c in charms if not c["body"])))
    print("no section       : {}".format(sum(1 for c in charms if not c["section"])))
    dupes = [n for n, k in Counter(c["name"] for c in charms).items() if k > 1]
    print("duplicate names  : {}  {}".format(len(dupes), dupes[:6]))
    print("written to       : {}".format(OUT))
    print()
    print("sections:")
    for name, count in Counter(c["section"] for c in charms).items():
        print("  {:4d}  {}".format(count, name))


if __name__ == "__main__":
    main()
