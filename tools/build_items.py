"""Map extracted charm records onto Exalted Essence Foundry Item documents.

Enum values (charmtype, ability) come from the system's own module/config.js,
so sheet dropdowns resolve instead of rendering blank. Document _ids are
derived from the charm name, which keeps them stable across rebuilds - a
re-import updates existing entries rather than duplicating them.
"""
import hashlib
import html
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "charms.raw.json"
OUT = ROOT / "data" / "packs"

# module/config.js -> ExEss.CharmTypes
SECTION_TO_CHARMTYPE = {
    # "universal" exists only from system 3.x (Foundry v14); on the 2.x line
    # these fell back to "other".
    "Universal Charms": "universal",
    "Exalted Charms": "universal",
    "Abyssal Charms": "abyssal",
    "Alchemical Charms": "alchemical",
    "Dragon-Blooded Charms": "dragonblooded",
    "Getimian Charms": "getimian",
    "Infernal Charms": "infernal",
    "Liminal Charms": "liminal",
    "Lunar Charms": "lunar",
    "Sidereal Charms": "sidereal",
    "Solar Charms": "solar",
    "Strawmaiden Janest Charms": "janest",
    "Martial Arts": "martialarts",
    "Artifacts": "evocation",
    "Manses and Demesnes": "evocation",
    "Hearthstones": "evocation",
    # Pillars of Creation. Its six extra Exalt types all already exist in the
    # system's CharmTypes enum, so none of them need a fallback.
    "Dragon Blooded Charms": "dragonblooded",
    "Exigent Charms": "exigent",
    "Architect Charms": "architect",
    "Sovereign Charms": "sovereign",
    "Dragon King Charms": "dragonking",
    "Dream-Souled Charms": "dreamsouled",
    "Umbral Charms": "umbral",
    "Martial Arts: Scattered Lotus Petals": "martialarts",
    "Sidereal Martial Arts": "martialarts",
    "Warstriders": "evocation",
}

# Sections that share a pack with a differently-named section elsewhere.
PACK_ALIASES = {
    "Dragon Blooded Charms": "dragon-blooded-charms",
    "Martial Arts: Scattered Lotus Petals": "martial-arts",
    "Warstriders": "evocations",
}

# module/config.js -> ExEss.Abilities
TRAIT_TO_ABILITY = {
    "athletics": "athletics",
    "awareness": "awareness",
    "close combat": "close",
    "close": "close",
    "craft": "craft",
    "embassy": "embassy",
    "integrity": "integrity",
    "navigate": "navigate",
    "performance": "performance",
    "physique": "physique",
    "presence": "presence",
    "ranged combat": "ranged",
    "ranged": "ranged",
    "sagacity": "sagacity",
    "stealth": "stealth",
    "war": "war",
    "force": "force",
    "finesse": "finesse",
    "fortitude": "fortitude",
    "martial arts": "martial",
}

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

TRAIT_RE = re.compile(r"^(?P<trait>[A-Za-z][A-Za-z ]*?)\s+(?P<rank>\d)$")
COST_RE = re.compile(
    r"\b(?P<verb>Spend|Commit|Pay)\s+(?P<amount>\d+|one|two|three|four|five)\s+"
    r"(?P<resource>motes?|[Aa]nima|[Pp]ower|[Ww]illpower)\b"
)
COST_RE_ANYCASE = re.compile(COST_RE.pattern, re.IGNORECASE)
CHARM_NAME_RE = re.compile(r"^[A-Z][A-Za-z'\-]+(?: [A-Za-z'\-]+)*$")
ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def doc_id(name, book=None, section=None, page=None):
    """Foundry needs a 16-char alphanumeric id; derive it from the name.

    Supplements are namespaced because names are not unique. "Shadow Cloak
    Technique" appears in both the core rulebook and Pillars of Creation, and
    the Player's Guide reuses six names across Exalt types, so the section
    joins the key too. A bare name hash silently drops one of each pair. Core
    ids stay unnamespaced so already-published packs keep their ids.
    """
    if book in (None, "core"):
        key = name
    else:
        # Page joins the key because the Player's Guide repeats six names
        # inside a single section, which book+section alone cannot separate.
        key = "{}:{}:{}:{}".format(book, section or "", page or "", name)
    n = int(hashlib.sha1(key.encode("utf-8")).hexdigest(), 16)
    out = []
    for _ in range(16):
        n, rem = divmod(n, len(ALPHABET))
        out.append(ALPHABET[rem])
    return "".join(out)


