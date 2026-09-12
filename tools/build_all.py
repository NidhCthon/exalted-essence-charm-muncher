"""Run the whole pipeline: PDFs in, Foundry module out.

Stages run in a fixed order because build_items.py clears data/packs/ before
writing, so the sorcery builder has to follow it and the pack compiler has to
come last.

Books are optional. Give the ones you own; the rest are skipped and their
packs simply do not appear in the manifest.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent

# (script, book key or None, description)
EXTRACTORS = [
    ("extract.py", "core", "core rulebook charms"),
    ("extract_sorcery.py", "core", "core spells and shaping rituals"),
    ("extract_pillars.py", "pillars", "Pillars of Creation charms"),
    ("extract_sorcery_pillars.py", "pillars", "Pillars spells and shaping rituals"),
    ("extract_pg.py", "playersguide", "Player's Guide charms"),
]
BUILDERS = [
    ("build_items.py", "map charms to Foundry Items"),
    ("build_sorcery.py", "map spells and rituals to Foundry Items"),
    # After the spells, because it links the ones an antagonist is given.
    ("build_antagonists.py", "map antagonists to Foundry Actors"),
    ("build_artifacts.py", "map artifacts to Foundry weapon and armor Items"),
    ("build_packs.py", "compile LevelDB packs and the manifest"),
]

# Extractors that read several books at once rather than one.
MULTI_BOOK = [
    ("extract_antagonists.py", ("core", "pillars", "tomb"),
     "antagonists from every book"),
    ("extract_artifacts.py", ("core", "pillars"), "artifacts"),
]

ENV_VARS = {
    "core": "ESSENCE_CORE_PDF",
    "pillars": "ESSENCE_PILLARS_PDF",
    "playersguide": "ESSENCE_PLAYERSGUIDE_PDF",
    "tomb": "ESSENCE_TOMB_PDF",
}


def run(script, args=()):
    result = subprocess.run([sys.executable, str(TOOLS / script), *args],
                            cwd=TOOLS)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key, var in ENV_VARS.items():
        parser.add_argument("--{}".format(key),
                            help="Path to that PDF (default: ${})".format(var))
    parser.add_argument("--skip-missing", action="store_true", default=True,
                        help="Skip books with no PDF instead of failing")
    args = parser.parse_args()
    supplied = {k: getattr(args, k) for k in ENV_VARS}

    # Clear previous output first. The builders consume whatever raw files
    # they find on disk, so leftovers from an earlier run with more books
    # would silently reappear in a build meant to contain fewer.
    data = TOOLS.parent / "data"
    for stale in list(data.glob("*.raw.json")):
        stale.unlink()
    for tree in (data / "packs", TOOLS.parent / "module" / "packs"):
        if tree.exists():
            shutil.rmtree(tree)

    ran, skipped = [], []
    for script, book, description in EXTRACTORS:
        path = supplied.get(book) or os.environ.get(ENV_VARS[book])
        if not path:
            skipped.append(description)
            continue
        print("\n=== {} ===".format(description))
        if not run(script, ["--pdf", path]):
            sys.exit("failed: {}".format(script))
        ran.append(description)

    for script, books, description in MULTI_BOOK:
        available = [b for b in books
                     if supplied.get(b) or os.environ.get(ENV_VARS[b])]
        if not available:
            skipped.append(description)
            continue
        print("\n=== {} ===".format(description))
        arguments = []
        for book in available:
            path = supplied.get(book)
            if path:
                arguments += ["--{}".format(book), path]
        if not run(script, arguments):
            sys.exit("failed: {}".format(script))
        ran.append(description)

    if not ran:
        sys.exit(
            "No PDFs supplied, so there is nothing to extract.\n"
            "Set at least {} or pass --core <path>.".format(ENV_VARS["core"])
        )

    for script, description in BUILDERS:
        print("\n=== {} ===".format(description))
        if not run(script):
            sys.exit("failed: {}".format(script))

    print("\n" + "=" * 58)
    print("done. extracted: {}".format(", ".join(ran)))
    if skipped:
        print("skipped (no PDF): {}".format(", ".join(skipped)))
    print("module is in module/ - copy it into your Foundry")
    print("Data/modules/ directory as exalted-essence-charms/")


if __name__ == "__main__":
    main()
