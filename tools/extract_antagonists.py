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

Covers the core rulebook and Pillars of Creation, which share a type scale;
the Tomb of Memory jumpstart, which does not; and the Storyteller's Guide
draft, which is set in a word processor's fonts and names an antagonist at
the same size as its stat block, so there the font is what tells them
apart. See Profile below.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

from books import BOOKS, open_book
from extract import clean, dedupe_doubled, titlecase
from extract_battle_groups import DRILL_RE

OUT = Path(__file__).resolve().parent.parent / "data" / "antagonists.raw.json"


class Profile:
    """The type sizes a book sets its antagonists in.

    The core book and Pillars share a scale. The jumpstart does not - it
    names antagonists at the size the other two use for a variant - so the
    sizes cannot be module constants shared by every book.
    """

    def __init__(self, name, stat, variant=(0.0, 0.0), banner=19.0,
                 name_font=None, stat_font=None, max_pages=2):
        self.name = name
        self.stat = stat
        self.variant = variant      # (0, 0) where a book has no variants
        self.banner = banner        # above a name, so banners divide a page
        # A draft manuscript is set in a word processor's fonts rather than
        # the published design, and sets an antagonist's name and its stat
        # block at the same size. Where that is so, the font is what tells
        # them apart and these are set instead of reading the sizes.
        self.name_font = name_font
        self.stat_font = stat_font
        # How many pages one entry may cover before that looks like runaway
        # collection rather than a long entry. The published books are
        # compact; a draft manuscript runs an antagonist over several pages.
        self.max_pages = max_pages

    def classify(self, size, font):
        """"name", "stat" or None for this span."""
        if self.name_font:
            if self.name_font in font:
                return "name"
            if self.stat_font in font:
                return "stat"
            return None
        if self.name[0] <= size <= self.name[1]:
            return "name"
        if self.stat[0] <= size <= self.stat[1]:
            return "stat"
        return None


RULEBOOK = Profile(name=(17.0, 18.4), stat=(10.6, 11.2), variant=(13.5, 14.3))
JUMPSTART = Profile(name=(13.6, 14.2), stat=(10.2, 11.2))
# The Storyteller's Guide draft: names in Arial, stat blocks in Calibri, both
# at the same size, with the prose in Times.
DRAFT = Profile(name=(13.6, 14.2), stat=(13.6, 14.2), banner=17.0,
                name_font="Arial", stat_font="Calibri", max_pages=5)

# (book key, first page, last page, profile) - pages 1-indexed, inclusive.
RANGES = [
    ("core", 316, 341, RULEBOOK),
    ("pillars", 168, 199, RULEBOOK),
    ("tomb", 41, 44, JUMPSTART),
    ("stg", 126, 228, DRAFT),
]

SOFT = "­"


def join_spans(parts):
    """Join spans with spaces, except across a word broken by a hyphen."""
    out = ""
    for part in parts:
        if out and not out.endswith(SOFT):
            out += " "
        out = out.rstrip(SOFT) if out.endswith(SOFT) else out
        out += part
    return out.rstrip(SOFT)


# A stat is a label followed by a number. The same words appear in the
# qualities prose - "reduces Defense by one" - so matching a bare label lets
# prose overwrite the real value. Numbers are required, and the first match
# wins, because the stat line always precedes the prose.
# "Health Levels" has to precede "Health" so the longer label wins; the
# jumpstart prints the short form for its battle groups.
NUM_LABELS = ("Health Levels", "Health", "Resolve", "Defense", "Defence",
              "Hardness", "Soak", "Essence", "Size", "Drill", "Command")

# Drill is a word. Where it is printed without its modifier in brackets,
# this is the modifier that word stands for.
DRILL_WORDS = {"poor": 0, "regular": 1, "veteran": 2, "elite": 3}
NUM_RE = re.compile(r"\b(" + "|".join(NUM_LABELS) + r")\s*:?\s*(\d+)", re.I)
# Named antagonists print the parenthesised form; the template blocks
# in sidebars print the colon form instead. Both forms, or the templates
# import with no pools at all.
POOL_RE = re.compile(
    r"\b(Primary|Secondary|Tertiary)\s+Pool\s*[:(]?\s*(\d+)\)?\s*:?\s*", re.I)
