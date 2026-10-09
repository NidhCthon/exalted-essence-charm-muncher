"""Extract charms from the final Exalted Essence Player's Guide (2026 release).

The final book is laid out like the core rulebook and Pillars (two columns,
capitals charm names, "Prerequisite:" lines), so it reuses the core extractor
wholesale, the way extract_pillars.py does. The draft manuscript, a Word export
with Title Case names, needed its own extractor (extract_pg.py); this does not.

Two things differ from the other books:

- Five chapters title their section just "NEW CHARMS". The Exalt type comes
  from the chapter, which the PDF outline gives by page.
- The Exigents chapter splits into March Lord, God-Admiral, Architect and
  Sovereign charms. March Lords and God-Admirals are Exigents and use that
  charm type.

It also extracts two kinds of entry that are not charms of their own, into
their own files:

- modes (data/pgfinal_modes.raw.json): new Exalt-specific riders for charms in
  the other books, under "Modes", "New Modes", "New Exalt Modes",
  "Constellation Modes" and "Charm Principle: Metropolis". Most are set as a
  capitals line naming the charm and its page, "GRACEFUL CRANE STANCE (P. 186)",
  one names two charms ("... (P.191) OR ... (P. 209)"), and the Sidereal
  Constellation Modes and one Architect mode use a name heading with no
  prerequisite line instead;
- errata (data/pgfinal_errata.raw.json): the appendix's Charm Clarifications
  and Updates, set the same way, for 16 core charms.

The PDF outline lists every charm, mode and erratum by name, so --check
compares the extraction against it and names anything missing.
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

from books import add_pdf_argument, open_book
from build_items import TRAIT_TO_ABILITY
from extract import PREREQ, build_stream, is_doubled, segment, titlecase

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "pgfinal.raw.json"
MODES_OUT = DATA / "pgfinal_modes.raw.json"
ERRATA_OUT = DATA / "pgfinal_errata.raw.json"

FIRST_PAGE, LAST_PAGE = 30, 309  # PDF pages; printed numbers run one lower
ERRATA_FIRST, ERRATA_LAST = 310, 314

# "GRACEFUL CRANE STANCE (P. 186)"; the page is the charm's in the core book.
REF = r"(?P<name{n}>[A-Z][A-Z0-9'’\-—,:!? ]+?)\s*\(P\.\s*(?P<page{n}>\d+)\)"
HEADER = re.compile("^" + REF.format(n=1) + r"(?:\s+OR\s+" + REF.format(n=2) + ")?$")
GROUP = re.compile(r"^(?:(?:New |New Exalt |Constellation |Bond )?Modes|Charm Principle:.*)$")
# Headings that end an entry: groups, Abilities (the charm lists are grouped by
# Ability), and the Architects' "General".
STOPS = {t.title() for t in TRAIT_TO_ABILITY} | {"General"}
# A heading welded onto the end of an entry's last line, after its full stop:
# "...article of clothing.Constellation Modes", "...any roll. Embassy".
WELDED_HEADING = re.compile(r"(?<=[.!?”\"])\s*((?:[A-Z][\w\-]*:? ?){1,3})$")

# "NEW CHARMS" banners, by the chapter they sit in.
NEW_CHARMS_BY_CHAPTER = {
    "Exigents": "Sovereign Charms",
    "Alchemical": "Alchemical Charms",
    "Getimian": "Getimian Charms",
    "Infernal": "Infernal Charms",
    "Liminal": "Liminal Charms",
}
SECTION_FIXES = {"Architects Charms": "Architect Charms",
                 # The Sovereigns' modes sit under the chapter's own banner.
                 "The Sovereigns of Uluiru": "Sovereign Charms"}
# Outline groups that list modes for existing charms rather than new charms.
MODE_GROUP = re.compile(r"Modes$|^Charm Principle", re.I)


def chapters(doc):
    """[(first PDF page, chapter title)] from the outline, in page order."""
    return sorted((page, title.strip()) for level, title, page in doc.get_toc() if level == 1)


def chapter_of(pdf_page, spans):
    title = None
    for first, name in spans:
        if first <= pdf_page:
            title = name
    return title or ""


def section_for(charm, spans):
    section = SECTION_FIXES.get(charm["section"], charm["section"])
    if section == "New Charms":
        chapter = chapter_of(charm["page"] + 1, spans)
        section = next((v for k, v in NEW_CHARMS_BY_CHAPTER.items() if k in chapter), section)
    return section


def sidebar(text):
    """Sidebar text is set twice. is_doubled() looks for an opening run of up to
    16 words repeating; a sidebar whose first sentence is longer than that (the
    Sidereal chapter's "Enemies of Fate" box) repeats later, so also look for
    the first six words recurring."""
    if is_doubled(text):
        return True
    words = text.split()
    return len(words) >= 12 and " ".join(words[:6]) in " ".join(words[6:])


def start(entries, refs, section, page, spans):
    entry = {"charms": [{"name": name, "core_page": core_page} for name, core_page in refs],
             "section": section_for({"section": section, "page": page}, spans) if section else None,
             "page": page, "body": [], "book": "pgfinal"}
    entries.append(entry)
    return entry


def references(stream, spans):
    """Mode and erratum entries: the charm(s) each belongs to, then its text.

    An entry runs until the next entry, a charm of this book (a name followed by
    its prerequisite), a section, or a group or Ability heading, including one
    welded onto the end of a line. A sidebar (a heading over text set twice) is
    stepped over, since an entry's text can continue below it.
    """
    entries, section, current, in_modes = [], None, None, False
    for i, (kind, text, page) in enumerate(stream):
        after = stream[i + 1] if i + 1 < len(stream) else ("", "", 0)
        if kind == "section":
            section, current, in_modes = titlecase(text), None, False
            continue
        if kind == "name":
            if after[0] == "body" and PREREQ.match(after[1]):
                current, in_modes = None, False  # a charm of this book begins
            elif after[0] == "body" and sidebar(after[1]):
                pass  # a sidebar's heading: step over it
            elif in_modes:
                current = start(entries, [(titlecase(text), None)], section, page, spans)
            else:
                current = None
            continue
        match = HEADER.match(text)
        if match:
            refs = [(titlecase(match.group("name1")), int(match.group("page1")))]
            if match.group("name2"):
                refs.append((titlecase(match.group("name2")), int(match.group("page2"))))
            current, in_modes = start(entries, refs, section, page, spans), True
            continue
        if sidebar(text) or text.isdigit():
            continue  # sidebar text and page numbers
        if GROUP.match(text) or text in STOPS:
            current, in_modes = None, in_modes or bool(GROUP.match(text))
            continue
        if current is None:
            continue
        welded = WELDED_HEADING.search(text)
        if welded:
            current["body"].append(text[:welded.start()].rstrip())
            current, in_modes = None, in_modes or bool(GROUP.match(welded.group(1).strip()))
            continue
        current["body"].append(text)
    return entries


def label_mode(entry):
    """'Immobile Border Defense: ...' or 'One of the Herd (Lunar): ...' -> mode name and tag."""
    match = re.match(r"^(?P<mode>[^:()]{2,60}?)(?: \((?P<tag>[^()]+)\))?:\s", entry["body"][0] if entry["body"] else "")
    entry["mode"] = match.group("mode") if match else None
    entry["tag"] = match.group("tag") if match else None
    return entry


def label_erratum(entry):
    first = entry["body"][0] if entry["body"] else ""
    entry["change"] = "update" if first.startswith("Update") else "clarification" if first.startswith("Clarif") else None
    return entry


def ref_key(entry):
    return " or ".join(key(c["name"]) for c in entry["charms"])


def outline_refs(doc):
    """(mode entries, errata entries) the outline lists, as keys."""
    modes, errata, in_charms, in_errata, group = set(), set(), False, False, None
    for level, title, _ in doc.get_toc():
        title = title.strip()
        if level <= 2:
            in_charms = level == 2 and "charms" in title.lower()
            in_errata = level == 2 and title.startswith("Charm Clarifications")
            continue
        if in_errata:
            errata.add(key(title))
        elif in_charms and level == 3:
            group = title
        elif in_charms and level == 4 and MODE_GROUP.search(group or ""):
            modes.add(key(title))
    return modes, errata


def outline_names(doc):
    """Every charm name the outline lists under a charm section, skipping mode lists."""
    names, in_charms, group = set(), False, None
    for level, title, _ in doc.get_toc():
        if level <= 2:
            in_charms = level == 2 and "charms" in title.lower()
            continue
        if not in_charms:
            continue
        if level == 3:
            group = title.strip()
        elif level == 4 and not MODE_GROUP.search(group or ""):
            names.add(key(title))
    return names


def key(name):
    """Compare names loosely: case, quotes, hyphens and page references don't matter."""
    name = re.sub(r"\(p\.\s*\d+\)", "", name)
    name = name.replace("�", "'").replace("’", "'").replace("-", " ")
    return re.sub(r"\s+", " ", name).strip().lower()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_pdf_argument(parser, "pgfinal")
    parser.add_argument("--check", action="store_true",
                        help="compare the extraction with the PDF outline's charm list")
    args = parser.parse_args()
    doc, path = open_book("pgfinal", args.pdf)
    print("reading: {}".format(path.name))
    spans = chapters(doc)
    charms = segment(build_stream(doc, FIRST_PAGE, LAST_PAGE))
    for charm in charms:
        charm["section"] = section_for(charm, spans)
        charm["book"] = "pgfinal"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(charms, indent=2, ensure_ascii=False), encoding="utf-8")

    print("charms extracted : {}".format(len(charms)))
    print("empty body       : {}".format(sum(1 for c in charms if not c["body"])))
    print("no section       : {}".format(sum(1 for c in charms if not c["section"])))
    dupes = [n for n, k in Counter((c["section"], c["name"]) for c in charms).items() if k > 1]
    print("duplicate names  : {}  {}".format(len(dupes), dupes[:5]))
    print("written to       : {}".format(OUT))
    print()
    print("sections:")
    for name, count in Counter(c["section"] for c in charms).items():
        print("  {:4d}  {}".format(count, name))

    modes = [label_mode(m) for m in references(build_stream(doc, FIRST_PAGE, LAST_PAGE), spans)]
    errata = [label_erratum(e) for e in references(build_stream(doc, ERRATA_FIRST, ERRATA_LAST), spans)]
    MODES_OUT.write_text(json.dumps(modes, indent=2, ensure_ascii=False), encoding="utf-8")
    ERRATA_OUT.write_text(json.dumps(errata, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print("modes extracted  : {}  (empty: {}, unnamed: {})".format(
        len(modes), sum(1 for m in modes if not m["body"]), sum(1 for m in modes if not m["mode"])))
    print("errata extracted : {}  (empty: {}, neither update nor clarification: {})".format(
        len(errata), sum(1 for e in errata if not e["body"]), sum(1 for e in errata if not e["change"])))
    print("written to       : {}, {}".format(MODES_OUT.name, ERRATA_OUT.name))

    if args.check:
        wanted, got = outline_names(doc), {key(c["name"]) for c in charms}
        missing, extra = sorted(wanted - got), sorted(got - wanted)
        print()
        print("outline charms   : {}".format(len(wanted)))
        print("missing          : {}  {}".format(len(missing), missing))
        print("not in outline   : {}  {}".format(len(extra), extra))
        want_modes, want_errata = outline_refs(doc)
        for label, wanted, entries in (("modes", want_modes, modes), ("errata", want_errata, errata)):
            got = {ref_key(e) for e in entries}
            print("outline {:9}: {}; missing {} {}; not in outline {} {}".format(
                label, len(wanted), len(wanted - got), sorted(wanted - got),
                len(got - wanted), sorted(got - wanted)))


if __name__ == "__main__":
    main()
