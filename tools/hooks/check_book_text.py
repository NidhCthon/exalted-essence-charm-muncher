#!/usr/bin/env python3
"""Refuse commits that contain text from the books.

Book text reached this public repository twice through .gitignore mistakes -
once by naming files instead of patterns, once through an inline comment, which
git does not support. Reading .gitignore carefully caught neither. This checks
the thing that actually matters: whether the content being committed shares
verbatim runs of words with the text extracted from your PDFs.

How it decides
--------------
data/*.raw.json holds every string the extractors pulled out of the books. Each
is cut into overlapping 8-word windows ("shingles"). A file that shares 3 or
more shingles with the books - roughly ten consecutive verbatim words - is
refused. Charm names and short game phrases are well under eight words, so
they pass; a copied sentence or stat line does not.

It does not try to tell prose from stat lines. That distinction is a judgement,
and a heuristic making it silently is how the earlier leaks got through.
Instead, deliberate exceptions are recorded with --allow in
tools/hooks/book-text-allow.txt as SHA-1 prefixes of the matched shingles. A
hash cannot be read back into text, so the allowlist is safe to commit, and
every exception is a visible decision in history rather than a gap in a rule.

Matches are reported as path, line numbers and a count. Book text is never
printed.

Path rules run first and need no corpus: anything under data/ or module/, and
any *.raw.json, *.pdf or *.zip, is refused even if forced past .gitignore.

Modes
-----
  (default)   check what is staged - what the pre-commit hook runs
  --tree      check every tracked file
  --history   check every blob ever committed, on every ref
  --allow P   accept the current matches in tracked file P

A clone that has never run the extractors has no data/*.raw.json, so only the
path rules can run there. It says so on every commit rather than passing
silently.

Exit codes: 0 clean, 1 refused or found.
"""
import argparse
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

K = 8
THRESHOLD = 3
MAX_BYTES = 5_000_000
TOKEN = re.compile(r"[a-z0-9']+")
REFUSED_PATHS = ["data/*", "module/*", "*.raw.json", "*.pdf", "*.zip"]


def git(*args, binary=False):
    out = subprocess.run(["git", *args], capture_output=True, check=True).stdout
    return out if binary else out.decode("utf-8", "replace")


ROOT = Path(git("rev-parse", "--show-toplevel").strip())
ALLOW_FILE = ROOT / "tools" / "hooks" / "book-text-allow.txt"


def shingle_key(words):
    # SHA-1 rather than hash(): Python salts str hashes per process, and the
    # allowlist has to mean the same thing on every run and every machine.
    return hashlib.sha1(" ".join(words).encode("utf-8")).hexdigest()[:16]


