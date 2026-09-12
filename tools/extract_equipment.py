"""Extract the mundane weapons from the equipment chapter.

These are not laid out like artifacts. An example weapon is a single run of
text under a category heading:

    Light Close Combat Weapons          <- the category, and the only place
    Knife: A short blade for cutting,      the statistics come from
    up to a foot in length. Thrown,
    concealable, paired.

So there is no Type line to read: the category comes from the heading above,
which this carries down the page. And the parts of an entry are told apart
by font rather than by size - the name is bold, the description roman, the
tags italic - since all three are set at the same size.

The same chapter defines the equipment tags in the same bold-name shape
before the examples begin, so nothing counts until the first category
heading has been seen.
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

OUT = Path(__file__).resolve().parent.parent / "data" / "equipment.raw.json"

RANGES = [("core", 343, 344)]

HEADING_SIZE = (13.5, 14.4)
BODY_SIZE = (9.5, 10.4)
BANNER_MIN = 19.0

# "Light Close Combat Weapons" -> light, melee. Close combat weapons always
# have the melee tag and ranged weapons the ranged tag, which the chapter
# says outright rather than listing per entry.
HEADING_RE = re.compile(
    r"^(Light|Medium|Heavy)\s+(Close Combat|Ranged)\s+Weapons$", re.I)


def entries(doc, book, first, last):
    found, current = [], None
    category = None

    for page, size, text, font in spans(doc, first, last, BANNER_MIN,
                                        with_font=True):
        plain = text.rstrip("­")
        # A word broken at a real hyphen across two spans - "off-" then
        # "hand" - needs closing up the same way a soft hyphen does.
        if text.endswith("-"):
            text += "­"

        if HEADING_SIZE[0] <= size <= HEADING_SIZE[1]:
            match = HEADING_RE.match(clean(plain))
            if match:
                category = (match.group(1).lower(),
                            "ranged" if match.group(2).lower() == "ranged"
                            else "melee")
            continue

        if category is None or not (BODY_SIZE[0] <= size <= BODY_SIZE[1]):
            continue

        if "Bold" in font and plain.endswith(":"):
            current = {
                "name": clean(plain[:-1]),
                "book": book,
                "page": page,
                "weight": category[0],
                "weapontype": category[1],
                "description": [],
                "tags": [],
            }
            found.append(current)
            continue
        if current is None:
            continue

        # The tags close an entry, and the punctuation between them is set
        # roman while the tags themselves are italic. Collecting only the
        # italic spans loses the commas - and loses the "or" that makes one
        # entry's tags a choice rather than a set. So the first italic span
        # opens the tag clause and everything after it belongs to it.
        if "Italic" in font or current["tags"]:
            current["tags"].append(text)
        else:
            current["description"].append(text)

    for entry in found:
        entry["description"] = clean(join_spans(entry["description"]))
        tags = clean(join_spans(entry["tags"]))
        # The tag clause is one sentence. Without stopping at its full stop,
        # the last entry of a column keeps swallowing whatever is set after
        # it - a sidebar, or the next section's prose.
        stop = tags.find(". ")
        if stop != -1:
            tags = tags[:stop + 1]
        entry["tags"] = tags
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", help="path to that PDF")
    args = parser.parse_args()

    all_entries = []
    for book, first, last in RANGES:
        if not (getattr(args, book, None) or os.environ.get(BOOKS[book].env_var)):
            print("skipping {}: no PDF supplied".format(book))
            continue
        doc, path = open_book(book, getattr(args, book, None))
        print("reading {}: {}".format(book, path.name))
        found = entries(doc, book, first, last)
        print("  weapons: {}".format(len(found)))
        all_entries.extend(found)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(all_entries, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print()
    print("total   : {}".format(len(all_entries)))
    print("written : {}".format(OUT))
    print("no tags : {}".format(sum(1 for e in all_entries if not e["tags"])))
    print("alternatives (\"or\" in the tags): {}".format(
        sum(1 for e in all_entries if " or " in e["tags"])))
    print()
    for entry in all_entries:
        print("  {:30s} {:6s} {:6s} {}".format(
            entry["name"][:28], entry["weight"], entry["weapontype"],
            entry["tags"][:44]))


if __name__ == "__main__":
    main()
