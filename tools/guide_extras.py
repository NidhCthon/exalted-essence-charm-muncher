"""Fold the final Player's Guide's modes and errata into the charms they name.

extract_pg_final.py writes data/pgfinal_modes.raw.json (new Exalt-type riders
for charms in the core book and Pillars) and data/pgfinal_errata.raw.json (the
appendix's Charm Clarifications and Updates). fold() appends each to the raw
charm records it names, so every consumer sees the same rules: build_items.py
for the Foundry packs, and the Essence Charm Forge for its reference set.

- A mode becomes a rider paragraph in the books' own form, "Mode Name (March
  Lord): ...". An unnamed mode becomes "Architect mode: ...".
- An erratum becomes "Player's Guide update: ..." or "Player's Guide
  clarification: ...". An update that restates the cost ("Spend 1 mote instead
  of 2") also sets record["cost_override"], since the cost parser reads the
  first cost sentence, which is still the book's original.
- The base cost still comes from the book's own text: fold() keeps it in
  record["cost_text"] before appending anything, because a mode's cost ("The
  March Lord commits a mote") is paid only when that mode is used, and the cost
  parser would otherwise count it as the charm's.
- Names the Player's Guide shortens are aliased ("Ox Body" is Ox-Body
  Technique). An entry whose charm is not among the records (the Excellency
  rule, a spell) is returned as unplaced.
"""
import json
import re
from pathlib import Path

from build_items import parse_cost

DATA = Path(__file__).resolve().parent.parent / "data"
ALIASES = {"ox body": "ox body technique"}


def name_key(name):
    key = re.sub(r"\s+", " ", name.replace("-", " ").replace("’", "'")).strip().lower()
    return ALIASES.get(key, key)


def load(stem):
    path = DATA / "{}.raw.json".format(stem)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def mode_text(mode):
    exalt = (mode.get("section") or "").replace(" Charms", "")
    first, rest = mode["body"][0], mode["body"][1:]
    if mode.get("mode") and not mode.get("tag"):
        first = "{} ({}):{}".format(mode["mode"], exalt, first[len(mode["mode"]) + 1:])
    elif not mode.get("mode"):
        first = "{} mode: {}".format(exalt, first)
    return [first] + rest


def erratum_text(erratum):
    return ["Player's Guide {}{}".format(line[0].lower(), line[1:]) if n == 0 else line
            for n, line in enumerate(erratum["body"])]


def fold(records, modes=None, errata=None):
    """Append modes and errata to the records they name; returns what had no record.

    records: raw charm records (name, section, prerequisite, body), changed in
    place. modes, errata: the extracted entries, read from data/ when omitted.
    """
    modes = load("pgfinal_modes") if modes is None else modes
    errata = load("pgfinal_errata") if errata is None else errata
    by_name = {}
    for record in records:
        by_name.setdefault(name_key(record["name"]), []).append(record)
    unplaced = []
    for kind, entries, text_of in (("mode", modes, mode_text), ("erratum", errata, erratum_text)):
        for entry in entries:
            text = text_of(entry)
            for ref in entry["charms"]:
                targets = by_name.get(name_key(ref["name"]))
                if not targets:
                    unplaced.append("{} for {}".format(kind, ref["name"]))
                for record in targets or []:
                    record.setdefault("cost_text", " ".join(record["body"]))
                    record["body"] = list(record["body"]) + text
                    if kind == "erratum":
                        record["errata"] = True
                        restated = parse_cost(" ".join(entry["body"]))
                        if "instead" in " ".join(entry["body"]) and any(
                                restated[k] for k in ("motes", "committed", "anima", "power")):
                            record["cost_override"] = {k: restated[k] for k in ("motes", "committed", "anima", "power")}
    return unplaced
