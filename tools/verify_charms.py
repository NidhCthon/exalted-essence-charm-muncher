"""Check extracted charms for the marks a mis-segmented stream leaves behind.

The charm extractors are regex over a PDF's type hierarchy, pinned to one
edition. When they go wrong they do not fail - they emit a plausible charm
whose body quietly contains the next charm, a sidebar, or a page footer. A
charm count does not catch that, so this looks for the specific signature each
failure leaves:

* MERGED      a body span that opens another charm's header: a prerequisite
              line at the start of a span, or straight after a short name with
              no sentence break before it. The next charm was read as prose and
              two charms became one, so one is missing from the packs. The
              swallowed name is shown. The charm equivalent of
              verify_antagonists.py's MERGED, and the worst failure here.
* HEADING     an all-caps span inside a body: a name-sized line that was not
              treated as a name. Either a missed charm, sidebar chrome, or - in
              the draft Player's Guide - an editor's layout note left in.
              (The Player's Guide sets names in Title Case, so there a missed
              name shows up as MERGED, not HEADING.)
* DOUBLED     a body span that repeats itself - sidebars are set twice in the
              source, and this is the mark of one leaking in.
* FOOTER      a running "CHAPTER N:" footer spliced into the body.
* EMPTY       no body at all.
* NO_PREREQ   a prerequisite line with nothing on it.
* PAGE_RANGE  a page outside the range the extractor reads. It cannot be right,
              so the page reference the charm shows in Foundry is wrong.
* BACKWARDS   a page lower than the charm immediately before it: either reading
              order broke between the two, or one of them carries a bad page
              label (in which case PAGE_RANGE flags it too).

And one note, reported but not counted as a failure:

* DUPLICATE   the same name twice in one section. The Player's Guide really does
              repeat six names inside a single section, and ids are namespaced
              by page, so repeats import correctly. Listed so that an unexpected
              seventh gets looked at.

It also answers a design question with data instead of instinct - whether
regex is good enough, or ambiguous entries need a smarter fallback such as an
LLM pass. The summary reports what share of charms trip nothing.

Book text is never printed: names, pages and reasons only.

    python tools/verify_charms.py          flagged charms, up to 25 per book
    python tools/verify_charms.py --all    every flagged charm

Exit codes: 0 clean, 1 something to look at.
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from extract import ALLCAPS, FOOTER, is_doubled
from extract import FIRST_PAGE as CORE_FIRST, LAST_PAGE as CORE_LAST
from extract_pg import CHAPTERS as PG_CHAPTERS
from extract_pillars import FIRST_PAGE as PILLARS_FIRST, LAST_PAGE as PILLARS_LAST

DATA = Path(__file__).resolve().parent.parent / "data"
SOURCES = ["charms", "pillars", "playersguide"]
# The page ranges each extractor reads, taken from the extractors themselves so
# they cannot drift apart.
PAGE_RANGES = {
    "charms": (CORE_FIRST, CORE_LAST),
    "pillars": (PILLARS_FIRST, PILLARS_LAST),
    "playersguide": (min(c[0] for c in PG_CHAPTERS), max(c[1] for c in PG_CHAPTERS)),
}
# Printed page numbers can sit a few pages off the PDF page index the ranges
# use; a real page label is never further out than this.
PAGE_SLACK = 10
NOTES = {"DUPLICATE"}  # reported, but not a failure
PREREQ_IN_BODY = re.compile(r"\bPrerequisites?:", re.I)
SENTENCE_BREAK = re.compile(r"[.?]\s")
# A swallowed name at the end of a span, including one welded onto the end of
# a prose sentence with no space ("...Evocation:NAME OF THE EVOCATION").
CAPS_TAIL = re.compile(r"[A-Z0-9(][A-Z0-9'’,:!()\-— ]{3,}$")
SHOWN_BY_DEFAULT = 25


def opens_a_charm(span):
    """The text before the prerequisite when this span starts another charm's
    header, else None.

    A header's prerequisite either starts its own span, or - where name and
    prerequisite share a block, as in four Player's Guide chapters - follows a
    short name with no sentence break. "...if he meets its Prerequisites" in
    running prose is neither, and is not a merge.
    """
    match = PREREQ_IN_BODY.search(span)
    if not match:
        return None
    before = span[:match.start()].strip()
    if not before or (len(before) <= 80 and not SENTENCE_BREAK.search(before)):
        return before
    return None


def swallowed_name(body, k, before):
    source = before or (body[k - 1].strip() if k else "")
    tail = CAPS_TAIL.search(source)
    return (tail.group(0) if tail else source)[-60:].strip()


def check(charms, page_range=None):
    """Map charm index -> reasons it looks wrong, and index -> swallowed names."""
    flags, swallowed = defaultdict(list), {}
    seen = Counter()
    previous_page = 0
    for i, charm in enumerate(charms):
        body = charm.get("body") or []
        joined = " ".join(body)

        if not body:
            flags[i].append("EMPTY")
        if not (charm.get("prerequisite") or "").strip():
            flags[i].append("NO_PREREQ")

        names = []
        for k, span in enumerate(body):
            before = opens_a_charm(span)
            if before is not None:
                names.append(swallowed_name(body, k, before))
        if names:
            flags[i].append("MERGED")
            swallowed[i] = names

        if any(ALLCAPS.match(span.strip()) for span in body):
            flags[i].append("HEADING")
        if any(is_doubled(span) for span in body):
            flags[i].append("DOUBLED")
        if FOOTER.search(joined):
            flags[i].append("FOOTER")

        page = charm.get("page") or 0
        if page_range and not (page_range[0] - PAGE_SLACK <= page <= page_range[1] + PAGE_SLACK):
            flags[i].append("PAGE_RANGE")
        # Compare with the charm immediately before, not the highest page seen
        # so far. Against the running maximum, one early out-of-place record
        # marks every charm after it, and the actual break point is buried.
        if page < previous_page:
            flags[i].append("BACKWARDS")
        previous_page = page

        key = (charm.get("section"), charm.get("name"))
        seen[key] += 1
        if seen[key] == 2:
            flags[i].append("DUPLICATE")
    return flags, swallowed


def report(source, charms, flags, swallowed, show_all):
    """Print one book's summary. True when anything is a failure, not a note."""
    problems = {i for i, rs in flags.items() if any(r not in NOTES for r in rs)}
    total = len(charms)
    clean = total - len(problems)
    share = 100 * clean / total if total else 0
    lost = sum(len(v) for v in swallowed.values())
    print(f"{source}: {total} charms, {clean} clean ({share:.1f}%)"
          + (f", {lost} swallowed charm(s) missing from the packs" if lost else ""))
    for reason, count in Counter(r for rs in flags.values() for r in rs).most_common():
        label = f"{reason} (note)" if reason in NOTES else reason
        print(f"  {label:<17} {count}")

    # MERGED always lists in full - it is the one that silently loses a charm.
    ordered = sorted(flags, key=lambda i: ("MERGED" not in flags[i], i))
    limit = None if show_all else SHOWN_BY_DEFAULT
    for n, i in enumerate(ordered):
        if limit is not None and n >= limit and "MERGED" not in flags[i]:
            print(f"    ... {len(ordered) - n} more (--all to list)")
            break
        c = charms[i]
        extra = f"  <- swallowed: {'; '.join(swallowed[i])}" if i in swallowed else ""
        print(f"    p{c.get('page')}  {c.get('name')}  [{c.get('section')}]  "
              f"{', '.join(flags[i])}{extra}")
    print()
    return bool(problems)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="list every flagged charm")
    args = parser.parse_args()

    anything = False
    for source in SOURCES:
        path = DATA / f"{source}.raw.json"
        if not path.exists():
            print(f"{source}: {path.name} not found - run its extractor first\n")
            continue
        charms = json.loads(path.read_text(encoding="utf-8"))
        flags, swallowed = check(charms, PAGE_RANGES.get(source))
        if report(source, charms, flags, swallowed, args.all):
            anything = True
    return 1 if anything else 0


if __name__ == "__main__":
    sys.exit(main())
