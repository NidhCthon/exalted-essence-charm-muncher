"""Extract warstriders, which are artifacts shaped unlike the others.

A warstrider has no "Type:" line, because it is neither a weapon nor a suit
of armour in the ordinary sense - it is a machine you climb into, added by
Pillars of Creation as a Merit. What it has instead is a chassis and a list
of built-in weapons:

    <name>
    <material> Warstrider
    <description>
    <weight> Chassis: <n> Defense, <n> Soak, <n> Hardness, <n> Health Levels
    <weapon name>: <n> Accuracy, <n> Damage, <n> Overwhelming. <tag>, <tag>
    <weapon name>: ...
    Hearthstone slots: <n>

So the chassis becomes the armour and each built-in weapon its own weapon,
with every number read from the page rather than derived.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from books import BOOKS, open_book
from build_artifacts import WEAPON_TAGS, tag_key
from extract import clean
from extract_antagonists import join_spans, spans

OUT = Path(__file__).resolve().parent.parent / "data" / "warstriders.raw.json"

RANGES = [("pillars", 207, 211)]

NAME_SIZE = (13.5, 14.4)
BODY_SIZE = (9.5, 10.4)
BANNER_MIN = 17.0

CHASSIS_RE = re.compile(
    r"(Light|Medium|Heavy)\s+Chassis\s*:\s*(.+?)(?=Hearthstone|$)", re.I)
STAT_RE = re.compile(
    r"(\d+)\s*(Defense|Defence|Soak|Hardness|Health Levels)", re.I)
SLOTS_RE = re.compile(r"Hearthstone\s+slots?\s*:\s*(\d+)", re.I)
# "<weapon name>: <n> Accuracy, <n> Damage, <n> Overwhelming. <tags>".
# Only the name and its colon are matched here; where one weapon ends is
# where the next one's name begins, because a greedy tag list otherwise eats
# the name after it and a greedy name eats the stat line before it.
BUILTIN_RE = re.compile(r"([A-Z][A-Za-z'\- ]{2,40}?)\s*:\s*(?=[+-]?\s*\d)")
# The chassis line always ends on Health Levels, and the weapons follow.
# Cutting after the last stat instead loses every weapon on a machine
# whose weapon grants Defense, because that reads as a chassis stat too.
HEALTH_RE = re.compile(r"\d+\s*Health\s+Levels", re.I)


def strip_leading_tags(name):
    """Split a name into the tags in front of it and the name itself.

    One weapon's tag list runs straight into the next weapon's name -
    "Ranged Feathersteel Crossbows" is the ranged tag and then a crossbow -
    and only the tag vocabulary can tell which words are which. The tags
    belong to the weapon before, so they are handed back rather than dropped:
    otherwise a ballista that shoots is filed as a melee weapon.
    """
    words = name.strip(" .,").split()
    taken = []
    while len(words) > 1 and tag_key(words[0]) in WEAPON_TAGS:
        taken.append(words.pop(0))
    return taken, " ".join(words)


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
        current = {"name": name, "book": book, "page": page,
                   "form": "", "body": []}
        found.append(current)

    for page, size, text in spans(doc, first, last, BANNER_MIN):
        if NAME_SIZE[0] <= size <= NAME_SIZE[1]:
            pending.append(text)
            continue
        flush(page)
        if current is None or not (BODY_SIZE[0] <= size <= BODY_SIZE[1]):
            continue
        if not current["form"]:
            current["form"] = clean(text)
        else:
            current["body"].append(text)

    flush(last)

    kept = []
    for entry in found:
        blob = clean(join_spans(entry["body"]))
        chassis = CHASSIS_RE.search(blob)
        if not chassis:
            # The section's own rules text has a name and prose but no
            # chassis; only a machine has one.
            continue
        entry["weight"] = chassis.group(1).lower()
        entry["chassis"] = {}
        for stat in STAT_RE.finditer(chassis.group(2)):
            entry["chassis"][stat.group(2).lower().replace("defence", "defense")] = \
                int(stat.group(1))
        slots = SLOTS_RE.search(blob)
        entry["slots"] = slots.group(1) if slots else ""
        # The chassis line states the machine's own numbers and ends on its
        # Health Levels; the weapons follow. Without cutting there, "Health
        # Levels" becomes part of the first weapon's name.
        health = HEALTH_RE.search(chassis.group(2))
        rest = chassis.group(2)[health.end():] if health else chassis.group(2)

        starts = []
        for match in BUILTIN_RE.finditer(rest):
            taken, name = strip_leading_tags(match.group(1))
            starts.append((match.start(), name, taken))

        entry["weapons"] = []
        for index, (start, name, taken) in enumerate(starts):
            stop = starts[index + 1][0] if index + 1 < len(starts) else len(rest)
            printed = rest[start:stop].strip(" .,")
            if index + 1 < len(starts):
                # Give the next name's leading tags back to this weapon.
                printed = "{}, {}".format(
                    printed.rstrip(" ,."), ", ".join(starts[index + 1][2]))
            entry["weapons"].append({"name": name,
                                     "printed": printed.strip(" .,")})
        entry["description"] = blob
        del entry["body"]
        kept.append(entry)
    return kept


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pillars", help="path to that PDF")
    args = parser.parse_args()

    all_entries = []
    for book, first, last in RANGES:
        if not (getattr(args, book, None) or os.environ.get(BOOKS[book].env_var)):
            print("skipping {}: no PDF supplied".format(book))
            continue
        doc, path = open_book(book, getattr(args, book, None))
        print("reading {}: {}".format(book, path.name))
        found = entries(doc, book, first, last)
        print("  warstriders: {}".format(len(found)))
        all_entries.extend(found)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(all_entries, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print()
    print("total   : {}".format(len(all_entries)))
    for entry in all_entries:
        print("  {:36s} {:7s} {} slots {}".format(
            entry["name"][:34], entry["weight"], entry["chassis"],
            entry["slots"]))
        for weapon in entry["weapons"]:
            print("      {}".format(weapon["printed"][:96]))


if __name__ == "__main__":
    main()
