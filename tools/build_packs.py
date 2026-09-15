"""Build LevelDB compendium packs and the module manifest.

Foundry v11+ stores compendia as LevelDB directories, so the per-document JSON
under data/packs/ is compiled with Foundry's own CLI rather than written by
hand. Regenerating is safe: document _ids are derived from charm names, so a
rebuild updates entries in place instead of duplicating them.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "packs"
MODULE = ROOT / "module"
CLI = ROOT / "node_modules" / "@foundryvtt" / "foundryvtt-cli" / "fvtt.mjs"

MODULE_ID = "exalted-essence-charms"
VERSION = "0.11.9"
# Where the built module is served from for Foundry to install and update.
# Loopback by default: see the note beside the manifest below.
MODULE_HOST = os.environ.get("MODULE_HOST", "http://127.0.0.1:8088")

# Packs of Actors rather than Items.
ACTOR_PACKS = {"antagonists"}
SYSTEM_ID = "exaltedessence"

# Stamped into every document's _stats. Foundry re-migrates any record with
# no _stats, or one whose coreVersion is older than a migration, on every
# startup after a deploy. These must match the server: a coreVersion newer
# than the running Foundry makes it refuse to migrate the record at all.
# Foundry's release version is "<generation>.<build>".
CORE_VERSION = "14.365"
SYSTEM_VERSION = "3.1.0"
# Documents that can sit inside another in these packs.
EMBEDDED_COLLECTIONS = ("items", "effects")

# Foundry builds these folders in the compendium sidebar once per world, so
# twenty-six packs arrive grouped rather than as one long list. A pack named
# here that does not exist is simply ignored, which is what should happen
# when a book was not supplied and its packs were never built.
#
# Evocations sit with the artifacts rather than with the charms. They are
# charm documents, but you look one up because of the artifact it belongs
# to, which is where a reader will go for it.
PACK_FOLDERS = [
    {
        "name": "Charms",
        "color": "#8a6d2f",
        "packs": [
            "universal-charms", "solar-charms", "lunar-charms",
            "abyssal-charms", "alchemical-charms", "dragon-blooded-charms",
            "getimian-charms", "infernal-charms", "liminal-charms",
            "sidereal-charms", "exigent-charms", "architect-charms",
            "sovereign-charms", "strawmaiden-janest-charms",
            "dragon-king-charms", "dream-souled-charms", "umbral-charms",
        ],
    },
    {
        "name": "Martial Arts",
        "color": "#7a3b3b",
        "packs": ["martial-arts", "sidereal-martial-arts"],
    },
    {
        "name": "Sorcery",
        "color": "#3f5d7a",
        "packs": ["sorcery-spells", "shaping-rituals"],
    },
    {
        "name": "Artifacts & Gear",
        "color": "#2f6b5a",
        "packs": ["artifacts", "evocations", "hearthstones", "equipment"],
    },
]


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
    "evocations": "Essence: Evocations",
    "sorcery-spells": "Essence: Sorcery & Necromancy Spells",
    "shaping-rituals": "Essence: Shaping Rituals",
    "antagonists": "Essence: Antagonists",
    "artifacts": "Essence: Artifacts",
    "hearthstones": "Essence: Hearthstones",
    "merits": "Essence: Merits",
    "equipment": "Essence: Basic Equipment",
}


def stamp(doc):
    """Give a document, and those embedded in it, current _stats."""
    doc["_stats"] = {
        "coreVersion": CORE_VERSION,
        "systemId": SYSTEM_ID,
        "systemVersion": SYSTEM_VERSION,
        "createdTime": None,
        "modifiedTime": None,
        "lastModifiedBy": None,
        "compendiumSource": None,
        "duplicateSource": None,
        "exportSource": None,
    }
    for collection in EMBEDDED_COLLECTIONS:
        for child in doc.get(collection) or []:
            stamp(child)
    return doc


def build_pack(name):
    """Compile one directory of JSON documents into a LevelDB pack.

    The documents are stamped in a scratch copy, so data/packs/ stays as the
    builders wrote it.
    """
    sources = sorted((SRC / name).glob("*.json"))
    with tempfile.TemporaryDirectory() as scratch:
        for source in sources:
            doc = stamp(json.loads(source.read_text(encoding="utf-8")))
            (Path(scratch) / source.name).write_text(
                json.dumps(doc, ensure_ascii=False), encoding="utf-8"
            )
        result = subprocess.run(
            [
                "node", str(CLI), "package", "pack",
                "--id", MODULE_ID,
                "--type", "Module",
                "-n", name,
                "--in", scratch,
                "--out", str(MODULE / "packs"),
            ],
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit("pack failed: {}".format(name))
    return len(sources)


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
            "type": "Actor" if name in ACTOR_PACKS else "Item",
            "system": SYSTEM_ID,
            "ownership": {"PLAYER": "OBSERVER", "ASSISTANT": "OWNER"},
        })
        print("  {:4d}  {}".format(count, name))

    # The manifest and download URLs are deliberately loopback-only. Foundry
    # fetches them from its own server process, so they never need to be
    # reachable from outside the box - and the packs are the publisher's
    # text, which NOTICE says is not to be redistributed. A public release
    # would be exactly that, so there is not one. Override the host with
    # MODULE_HOST if the module server runs somewhere else.
    manifest = {
        "id": MODULE_ID,
        "title": "Exalted Essence - Charms",
        "description": (
            "Charms, Martial Arts, and Evocations from Exalted Essence as "
            "drag-and-drop compendium items for the Exalted Essence system."
        ),
        "version": VERSION,
        # Stamped documents fail to load on a Foundry older than
        # CORE_VERSION, so do not let one install the module. Verified stays
        # a bare generation: a full build there flags the module unverified
        # after every 14.x update.
        "compatibility": {"minimum": CORE_VERSION, "verified": "14"},
        "authors": [{"name": "NidhCthon"}],
        "url": "https://github.com/NidhCthon/exalted-essence-charm-muncher",
        "readme": "https://github.com/NidhCthon/exalted-essence-charm-muncher#readme",
        "license": "https://github.com/NidhCthon/exalted-essence-charm-muncher/blob/main/LICENSE",
        "bugs": "https://github.com/NidhCthon/exalted-essence-charm-muncher/issues",
        "manifest": "{}/{}/module.json".format(MODULE_HOST, MODULE_ID),
        "download": "{}/{}/module-{}.zip".format(
            MODULE_HOST, MODULE_ID, VERSION),
        "relationships": {
            "systems": [{
                "id": SYSTEM_ID,
                "type": "system",
                # verified records the SYSTEM_VERSION the documents were
                # stamped with, so publish_local.py can spot a stale build.
                # Foundry only enforces minimum and maximum here.
                "compatibility": {"minimum": "3.0.0",
                                  "verified": SYSTEM_VERSION},
            }]
        },
        "packs": packs,
        # Only folders that still have a pack in this build, so a partial
        # build does not declare an empty one.
        "packFolders": [
            dict(folder, packs=[p for p in folder["packs"] if p in names])
            for folder in PACK_FOLDERS
            if any(p in names for p in folder["packs"])
        ],
    }
    (MODULE / "module.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print("\n{} packs, {} items".format(len(packs), total))
    print("manifest: {}".format(MODULE / "module.json"))


if __name__ == "__main__":
    main()
