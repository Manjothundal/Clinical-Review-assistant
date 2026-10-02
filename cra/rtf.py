# -*- coding: utf-8 -*-
"""
Reads a SAS ODS RTF output and turns it into something the checks can work with.

An RTF file is plain text full of control words like \\par and \\cell. We do not
try to render it. We only pull out the four things a reviewer looks at:

    titles      the lines above the table
    headers     the column header row
    rows        the body rows
    footnotes   the lines below the table, including the Source line

Nothing here knows anything about clinical data. It is just a reader.
"""
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

# Groups we throw away completely. Font tables, colour tables, style sheets,
# revision marks. None of them carry text the reviewer sees.
_SKIP_GROUPS = ("fonttbl", "colortbl", "stylesheet", "info", "listtable",
                "listoverridetable", "rsidtbl", "generator", "pnseclvl",
                "themedata", "colorschememapping", "latentstyles", "datastore")

_CONTROL = re.compile(r"\\([a-zA-Z]+)(-?\d+)? ?")
_HEXCHAR = re.compile(r"\\'([0-9a-fA-F]{2})")
_UNICHAR = re.compile(r"\\u(-?\d+)\s*\??")


def _strip_skip_groups(text):
    """Remove {\\fonttbl ...} and friends, brace-balanced."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "{":
            # look at the first control word inside this group
            m = re.match(r"\{\\\*?\\?([a-zA-Z]+)", text[i:])
            name = m.group(1) if m else ""
            if name in _SKIP_GROUPS or text[i:i + 3] == "{\\*":
                depth = 0
                j = i
                while j < n:
                    if text[j] == "\\" and j + 1 < n:
                        j += 2
                        continue
                    if text[j] == "{":
                        depth += 1
                    elif text[j] == "}":
                        depth -= 1
                        if depth == 0:
                            j += 1
                            break
                    j += 1
                i = j
                continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _decode_escapes(text):
    text = _HEXCHAR.sub(lambda m: bytes([int(m.group(1), 16)]).decode("cp1252",
                                                                     "replace"),
                        text)
    text = _UNICHAR.sub(lambda m: chr(int(m.group(1)) % 65536), text)
    return text


def to_lines(raw):
    """
    RTF source -> a list of lines. A line is either plain text, or a table row
    whose cells are separated by the tab character.
    """
    text = _strip_skip_groups(raw)
    text = _decode_escapes(text)

    # Protect the three control words that carry structure before we delete
    # every other control word.
    # \par ends a paragraph. \pard only resets the formatting, so it must NOT
    # break the line - inside a table every cell starts with \pard\intbl, and
    # breaking there would shatter each row into single cells.
    text = re.sub(r"\\par\b ?", "\n\x01", text)         # paragraph
    text = re.sub(r"\\line\b ?", "\n\x01", text)
    text = re.sub(r"\\cell\b ?", "\t", text)            # end of a table cell
    # \row CLOSES the row, so the marker goes at the end of the line it closes,
    # not at the start of the next one.
    text = re.sub(r"\\row\b ?", "\x02\n", text)         # end of a table row
    text = re.sub(r"\\tab\b ?", "\t", text)

    text = _CONTROL.sub("", text)                       # every other \word
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"\\([^a-zA-Z])", r"\1", text)        # \{ \} \\ escapes

    lines = []
    for chunk in text.split("\n"):
        kind = "row" if "\x02" in chunk else "text"
        chunk = chunk.replace("\x01", "").replace("\x02", "")
        cells = [c.strip() for c in chunk.split("\t")]
        cells = [c for c in cells if c != ""]
        if not cells:
            continue
        lines.append((kind, cells))
    return lines


# Words that mark a line below the table rather than a title above it.
_FOOTNOTE_STARTS = ("source", "note", "notes", "program", "pgm", "generated",
                    "produced", "abbrevi", "footnote", "ref:", "n =", "n=")


@dataclass
class Output:
    """One delivered output file, read back as a reviewer sees it."""
    path: str
    filename: str
    titles: List[str] = field(default_factory=list)
    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    footnotes: List[str] = field(default_factory=list)
    text: str = ""

    # ---- convenience -----------------------------------------------------
    @property
    def title(self):
        return self.titles[0] if self.titles else ""

    @property
    def full_title(self):
        return " ".join(self.titles)

    @property
    def source_line(self):
        for f in self.footnotes:
            low = f.lower()
            if low.startswith("source") or low.startswith("program") \
               or low.startswith("pgm"):
                return f
        return None

    @property
    def kind(self):
        """
        table, listing or figure, taken from the title and the file name.

        Whole words only. "Demographic" contains the letters of "graph", and
        matching on the letters filed the demographics table as a figure.
        """
        blob = (self.filename + " " + self.full_title).lower()
        if re.search(r"\bfigure\b", blob) or \
           re.search(r"graphs?[_\-. ]", self.filename, re.I):
            return "figure"
        if re.search(r"\blisting\b", blob):
            return "listing"
        return "table"

    def column(self, index):
        return [r[index] for r in self.rows if len(r) > index]

    def column_by_header(self, name):
        """Cells of the first column whose header contains `name`."""
        low = name.lower()
        for i, h in enumerate(self.headers):
            if low in h.lower():
                return self.column(i)
        return []

    def footnote_text(self):
        return " ".join(self.footnotes)


def read_output(path):
    """Read one .rtf file into an Output."""
    with open(path, "r", encoding="latin-1", errors="replace") as fh:
        raw = fh.read()

    lines = to_lines(raw)
    row_positions = [i for i, (kind, _) in enumerate(lines) if kind == "row"]

    out = Output(path=path, filename=os.path.basename(path))

    if not row_positions:
        # A figure file, or anything else with no table in it.
        out.titles = [" ".join(c) for kind, c in lines]
    else:
        first, last = row_positions[0], row_positions[-1]

        for kind, cells in lines[:first]:
            out.titles.append(" ".join(cells))

        body = [cells for kind, cells in lines[first:last + 1] if kind == "row"]
        if body:
            out.headers = body[0]
            out.rows = body[1:]

        for kind, cells in lines[last + 1:]:
            out.footnotes.append(" ".join(cells))

    # A footnote can land in the title block, and on a figure everything lands
    # there. Move any line that clearly reads as a footnote down where it
    # belongs, so source_line and footnote_text work the same on every output.
    keep = []
    for t in out.titles:
        if t.lower().startswith(_FOOTNOTE_STARTS):
            out.footnotes.append(t)
        else:
            keep.append(t)
    out.titles = keep

    out.text = "\n".join(
        out.titles
        + ["\t".join(out.headers)]
        + ["\t".join(r) for r in out.rows]
        + out.footnotes
    )
    return out
