"""Map extracted antagonist stat blocks onto Foundry `npc` Actor documents.

The system's NPC model lines up with the book's format almost field for field,
which is what makes this worth doing at all:

    pools.primary.value / .actions   <-  "Primary Pool (<n>): <actions>"
    health.levels                    <-  "Health Levels: <n>"
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

from build_weapons import weapon_items
from extract_battle_groups import parse_boxes

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "antagonists.raw.json"
OUT = ROOT / "data" / "packs" / "antagonists"

ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
NUMBER = re.compile(r"-?\d+")

# Some blocks print pools and defences and nothing else. Left empty those
# panels read as an import that failed rather than as a faithful one, so they
# say what the book does - and never invent what it does not print.
NO_QUALITIES = "None printed."
NO_DESCRIPTION = ("The book prints this as a stat block only - pools and "
                  "defences, with no description beside them.")
PARTIAL = ("STATS INCOMPLETE: this entry's stat block is interrupted in the "
           "book by other text, and its defensive values could not be read "
           "with confidence. The pools and anything else below are as "
           "printed; enter Defense, Soak, Hardness and Resolve from the page.")

GROUP_NOT_PRINTED = ("The book gives this battle group its Size, Drill, "
                     "Health and Qualities and nothing else, so its pools, "
                     "Defense, Soak and Resolve are left at zero rather than "
                     "borrowed from its commander.")


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


MODULE_ID = "exalted-essence-charms"
SPELLS = ROOT / "data" / "packs" / "sorcery-spells"

# Sorcerers and necromancers are the one kind of antagonist the books give a
# list of magic outright. Everything else on the qualities line is Qualities,
# which are their own mechanic and must not be matched against charm names.
SPELL_LIST_RE = re.compile(r"knows the following spells\s*:?\s*(.+)$", re.I)
# The sentence after the list runs straight on from it, because the full stop
# between them does not survive extraction. These end the list instead.
LIST_END_RE = re.compile(
    r"\b(?:and\s+|or\s+)?any other spell"
    r"|\b(?:she|he|they)\s+may\s+have\b", re.I)


def spell_key(name):
    """Match on words alone. An antagonist's list writes "Life Ending Wave"
    for a spell the sorcery chapter sets as "Life-Ending Wave"."""
    return re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()


def spell_index():
    """Spell name to document id, for linking. Empty if none were built."""
    if not SPELLS.exists():
        return {}
    index = {}
    for path in SPELLS.glob("*.json"):
        spell = json.loads(path.read_text(encoding="utf-8"))
        index[" ".join(spell_key(spell["name"]))] = spell["_id"]
    return index


def spell_links(entry, index):
    """Link the spells this antagonist is actually given.

    Only a printed "knows the following spells" list counts. Matching names
    anywhere in the text would attach a spell to any antagonist whose
    Qualities happen to share a name with one.

    Split on commas alone - one spell is "Baneful Sun and Shadow", so
    splitting on "and" as well would tear it in half.
    """
    found = SPELL_LIST_RE.search(entry.get("qualities", "") or "")
    if not found or not index:
        return ""

    listed = found.group(1)
    stop = LIST_END_RE.search(listed)
    if stop:
        listed = listed[:stop.start()]

    links = []
    for name in listed.split(","):
        name = re.sub(r"^and\s+", "", name.strip(" .,;:"), flags=re.I)
        if len(name) < 4:
            continue
        identifier = index.get(" ".join(spell_key(name)))
        if identifier:
            links.append("@UUID[Compendium.{}.sorcery-spells.Item.{}]{{{}}}"
                         .format(MODULE_ID, identifier, name))
        else:
            # Named but not in the pack - say so rather than link nothing.
            links.append("{} (not in the compendium)".format(html.escape(name)))
    if not links:
        return ""
    return "<h3>Spells</h3><p>{}</p>".format(", ".join(links))


def partial_import(entry):
    """Pools but no Defense: something interrupted the stat block."""
    return bool(entry.get("pools")) and "defense" not in entry.get("stats", {})


def biography(entry, spells=None):
    """Prose, the weapon line, the spell list, and any variants."""
    parts = list(entry["body"])
    if partial_import(entry):
        parts.insert(0, PARTIAL)
    if prints_stats_as_a_table(entry):
        parts.insert(0, "STATS NOT IMPORTED: this battle group prints its "
                        "Defense, Health, Soak, Drill and Size as a table, "
                        "which the extractor cannot read reliably. Enter them "
                        "from the book. The printed row follows.")
        parts.insert(1, entry.get("qualities", ""))

    weapon = entry.get("weapon")
    if weapon and not weapon_items(entry["name"], weapon):
        # Only as text when it could not be read as weapons - otherwise the
        # sheet would show the same thing twice.
        parts.append("Weapon: {}".format(weapon))

    blocks = to_html(parts)
    # A battle group boxed out beside this antagonist - their warship or
    # warband. It is a separate entity with its own stats, so it is kept as
    # text here rather than folded into the commander's numbers.
    sidebar = entry.get("sidebar")
    if sidebar:
        groups = parse_boxes(sidebar)
        if groups:
            # Imported as their own actors, so point at them instead of
            # printing the same numbers twice.
            named = ", ".join(group_name(entry, g) for g in groups)
            blocks += "<h3>Battle group printed alongside</h3>"
            blocks += to_html(["Imported separately as: {}.".format(named)])
        else:
            blocks += "<h3>Printed alongside</h3>"
            blocks += to_html([sidebar])
    for variant in entry.get("variants", []):
        blocks += "<h3>{}</h3>".format(html.escape(variant["name"]))
        blocks += to_html(variant["notes"])
    blocks += spell_links(entry, spells or {})
    return blocks or to_html([NO_DESCRIPTION])


TABLE_MARKERS = ("DRILL", "SIZE", "DEFENSE", "HEALTH", "SOAK")


def prints_stats_as_a_table(entry):
    """Battle groups print their stats as a table, not as labelled values.

    "QUALITIES DEFENSE HEALTH SOAK DRILL SIZE" sits on one row and the numbers
    on another, so a label-then-number parser reads neither. Rather than ship
    numbers borrowed from the surrounding text, these are flagged for a human.
    """
    qualities = entry.get("qualities", "") or ""
    return sum(1 for marker in TABLE_MARKERS if marker in qualities) >= 3


def build(entry, spells=None):
    stats = entry["stats"]
    pools = entry["pools"]
    identifier = doc_id(entry["name"], entry["book"], entry["page"])

    # An embedded document needs its own key, the way a top-level one does,
    # and the packer fails outright without it rather than skipping the
    # document quietly.
    weapons = weapon_items(entry["name"], entry.get("weapon", ""))
    for weapon in weapons:
        weapon["_key"] = "!actors.items!{}.{}".format(identifier, weapon["_id"])

    levels = number(stats.get("health levels"))
    tabled = prints_stats_as_a_table(entry)
    # A battle group is the entry that carries Size, or prints a Drill/Size
    # table.
    battlegroup = "size" in stats or tabled
    qualities = entry.get("qualities", "") or NO_QUALITIES
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
            "biography": biography(entry, spells),
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
            # Combat Reforged replaces Hardness with Poise and gives an
            # antagonist Poise equal to their Hardness. Leaving it unset left
            # every antagonist showing the system's default of 3 - and told
            # the turn panel the wrong number to Break them on.
            "poise": {
                "value": number(stats.get("hardness")),
                "min": 0,
                "max": number(stats.get("hardness")),
            },
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
            # Foundry v14 requires a number here; 1 is TokenDocument's own
            # initial. Leaving it out makes every deploy log a validation
            # warning per actor until Foundry migrates the record.
            "depth": 1,
        },
        "items": weapons,
        "effects": [],
        "folder": None,
        "sort": 0,
        "ownership": {"default": 0},
        "flags": {},
    }


def group_name(entry, box):
    """Name a battle group after the commander the book prints for it.

    Naming it after the antagonist it sits beside would be a guess: a group
    can be boxed next to one character while another commands it, and one
    page prints a group whose commander is given as none at all.
    """
    if box["commander"]:
        return "{}'s Battle Group".format(box["commander"])
    return "Battle Group ({} p{})".format(entry["book"], entry["page"])


def build_group(entry, box, index):
    """A battle group as its own actor.

    The box prints Size, Drill, Commander and Qualities and nothing else, so
    Defense, Soak and the rest stay zero rather than borrowing the
    commander's. The box's own text is kept in the biography so nothing that
    was printed is lost.
    """
    name = group_name(entry, box)
    identifier = doc_id("{}#{}".format(name, index), entry["book"], entry["page"])
    notes = ["Printed beside {} ({} p{}).".format(
        entry["name"], entry["book"], entry["page"])]
    if box["drill_name"]:
        notes.append("Drill: {} (+{}).".format(box["drill_name"], box["drill"]))
    notes.append(box["text"])
    notes.append(GROUP_NOT_PRINTED)

    return {
        "_id": identifier,
        "_key": "!actors!{}".format(identifier),
        "name": name,
        "type": "npc",
        "img": "icons/svg/mystery-man.svg",
        "system": {
            "biography": to_html(notes),
            "pagenum": str(entry["page"]),
            "creaturetype": "mortal",
            "battlegroup": True,
            "pools": {
                "primary": {"value": 0, "actions": ""},
                "secondary": {"value": 0, "actions": ""},
                "tertiary": {"value": 0, "actions": ""},
            },
            "health": {
                "value": 0, "min": 0, "max": box["health"],
                "levels": box["health"], "lethal": 0, "aggravated": 0,
                "penalty": 0,
            },
            "defense": {"value": 0},
            "soak": {"value": 0},
            "hardness": {"value": 0},
            # Battle groups have no Poise at all under Combat Reforged.
            "poise": {"value": 0, "min": 0, "max": 0},
            "resolve": {"value": 0},
            "essence": {"value": 1},
            "size": {"value": box["size"]},
            "drill": {"value": box["drill"]},
            "commandbonus": {"value": 0},
            "qualities": box["qualities"] or NO_QUALITIES,
        },
        "prototypeToken": {
            "name": name,
            "actorLink": False,
            "disposition": -1,
            "sight": {"enabled": False},
            "depth": 1,
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
    spells = spell_index()
    actors = [build(e, spells) for e in entries]
    for entry in entries:
        for index, box in enumerate(parse_boxes(entry.get("sidebar", ""))):
            actors.append(build_group(entry, box, index))

    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.json"):
        stale.unlink()
    for actor in actors:
        (OUT / "{}.json".format(actor["_id"])).write_text(
            json.dumps(actor, indent=2, ensure_ascii=False), encoding="utf-8")

    armed = sum(1 for a in actors if a["items"])
    weapons = sum(len(a["items"]) for a in actors)
    print("weapons as items      : {} on {} actors".format(weapons, armed))
    partial = sum(1 for e in entries if partial_import(e))
    print("flagged as incomplete : {}".format(partial))
    linked = sum(1 for a in actors if "@UUID[" in a["system"]["biography"])
    print("actors written : {}".format(len(actors)))
    print("spell lists    : {} linked from {} spells indexed".format(
        linked, len(spells)))
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
