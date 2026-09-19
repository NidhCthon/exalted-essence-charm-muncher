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

With all five books, 2,085 documents across 27 packs:

| Pack | Items |
|---|---|
| Universal Charms | 162 |
| Infernal, Alchemical, Dragon-Blooded, Sidereal | 137-142 each |
| Abyssal, Lunar, Solar, Getimian, Liminal | 131-136 each |
| Martial Arts | 102 |
| Antagonists | 132 |
| Exigent, Architect, Sovereign | 52-67 each |
| Sorcery & Necromancy Spells | 63 |
| Evocations | 45 |
| Sidereal Martial Arts | 32 |
| Basic Equipment | 29 |
| Shaping Rituals | 28 |
| Strawmaiden Janest | 25 |
| Hearthstones | 21 |
| Merits | 11 |
| Artifacts and warstriders | 27 |
| Dragon King, Dream-Souled, Umbral | 6 each |

Charms carry ability, requirement, Essence, mote/anima/Power cost, prerequisite
charms, page reference and a formatted description. Spells carry circle, spell
type and Will cost. Everything uses the enum values from the system's own
`config.js`, so sheet dropdowns resolve rather than rendering blank.

Merits lead their description with the ratings they may take, and leave
`rating` for the player to set unless the book allows only one. Hearthstones
are rated as the Merit that buys them: secondary for a lesser or standard
stone, primary for a greater. The dice roller looks `rating` up to add Merit
dice, so any other value there breaks the roll.

Every weapon gets an attack animation preset, matched from its name and then
its tags (a bow fires an arrow, a maul cracks the ground). The system plays it
only with its "attack effects" setting on and the Sequencer and JB2A modules
installed; players can change a weapon's preset on its sheet.

## Requirements

- Python 3.10+, then `pip install -r requirements.txt`
- Node.js, then `npm install` for [Foundry's CLI](https://github.com/foundryvtt/foundryvtt-cli)
- Foundry VTT **v14** with system `exaltedessence` **3.x**
- Your own PDFs

## Supported books

| Book | Content | Env var |
|---|---|---|
| Exalted Essence (core) | 498 charms, 35 spells, 15 rituals, 10 merits | `ESSENCE_CORE_PDF` |
| Pillars of Creation | 397 charms, 28 spells, 13 rituals, 1 merit | `ESSENCE_PILLARS_PDF` |
| Player's Guide (draft manuscript) | 879 charms, no sorcery | `ESSENCE_PLAYERSGUIDE_PDF` |
| Tomb of Memory (jumpstart) | antagonists, hearthstones | `ESSENCE_TOMB_PDF` |
| Storyteller's Guide (draft preview) | 64 antagonists | `ESSENCE_STG_PDF` |

Books are optional — supply only what you own. The Player's Guide entry is the
**draft manuscript**, whose charms may not match the published book.

## Usage

```
python tools/build_all.py --core "/path/to/Exalted_Essence.pdf"
```

Or set the environment variables and run it bare. Add `--pillars`,
`--playersguide`, `--tomb` and `--stg` for the supplements. Individual stages can be run alone; each
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

**Charm names carry punctuation.** Names were first matched as capital
letters, apostrophes and hyphens only. Thirteen charms and Evocations have a
comma, colon, digit, parenthesis or exclamation mark in their name, or run past
sixty characters, and every one was read as body text and swallowed into the
description of the charm before it - present in no pack, and no count showed
it. A few Pillars Evocation names are also set on the same line as the end of
the paragraph before them; those are split off when a prerequisite follows.
`tools/verify_charms.py` is what found them.

**Pillars sets its page footer twice**, title and number both, so page 52
arrives as `...5252` and read as 252. The number is halved only when the title
before it is doubled too, so a genuine page 55 is never read as 5. The core
book's running page headers are doubled the same way; they are dropped as page
chrome, having reached 31 charm descriptions as text.

**The draft manuscript still holds its editors' layout notes** - capitals-only
instructions marking where a table or call-out box goes. The notes are dropped
and what they mark is kept.

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
- Prerequisite charms are linked where the system can follow them: 192 of the
  210 named. The system looks a prerequisite up in the charm's own pack, so one
  naming a charm in another pack cannot be linked, and neither can one naming a
  Merit or a requirement rather than a charm ("Any Excellency"). Those keep the
  name in the prerequisites text instead of a pill that would error.
- Cross-referenced charms appear once, under their primary entry.
- Player's Guide content comes from a draft manuscript.

## Verifying an extraction

The books have internal referential integrity worth exploiting: every
cross-reference, and every charm named as another charm's prerequisite, must
resolve to a charm that was extracted. On the core book all 75 cross-references
and 50 of 54 named prerequisites resolve — the 4 that do not are not charms
(`Familiar Merit`, `Any Excellency`, and similar).

That check is what caught the sidebar truncation bug.

`tools/verify_charms.py` checks the extracted data for the marks segmentation
errors leave behind: a charm swallowed into the body of the one before it,
sidebar or editor's-note text inside a description, and page numbers outside
the chapter range the extractor reads. It names each swallowed charm, never
prints book text, and exits non-zero when anything needs looking at. Run it
after any change to an extractor.

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

## Committing safely

This repository is public, and everything the extractors produce is copyrighted
book text. Book text has reached a commit here twice through `.gitignore`
mistakes, and careful reading of `.gitignore` caught neither time. So a
pre-commit hook checks what is actually being committed rather than trusting
ignore rules. Enable it once per clone:

```
git config core.hooksPath tools/hooks
```

On every commit it refuses anything under `data/` or `module/` (and any
`*.raw.json`, `*.pdf` or `*.zip`, even forced past `.gitignore`), then compares
each staged file with your extracted text in `data/*.raw.json`. A file sharing
three or more 8-word verbatim runs with the books — about ten consecutive words
— is refused. It reports paths and line numbers, never the text.

Deliberate exceptions, such as a stat line kept as a parser format example, are
accepted explicitly and recorded as hashes that cannot be read back into text:

```
python tools/hooks/check_book_text.py --allow tools/some_file.py
```

Audit the whole tree, or every blob ever committed, with `--tree` or
`--history`. On a clone that has never run the extractors there is no
`data/*.raw.json`, so only the path rules can run; the hook says so on every
commit rather than passing silently.

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
  verify_charms.py    flags charms showing a mis-segmentation signature
  hooks/              pre-commit guard against committing book text
```
