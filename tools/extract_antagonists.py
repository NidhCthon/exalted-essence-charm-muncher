"""Extract antagonist stat blocks from the published Essence books.

Antagonists are Actors, not Items, and their blocks are laid out unlike
anything the charm extractor handles:

* An antagonist's name is a 17.8pt span welded onto the end of the previous
  paragraph - "Weapon: Soulsteel Goremaul (...).Champion" - and a long name
  wraps across several spans. Working at block level buries every name, so
  this reads spans and joins consecutive large ones.
* Stat lines run together without separators: "Health Levels: 5Resolve:
  3Defense: 5Hardness: 3Soak: 3". They are split on the known label set
  instead of on punctuation.
* "Variant:" entries are deltas on the parent ("increase pools by two"), not
  stat blocks. Each is kept as text on its parent rather than invented as a
  separate actor, because applying prose adjustments is guesswork.

Covers the core rulebook and Pillars of Creation, which share a type scale.
The Storyteller's Guide draft is set differently and is handled separately.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from books import BOOKS, open_book
from extract import clean, dedupe_doubled

OUT = Path(__file__).resolve().parent.parent / "data" / "antagonists.raw.json"

# (book key, first page, last page) - 1-indexed, inclusive.
RANGES = [
    ("core", 316, 341),
    ("pillars", 168, 199),
]

NAME_SIZE = (17.0, 18.4)
STAT_SIZE = (10.6, 11.2)
VARIANT_SIZE = (13.5, 14.3)

# A stat is a label followed by a number. The same words appear in the
# qualities prose - "reduces Defense by one" - so matching a bare label lets
# prose overwrite the real value. Numbers are required, and the first match
# wins, because the stat line always precedes the prose.
NUM_LABELS = ("Health Levels", "Resolve", "Defense", "Defence", "Hardness",
              "Soak", "Essence", "Size", "Drill", "Command")
NUM_RE = re.compile(r"\b(" + "|".join(NUM_LABELS) + r")\s*:?\s*(\d+)", re.I)
POOL_RE = re.compile(
    r"\b(Primary|Secondary|Tertiary)\s+Pool\s*\((\d+)\)\s*:?\s*", re.I)
QUALITIES_RE = re.compile(r"\b(ATTACKS AND QUALITIES|QUALITIES|ATTACKS)\b")
WEAPON_RE = re.compile(r"\bWeapon\s*:\s*", re.I)
FOOTER_RE = re.compile(r"CHAPTER [A-Z]+:|Mortals and Exalted|Gods and Monsters"
                       r"|Exalted Antagonists|Strange Beasts", re.I)


def spans(doc, first, last):
    """Every span in reading order: left column, then right, then next page."""
    for pno in range(first - 1, last):
        page = doc[pno]
        mid = page.rect.width / 2
        blocks = []
        for blk in page.get_text("dict")["blocks"]:
            if blk.get("type") != 0:
                continue
            x0, y0, x1, _ = blk["bbox"]
            blocks.append((0 if (x0 + x1) / 2 < mid else 1, y0, blk))
        blocks.sort(key=lambda b: (b[0], round(b[1], 1)))
        for _, _, blk in blocks:
            for line in blk.get("lines", []):
                for sp in line.get("spans", []):
                    text = clean(sp["text"])
                    if text:
                        yield pno + 1, round(sp["size"], 1), text


def parse_stats(text):
    """Split a run-together stat line into numbers, pools and prose."""
    stats, pools = {}, {}

    for match in NUM_RE.finditer(text):
        label = match.group(1).lower()
        if label not in stats:            # first occurrence is the stat block
            stats[label] = int(match.group(2))

    # A pool's actions run until the next pool, the next stat, or the
    # qualities heading - whichever comes first.
    pool_matches = list(POOL_RE.finditer(text))
    stops = [m.start() for m in NUM_RE.finditer(text)]
    stops += [m.start() for m in QUALITIES_RE.finditer(text)]
    for i, match in enumerate(pool_matches):
        after = match.end()
        candidates = [m.start() for m in pool_matches[i + 1:]]
        candidates += [x for x in stops if x >= after]
        end = min(candidates) if candidates else len(text)
        pools[match.group(1).lower()] = {
            "value": int(match.group(2)),
            "actions": text[after:end].strip(" .,;:"),
        }

    qualities = ""
    qmatch = QUALITIES_RE.search(text)
    if qmatch:
        qualities = text[qmatch.end():].strip(" .,;:")

    weapon = ""
    wmatch = WEAPON_RE.search(text)
    if wmatch:
        weapon = text[wmatch.end():].strip()
        if qmatch and wmatch.start() > qmatch.end():
            qualities = text[qmatch.end():wmatch.start()].strip(" .,;:")

    return stats, pools, qualities, weapon


def extract(doc, book, first, last):
    entries = []
    current = None
    pending_name = []

    def flush_name(page):
        nonlocal current, pending_name
        if not pending_name:
            return
        name = clean(" ".join(pending_name))
        pending_name = []
        if len(name) < 3 or FOOTER_RE.search(name):
            return
        current = {
            "name": dedupe_doubled(name),
            "book": book,
            "page": page,
            "stats": {},
            "pools": {},
            "statline": [],
            "body": [],
            "variants": [],
        }
        entries.append(current)

    for page, size, text in spans(doc, first, last):
        if FOOTER_RE.search(text) and size < NAME_SIZE[0]:
            continue

        if NAME_SIZE[0] <= size <= NAME_SIZE[1]:
            pending_name.append(text)
            continue
        # Pillars names its sub-entries at the size the core book uses for
        # "Variant:", so the leading word is what separates them.
        if (VARIANT_SIZE[0] <= size <= VARIANT_SIZE[1]
                and not text.lower().startswith("variant")):
            pending_name.append(text)
            continue
        flush_name(page)

        if current is None:
            continue

        if STAT_SIZE[0] <= size <= STAT_SIZE[1]:
            current["statline"].append(text)
        elif VARIANT_SIZE[0] <= size <= VARIANT_SIZE[1] and text.lower().startswith("variant"):
            current["variants"].append({"name": text, "notes": []})
        elif current["variants"]:
            current["variants"][-1]["notes"].append(text)
        else:
            current["body"].append(text)

    flush_name(last)

    for entry in entries:
        stats, pools, qualities, weapon = parse_stats(" ".join(entry.pop("statline")))
        entry["stats"] = stats
        entry["pools"] = pools
        entry["qualities"] = qualities
        entry["weapon"] = weapon

    def is_antagonist(entry):
        if entry["pools"].get("primary", {}).get("value", 0) > 0:
            return True
        return "defense" in entry["stats"] and "soak" in entry["stats"]

    return [e for e in entries if is_antagonist(e)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("core", "pillars"):
        parser.add_argument("--{}".format(key), help="path to that PDF")
    args = parser.parse_args()

    all_entries = []
    for book, first, last in RANGES:
        doc, path = open_book(book, getattr(args, book, None))
        print("reading {}: {}".format(book, path.name))
        found = extract(doc, book, first, last)
        print("  entries: {}".format(len(found)))
        all_entries.extend(found)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(all_entries, indent=2, ensure_ascii=False),
                   encoding="utf-8")

    print()
    print("total          : {}".format(len(all_entries)))
    print("written to     : {}".format(OUT))
    withpools = [e for e in all_entries if e["pools"].get("primary")]
    print("with a primary pool : {}".format(len(withpools)))
    print("no stats at all     : {}".format(
        sum(1 for e in all_entries if not e["stats"] and not e["pools"])))
    print("with variants       : {}".format(
        sum(1 for e in all_entries if e["variants"])))
    print()
    print("stat labels seen:")
    labels = Counter(k for e in all_entries for k in e["stats"])
    for k, n in labels.most_common():
        print("  {:24s} {}".format(k, n))
    print()
    print("first 12 names:")
    for e in all_entries[:12]:
        pools = e["pools"].get("primary", {}).get("value", "-")
        print("  p{:<4} pool {:<3} {}".format(e["page"], pools, e["name"][:52]))


if __name__ == "__main__":
    main()
