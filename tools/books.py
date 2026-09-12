"""Book registry: where each PDF lives, and how to tell it is the right one.

Every extractor is pinned to page ranges taken from a specific PDF release. A
different printing shifts those ranges, and the extractors would happily emit
hundreds of confidently wrong charms rather than fail. So each book carries a
fingerprint - a page count plus a phrase expected on a known page - which is
checked before extraction starts.

PDFs are never bundled. Point the tool at your own copy with --pdf, or set the
environment variable named in each entry.
"""
import os
import sys
from pathlib import Path

import pymupdf


class Book:
    def __init__(self, key, title, env_var, page_count, anchor_page, anchor_text):
        self.key = key
        self.title = title
        self.env_var = env_var
        self.page_count = page_count
        self.anchor_page = anchor_page      # 1-indexed
        self.anchor_text = anchor_text

    def resolve(self, override=None):
        """Find the PDF: explicit path, then environment variable."""
        candidate = override or os.environ.get(self.env_var)
        if not candidate:
            sys.exit(
                "No PDF given for {}.\n"
                "  Pass --pdf <path>, or set {}=<path>.\n"
                "  PDFs are not distributed with this tool - use your own copy."
                .format(self.title, self.env_var)
            )
        path = Path(candidate).expanduser()
        if not path.exists():
            sys.exit("PDF not found: {}".format(path))
        return path

    def verify(self, path):
        """Fail loudly when the PDF is not the edition the ranges were built for."""
        doc = pymupdf.open(path)
        problems = []
        if doc.page_count != self.page_count:
            problems.append("expected {} pages, found {}".format(
                self.page_count, doc.page_count))
        elif self.anchor_text.lower() not in doc[self.anchor_page - 1].get_text().lower():
            problems.append("expected {!r} on page {}".format(
                self.anchor_text, self.anchor_page))
        if problems:
            sys.exit(
                "{} does not look like the expected edition:\n  {}\n"
                "Page ranges are pinned to a specific release, so extraction "
                "would produce wrong output rather than fail. Refusing to run."
                .format(path.name, "\n  ".join(problems))
            )
        return doc


BOOKS = {
    "core": Book(
        key="core",
        title="Exalted Essence (core rulebook)",
        env_var="ESSENCE_CORE_PDF",
        page_count=412,
        anchor_page=186,
        anchor_text="UNIVERSAL CHARMS",
    ),
    "pillars": Book(
        key="pillars",
        title="Exalted Essence: Pillars of Creation",
        env_var="ESSENCE_PILLARS_PDF",
        page_count=213,
        anchor_page=51,
        anchor_text="UNIVERSAL CHARMS",
    ),
    "playersguide": Book(
        key="playersguide",
        title="Exalted Essence Player's Guide (draft manuscript)",
        env_var="ESSENCE_PLAYERSGUIDE_PDF",
        page_count=378,
        anchor_page=1,
        # Apostrophe-free: the title on page 1 uses a curly apostrophe.
        anchor_text="Draft Manuscript",
    ),
    "tomb": Book(
        key="tomb",
        title="Tomb of Memory: An Exalted Essence Jumpstart",
        env_var="ESSENCE_TOMB_PDF",
        page_count=83,
        anchor_page=41,
        anchor_text="CHAPTER TWO: TOMB OF MEMORY",
    ),
}


def open_book(key, override=None):
    """Resolve, verify and open one book. Returns (document, path)."""
    book = BOOKS[key]
    path = book.resolve(override)
    return book.verify(path), path


def add_pdf_argument(parser, key):
    parser.add_argument(
        "--pdf",
        help="Path to {}. Defaults to ${}".format(
            BOOKS[key].title, BOOKS[key].env_var),
    )
    return parser
