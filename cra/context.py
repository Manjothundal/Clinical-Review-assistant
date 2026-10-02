# -*- coding: utf-8 -*-
"""
What the explain agent is allowed to read.

Judging a flag needs almost nothing: a check name and some counts. Answering a
question needs more, because the question might be "what does the footnote
actually say" or "how many rows are on that table".

So there is a second, larger context, and this module is the only place it is
built. One file to audit, the same way profile.py is the only place the dataset
view is built.

Three levels, and the app shows which one was used:

    summary   the finding, the output's titles, headers and footnotes, the
              study rules, and the other findings on the same file.
              NO body rows. This is the default.
    table     the above plus the body rows, with identifier columns replaced
              by a count. Turned on per question by the person asking.
    (never)   a dataset record, a subject identifier, a file from the study
              folder. There is no level that includes these.
"""
import re

# Column headers that hold something identifying. Their values are never sent,
# whichever level is used.
ID_HEADERS = ("subject", "usubjid", "subjid", "patient", "site", "investigator",
              "initials", "screening", "randomi")

MAX_ROWS = 40          # a long listing is summarised rather than sent whole


def _is_id_header(head):
    low = str(head).strip().lower()
    return any(word in low for word in ID_HEADERS)


def _redact_rows(output):
    """Body rows with identifier columns blanked out."""
    id_cols = [i for i, h in enumerate(output.headers) if _is_id_header(h)]
    rows = []
    for r in output.rows[:MAX_ROWS]:
        cells = []
        for i, c in enumerate(r):
            cells.append("(id)" if i in id_cols else c)
        rows.append(cells)
    return rows, id_cols


def build(finding, output=None, package=None, level="summary",
          other_findings=None):
    """
    Return (text, notes).

    text  is what goes to the model.
    notes is a short list for the screen saying what was included, so the
          person asking can see it before they ask.
    """
    lines, notes = [], []

    lines.append("FINDING")
    lines.append("  area:      %s" % finding.area)
    lines.append("  finding:   %s" % finding.finding)
    lines.append("  output:    %s" % finding.output_file)
    lines.append("  wrong:     %s" % finding.what_is_wrong)
    lines.append("  evidence:  %s" % finding.evidence)
    lines.append("  check:     %s" % finding.found_by)
    lines.append("  severity:  %s" % finding.severity)
    notes.append("the finding and its evidence")

    if output is not None:
        lines.append("")
        lines.append("THE OUTPUT")
        lines.append("  file:      %s" % output.filename)
        lines.append("  kind:      %s" % output.kind)
        for t in output.titles:
            lines.append("  title:     %s" % t)
        if output.headers:
            lines.append("  columns:   %s" % " | ".join(output.headers))
            lines.append("  body rows: %d" % len(output.rows))
        for f in output.footnotes:
            lines.append("  footnote:  %s" % f)
        notes.append("that output's titles, column names and footnotes")

        if level == "table" and output.rows:
            rows, id_cols = _redact_rows(output)
            lines.append("")
            lines.append("  THE TABLE (%d of %d rows)" % (len(rows), len(output.rows)))
            for r in rows:
                lines.append("    " + " | ".join(str(c) for c in r))
            if id_cols:
                names = ", ".join(output.headers[i] for i in id_cols)
                lines.append("    note: the %s column(s) are shown as (id). "
                             "Their values are not sent." % names)
                notes.append("the table rows, with %s blanked out" % names)
            else:
                notes.append("the table rows")

    if package is not None and package.spec:
        lines.append("")
        lines.append("STUDY RULES (copied out of the SAP by hand)")
        for k, v in package.spec.items():
            lines.append("  %s = %s" % (k, v))
        notes.append("the few SAP rules in spec.txt")

    same = [f for f in (other_findings or [])
            if f.key != finding.key
            and any(n.strip() in finding.output_file
                    for n in f.output_file.split(","))]
    if same:
        lines.append("")
        lines.append("OTHER FINDINGS ON THE SAME OUTPUT")
        for f in same[:8]:
            lines.append("  - [%s] %s" % (f.severity, f.finding))
        notes.append("the other findings on the same file")

    return "\n".join(lines), notes


# ---------------------------------------------------------------------------
def numbers_in(text):
    return set(re.findall(r"\d+(?:\.\d+)?", text or ""))


def invented_numbers(answer, context):
    """Numbers in the answer that are nowhere in what the model was given."""
    return sorted(numbers_in(answer) - numbers_in(context))


def leaked_identifiers(context, datasets):
    """
    Any subject identifier from the study data that appears in the context.
    Used by the tests. Should always be empty.
    """
    out = []
    for name, d in (datasets or {}).items():
        df = d["data"] if isinstance(d, dict) else d
        if "USUBJID" not in getattr(df, "columns", []):
            continue
        for sid in df["USUBJID"].astype(str).unique():
            if sid and sid in context:
                out.append(sid)
    return sorted(set(out))