def parse_prerequisite(text):
    """Split a prerequisite line into ability/rank, Essence, and named charms.

    Handles a single trait and value, a comma-separated list of them, an
    "Grand Eruption, Sagacity 4", and "None".
    """
    ability, requirement, essence, charms = None, 0, 0, []
    if not text or text.strip().lower().startswith("none"):
        return ability, requirement, essence, charms

    for part in re.split(r",|\band\b(?=\s+[A-Z])", text):
        part = part.strip().rstrip(".")
        if not part:
            continue
        # Alternatives take two forms: "Force 3 or Fortitude 3" repeats the
        # rank, while "Embassy or Presence 4" states it only once at the end.
        # Either way we take the first named trait, and fall back to the last
        # alternative's rank when the first carries none.
        alternatives = [a.strip() for a in re.split(r"\bor\b", part) if a.strip()]
        first = alternatives[0]
        match = TRAIT_RE.match(first)
        if match is None and len(alternatives) > 1:
            tail = TRAIT_RE.match(alternatives[-1])
            if tail and first.lower() in TRAIT_TO_ABILITY:
                match = TRAIT_RE.match("{} {}".format(first, tail.group("rank")))
        if match:
            trait = match.group("trait").strip().lower()
            rank = int(match.group("rank"))
            if trait == "essence":
                essence = rank
            elif trait in TRAIT_TO_ABILITY and ability is None:
                ability, requirement = TRAIT_TO_ABILITY[trait], rank
            continue
        # Anything title-cased that is not a trait is a prerequisite charm.
        if CHARM_NAME_RE.match(first):
            charms.append({"id": "", "name": first})
    return ability, requirement, essence, charms


def parse_cost(body_text):
    """Pull the first mote/anima/power cost out of the mechanical prose."""
    cost = {
        "motes": 0,
        "committed": 0,
        "anima": 0,
        "health": 0,
        "healthtype": "bashing",
        "stunt": 0,
        "power": 0,
    }
    seen = set()
    # A capitalised verb starts the sentence that states the actual cost, so
    # trust that pass first. Only then sweep case-insensitively to pick up
    # trailing clauses like "...and commit 1 mote", without letting a
    # lower-case mention in flavour text outrank the real cost line.
    for pattern in (COST_RE, COST_RE_ANYCASE):
        for match in pattern.finditer(body_text):
            verb = match.group("verb").lower()
            resource = match.group("resource").lower().rstrip("s")
            raw = match.group("amount").lower()
            amount = NUMBER_WORDS.get(raw) or int(raw)
            if resource == "mote":
                key = "committed" if verb == "commit" else "motes"
            elif resource in ("anima", "power"):
                key = resource
            else:
                continue
            if key not in seen:
                cost[key] = amount
                seen.add(key)
    return cost


def to_html(paragraphs):
    return "".join("<p>{}</p>".format(html.escape(p)) for p in paragraphs)


def build(record):
    ability, requirement, essence, prereq_charms = parse_prerequisite(
        record["prerequisite"]
    )
    charmtype = SECTION_TO_CHARMTYPE.get(record["section"], "other")
    if ability is None:
        ability = "evocation" if charmtype == "evocation" else "other"
    identifier = doc_id(record["name"], record.get("book"),
                        record.get("section"), record.get("page"))
    return {
        "_id": identifier,
        # Foundry's CLI derives each LevelDB key from _key and silently skips
        # documents that lack it, producing an empty pack.
        "_key": "!items!{}".format(identifier),
        "name": record["name"],
        "type": "charm",
        "img": "icons/svg/aura.svg",
        "system": {
            "description": to_html(record["body"]),
            "pagenum": str(record["page"]),
            "activatable": False,
            "active": False,
            "autoaddtorolls": "",
            "endtrigger": "none",
            "cost": parse_cost(" ".join(record["body"])),
            "gain": {"motes": 0, "anima": 0, "health": 0, "power": 0},
            "charmtype": charmtype,
            "ability": ability,
            "requirement": requirement,
            "essence": essence,
            "prerequisites": record["prerequisite"],
            "charmprerequisites": prereq_charms,
            # Added by system 3.x. The DataModel would default these, but
            # writing them keeps stored documents matching the live schema.
            "listingname": "",
            "modes": {},
            "triggers": {"dicerollertriggers": {}},
        },
        "effects": [],
        "folder": None,
        "sort": 0,
        "ownership": {"default": 0},
        "flags": {},
    }


def pack_name(section):
    if section in PACK_ALIASES:
        return PACK_ALIASES[section]
    if SECTION_TO_CHARMTYPE.get(section) == "evocation":
        return "evocations"
    return re.sub(r"[^a-z0-9]+", "-", section.lower()).strip("-")


