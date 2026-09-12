# Handoff: antagonist stat bleed

Status: `tools/extract_antagonists.py` and `tools/build_antagonists.py` run clean
and produce 58 actors, but some of those actors carry numbers that belong to a
neighbouring stat block. The pack is built and committed but **has not been
deployed to the server**, deliberately. The charm, spell and ritual packs
(1,852 items) are unaffected and remain verified.

Do not deploy the antagonist pack until the verification below passes.

## What is wrong

Verified by hand against the Pillars PDF for three entries:

| entry | page | verdict |
| --- | --- | --- |
| Yvayn, Patriarch of the Northern S… | 180 | stats correct, but `Size` was imported from a neighbour, so `battlegroup` is wrongly true |
| Lintha Angsara Father Duretti | 191 | same: stats correct, `Size` borrowed, `battlegroup` wrongly true |
| Lintha Ng Hut Dukantha | 189 | **wrong.** Blends the two stat blocks printed on that page, and its Hardness and Soak match *neither* block — those two numbers do not appear anywhere on p189 |

The Dukantha case is the important one, because it rules out the simplest
explanation. If the bug were only "two blocks on one page merged", every
imported number would still be a number printed on that page. Two of them are
not. So the accumulated stat line reaches beyond the page boundary as well.

The `57 of 58 have Defense/Soak/Hardness` figure printed by
`build_antagonists.py` measures only that *something* parsed, not that it
parsed the right thing. Assume a handful of the other 54 are blended too.

## Mechanism

In `extract()`, every span in the `STAT_SIZE` window is appended to
`current["statline"]`, and `current` only changes when a name is detected
(`NAME_SIZE`, or `VARIANT_SIZE` with a leading word that is not "Variant").
Nothing bounds the run. When a name is missed — wrong size, or a name that
never made it into a name-sized span — the next antagonist's stat spans land on
the previous entry's stat line.

`parse_stats()` then resolves collisions with first-match-wins:

```python
if label not in stats:            # first occurrence is the stat block
    stats[label] = int(match.group(2))
```

That rule is right for separating a stat block from the prose that follows it
("reduces Defense by one"), and it should stay. It is the wrong tool for
separating two stat blocks from each other, because whichever block happens to
come first silently wins per-label — which is why Dukantha ends up with Defense
from one block and Health/Resolve/Essence from another.

## Do this first

Before changing any parsing, dump the raw stat spans with their page numbers
for the three entries above. That pins the mechanism instead of inferring it,
and it is cheap:

- in `extract()`, keep `(page, text)` pairs in `statline` rather than bare text
- print them for Dukantha and look at where Hardness 7 / Soak 6 actually come from

If those two land from p188 or p190, the fix has to bound the run positionally,
not just per page. If they come from somewhere stranger, the plan below needs
revisiting before it is worth writing.

## The fix

1. **Bound each entry's stat line.** A stat block is a contiguous run of
   stat-sized spans that starts near its own name. Stop collecting at the first
   non-stat content after that run, so a second block cannot merge into the
   first. A span from a different page should never join a run that started on
   an earlier one.
2. **Stop inferring `battlegroup` from `Size`.** `build_antagonists.py:97` reads
   `battlegroup = "size" in stats or tabled`. With `Size` leaking between
   entries that is wrong twice over — it marks ordinary antagonists as battle
   groups, and it would keep doing so even after the bleed is fixed for any
   entry that sits next to a real group. Either drop `size` from `NUM_LABELS`
   general parsing, or only accept it once the entry independently looks like a
   group (Drill and Command present, or the tabled layout).
3. Re-check that the `is_antagonist()` filter still admits the same 58 once the
   stat lines shrink. Entries that only qualified on borrowed Defense/Soak will
   now drop out, and that is the correct outcome, but the count changing is
   expected and should not be read as a regression.

## Re-verification

The check that found this: for each entry, regex every `Label: number` pair on
its page out of the PDF and compare against the imported stats. Run it over a
sample well beyond the three above — at minimum every entry that shares a page
with another entry, since those are where bleed is possible.

An entry passes when each imported value appears on its page **and** belongs to
the same printed block as the rest. Matching "some number on the page" is the
weak check that let this through the first time.

## Commands

```
cd /k/foundry-exalted-charms/tools
export ESSENCE_CORE_PDF="K:\exalted\Exalted_Essence_(Final_Download_v2) (1).pdf"
export ESSENCE_PILLARS_PDF="C:\Users\Pugjc\Downloads\Ex_Essence_Pillars_of_Creation_(Download).pdf"
../.venv/Scripts/python.exe extract_antagonists.py
../.venv/Scripts/python.exe build_antagonists.py
cd .. && ./.venv/Scripts/python.exe tools/build_packs.py
```

## Traps

- **Never commit book text.** Verify with `git check-ignore -v` and a
  clone-and-grep, not by reading `.gitignore`. This note deliberately describes
  the wrong numbers without reproducing the printed ones.
- **Do not put Python containing regex escapes in a bash heredoc.** `\b` was
  silently converted to a literal backspace control character, every pattern
  matched nothing, and the extractor returned zero entries with no error. Write
  patch scripts with the Write tool.
- `/tmp` differs between git-bash and Windows Python (`K:\tmp`). Use one
  absolute path both can see.
- Commits here use `NidhCthon <NidhCthon@users.noreply.github.com>`.

## Still open, separately

- Battle groups that print Defense/Health/Soak/Drill/Size as a table are
  detected by `prints_stats_as_a_table()` and flagged in the biography rather
  than imported. Reading them needs position-aware parsing: the labels sit on
  one row and the numbers on another, so label-then-number cannot work. Only 1
  of 4 known groups is caught by the current marker heuristic.
- The Storyteller's Guide draft's ~45 antagonists are set on a different type
  scale and need their own pass.