def leaves(value):
    """Every string in an extracted record. A list of lines counts as one text,
    so a sentence broken across two PDF lines still matches as a sentence."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        if value and all(isinstance(v, str) for v in value):
            yield " ".join(value)
        else:
            for v in value:
                yield from leaves(v)
    elif isinstance(value, dict):
        for v in value.values():
            yield from leaves(v)


def load_corpus():
    corpus = set()
    for path in sorted((ROOT / "data").glob("*.raw.json")):
        for text in leaves(json.loads(path.read_text(encoding="utf-8"))):
            words = TOKEN.findall(text.lower())
            corpus.update(shingle_key(words[i:i + K])
                          for i in range(len(words) - K + 1))
    return corpus


def load_allowed():
    if not ALLOW_FILE.exists():
        return set()
    return {line.strip()
            for line in ALLOW_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")}


def find_matches(text, corpus, allowed):
    """Keys of shingles shared with the books, and the lines they start on."""
    lowered = text.lower()
    tokens = [(m.group(0), m.start()) for m in TOKEN.finditer(lowered)]
    found, lines = set(), set()
    for i in range(len(tokens) - K + 1):
        key = shingle_key([t for t, _ in tokens[i:i + K]])
        if key in corpus and key not in allowed:
            found.add(key)
            lines.add(lowered.count("\n", 0, tokens[i][1]) + 1)
    return found, sorted(lines)


def refused_path(name):
    return any(fnmatch.fnmatch(name, pattern) for pattern in REFUSED_PATHS)


def decode(data):
    if len(data) > MAX_BYTES:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None  # binary; not something prose hides in


def scan(items, corpus, allowed):
    """items: (label, path, fetch-bytes callable). Returns report lines."""
    problems = []
    for label, path, fetch in items:
        if refused_path(path):
            problems.append(f"  {label}: book-derived or generated path - never commit")
            continue
        if corpus is None:
            continue
        text = decode(fetch())
        if text is None:
            continue
        found, lines = find_matches(text, corpus, allowed)
        if len(found) >= THRESHOLD:
            shown = ", ".join(map(str, lines[:12])) + (" ..." if len(lines) > 12 else "")
            problems.append(f"  {label}: {len(found)} verbatim runs shared with "
                            f"the books (lines {shown})")
    return problems


def index_items(names):
    return [(n, n, lambda n=n: git("show", f":{n}", binary=True)) for n in names]


def staged_items():
    names = git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR").split("\0")
    return index_items([n for n in names if n])


def tree_items():
    return index_items([n for n in git("ls-files", "-z").split("\0") if n])


def history_items():
    seen = {}
    for line in git("rev-list", "--all", "--objects").splitlines():
        sha, _, path = line.partition(" ")
        if path and sha not in seen:
            seen[sha] = path
    return [(f"{path} (blob {sha[:8]})", path,
             lambda sha=sha: git("cat-file", "-p", sha, binary=True))
            for sha, path in seen.items()]


def allow(path, corpus, allowed):
    found, _ = find_matches(git("show", f":{path}"), corpus, allowed)
    if not found:
        print(f"{path}: nothing new to allow")
        return 0
    new_file = not ALLOW_FILE.exists()
    with ALLOW_FILE.open("a", encoding="utf-8", newline="\n") as out:
        if new_file:
            out.write("# SHA-1 prefixes of 8-word runs deliberately allowed to match the books.\n"
                      "# Written by tools/hooks/check_book_text.py --allow. Hashes, not text:\n"
                      "# safe to commit, and each block records one explicit decision.\n")
        out.write(f"# {path}\n")
        for key in sorted(found):
            out.write(key + "\n")
    print(f"{path}: allowed {len(found)} run(s). "
          f"Stage {ALLOW_FILE.relative_to(ROOT).as_posix()} too.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--tree", action="store_true")
    mode.add_argument("--history", action="store_true")
    mode.add_argument("--allow", metavar="PATH")
    args = parser.parse_args()

    corpus = load_corpus() or None
    if corpus is None:
        print("book-text check: no data/*.raw.json on this machine, so only the path "
              "rules ran. Content was NOT checked.", file=sys.stderr)
    allowed = load_allowed()

    if args.allow:
        if corpus is None:
            sys.exit("--allow needs data/*.raw.json to know what matches.")
        return allow(args.allow, corpus, allowed)

    if args.history:
        items, what = history_items(), "blobs in history"
    elif args.tree:
        items, what = tree_items(), "tracked files"
    else:
        items, what = staged_items(), "staged files"

    problems = scan(items, corpus, allowed)
    if not problems:
        if args.tree or args.history:
            print(f"clean: {len(items)} {what} checked")
        return 0

    if args.tree or args.history:
        print(f"Book text found in {len(problems)} of {len(items)} {what}:\n")
        print("\n".join(problems))
        return 1

    print("Refusing to commit: book text found.\n", file=sys.stderr)
    print("\n".join(problems), file=sys.stderr)
    print("\nThis repository is public and the books are copyrighted. Remove the text.\n"
          "If a match is deliberate - a stat line kept as a format example, say -\n"
          "accept it explicitly and stage the allowlist with it:\n"
          "    python tools/hooks/check_book_text.py --allow <path>", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
