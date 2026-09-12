# Next: basic equipment

Mundane weapons and armour are not imported. Only artifacts are, which means
a player can drag a daiklave onto a sheet but not a sword.

## Where it is

Core rulebook:

- p342 - the rules, including the category tables the artifact builder
  already reads
- pp343-344 - "Equipment Examples", the named mundane weapons, grouped under
  Light/Medium/Heavy and Close Combat/Ranged headings

Pillars adds equipment tags on p202 but no new mundane weapons.

## What makes it easy

The hard part is already done. `build_artifacts.py` holds the category
tables and the tag vocabulary, and `extract_artifacts.py` already reads a
14pt name followed by body text in these very chapters.

## What makes it different

An example weapon is one line, not a block:

    Knife: A short blade for cutting, up to a foot in length. Thrown,
    concealable, paired.

So there is no Type line to read. The category comes from the heading the
weapon sits under, which means the extractor has to carry the current
heading down the page rather than read a label per entry. The tags are the
sentence's last clause, in prose, lowercase, ending in a full stop - not a
"Tags:" line.

Names carry alternatives: "Cestus/Gauntlets", "Club/Cudgel/Baton". Decide
whether that is one item with a compound name or several; one item is
probably right, since the book treats them as one entry with one stat line.

## Stats

Same derivation as artifacts, minus the artifact bonus:

    Light   accuracy +2  damage +0  defense +1  overwhelming 1
    Medium  accuracy +1  damage +1  defense +1  overwhelming 1
    Heavy   accuracy +0  damage +2  defense +1  overwhelming 1

    Light armour  soak +1  penalty  0  hardness 0
    Heavy armour  soak +2  penalty -1  hardness 0

Do not fold in the other tags' effects. The system's roller reads the tags
and applies them itself - balanced raises Overwhelming by one - so adding
them here counts them twice. The artifact tag is the exception the roller
does not handle, which is why that one is applied in the builder.

## Suggested shape

A new pack, "Essence: Equipment", kept apart from artifacts so a player can
tell a mundane sword from a daiklave in the compendium list.

## Traps

- **Never commit book text**, in notes and comments as much as in data.
- Do not put Python containing regex escapes in a bash heredoc; `\b` becomes
  a literal backspace and every pattern silently matches nothing.
- Read one built item end to end before believing the counts. Every
  display-level bug in the artifact and hearthstone work - page numbers in
  descriptions, words split across spans, one paragraph per line - was
  invisible to aggregate checks.
