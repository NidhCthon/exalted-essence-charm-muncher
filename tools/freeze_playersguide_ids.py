"""Record the document ids the draft Player's Guide's charms were published with.

The packs now take the Player's Guide's charms from the final book, whose ids
would all differ: a supplement id hashes the book, section and page with the
name, and all three changed. build_items.py gives a final charm its draft id
instead when the same Exalt type had a charm of that name, so a world that
imported or dragged out a draft charm still finds it in the pack.

This writes tools/playersguide_ids.json: charm type and name, hashed, to the
draft id. It holds no book text, so it can be committed; run it once from a
build that still has data/playersguide.raw.json.
"""
import hashlib
import json
from pathlib import Path

from build_items import SECTION_TO_CHARMTYPE, doc_id

ROOT = Path(__file__).resolve().parent.parent
DRAFT = ROOT / "data" / "playersguide.raw.json"
OUT = Path(__file__).resolve().parent / "playersguide_ids.json"


# The final spells one draft name differently: a hyphen and a doubled s.
SPELLINGS = {"transsubstantiveegocompressionalgorithm": "transubstantiveegocompressionalgorithm"}


def match_key(section, name, any_type=False):
    """The draft and the final share a charm when its type and name match.

    The type rather than the section: the final splits the draft's Exigent
    Charms into March Lord and God-Admiral Charms, both of type exigent. With
    any_type, the key is the name alone, for a charm the final moved to
    another Exalt type (Wave-Breaking Gesture, Architect to God-Admiral).
    """
    charmtype = "*" if any_type else SECTION_TO_CHARMTYPE.get(section, "other")
    words = "".join(ch for ch in name.lower() if ch.isalnum())
    words = SPELLINGS.get(words, words)
    return hashlib.sha1("{}|{}".format(charmtype, words).encode("utf-8")).hexdigest()[:16]


def main():
    records = json.loads(DRAFT.read_text(encoding="utf-8"))
    ids, types_by_name = {}, {}
    # The draft repeats six names inside one section. The first by page keeps
    # its id; the final book prints each of them once.
    for record in sorted(records, key=lambda r: r["page"]):
        identifier = doc_id(record["name"], "playersguide", record["section"], record["page"])
        ids.setdefault(match_key(record["section"], record["name"]), identifier)
        types_by_name.setdefault(match_key(None, record["name"], any_type=True), {}).setdefault(
            SECTION_TO_CHARMTYPE.get(record["section"]), identifier)
    # A name-only key only where the draft used the name for a single type.
    for key, by_type in types_by_name.items():
        if len(by_type) == 1:
            ids[key] = next(iter(by_type.values()))
    OUT.write_text(json.dumps(ids, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("draft charms: {}   keys recorded: {}   written to {}".format(len(records), len(ids), OUT.name))


if __name__ == "__main__":
    main()
