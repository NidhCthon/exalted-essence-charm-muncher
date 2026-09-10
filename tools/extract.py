"""Extract Exalted Essence charms from the core rulebook PDF.

The book is two-column. Flat text extraction interleaves the columns and
produces charms wearing each other's mechanics, so we work from positioned
text blocks instead: for each page, read the left column top-to-bottom, then
the right column. Concatenating pages yields one linear stream in true reading
order, so a charm flowing across a column or page break stays intact.

Blocks are classified by rendered font size rather than by capitalisation,
which is what separates a 30pt section title from a 12pt charm name reliably.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pymupdf

from books import add_pdf_argument, open_book

OUT = Path(__file__).resolve().parent.parent / "data" / "charms.raw.json"

FIRST_PAGE, LAST_PAGE = 186, 353  # 1-indexed inclusive: the charm chapter

SECTION_MIN_SIZE = 18.0   # section titles render around 30pt
NAME_SIZE = (10.5, 13.2)  # charm names: 12pt in most chapters, 10.9pt in Sorcery
ALLCAPS = re.compile(r"^[A-Z][A-Z'\u2019\-\u2014 ]{3,60}$")
PREREQ = re.compile(r"^Prerequisites?:\s*(.*)$", re.I | re.S)
FOOTER = re.compile(r"CHAPTER [A-Z]+:", re.I)
XREF = re.compile(r"^See p\. ?\d", re.I)
TRAILING_PAGENO = re.compile(r"(\d{1,3})(?!.*\d)")


def clean(s: str) -> str:
    """Drop soft hyphens, rejoin split words, normalise quotes and space."""
    s = s.replace("\u00ad", "")
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"-\s*\n\s*", "", s)
    return re.sub(r"\s+", " ", s).strip()


def dedupe_doubled(s: str) -> str:
    """Some headings are set twice in the source; keep a single copy.

    The two copies may be joined with no separator ("FOOFOO") or with a space
    ("FOO FOO"), depending on how the spans were laid out.
    """
    n = len(s)
    if n % 2 == 0 and s[: n // 2] == s[n // 2:]:
        return s[: n // 2]
    words = s.split()
    half = len(words) // 2
    if len(words) % 2 == 0 and half and words[:half] == words[half:]:
        return " ".join(words[:half])
    return s


def page_units(page):
    """Yield (column, y, size, text) for every text block on the page."""
    mid = page.rect.width / 2
    for blk in page.get_text("dict")["blocks"]:
        if blk.get("type") != 0:
            continue
        size, parts = 0.0, []
        for line in blk.get("lines", []):
            for span in line.get("spans", []):
                size = max(size, span["size"])
                parts.append(span["text"])
        text = clean("".join(parts))
        if not text:
            continue
        x0, y0, x1, _ = blk["bbox"]
        yield (0 if (x0 + x1) / 2 < mid else 1, y0, size, text)


def order_page(units):
    """Order one page's blocks, honouring full-width section banners.

    Section titles are centred banners spanning both columns, so their bbox
    centre falls arbitrarily on either side of the page midline - "ABYSSAL
    CHARMS" sits two points right of centre and would otherwise sort after
    every left-column charm on its own page, stranding Abyssal charms in the
    preceding section. A banner is not column content: it divides the page
    horizontally, and everything above it in either column belongs to the
    previous section. Split the page into regions at each banner, and order
    by column only within a region.
    """
    banners = sorted((u for u in units if u[2] >= SECTION_MIN_SIZE),
                     key=lambda u: u[1])
    body = [u for u in units if u[2] < SECTION_MIN_SIZE]
    ordered, lower = [], float("-inf")
    for index, upper in enumerate([b[1] for b in banners] + [float("inf")]):
        region = [u for u in body if lower <= u[1] < upper]
        ordered.extend(sorted(region, key=lambda u: (u[0], round(u[1], 1))))
        if index < len(banners):
            ordered.append(banners[index])
        lower = upper
    return ordered


def build_stream(doc, first=FIRST_PAGE, last=LAST_PAGE):
    """Linear [(kind, text, printed_page)] across a book's charm chapter.

    Defaults cover the core rulebook; supplements pass their own range.
    """
    stream = []
    for pno in range(first - 1, last):
        printed = pno
        units = order_page(list(page_units(doc[pno])))
        for _, _, size, text in units:
            if FOOTER.search(text):
                m = TRAILING_PAGENO.search(text)
                if m:
                    printed = int(m.group(1))
                continue
            if size >= SECTION_MIN_SIZE:
                kind = "section"
                text = dedupe_doubled(text)
            elif NAME_SIZE[0] <= size <= NAME_SIZE[1] and ALLCAPS.match(text):
                kind = "name"
                text = dedupe_doubled(text)
            else:
                kind = "body"
            stream.append((kind, text, printed))
    return stream


def is_doubled(text: str) -> bool:
    """True when a block repeats itself - the signature of sidebar chrome.

    Sidebars are set twice in the source, but the duplication is per *line*,
    not per block: each line is emitted, repeated, then the next line follows.
    So the block is not two equal halves, and comparing halves never fires.
    Detect it by looking for the opening run of words repeating immediately.
    """
    if dedupe_doubled(text) != text:
        return True
    words = text.split()
    for size in range(4, min(16, len(words) // 2) + 1):
        if words[:size] == words[size:size * 2]:
            return True
    return False


def titlecase(name: str) -> str:
    out = name.title()
    out = re.sub(r"'S\b", "'s", out)
    for small in (" Of ", " The ", " And ", " In ", " A ", " To ", " All "):
        out = out.replace(small, small.lower())
    return out[0].upper() + out[1:]


def segment(stream):
    """Split the stream into charm records, tracking the enclosing section."""
    charms, section, i = [], None, 0
    while i < len(stream):
        kind, text, page = stream[i]
        if kind == "section":
            section = titlecase(text)
            i += 1
            continue
        if kind == "name":
            nxt = stream[i + 1] if i + 1 < len(stream) else ("", "", 0)
            m = PREREQ.match(nxt[1]) if nxt[0] == "body" else None
            if m:
                body, j = [], i + 2
                while j < len(stream):
                    kind_j, text_j, _ = stream[j]
                    if kind_j == "section":
                        break
                    if kind_j == "name":
                        after = stream[j + 1] if j + 1 < len(stream) else ("", "", 0)
                        if after[0] == "body" and PREREQ.match(after[1]):
                            break  # the next charm begins here
                        # A heading with no prerequisite is a sidebar floated
                        # into the column. Stepping over it rather than
                        # stopping keeps the charm's remaining paragraphs -
                        # its Exalt-specific variants usually continue below.
                        j += 1
                        continue
                    if is_doubled(text_j) or XREF.match(text_j):
                        # Sidebar prose, or the "See p. 197." body belonging
                        # to a cross-reference heading we just stepped over.
                        j += 1
                        continue
                    body.append(text_j)
                    j += 1
                charms.append({
                    "name": titlecase(text),
                    "section": section,
                    "page": page,
                    "prerequisite": m.group(1).strip(),
                    "body": body,
                })
                i = j
                continue
        i += 1
    return charms


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_pdf_argument(parser, "core")
    args = parser.parse_args()
    doc, path = open_book("core", args.pdf)
    print(f"reading: {path.name}")
    charms = segment(build_stream(doc))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(charms, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"charms extracted : {len(charms)}")
    print(f"empty body       : {sum(1 for c in charms if not c['body'])}")
    print(f"no section       : {sum(1 for c in charms if not c['section'])}")
    dupes = [n for n, k in Counter(c["name"] for c in charms).items() if k > 1]
    print(f"duplicate names  : {len(dupes)}  {dupes[:5]}")
    print(f"written to       : {OUT}\n")
    print("sections:")
    for name, n in Counter(c["section"] for c in charms).items():
        print(f"  {n:4d}  {name}")


if __name__ == "__main__":
    main()
