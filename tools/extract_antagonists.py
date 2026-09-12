"""Extract antagonist stat blocks from the published Essence books.

Antagonists are Actors, not Items, and their blocks are laid out unlike
anything the charm extractor handles:

* An antagonist's name is a 17.8pt span welded onto the end of the previous
  paragraph - "Weapon: <weapon> (...).<name>" - and a long name
  wraps across several spans. Working at block level buries every name, so
  this reads spans and joins consecutive large ones.
* Stat lines run together without separators: "<label>: <n><label>:
  <n><label>: <n><label>: <n>". They are split on the known label set
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
from extract import clean, dedupe_doubled, titlecase

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
# Named antagonists print the parenthesised form; the template blocks
# in sidebars print the colon form instead. Both forms, or the templates
# import with no pools at all.
POOL_RE = re.compile(
    r"\b(Primary|Secondary|Tertiary)\s+Pool\s*[:(]?\s*(\d+)\)?\s*:?\s*", re.I)
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


def split_doubled_sidebar(spans_seen):
    """Separate a stat line from the sidebar box printed on top of it.

    Several antagonists have a battle group boxed out beside them - a
    commander's warship or warband, with its own Size, Drill, Commander and
    Qualities. That box is a separate entity, but it lands in the middle of
    the host's stat spans, so its Size was being read as the commander's and
    its prose spliced into the middle of the commander's qualities.

    These boxes are drawn twice, span for span, the way sidebars are
    throughout these books - which is what tells them apart from the stat
    block they interrupt. A span is sidebar when it repeats the span either
    side of it; real stat spans never do. Dropping exactly those spans also
    rejoins the host's prose across the interruption.
    """
    texts = [text for _, text in spans_seen]
    kept, sidebar = [], []
    for i, (page, text) in enumerate(spans_seen):
        doubled = ((i > 0 and texts[i - 1] == text)
                   or (i + 1 < len(texts) and texts[i + 1] == text))
        if doubled:
            # Keep one copy of each pair, in order, as the box's own text.
            if not sidebar or sidebar[-1] != text:
                sidebar.append(text)
        else:
            kept.append((page, text))
    return kept, sidebar


TABLE_LABEL = re.compile(r"^(QUALITIES|DEFENSE|DEFENCE|HEALTH|SOAK|DRILL|SIZE"
                         r"|COMMAND|ESSENCE|RESOLVE|HARDNESS)$")


def cut_at_battle_group_table(spans_seen):
    """Stop a stat line where a battle group's stat table begins.

    Battle groups print their stats as a table: the labels on one row, the
    numbers on the next. Read as a run of spans that becomes a label row
    followed by a number row, so the last label takes the first number of
    that row - and when the table sits beside another antagonist, that
    number lands on them.

    A wrapped "ATTACKS AND QUALITIES" heading can leave one bare label span on
    its own, so a table is only called where two run together. Everything from
    there is set aside rather than parsed: those numbers need position-aware
    reading, which is tracked separately.
    """
    for i in range(len(spans_seen) - 1):
        if (TABLE_LABEL.match(spans_seen[i][1])
                and TABLE_LABEL.match(spans_seen[i + 1][1])):
            return spans_seen[:i], [text for _, text in spans_seen[i:]]
    return spans_seen, []


TEMPLATE_HEAD = re.compile(r"^[A-Z][A-Z' -]{3,40}$")


def heads_a_stat_block(stream, index):
    """True when an all-caps span is a stat block's heading.

    Template blocks in sidebars - the two animal templates - are headed
    at stat size rather than name size, so nothing marks them as names and two
    templates merge into one entry. What separates such a heading from
    "ATTACKS AND QUALITIES" or a table's label row is simply what follows it:
    a stat block opens on its pools.
    """
    following = stream[index + 1][2] if index + 1 < len(stream) else ""
    return following.lower().startswith("primary pool")


def dump_statline(entry, spans_seen):
    """Print the spans that fed one entry's stat line, with their pages.

    The stat line is what parse_stats() sees, so when an actor ends up with a
    number nobody printed on its page, this is where that number came from.
    """
    print()
    print("=" * 72)
    print("{}  (name found on p{})".format(entry["name"], entry["page"]))
    print("-" * 72)
    for page, text in spans_seen:
        flag = " " if page == entry["page"] else "*"
        print("  {} p{:<4} {}".format(flag, page, text))
    pages = sorted({p for p, _ in spans_seen})
    print("-" * 72)
    print("  spans: {}   pages spanned: {}".format(len(spans_seen), pages))


def extract(doc, book, first, last, dump=None):
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

    stream = list(spans(doc, first, last))
    for index, (page, size, text) in enumerate(stream):
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
            if TEMPLATE_HEAD.match(text) and heads_a_stat_block(stream, index):
                pending_name.append(titlecase(text))
                flush_name(page)
                continue
            current["statline"].append((page, text))
        elif VARIANT_SIZE[0] <= size <= VARIANT_SIZE[1] and text.lower().startswith("variant"):
            current["variants"].append({"name": text, "notes": []})
        elif current["variants"]:
            current["variants"][-1]["notes"].append(text)
        else:
            current["body"].append(text)

    flush_name(last)

    for entry in entries:
        spans_seen = entry["statline"]
        if dump and dump.lower() in entry["name"].lower():
            dump_statline(entry, spans_seen)
        spans_seen, sidebar = split_doubled_sidebar(spans_seen)
        spans_seen, table = cut_at_battle_group_table(spans_seen)
        # Kept for verify_antagonists.py; main() strips it before writing.
        entry["statline"] = spans_seen
        entry["sidebar"] = clean(" ".join(sidebar + table))
        stats, pools, qualities, weapon = parse_stats(
            " ".join(text for _, text in spans_seen))
        entry["stats"] = stats
        entry["pools"] = pools
        entry["qualities"] = qualities
        entry["weapon"] = weapon

    def is_antagonist(entry):
        if entry["pools"].get("primary", {}).get("value", 0) > 0:
            return True
        return "defense" in entry["stats"] and "soak" in entry["stats"]

    kept = [e for e in entries if is_antagonist(e)]
    skipped = [e for e in entries if not is_antagonist(e)]
    if skipped:
        # Mostly section headings that were read as names. Printed because a
        # real antagonist landing here means its stat block was lost.
        print("  skipped, no stats: {}".format(
            ", ".join("{} (p{})".format(e["name"][:34], e["page"])
                      for e in skipped)))
    return kept


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("core", "pillars"):
        parser.add_argument("--{}".format(key), help="path to that PDF")
    parser.add_argument("--dump", metavar="NAME",
                        help="print the raw stat-line spans, with their page "
                             "numbers, for every entry whose name contains "
                             "NAME - use this to find where a wrong number "
                             "actually came from")
    args = parser.parse_args()

    all_entries = []
    for book, first, last in RANGES:
        doc, path = open_book(book, getattr(args, book, None))
        print("reading {}: {}".format(book, path.name))
        found = extract(doc, book, first, last, dump=args.dump)
        print("  entries: {}".format(len(found)))
        all_entries.extend(found)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    for entry in all_entries:
        entry.pop("statline", None)
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