SOURCES = [
    ("core", SRC),
    ("pillars", ROOT / "data" / "pillars.raw.json"),
    ("playersguide", ROOT / "data" / "playersguide.raw.json"),
]


# Two prerequisite lines spell a charm differently from that charm's own
# heading, so the pill cannot find it. Both are in the same pack as the charm
# that needs them and both are unmistakable, so they are corrected here.
#
# A third is left alone: "Silken Rope Trick" requires "Eternal Infatuation
# Depths, Into Infinite Depths", and no charm has the first name. The likely
# referent is "Eternal Infatuation Dance", with "Depths" carried over from
# the name beside it - but likely is not certain, and a pill that opens the
# wrong charm is worse than a line of text that names the right one.
PREREQUISITE_NAME_FIXES = {
    "ghostly sentinel technic": "Ghostly Sentinel Technique",
    "blood-and-glory exhoration": "Blood-and-Glory Exhortation",
}


def link_prerequisites(packs):
    """Point each prerequisite pill at the charm it names.

    build() records a named prerequisite as a pill with no id, which the
    sheet renders but cannot open. The system resolves a pill by looking the
    id up in the pack the charm itself belongs to, so only a prerequisite in
    the same pack can resolve - and one prerequisite in the books names a
    charm from another pack.

    A pill that cannot resolve is worse than no pill: it renders as something
    to click that errors. Those are dropped, and the name stays in the
    prerequisites text where it was already written, so nothing is lost.
    """
    def key(text):
        # A prerequisite does not always hyphenate a charm's name the way the
        # charm's own heading does, so match on the words alone.
        return re.sub(r"[^a-z0-9]", "", text.lower())

    linked, dropped = 0, []
    for name, items in packs.items():
        index = {}
        for item in items:
            index.setdefault(key(item["name"]), (item["_id"], item["name"]))

        for item in items:
            pills = item["system"].get("charmprerequisites") or []
            resolved = []
            for pill in pills:
                named = PREREQUISITE_NAME_FIXES.get(
                    pill["name"].strip().lower(), pill["name"])
                found = index.get(key(named))
                if found and found[0] != item["_id"]:
                    # Labelled with the charm's own name rather than the
                    # spelling the prerequisite line used: the two differ in
                    # hyphenation often enough that a pill would otherwise
                    # open a charm it does not appear to name.
                    resolved.append({"id": found[0], "name": found[1]})
                    linked += 1
                else:
                    dropped.append((item["name"], pill["name"]))
            item["system"]["charmprerequisites"] = resolved
    return linked, dropped


def main():
    packs = {}
    for book, path in SOURCES:
        if not path.exists():
            print("skipping missing source: {}".format(path))
            continue
        for record in json.loads(path.read_text(encoding="utf-8")):
            record.setdefault("book", book)
            packs.setdefault(pack_name(record["section"]), []).append(build(record))

    linked, dropped = link_prerequisites(packs)
    print("prerequisite pills linked : {}".format(linked))
    print("  dropped as unresolvable : {}  {}".format(
        len(dropped), dropped[:2]))

    if OUT.exists():
        for stale in OUT.rglob("*.json"):
            stale.unlink()
    for name, items in packs.items():
        directory = OUT / name
        directory.mkdir(parents=True, exist_ok=True)
        for item in items:
            path = directory / "{}.json".format(item["_id"])
            path.write_text(
                json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    total = sum(len(v) for v in packs.values())
    every = [item for items in packs.values() for item in items]
    print("packs: {}   items: {}".format(len(packs), total))
    for name, items in sorted(packs.items()):
        print("  {:4d}  {}".format(len(items), name))

    def count(predicate):
        return sum(1 for item in every if predicate(item["system"]))

    print("")
    print("ids unique        : {}".format(len({i["_id"] for i in every}) == total))
    print("ability 'other'   : {}".format(count(lambda s: s["ability"] == "other")))
    print("requirement 0     : {}".format(count(lambda s: s["requirement"] == 0)))
    print("essence set       : {}".format(count(lambda s: s["essence"] > 0)))
    print("zero cost         : {}".format(count(
        lambda s: not any(s["cost"][k] for k in ("motes", "committed", "anima", "power"))
    )))
    print("has charm prereqs : {}".format(count(lambda s: s["charmprerequisites"])))
    print("charmtypes        : {}".format(
        dict(Counter(i["system"]["charmtype"] for i in every))
    ))


if __name__ == "__main__":
    main()