# The published books set this heading in capitals; the draft manuscript
# sets it in title case. Spelled out rather than matched case-insensitively,
# because a case-insensitive "attacks" would match the ordinary word in prose
# and cut a stat block short wherever it appeared.
QUALITIES_RE = re.compile(
    r"\b(ATTACKS AND QUALITIES|Attacks and Qualities|QUALITIES|ATTACKS)\b")
# Plural too: an antagonist carrying more than one is given a "Weapons:"
# line, and matching only the singular left those stats inside qualities.
WEAPON_RE = re.compile(r"\bWeapons?\s*:\s*", re.I)
DRILL_WORD_RE = re.compile(r"\bDrill\s*:\s*([A-Za-z]+)", re.I)
# A page number, set twice the way the running foot is. It carries no
# meaning into a description, where it reads as a stray number.
FOLIO_RE = re.compile(r"^\d{1,4}$")
FOOTER_RE = re.compile(r"CHAPTER [A-Z]+:|Mortals and Exalted|Gods and Monsters"
                       r"|Exalted Antagonists|Strange Beasts", re.I)


def spans(doc, first, last, banner_min, with_font=False):
    """Every span in reading order: left column, then right, then next page.

    Except that a centred section banner straddles both columns and divides
    the page, so the columns above it are read before it and the columns
    below it after. Reading a whole column at a time instead walks an
    antagonist's stats past the heading of the section underneath, which is
    how one warship's stats ended up filed after a later name. The charm
    extractor splits pages this way too - see order_page() in extract.py.
    """
    for pno in range(first - 1, last):
        page = doc[pno]
        mid = page.rect.width / 2
        units = []
        for blk in page.get_text("dict")["blocks"]:
            if blk.get("type") != 0:
                continue
            x0, y0, x1, _ = blk["bbox"]
            size = max((sp["size"] for line in blk.get("lines", [])
                        for sp in line.get("spans", [])), default=0.0)
            units.append((0 if (x0 + x1) / 2 < mid else 1, y0, size, blk))

        banners = sorted((u for u in units if u[2] >= banner_min),
                         key=lambda u: u[1])
        body = [u for u in units if u[2] < banner_min]

        ordered, lower = [], float("-inf")
        edges = [b[1] for b in banners] + [float("inf")]
        for index, upper in enumerate(edges):
            region = [u for u in body if lower <= u[1] < upper]
            ordered.extend(sorted(region, key=lambda u: (u[0], round(u[1], 1))))
            if index < len(banners):
                ordered.append(banners[index])
            lower = upper

        for _, _, _, blk in ordered:
            for line in blk.get("lines", []):
                for sp in line.get("spans", []):
                    raw = sp["text"]
                    text = clean(raw)
                    if not text:
                        continue
                    # clean() rejoins a word broken over a line, but only
                    # where the break is still there to see. At span level it
                    # is not: the span just ends on a soft hyphen and the
                    # word continues in the next one, so "Signifi" and
                    # "cant" would be joined with a space between them.
                    # Carry the hyphen through for join_spans() to close up.
                    if raw.rstrip().endswith(SOFT):
                        text += SOFT
                    # The equipment chapter tells a name from its tags by
                    # font rather than by size, so that is offered too - but
                    # only on request, to leave the common shape alone.
                    if with_font:
                        yield pno + 1, round(sp["size"], 1), text, sp["font"]
                    else:
                        yield pno + 1, round(sp["size"], 1), text


def stat_block_of(text):
    """The part of a stat line before the prose starts.

    Everything after the qualities heading is description, and description
    names traits with numbers: one antagonist can "create a Size 1 battle
    group", which is not that antagonist having a Size. Reading numbers only
    from the block keeps prose out by construction rather than relying on the
    block happening to come first.
    """
    # A marker that appears before any stat does not belong to this block:
    # an entry can open with the tail of the one above it, and truncating
    # there threw away every stat that followed. Measure from the first stat
    # instead, and take the first marker after it.
    first = NUM_RE.search(text)
    if first is None:
        return text
    ends = [match.start() for match in
            (QUALITIES_RE.search(text, first.start()),
             WEAPON_RE.search(text, first.start())) if match]
    return text[:min(ends)] if ends else text


