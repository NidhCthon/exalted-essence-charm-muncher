"""Extract hearthstones, which both books set the same way.

    The Freedom Stone              set larger than the body
    (Water, Greater Hearthstone)   aspect and rating, in brackets
    <description>
    Manse attributes: <what the manse is like>
    <what the stone does>

A hearthstone has no category or tag line the way an artifact does, and
nothing numeric at all. What it does have is an aspect and a rating, both in
that bracketed line, and those are what distinguish one from another.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from books import BOOKS, open_book
from extract import clean
from extract_antagonists import join_spans, spans

OUT = Path(__file__).resolve().parent.parent / "data" / "hearthstones.raw.json"

# (book key, first page, last page) - 1-indexed, inclusive.
RANGES = [
    ("core", 353, 354),
    ("pillars", 200, 201),
]

NAME_SIZE = (17.0, 18.4)
SUBTITLE_SIZE = (11.5, 12.3)
BODY_SIZE = (9.5, 10.4)
# Only the chapter banner divides these pages; a name must not.
BANNER_MIN = 24.0

# "(Water, Greater Hearthstone)" - aspect first, rating second.
SUBTITLE_RE = re.compile(
    r"\(\s*([^,]+?)\s*,\s*(\w+)\s+Hearthstone\s*\)", re.I)


def entries(doc, book, first, last):
    found, current, pending = [], None, []

    def flush(page):
        nonlocal current, pending
        if not pending:
            return
        name = clean(join_spans(pending))
        pending = []
        if len(name) < 4:
            return
        current = {
            "name": name,
            "book": book,
            "page": page,
            "aspect": "",
            "rating": "",
            "subtitle": "",
            "body": [],
        }
        found.append(current)

    for page, size, text in spans(doc, first, last, BANNER_MIN):
        if NAME_SIZE[0] <= size <= NAME_SIZE[1]:
            pending.append(text)
            continue
        flush(page)
        if current is None:
            continue

        if SUBTITLE_SIZE[0] <= size <= SUBTITLE_SIZE[1]:
            current["subtitle"] = clean(text)
            match = SUBTITLE_RE.search(current["subtitle"])
            if match:
                current["aspect"] = match.group(1).strip()
                current["rating"] = match.group(2).strip().title()
        elif BODY_SIZE[0] <= size <= BODY_SIZE[1]:
            # Not clean()ed again: that strips the hyphen marking a word
            # broken across spans, and the builder needs it to rejoin them.
            current["body"].append(text)

    flush(last)
    # The chapter's own introduction picks up no bracketed line, so the
    # subtitle is what separates a hearthstone from the prose around it.
    return [e for e in found if e["subtitle"]]


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
        found = entries(doc, book, first, last)
        print("  hearthstones: {}".format(len(found)))
        all_entries.extend(found)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(all_entries, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print()
    print("total   : {}".format(len(all_entries)))
    print("written : {}".format(OUT))
    missing = [e["name"] for e in all_entries if not e["aspect"]]
    print("no aspect parsed: {} {}".format(len(missing), missing[:3]))
    for entry in all_entries[:10]:
        print("  p{:<5} {:34s} {:12s} {}".format(
            entry["page"], entry["name"][:32], entry["rating"],
            entry["aspect"]))


if __name__ == "__main__":
    main()
