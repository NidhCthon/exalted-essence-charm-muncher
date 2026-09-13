"""Check imported antagonist stats against what the books actually print.

The weak version of this check - "is each imported number somewhere on the
page the name was found on?" - is what let a real bug through once already. It
fails in both directions: a stat block that continues onto the next page looks
like invented numbers, and a sidebar boxed out beside the antagonist supplies
numbers that are on the page but belong to something else.

So this checks four sharper things instead:

* MERGED    two stat blocks run together, which shows up as the same label
            appearing twice in one stat line with different numbers. This is
            the signature of a missed name.
* UNSOURCED an imported number that appears nowhere on any page the entry's
            stat line actually touches. Nothing can legitimately produce one.
* SIZE      Size on an entry that is not a battle group. Size is printed by
            battle groups, so on anyone else it came from somewhere it
            should not have.
* INCOMPLETE pools imported but no defensive stats. Wrong numbers are the
            danger and missing ones are merely useless, but they look
            identical on a character sheet.

Exit codes: 0 clean, 1 something to look at.
"""
import os
import re
import sys
from collections import defaultdict

from books import BOOKS, open_book
from extract_antagonists import (DRILL_WORD_RE, DRILL_WORDS, NUM_RE,
                                 QUALITIES_RE, RANGES, WEAPON_RE, extract,
                                 join_spans, stat_block_of)


def printed_on(doc, pages):
    """Every (label, number) pair the book prints on those pages.

    The two labels the extractor normalises have to be normalised here too,
    or a correct import looks unsourced: a page printing "Health: 10" is the
    source of a health levels of 10, and one printing "Drill: Regular" is the
    source of that drill's modifier.
    """
    found = set()
    for page in pages:
        text = doc[page - 1].get_text()
        for match in NUM_RE.finditer(text):
            label, value = match.group(1).lower(), int(match.group(2))
            found.add((label, value))
            if label == "health":
                found.add(("health levels", value))
        for match in DRILL_WORD_RE.finditer(text):
            word = match.group(1).lower()
            if word in DRILL_WORDS:
                found.add(("drill", DRILL_WORDS[word]))
    return found


def stat_block_only(statline):
    """The stat line up to where the prose starts.

    This is the extractor's own boundary, imported rather than restated: a
    check that draws the line somewhere else reports noise, or misses what it
    was meant to catch.
    """
    return stat_block_of(join_spans([span for _, span in statline]))


def merged_labels(statline):
    """Labels the stat block gives more than one value for."""
    seen = defaultdict(set)
    for match in NUM_RE.finditer(stat_block_only(statline)):
        seen[match.group(1).lower()].add(int(match.group(2)))
    return {label: values for label, values in seen.items() if len(values) > 1}


def main():
    problems = 0
    checked = 0

    for book, first, last, profile in RANGES:
        # Books are optional, as they are everywhere else in this pipeline.
        if not os.environ.get(BOOKS[book].env_var):
            print("skipping {}: no PDF supplied".format(book))
            continue
        doc, path = open_book(book, None)
        print("checking {}: {}".format(book, path.name))

        for entry in extract(doc, book, first, last, profile):
            checked += 1
            name = entry["name"][:44]
            statline = entry["statline"]
            pages = sorted({page for page, _ in statline}) or [entry["page"]]

            merged = merged_labels(statline)
            if merged:
                problems += 1
                print("  MERGED    {:46s} p{}".format(name, pages))
                for label, values in sorted(merged.items()):
                    print("              {} printed as {}".format(
                        label, sorted(values)))

            available = printed_on(doc, pages)
            unsourced = [(label, value) for label, value in entry["stats"].items()
                         if (label, value) not in available]
            if unsourced:
                problems += 1
                print("  UNSOURCED {:46s} p{}".format(name, pages))
                print("              {} on none of those pages".format(
                    sorted(unsourced)))

            # A battle group prints Size and Drill together, so Size beside a
            # Drill line is its own, not borrowed.
            printed = stat_block_only(statline).lower()
            if "size" in entry["stats"] and "drill" not in printed:
                problems += 1
                print("  SIZE      {:46s} p{}  size {}".format(
                    name, pages, entry["stats"]["size"]))

            # Wrong numbers are the danger; missing ones are merely useless,
            # but they look identical on a character sheet, so say so.
            if entry["pools"] and "defense" not in entry["stats"]:
                problems += 1
                print("  INCOMPLETE {:45s} p{}  pools but no defensive stats"
                      .format(name, pages))

            if len(pages) > profile.max_pages:
                problems += 1
                print("  SPREAD    {:46s} p{}".format(name, pages))

    print()
    print("entries checked : {}".format(checked))
    print("problems        : {}".format(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