def parse_stats(text):
    """Split a run-together stat line into numbers, pools and prose."""
    stats, pools = {}, {}

    block = stat_block_of(text)
    for match in NUM_RE.finditer(block):
        label = match.group(1).lower()
        if label not in stats:            # first occurrence is the stat block
            stats[label] = int(match.group(2))

    # Drill is printed as a word with its modifier in brackets, so it never
    # matches the label-and-number pattern the other stats use.
    if "health" in stats:
        stats.setdefault("health levels", stats.pop("health"))
    else:
        stats.pop("health", None)

    drill = DRILL_RE.search(block)
    if drill:
        stats["drill"] = int(drill.group(2))
    else:
        word = DRILL_WORD_RE.search(block)
        if word and word.group(1).lower() in DRILL_WORDS:
            stats["drill"] = DRILL_WORDS[word.group(1).lower()]

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


def extract(doc, book, first, last, profile, dump=None):
    entries = []
    current = None
    pending_name = []

    def flush_name(page):
        nonlocal current, pending_name
        if not pending_name:
            return
        name = clean(join_spans(pending_name))
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

    stream = list(spans(doc, first, last, profile.banner, with_font=True))
    for index, (page, size, text, font) in enumerate(stream):
        kind = profile.classify(size, font)
        if FOOTER_RE.search(text) and size < profile.name[0]:
            continue

        if kind == "name":
            pending_name.append(text)
            continue
        # Pillars names its sub-entries at the size the core book uses for
        # "Variant:", so the leading word is what separates them.
        if (profile.variant[0] <= size <= profile.variant[1]
                and profile.variant[1]
                and not text.lower().startswith("variant")):
            pending_name.append(text)
            continue
        flush_name(page)

        if current is None:
            continue

        if kind == "stat":
            if TEMPLATE_HEAD.match(text) and heads_a_stat_block(stream, index):
                pending_name.append(titlecase(text))
                flush_name(page)
                continue
            current["statline"].append((page, text))
        elif (profile.variant[1] and profile.variant[0] <= size <= profile.variant[1]
              and text.lower().startswith("variant")):
            current["variants"].append({"name": text.rstrip(SOFT), "notes": []})
        elif FOLIO_RE.match(text):
            continue                      # a page number, not description
        elif current["variants"]:
            current["variants"][-1]["notes"].append(text.rstrip(SOFT))
        else:
            current["body"].append(text.rstrip(SOFT))

    flush_name(last)

    for entry in entries:
        spans_seen = entry["statline"]
        if dump and dump.lower() in entry["name"].lower():
            dump_statline(entry, spans_seen)
        spans_seen, sidebar = split_doubled_sidebar(spans_seen)
        spans_seen, table = cut_at_battle_group_table(spans_seen)
        # Kept for verify_antagonists.py; main() strips it before writing.
        entry["statline"] = spans_seen
        entry["sidebar"] = clean(join_spans(sidebar + table))
        stats, pools, qualities, weapon = parse_stats(
            join_spans([text for _, text in spans_seen]))
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
    for key in ("core", "pillars", "tomb", "stg"):
        parser.add_argument("--{}".format(key), help="path to that PDF")
    parser.add_argument("--dump", metavar="NAME",
                        help="print the raw stat-line spans, with their page "
                             "numbers, for every entry whose name contains "
                             "NAME - use this to find where a wrong number "
                             "actually came from")
    args = parser.parse_args()

    all_entries = []
    for book, first, last, profile in RANGES:
        # Books are optional here as they are in build_all: extract from the
        # ones that were supplied rather than refusing to run without all.
        if not (getattr(args, book, None) or os.environ.get(BOOKS[book].env_var)):
            print("skipping {}: no PDF supplied".format(book))
            continue
        doc, path = open_book(book, getattr(args, book, None))
        print("reading {}: {}".format(book, path.name))
        found = extract(doc, book, first, last, profile, dump=args.dump)
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
