"""Extract the general Merits that character creation lists.

    Allies (Any)                  name, then the ratings it may take
    <description>
    Tertiary: <what that rating gives>
    Secondary: ...
    Primary: ...

The core rulebook prints ten. Pillars of Creation adds one in its warstrider
section, headed "New Merit: Warstrider (Primary Only)" over two lines. The
bracket is what marks a heading as a Merit: the same size is used for
"Virtues" and "New Combat Action:", which are not.

Paragraphs are kept, found by their first-line indent, because a Merit's
ratings are separate paragraphs and are hard to read run together. The
Familiar Template sidebar is the stat block the Familiar Merit tells you to
use, so it is kept with that Merit; every other sidebar is dropped.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from books import BOOKS, open_book
from extract import clean
from extract_antagonists import SOFT, join_spans, spans

OUT = Path(__file__).resolve().parent.parent / "data" / "merits.raw.json"

# (book key, first page, last page) - pages 1-indexed, inclusive.
RANGES = [
    ("core", 102, 104),
    ("pillars", 207, 207),
]

HEADING_SIZE = (13.5, 14.3)
BODY_SIZE = (9.7, 10.1)
BODY_FONT = "MercuryTextG2"
# Only a banner this size spans both columns and divides the page. "Step 6:
# Virtues and Intimacies" is a column heading: treating it as a banner reads
# the whole page above it first, which filed Resources' ratings under
# Influence and dropped Influence's own.
PAGE_BANNER_MIN = 24.0
# A section heading, banner or not, ends a Merit.
SECTION_MIN = 17.0
# A line starting this far in from its column's edge starts a paragraph.
INDENT = 12.0

HEADING_RE = re.compile(
    r"^(?:New Merit:\s*)?(?P<name>[^()]+?)\s*"
    r"\((?P<restriction>Any|Cannot be \w+|\w+ Only)\)$", re.I)

# Sidebars worth keeping, by printed title, and the Merit each belongs to.
SIDEBARS = {"FAMILIAR TEMPLATE": "Familiar"}
SIDEBAR_TITLE_FONT = "DIN"
SIDEBAR_FONT = "FuturaPT"


def column_edges(layout):
    """Where each column's lines start, so an indent is measured from it."""
    edges = {}
    for page, size, _, font, column, x0, starts in layout:
        if (starts and BODY_SIZE[0] <= size <= BODY_SIZE[1]
                and font.startswith(BODY_FONT)):
            key = (page, column)
            edges[key] = min(edges.get(key, x0), x0)
    return edges


def entries(doc, book, first, last):
    layout = list(spans(doc, first, last, PAGE_BANNER_MIN, with_layout=True))
    edges = column_edges(layout)
    found, sidebars = [], []
    current, heading, heading_page = None, [], None
    sidebar, previous = None, None

    def close_heading():
        nonlocal current, heading
        if not heading:
            return
        match = HEADING_RE.match(clean(" ".join(heading)))
        heading = []
        if not match:
            # "Virtues", "New Combat Action:" - a heading, but not a Merit's.
            current = None
            return
        current = {
            "name": match.group("name").strip(),
            "book": book,
            "page": heading_page,
            "restriction": match.group("restriction").strip(),
            "paragraphs": [],
        }
        found.append(current)

    for page, size, text, font, column, x0, starts in layout:
        if size >= SECTION_MIN:
            close_heading()
            current = sidebar = None
            continue

        if (HEADING_SIZE[0] <= size <= HEADING_SIZE[1]
                and not font.startswith(SIDEBAR_TITLE_FONT)):
            if not heading:
                heading_page = page
            heading.append(text)
            sidebar = None
            continue
        close_heading()

        if font.startswith(SIDEBAR_TITLE_FONT):
            if sidebar is None or sidebar["lines"]:
                sidebar = {"title": [], "lines": [], "size": None,
                           "book": book, "page": page}
                sidebars.append(sidebar)
            # Sidebar text is set twice, one copy over the other.
            if not sidebar["title"] or sidebar["title"][-1] != text:
                sidebar["title"].append(text)
            previous = None
            continue

        if font.startswith(SIDEBAR_FONT):
            # An untitled aside, such as the running example, is dropped.
            if sidebar is None or text == previous:
                continue
            previous = text
            lines = sidebar["lines"]
            # A stat line starts with a bold label; the note after the stat
            # block is set a size smaller. Either starts a new line of its
            # own, and so does whatever follows a line ending in a colon -
            # unless the line before ended mid-word, as "Ter-" does.
            new_line = starts and (
                not lines or "Bold" in font or size != sidebar["size"]
                or join_spans(lines[-1]).endswith(":")
            ) and not (lines and lines[-1][-1].endswith(SOFT))
            if new_line:
                lines.append([text])
            else:
                lines[-1].append(text)
            if starts:
                sidebar["size"] = size
            continue

        if BODY_SIZE[0] <= size <= BODY_SIZE[1] and font.startswith(BODY_FONT):
            sidebar = None
            if current is None:
                continue
            indented = starts and x0 - edges.get((page, column), x0) >= INDENT
            if indented or not current["paragraphs"]:
                current["paragraphs"].append([])
            # Not clean()ed again: that strips the hyphen marking a word
            # broken across spans, and the builder needs it to rejoin them.
            current["paragraphs"][-1].append(text)
        # Anything else is page furniture: running heads and page numbers.

    close_heading()

    unplaced = []
    for box in sidebars:
        title = clean(" ".join(box["title"])).upper()
        owner = next((e for e in found if e["name"] == SIDEBARS.get(title)),
                     None)
        if owner is None:
            unplaced.append(title)
            continue
        owner["sidebar"] = {"title": title.title(), "lines": box["lines"]}
    return found, unplaced


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("core", "pillars"):
        parser.add_argument("--{}".format(key), help="path to that PDF")
    args = parser.parse_args()

    all_entries = []
    for book, first, last in RANGES:
        if not (getattr(args, book, None) or os.environ.get(BOOKS[book].env_var)):
            print("skipping {}: no PDF supplied".format(book))
            continue
        doc, path = open_book(book, getattr(args, book, None))
        print("reading {}: {}".format(book, path.name))
        found, unplaced = entries(doc, book, first, last)
        print("  merits: {}".format(len(found)))
        if unplaced:
            print("  sidebars dropped: {}".format(", ".join(unplaced)))
        all_entries.extend(found)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(all_entries, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print()
    print("total   : {}".format(len(all_entries)))
    print("written : {}".format(OUT))
    empty = [e["name"] for e in all_entries if not e["paragraphs"]]
    print("no body : {} {}".format(len(empty), empty))
    for entry in all_entries:
        print("  p{:<5} {:14s} {:20s} {} paragraphs{}".format(
            entry["page"], entry["name"][:14], entry["restriction"],
            len(entry["paragraphs"]),
            ", sidebar" if "sidebar" in entry else ""))
    if empty:
        sys.exit("a Merit was extracted with no body")


if __name__ == "__main__":
    main()
