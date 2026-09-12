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

59 actors, verification clean apart from one known gap. Previously 58; the
merged animal-template entry became two templates, and nothing else changed
count.

Three entries on Pillars pp180-191 - the ones that first exposed the bug -
were spot-checked against the book and are correct field for field.

## The one remaining gap

One Pillars entry (p192) imports its pools but no defensive stats, and the
verifier reports it as INCOMPLETE. Its stats are printed as a battle group
table, so this is the table limitation noted below rather than a new fault.
Enter its numbers by hand, or write the table parser.

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

- Battle groups print their stats as a table and are still not imported. The
  table text is preserved in the neighbouring actor's biography under
  "Battle group printed alongside" rather than parsed. Reading it needs
  position-aware parsing, since labels and numbers are on separate rows.
- No actor is flagged `battlegroup` any more. That is deliberate: nothing
  claims to be a battle group on the strength of a number borrowed from
  somewhere else. It becomes correct on its own once the tables are parsed.
- The Storyteller's Guide draft's antagonists are set on a different type
  scale and need their own pass.

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
