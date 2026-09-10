"""Build LevelDB compendium packs and the module manifest.

Foundry v11+ stores compendia as LevelDB directories, so the per-document JSON
under data/packs/ is compiled with Foundry's own CLI rather than written by
hand. Regenerating is safe: document _ids are derived from charm names, so a
rebuild updates entries in place instead of duplicating them.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "packs"
MODULE = ROOT / "module"
CLI = ROOT / "node_modules" / "@foundryvtt" / "foundryvtt-cli" / "fvtt.mjs"

MODULE_ID = "exalted-essence-charms"
SYSTEM_ID = "exaltedessence"

LABELS = {
    "universal-charms": "Essence: Universal Charms",
    "exalted-charms": "Essence: Exalted Charms",
    "solar-charms": "Essence: Solar Charms",
    "lunar-charms": "Essence: Lunar Charms",
    "abyssal-charms": "Essence: Abyssal Charms",
    "alchemical-charms": "Essence: Alchemical Charms",
    "dragon-blooded-charms": "Essence: Dragon-Blooded Charms",
    "getimian-charms": "Essence: Getimian Charms",
    "infernal-charms": "Essence: Infernal Charms",
    "liminal-charms": "Essence: Liminal Charms",
    "sidereal-charms": "Essence: Sidereal Charms",
    "strawmaiden-janest-charms": "Essence: Strawmaiden Janest Charms",
    "martial-arts": "Essence: Martial Arts",
    "evocations": "Essence: Evocations & Hearthstones",
    "sorcery-spells": "Essence: Sorcery & Necromancy Spells",
    "shaping-rituals": "Essence: Shaping Rituals",
}


def build_pack(name):
    """Compile one directory of JSON documents into a LevelDB pack."""
    result = subprocess.run(
        [
            "node", str(CLI), "package", "pack",
            "--id", MODULE_ID,
            "--type", "Module",
            "-n", name,
            "--in", str(SRC / name),
            "--out", str(MODULE / "packs"),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit("pack failed: {}".format(name))
    return sum(1 for _ in (SRC / name).glob("*.json"))


def main():
    if not CLI.exists():
        raise SystemExit("Foundry CLI missing - run: npm install")
    names = sorted(d.name for d in SRC.iterdir() if d.is_dir())

    packs, total = [], 0
    for name in names:
        count = build_pack(name)
        total += count
        packs.append({
            "name": name,
            "label": LABELS.get(name, name),
            "path": "packs/{}".format(name),
            "type": "Item",
            "system": SYSTEM_ID,
            "ownership": {"PLAYER": "OBSERVER", "ASSISTANT": "OWNER"},
        })
        print("  {:4d}  {}".format(count, name))

    manifest = {
        "id": MODULE_ID,
        "title": "Exalted Essence - Charms",
        "description": (
            "Charms, Martial Arts, and Evocations from Exalted Essence as "
            "drag-and-drop compendium items for the Exalted Essence system."
        ),
        "version": "0.2.0",
        "compatibility": {"minimum": "14", "verified": "14"},
        "authors": [{"name": "NidhCthon"}],
        "relationships": {
            "systems": [{
                "id": SYSTEM_ID,
                "type": "system",
                "compatibility": {"minimum": "3.0.0"},
            }]
        },
        "packs": packs,
    }
    (MODULE / "module.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print("\n{} packs, {} items".format(len(packs), total))
    print("manifest: {}".format(MODULE / "module.json"))


if __name__ == "__main__":
    main()
