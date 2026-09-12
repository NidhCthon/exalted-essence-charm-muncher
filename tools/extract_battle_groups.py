"""Read battle group stat tables, which are set sideways.

A battle group's stats are not printed as labelled values like an
antagonist's. They are a table: the column headings are rotated ninety
degrees, and one row of values sits underneath them. In span order that comes
out as a run of headings followed by a run of bare numbers, which is why a
label-then-number parser reads nothing from it and, worse, hands the first
number to whichever label happened to land last.

Position is the only thing that relates the two rows, so this matches them on
horizontal overlap: the value under SIZE is the one whose box overlaps SIZE's.

Rotated text is what identifies a heading. A span's box is much narrower than
its text is long when the text runs vertically, which no ordinary heading
does.
"""
import re

HEADINGS = ("QUALITIES", "DEFENSE", "DEFENCE", "HEALTH", "SOAK", "DRILL",
            "SIZE", "COMMAND", "ESSENCE", "RESOLVE", "HARDNESS")

# How far under the headings a value row can sit, and how far apart two
# headings can be and still belong to the same table.
VALUE_GAP = 60.0
HEADING_SPREAD = 80.0


def page_spans(page):
    out = []
    for blk in page.get_text("dict")["blocks"]:
        if blk.get("type") != 0:
            continue
        for line in blk.get("lines", []):
            for sp in line.get("spans", []):
                text = sp["text"].strip()
                if text:
                    x0, y0, x1, y1 = sp["bbox"]
                    out.append({"text": text, "x0": x0, "x1": x1, "y0": y0,
                                "y1": y1, "size": sp["size"]})
    return out


def is_rotated(span):
    """A vertical span's box is taller than it is wide.

    Comparing width against the length of the text instead fails on the short
    headings - SIZE and SOAK are narrow enough to look horizontal. The length
    guard is what keeps a one-digit value cell out: a lone "3" is also taller
    than it is wide, and without it the values are discarded along with the
    headings they belong to.
    """
    return (len(span["text"]) >= 3
            and (span["y1"] - span["y0"]) > (span["x1"] - span["x0"]) * 1.5)


def find_tables(page):
    """Every battle group table on a page, as {label: value} plus its box."""
    spans = page_spans(page)
    headings = [s for s in spans
                if s["text"].upper() in HEADINGS and is_rotated(s)]
    if len(headings) < 3:
        return []

    headings.sort(key=lambda s: s["y1"])
    groups, current = [], [headings[0]]
    for span in headings[1:]:
        if span["y1"] - current[0]["y1"] <= HEADING_SPREAD:
            current.append(span)
        else:
            groups.append(current)
            current = [span]
    groups.append(current)

    tables = []
    for group in groups:
        if len(group) < 3:
            continue
        floor = max(s["y1"] for s in group)
        row = [s for s in spans
               if floor < s["y0"] <= floor + VALUE_GAP and not is_rotated(s)]
        table = {}
        for heading in group:
            hits = [s for s in row
                    if s["x0"] < heading["x1"] and s["x1"] > heading["x0"]]
            if not hits:
                continue
            hits.sort(key=lambda s: s["y0"])
            value = hits[0]["text"].strip(" .,;:")
            # A numeric column is one line. A text column - qualities, most
            # of all - wraps over several, and taking only the first would
            # quietly truncate it.
            if not NUMERIC.match(value) and len(hits) > 1:
                value = " ".join(s["text"].strip() for s in hits).strip(" .,;:")
            table[heading["text"].upper()] = value
        if table:
            tables.append({
                "stats": table,
                "x0": min(s["x0"] for s in group),
                "x1": max(s["x1"] for s in group),
                "y0": min(s["y0"] for s in group),
            })
    return tables


# Most battle groups are not tables at all. They are boxed out beside their
# commander and print labelled values, which is the format below. The Size
# line carries the group's Health levels in its parenthetical, and Drill
# carries its success modifier in the same way, so both numbers are read from
# there rather than from a column of their own.
SIZE_RE = re.compile(
    r"Size\s*:\s*(\d+)\s*\(\s*(\d+)\s*Health\s+levels", re.I)
DRILL_RE = re.compile(r"Drill\s*:\s*([A-Za-z]+)\s*\(\s*\+?(\d+)", re.I)
COMMANDER_RE = re.compile(r"Commander\s*:\s*(.+?)\s*(?:Qualities\s*:|$)", re.I)
BOX_QUALITIES_RE = re.compile(r"Qualities\s*:\s*(.+)$", re.I)


def parse_box(text):
    """Read a boxed battle group, or return None if this is ordinary prose.

    Size is what makes it a battle group; a box with only a Drill line is a
    fragment of one whose other half was set elsewhere on the page, and
    guessing the rest would be worse than leaving it as text.
    """
    if not text:
        return None
    size = SIZE_RE.search(text)
    if not size:
        return None

    group = {
        "text": text.strip(),
        "size": int(size.group(1)),
        "health": int(size.group(2)),
        "drill": 0,
        "drill_name": "",
        "commander": "",
        "qualities": "",
    }

    drill = DRILL_RE.search(text)
    if drill:
        group["drill_name"] = drill.group(1)
        group["drill"] = int(drill.group(2))

    commander = COMMANDER_RE.search(text)
    if commander:
        name = commander.group(1).strip(" .,;:")
        group["commander"] = "" if name.lower() == "none" else name

    qualities = BOX_QUALITIES_RE.search(text)
    if qualities:
        group["qualities"] = qualities.group(1).strip(" .,;:")

    return group


def parse_boxes(text):
    """Every battle group in a sidebar, since a page can print two.

    Two boxes set one above the other arrive as a single run of text, and
    read as one group the second one's Size line and everything after it end
    up inside the first one's qualities. Each Size line starts a new group.
    """
    if not text:
        return []
    starts = [match.start() for match in SIZE_RE.finditer(text)]
    if not starts:
        return []
    bounds = starts + [len(text)]
    groups = []
    for index, start in enumerate(starts):
        box = parse_box(text[start:bounds[index + 1]])
        if box:
            groups.append(box)
    return groups


NUMERIC = re.compile(r"^-?\d+$")


def numeric(table):
    """Only the entries that are plain numbers, lowercased."""
    return {label.lower(): int(value) for label, value in table.items()
            if NUMERIC.match(value)}
