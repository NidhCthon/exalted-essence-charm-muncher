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

Not extracted here: the "Modes" lists (new Exalt-specific ways to use core
charms, not charms of their own) and the appendix's Charm Clarifications and
Updates (errata for 16 core charms).

The PDF outline lists every charm by name, so --check compares the extraction
against it and names anything missing.
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

from books import add_pdf_argument, open_book
from extract import build_stream, segment

OUT = Path(__file__).resolve().parent.parent / "data" / "pgfinal.raw.json"

FIRST_PAGE, LAST_PAGE = 30, 309  # PDF pages; printed numbers run one lower

# "NEW CHARMS" banners, by the chapter they sit in.
NEW_CHARMS_BY_CHAPTER = {
    "Exigents": "Sovereign Charms",
    "Alchemical": "Alchemical Charms",
    "Getimian": "Getimian Charms",
    "Infernal": "Infernal Charms",
    "Liminal": "Liminal Charms",
}
SECTION_FIXES = {"Architects Charms": "Architect Charms"}
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

    if args.check:
        wanted, got = outline_names(doc), {key(c["name"]) for c in charms}
        missing, extra = sorted(wanted - got), sorted(got - wanted)
        print()
        print("outline charms   : {}".format(len(wanted)))
        print("missing          : {}  {}".format(len(missing), missing))
        print("not in outline   : {}  {}".format(len(extra), extra))


if __name__ == "__main__":
    main()
