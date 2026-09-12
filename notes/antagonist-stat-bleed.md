# Antagonist stat bleed - fixed

Resolved. `tools/verify_antagonists.py` is the check that proves it and the
thing to run after any change to the antagonist extractor.

## What it actually was

The first diagnosis in this file was wrong, and wrong in an instructive way.
It said adjacent antagonists' stat blocks were merging, because a spot check
found imported numbers that were not printed on the page where the name was
found. That check was too weak: a stat block often continues onto the next
page, so a legitimate continuation looked like an invented number.

Dumping the raw spans (`extract_antagonists.py --dump NAME`) showed three
separate causes:

1. **Doubled sidebar boxes.** Several commanders have a battle group boxed
   out beside them, with its own Size, Drill, Commander and Qualities. These
   boxes are drawn twice, span for span, the way sidebars are throughout
   these books, and they land in the middle of the host's stat spans. The
   box's Size was read as the commander's, and its prose was spliced into the
   middle of the commander's qualities. Fixed by `split_doubled_sidebar()`,
   which drops spans that repeat their neighbour and keeps one copy as the
   box's own text. Dropping exactly those spans also rejoins the host's prose
   across the interruption.

2. **Battle group tables.** Labels on one row, numbers on the next, which
   reads as a label row followed by a number row, so the last label takes the
   first number of the number row - and when the table sits beside another
   antagonist, that number lands on them. Fixed by
   `cut_at_battle_group_table()`.

3. **Template blocks headed at stat size.** The two animal templates in the
   core book are headed at stat size rather than name size, so nothing marked
   them as names and both merged into one entry. This one was the original
   hypothesis, and it was real - just not on any of the entries first checked.
   Fixed by `heads_a_stat_block()`, which treats an all-caps span as a name
   when the span after it opens a pool. They now import as two usable
   templates.

`parse_stats()`'s first-match-wins rule was never the problem and has not
changed. It is what correctly keeps a defensive stat printed as zero with a
parenthetical pointing at the trait that explains it, rather than a value for
the same trait mentioned later in that antagonist's prose.

`POOL_RE` also now accepts the template blocks' pool format alongside the one
named antagonists use, without which the templates imported with no pools.

## State

68 actors, verification clean: 64 antagonists plus 4 battle groups imported
as their own actors. Three books - the core rulebook, Pillars of Creation,
and the Tomb of Memory jumpstart.

Three entries on Pillars pp180-191 - the ones that first exposed the bug -
were spot-checked against the book and are correct field for field.

## Two more causes, found later

4. **Reading order ignored section banners.** A centred banner straddles both
   columns and divides the page, but the reader took a whole column at a
   time. A stat block in the upper right was therefore walked past the
   heading of the section underneath and filed against a later name - one
   entry lost its stats entirely and a section heading gained them and was
   imported as an antagonist. Pages are now split into regions at each
   banner, which is what the charm extractor already did.

5. **Stats were read from the prose as well as the block.** An antagonist
   whose quality lets them "create a Size 1 battle group" was importing a
   Size of 1. Numbers are now read only from the part of the stat line before
   the qualities heading, which keeps prose out by construction instead of
   relying on the block happening to come first.

## Battle groups

Mostly not tables. The one table in range is the example in the rules text,
and it is now readable - its headings are rotated ninety degrees, so nothing
but horizontal overlap relates them to the row of values underneath.

The groups that belong to antagonists are boxed out beside their commander
and print labelled values, two to a page in one case. Those are imported as
their own actors, named after the commander the book prints rather than the
antagonist they happen to sit beside - one page prints a group next to one
character while another commands it, and another gives no commander at all.
Size, Drill and Health come from the box; Defense and the rest stay zero
rather than borrowing the commander's.

The jumpstart prints its one group a third way again, with a short "Health"
label and a Drill given as a word with no modifier in brackets. Both are
handled.

A caveat on the jumpstart generally: it was written against an earlier draft
of the rules than the core book. Where its stat blocks are laid out
differently, or where a number or a quality does not match what the core
book would give the same creature, that is the reason. Its actors are
imported as printed, not reconciled to the core rules, so treat them as the
jumpstart's own versions rather than as errors to correct.

## Verification

    ../.venv/Scripts/python.exe verify_antagonists.py

Checks four things, and the reasoning behind each is in the module docstring:

* MERGED - one stat block giving two values for a label, scanned only over
  the block itself, since past that point a trait named with a number is
  ordinary prose
* UNSOURCED - a number on none of the pages the stat line actually touches
* SIZE - Size on an entry that is not a battle group
* INCOMPLETE - pools but no defensive stats

Exit code 1 on any finding, so it can gate a rebuild.

## Still open

- There is no Essence Storyteller's Guide on this machine. What was taken for
  one is a six-page Combat Reforged summary with no antagonists in it, so
  that book is not pending work - it is simply absent. The Player's Guide
  draft has antagonists on a single page and is not worth a pass.
- Battle groups carry no Defense, Soak or Resolve, because the boxes do not
  print any. That is faithful to the book rather than a gap.

## Traps

- **Never commit book text.** That means no names, no printed values, and no
  quoted lines, in code comments and notes as much as in data. Verify with
  `git check-ignore -v` and a clone-and-grep, not by reading `.gitignore` -
  and control-test the grep, because a probe that silently matches nothing
  reads exactly like a clean result.
- **Do not put Python containing regex escapes in a bash heredoc.** `\b` was
  silently turned into a literal backspace control character, every pattern
  matched nothing, and the extractor returned zero entries with no error.
- Commits here use `NidhCthon <NidhCthon@users.noreply.github.com>`.
