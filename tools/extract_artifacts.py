"""Extract artifacts - the weapons and armour of the artifact chapters.

Each entry is regular enough to read by its labels:

    <name>                        set larger than the body
    <material and form>           the first body line under the name
    <description>
    Type: Heavy Melee Weapon
    Tags: Artifact, Melee, Reaching, Two-Handed
    Hearthstone slots: 2
    <what the artifact does>

What an artifact does *not* print is its Accuracy, Damage, Defense and
Overwhelming. Those come from the category on the Type line, plus one for
being an artifact, under the rules in the equipment chapter. The builder
derives them; this only records what the page says.

Hearthstones are set in the same chapters but carry no Type or Tags line -
they are a different kind of thing and are not read here.
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

OUT = Path(__file__).resolve().parent.parent / "data" / "artifacts.raw.json"

# (book key, first page, last page) - 1-indexed, inclusive.
RANGES = [
    ("core", 347, 351),
    ("pillars", 202, 206),
]

NAME_SIZE = (13.5, 14.4)
BODY_SIZE = (9.5, 10.4)
# The "Greater Wonders" heading is set at the size an antagonist's name uses,
# but it does not divide the page the way a chapter banner does. Treating it
# as one reorders the columns around it and files an artifact's stat line
# under the name above it.
BANNER_MIN = 19.0

TYPE_RE = re.compile(r"^Type\s*:\s*(.*)$", re.I)
TAGS_RE = re.compile(r"^Tags\s*:\s*(.*)$", re.I)
SLOTS_RE = re.compile(r"^Hearthstone\s+slots?\s*:\s*(.*)$", re.I)
LABEL_RE = re.compile(r"^(Type|Tags|Hearthstone\s+slots?)\s*:\s*$", re.I)
# "Volcano Cutter (Primary)" marks which book line an artifact belongs to,
# not part of its name.
SUFFIX_RE = re.compile(r"\s*\((?:Primary|Primary Only)\)\s*$", re.I)


def entries(doc, book, first, last):
    """Split the pages into artifacts, one per name."""
    found, current, pending = [], None, []

    def flush(page):
        nonlocal current, pending
        if not pending:
            return
        name = SUFFIX_RE.sub("", clean(join_spans(pending))).strip()
        pending = []
        if len(name) < 4:
            return
        current = {
            "name": name,
            "book": book,
            "page": page,
            "form": "",
            "type": "",
            "tags": "",
            "slots": "",
            "body": [],
        }
        found.append(current)

    label = None
    for page, size, text in spans(doc, first, last, BANNER_MIN):
        if NAME_SIZE[0] <= size <= NAME_SIZE[1]:
            pending.append(text)
            continue
        flush(page)
        if current is None or not (BODY_SIZE[0] <= size <= BODY_SIZE[1]):
            continue

        # A label and its value are often separate spans.
        if label:
            current[label] = clean(text)
            label = None
            continue
        bare = LABEL_RE.match(text)
        if bare:
            word = bare.group(1).lower()
            label = "slots" if word.startswith("hearthstone") else word
            continue

        for pattern, field in ((TYPE_RE, "type"), (TAGS_RE, "tags"),
                               (SLOTS_RE, "slots")):
            match = pattern.match(text)
            if match:
                current[field] = clean(match.group(1))
                break
        else:
            if not current["form"]:
                current["form"] = clean(text)
            else:
                current["body"].append(clean(text))

    flush(last)
    # An artifact is an entry with a Type line. Anything else on these pages
    # is a sidebar, a heading, or the chapter's prose.
    return [e for e in found if e["type"]]


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
        print("  artifacts: {}".format(len(found)))
        all_entries.extend(found)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(all_entries, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print()
    print("total    : {}".format(len(all_entries)))
    print("written  : {}".format(OUT))
    for entry in all_entries:
        print("  p{:<5} {:34s} {:26s} {}".format(
            entry["page"], entry["name"][:32], entry["type"][:24],
            entry["tags"][:40]))


if __name__ == "__main__":
    main()
