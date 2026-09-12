# Basic equipment - done

See `tools/extract_equipment.py` and `tools/build_equipment.py`.
Kept as a note only for what it records about the layout:

- The category comes from the heading above an entry, not from the entry.
- Name, description and tags are told apart by font, not size:
  bold, roman, italic. All three are the same size.
- The punctuation between tags is set roman while the tags are
  italic, so collecting only italic spans loses the commas - and
  loses the "or" that makes a list a choice.
- A tag clause is one sentence; without stopping at its full stop
  the last entry in a column swallows whatever follows it.
- "Smashing, improvised, or balanced" is one of three, while
  "balanced, chopping or piercing, off-hand" gives two and offers
  a choice of the other two. The last item opening with "or" is
  what separates them.
- The book prints no example armour, only the two categories with
  their statistics, so those two are built from the table.
