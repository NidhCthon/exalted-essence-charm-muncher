"""Map extracted antagonist stat blocks onto Foundry `npc` Actor documents.

The system's NPC model lines up with the book's format almost field for field,
which is what makes this worth doing at all:

    pools.primary.value / .actions   <-  "Primary Pool (9): Athletics and Combat"
    health.levels                    <-  "Health Levels: 5"
    defense / soak / hardness / resolve / essence
    battlegroup / size / drill / commandbonus
    qualities                        <-  a plain string, so no linking needed

Variants ("increase pools by two") are deltas written in prose, not stat
blocks. They are kept in the biography of the antagonist they modify rather
than generated as separate actors with numbers nobody printed.
"""
import hashlib
import html
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "antagonists.raw.json"
OUT = ROOT / "data" / "packs" / "antagonists"

ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
NUMBER = re.compile(r"-?\d+")


def doc_id(name, book, page):
    key = "npc:{}:{}:{}".format(book, page, name)
    n = int(hashlib.sha1(key.encode("utf-8")).hexdigest(), 16)
    out = []
    for _ in range(16):
        n, rem = divmod(n, len(ALPHABET))
        out.append(ALPHABET[rem])
    return "".join(out)


def number(value, default=0):
    """First integer in a field: "1 (2 for artisans)" is a 1 with a caveat."""
    if value is None:
        return default
    match = NUMBER.search(str(value))
    return int(match.group(0)) if match else default


def to_html(paragraphs):
    return "".join("<p>{}</p>".format(html.escape(p)) for p in paragraphs if p)


def biography(entry):
    """Prose, the weapon line, and any variants, in that order."""
    parts = list(entry["body"])
    if prints_stats_as_a_table(entry):
        parts.insert(0, "STATS NOT IMPORTED: this battle group prints its "
                        "Defense, Health, Soak, Drill and Size as a table, "
                        "which the extractor cannot read reliably. Enter them "
                        "from the book. The printed row follows.")
        parts.insert(1, entry.get("qualities", ""))

    weapon = entry.get("weapon")
    if weapon:
        parts.append("Weapon: {}".format(weapon))

    blocks = to_html(parts)
    for variant in entry.get("variants", []):
        blocks += "<h3>{}</h3>".format(html.escape(variant["name"]))
        blocks += to_html(variant["notes"])
    return blocks


TABLE_MARKERS = ("DRILL", "SIZE", "DEFENSE", "HEALTH", "SOAK")


def prints_stats_as_a_table(entry):
    """Battle groups print their stats as a table, not as labelled values.

    "QUALITIES DEFENSE HEALTH SOAK DRILL SIZE" sits on one row and the numbers
    on another, so a label-then-number parser reads neither. Rather than ship
    numbers borrowed from the surrounding text, these are flagged for a human.
    """
    qualities = entry.get("qualities", "") or ""
    return sum(1 for marker in TABLE_MARKERS if marker in qualities) >= 3


def build(entry):
    stats = entry["stats"]
    pools = entry["pools"]
    identifier = doc_id(entry["name"], entry["book"], entry["page"])

    levels = number(stats.get("health levels"))
    tabled = prints_stats_as_a_table(entry)
    # A battle group is the entry that carries Size, or prints a Drill/Size
    # table.
    battlegroup = "size" in stats or tabled
    qualities = entry.get("qualities", "")
    if tabled:
        # Its numbers could only have come from neighbouring prose, so do not
        # pretend to know them.
        stats = {}
        levels = 0

    def pool(kind):
        got = pools.get(kind, {})
        return {
            "value": number(got.get("value")),
            "actions": got.get("actions", "")
        }

    return {
        "_id": identifier,
        "_key": "!actors!{}".format(identifier),
        "name": entry["name"],
        "type": "npc",
        "img": "icons/svg/mystery-man.svg",
        "system": {
            "biography": biography(entry),
            "pagenum": str(entry["page"]),
            "creaturetype": "mortal",
            "battlegroup": battlegroup,
            "pools": {
                "primary": pool("primary"),
                "secondary": pool("secondary"),
                "tertiary": pool("tertiary"),
            },
            "health": {
                "value": 0,
                "min": 0,
                "max": levels,
                "levels": levels,
                "lethal": 0,
                "aggravated": 0,
                "penalty": 0,
            },
            "defense": {"value": number(stats.get("defense", stats.get("defence")))},
            "soak": {"value": number(stats.get("soak"))},
            "hardness": {"value": number(stats.get("hardness"))},
            "resolve": {"value": number(stats.get("resolve"))},
            "essence": {"value": number(stats.get("essence"), 1)},
            "size": {"value": number(stats.get("size"))},
            "drill": {"value": number(stats.get("drill"))},
            "commandbonus": {"value": number(stats.get("command"))},
            "qualities": qualities,
        },
        "prototypeToken": {
            "name": entry["name"],
            "actorLink": False,
            "disposition": -1,
            "sight": {"enabled": False},
        },
        "items": [],
        "effects": [],
        "folder": None,
        "sort": 0,
        "ownership": {"default": 0},
        "flags": {},
    }


def main():
    entries = json.loads(SRC.read_text(encoding="utf-8"))
    actors = [build(e) for e in entries]

    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.json"):
        stale.unlink()
    for actor in actors:
        (OUT / "{}.json".format(actor["_id"])).write_text(
            json.dumps(actor, indent=2, ensure_ascii=False), encoding="utf-8")

    print("actors written : {}".format(len(actors)))
    print("ids unique     : {}".format(
        len({a["_id"] for a in actors}) == len(actors)))
    dupes = [n for n, k in Counter(a["name"] for a in actors).items() if k > 1]
    print("duplicate names: {}  {}".format(len(dupes), dupes[:4]))
    print("battle groups  : {}".format(
        sum(1 for a in actors if a["system"]["battlegroup"])))
    print("with qualities : {}".format(
        sum(1 for a in actors if a["system"]["qualities"])))
    for field in ("defense", "soak", "hardness", "resolve"):
        zero = sum(1 for a in actors if not a["system"][field]["value"])
        print("  {:9s} zero on {} of {}".format(field, zero, len(actors)))
    print("  health 0   on {} of {}".format(
        sum(1 for a in actors if not a["system"]["health"]["levels"]), len(actors)))
    print()
    print("sample:")
    for a in actors[:6]:
        s = a["system"]
        print("  {:34s} pool {:<3} def {:<3} soak {:<3} hp {:<3} {}".format(
            a["name"][:32], s["pools"]["primary"]["value"], s["defense"]["value"],
            s["soak"]["value"], s["health"]["levels"],
            "battlegroup" if s["battlegroup"] else ""))


if __name__ == "__main__":
    main()
