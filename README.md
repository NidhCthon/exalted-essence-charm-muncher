# Exalted Essence → Foundry VTT compendium builder

Builds Foundry VTT compendium packs of Exalted Essence Charms, Spells, Shaping
Rituals and Evocations from PDFs **you already own**, so they can be browsed
and dragged onto character sheets instead of typed in by hand.

Targets the [Exalted Essence system](https://github.com/Aliharu/Foundry-ExEss)
(`exaltedessence`), which ships no charm content of its own.

> **This tool contains no game text.** It reads a PDF you supply. The packs it
> builds on your machine are Onyx Path Publishing's copyrighted text — they are
> for your own table, and must not be redistributed. See [NOTICE](NOTICE).

## What you get

With all four books, 1,954 documents across 25 packs:

| Pack | Items |
|---|---|
| Universal Charms | 162 |
| Infernal, Alchemical, Dragon-Blooded, Sidereal | 137–141 each |
| Abyssal, Lunar, Solar, Getimian, Liminal | 130–136 each |
| Martial Arts | 99 |
| Exigent, Architect, Sovereign | 52–67 each |
| Evocations & Hearthstones | 40 |
| Sorcery & Necromancy Spells | 63 |
| Sidereal Martial Arts | 31 |
| Strawmaiden Janest | 25 |
| Shaping Rituals | 28 |
| Dragon King, Dream-Souled, Umbral | 6 each |

Charms carry ability, requirement, Essence, mote/anima/Power cost, prerequisite
charms, page reference and a formatted description. Spells carry circle, spell
type and Will cost. Everything uses the enum values from the system's own
`config.js`, so sheet dropdowns resolve rather than rendering blank.

## Requirements

- Python 3.10+, then `pip install -r requirements.txt`
- Node.js, then `npm install` for [Foundry's CLI](https://github.com/foundryvtt/foundryvtt-cli)
- Foundry VTT **v14** with system `exaltedessence` **3.x**
- Your own PDFs

## Supported books

| Book | Content | Env var |
|---|---|---|
| Exalted Essence (core) | 495 charms, 35 spells, 15 rituals | `ESSENCE_CORE_PDF` |
| Pillars of Creation | 387 charms, 28 spells, 13 rituals | `ESSENCE_PILLARS_PDF` |
| Player's Guide (draft manuscript) | 879 charms, no sorcery | `ESSENCE_PLAYERSGUIDE_PDF` |

Books are optional — supply only what you own. The Player's Guide entry is the
**draft manuscript**, whose charms may not match the published book.

## Usage

```
python tools/build_all.py --core "/path/to/Exalted_Essence.pdf"
```

Or set the environment variables and run it bare. Add `--pillars` and
`--playersguide` for the supplements. Individual stages can be run alone; each
takes `--pdf`.

The result is a `module/` directory. Copy it into your Foundry data directory
as `Data/modules/exalted-essence-charms/`, restart Foundry, and enable it.

### Edition checking

Page ranges are pinned to specific PDF releases. A different printing shifts
them, and extraction would emit confidently wrong output rather than fail — so
each book is fingerprinted by page count plus an expected phrase on a known
page, and the tool refuses to run on a mismatch. If you have a different
printing, adjust the ranges and fingerprint in `tools/books.py`.

## How it works

The published books are two-column. Flat text extraction interleaves the
columns and produces charms wearing each other's mechanics, so the extractor
works from positioned text blocks: left column top-to-bottom, then right
column, then the next page, giving one linear stream in true reading order.

Several details turned out to matter more than expected.

**Blocks are classified by rendered font size, not capitalisation.** A 30pt
banner, a 12pt charm name and a 13pt sidebar heading are all upper case.

**Section banners are centred across both columns**, so their bounding-box
centre falls arbitrarily either side of the page midline — "ABYSSAL CHARMS"
sits two points right of centre. Treating one as column content sorts it after
every left-column charm on its own page, stranding those charms in the previous
section. Banners instead divide the page horizontally.

**Sidebars float into a column mid-charm.** Stopping body collection at any
heading silently truncates the charm, losing every paragraph after the sidebar.
Non-charm headings are stepped over instead, and sidebar prose is filtered by
its signature: it is set twice, doubled per line rather than per block.

**Cross-references** ("FLOW LIKE BLOOD — See p. 185") look exactly like charm
headings but have no `Prerequisite:` line, which is how they are excluded.

**Sorcery needs a separate pass** — spells carry no prerequisite line at all,
so the charm rule cannot see them. The First/Second/Third circle headings cycle
three times, and that reset is the only marker separating universal, sorcery
and necromancy spells.

**Pillars marks its circles differently.** The core book uses clean 13.9pt
circle headings; Pillars sets them at 17.8pt and usually welds them onto the
end of the preceding paragraph ("...usable by both sorcerers and
necromancers.First Circle Spells"). Blocks are split at the marker, because the
text before it belongs to the previous spell. Missing that is how 41 Pillars
sorcery entries went unnoticed at first.

**The Player's Guide is inconsistent with itself.** Four of its chapters put
the prerequisite in the same block as the charm name; the rest use separate
blocks. It also splits 31 charms across a page boundary, name on one page and
prerequisite on the next, so blocks are streamed continuously rather than per
page.

**Document `_id`s derive from the charm name**, so rebuilding and re-importing
updates existing entries rather than duplicating them. Supplement ids are
namespaced by book, section and page: names are not unique across books, and
the Player's Guide repeats six of them inside a single section.

**Every document needs `_key`.** Foundry's CLI derives the LevelDB key from it
and silently skips documents that lack it, writing an empty pack while still
exiting successfully. If a pack imports as empty, check this first.

## Known limits

- Variable costs ("Commit up to 3 motes", "Spend any number of motes") are left
  at zero rather than guessed; the full text is in the description.
- Charms whose only prerequisite is `Essence 3`, `None` or `Any Excellency` get
  `ability: other`, having no ability to parse.
- `charmprerequisites` records prerequisite charms by name with a blank `id`,
  so the system will not link them automatically.
- Cross-referenced charms appear once, under their primary entry.
- Player's Guide content comes from a draft manuscript.

## Verifying an extraction

The books have internal referential integrity worth exploiting: every
cross-reference, and every charm named as another charm's prerequisite, must
resolve to a charm that was extracted. On the core book all 75 cross-references
and 50 of 54 named prerequisites resolve — the 4 that do not are not charms
(`Familiar Merit`, `Any Excellency`, and similar).

That check is what caught the sidebar truncation bug.

### Which books hold sorcery

Only the core rulebook and Pillars of Creation. The Player's Guide has no
spells or shaping rituals at all, which is worth stating because its absence
looks like a gap in this tool rather than in the book. Three checks over its
full text, not just its headings, agree:

- no `First/Second/Third Circle Spells` heading anywhere in its 378 pages;
- no `Spend N Will`, and every spell in Essence costs Will;
- no mention of a shaping ritual.

Its twenty-odd uses of the word "spell" are all prose inside Charms and
fiction, and its ten chapters are one per Exalt type with no sorcery chapter.

## Layout

```
tools/
  books.py            book registry, PDF resolution, edition fingerprints
  extract.py          core rulebook charms; shared column/banner/sidebar logic
  extract_sorcery.py  core spells and shaping rituals
  extract_pillars.py  Pillars of Creation charms (reuses the core extractor)
  extract_sorcery_pillars.py
                      Pillars spells and shaping rituals
  extract_pg.py       Player's Guide (single-column manuscript)
  build_items.py      charms  -> Foundry Item documents
  build_sorcery.py    spells and rituals -> Foundry Item documents
  build_packs.py      documents -> LevelDB packs, and module.json
  build_all.py        runs all of the above in order
```
