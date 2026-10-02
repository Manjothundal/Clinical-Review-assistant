# -*- coding: utf-8 -*-
"""
Checks that read one output on its own.

Plain Python. No AI. Every check takes a Package and returns Flags.

The number in each docstring is the row of the AQ109109 review sheet the check
was written from, so you can always trace a check back to a real finding.
"""
import re
from .flags import Flag, area_for_output

NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _num(text):
    """First number in a cell, or None. Handles '7 (14.6)' and '1.018'."""
    m = NUM.search(str(text).replace(",", ""))
    return float(m.group()) if m else None


def _ints(cells):
    out = []
    for c in cells:
        v = _num(c)
        if v is not None and float(v).is_integer():
            out.append(int(v))
    return out


def _decimals(text):
    """How many digits after the point. '1.018' -> 3, '12' -> 0."""
    s = str(text).strip()
    m = re.fullmatch(r"-?\d+\.(\d+)", s)
    return len(m.group(1)) if m else 0


def _sig_digits(text):
    s = str(text).strip().lstrip("-").replace(".", "").lstrip("0")
    return len(s.rstrip("0")) if s.rstrip("0") else len(s)


def _area(o):
    return area_for_output(o.filename, o.full_title)


# ---------------------------------------------------------------------------
# row 12, row 13, row 30: no Source line, no footer
# ---------------------------------------------------------------------------
def source_line_present(pkg):
    out = []
    for o in pkg.outputs:
        if o.source_line:
            continue
        out.append(Flag(
            kind="source_line_present", area=_area(o), output=o.filename,
            finding="%s has no Source line" % (o.titles[1] if len(o.titles) > 1
                                               else o.filename),
            what_is_wrong="The output carries no Source line, so nothing on the "
                          "page says which program produced it. A reviewer "
                          "cannot rerun it or tie it back to the program "
                          "library.",
            evidence="%s has %d footnote line(s) and none of them begins with "
                     "Source, Program or Pgm. %d of %d outputs in this delivery "
                     "do carry one."
                     % (o.filename, len(o.footnotes),
                        sum(1 for x in pkg.outputs if x.source_line),
                        len(pkg.outputs)),
            severity="Major"))
    return out


# ---------------------------------------------------------------------------
# row 35: a bare program name with no path and no version
# ---------------------------------------------------------------------------
def program_has_path_and_version(pkg):
    out = []
    for o in pkg.outputs:
        src = o.source_line
        if not src:
            continue
        missing = []
        if "/" not in src and "\\" not in src:
            missing.append("path")
        if not re.search(r"(version|v\d|\bv\s*\d)", src, re.I):
            missing.append("version")
        if not re.search(r"\d{2}[A-Z]{3}\d{4}|\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}",
                         src):
            missing.append("run date")
        if not missing:
            continue
        words = {"path": "a directory path", "version": "a version",
                 "run date": "a run date"}
        phrase = " and ".join(words[m] for m in missing)
        out.append(Flag(
            kind="program_has_path_and_version", area=_area(o),
            output=o.filename,
            finding="%s carries a bare program name with no %s"
                    % (o.filename, " and no ".join(missing)),
            what_is_wrong="The Source line names a program but leaves out %s. "
                          "Two programs of the same name can sit in different "
                          "libraries, so the line does not identify what was "
                          "run." % phrase,
            evidence="Source line reads: %s" % src.strip(),
            severity="Minor"))
    return out


# ---------------------------------------------------------------------------
# row 16: the title names a window the values run past
# ---------------------------------------------------------------------------
_RANGE_IN_TITLE = re.compile(
    r"from\s+(\d+(?:\.\d+)?)\s*(?:to|-|through)\s*(\d+(?:\.\d+)?)\s*"
    r"(minutes?|min|hours?|h|days?)", re.I)


def title_range_vs_values(pkg):
    out = []
    for o in pkg.outputs:
        m = _RANGE_IN_TITLE.search(o.full_title)
        if not m or not o.rows:
            continue
        lo, hi, unit = float(m.group(1)), float(m.group(2)), m.group(3)
        breaches = []
        for r in o.rows:
            label = r[0] if r else ""
            if not re.search(r"max", label, re.I):
                continue
            for cell in r[1:]:
                v = _num(cell)
                if v is not None and v > hi:
                    breaches.append((label, cell))
        if not breaches:
            continue
        shown = ", ".join("%s %s" % (lab, val) for lab, val in breaches[:6])
        out.append(Flag(
            kind="title_range_vs_values", area=_area(o), output=o.filename,
            finding="Reported maxima run past the %g to %g %s window named in "
                    "the table title" % (lo, hi, unit),
            what_is_wrong='The table is titled "%s". %d of the reported maximum '
                          "values sit above %g %s, so the values do not fit the "
                          "window the title claims."
                          % (m.group(0), len(breaches), hi, unit),
            evidence="%s: %d value(s) above %g %s - %s."
                     % (o.filename, len(breaches), hi, unit, shown),
            severity="Major"))
    return out


# ---------------------------------------------------------------------------
# row 18, row 37: a count falls at one row and comes back at the next
# ---------------------------------------------------------------------------
_N_HEADER = re.compile(r"^\s*n\b|^\s*N\b|^\s*n\s*\(", re.I)


def _series_groups(rows):
    """
    Split consecutive rows into groups that belong to the same series.

    A dip only means something inside one series. Rows labelled
    AUC0-5min, AUC0-10min, AUC0-15min are one series. Rows labelled
    Specific gravity, Specific gravity, pH, pH are three different pairs, and a
    count that changes between them is not a dip at all.

    Two labels belong together when they are the same once the digits are
    removed.
    """
    groups, current, shape = [], [], None
    for i, r in enumerate(rows):
        label = re.sub(r"\d+(\.\d+)?", "#", r[0] if r else "").strip().lower()
        if label != shape:
            if len(current) >= 3:
                groups.append(current)
            current, shape = [], label
        current.append(i)
    if len(current) >= 3:
        groups.append(current)
    return groups


_N_ROW = re.compile(r"(^|\s)n$", re.I)


def _n_columns(o):
    """
    Which columns hold subject counts.

    Two layouts turn up. Either a column is headed n, or - the usual shape for
    a PK descriptive table - the row is the n row and every treatment has its
    own column. Rows and columns both have to be handled.
    """
    by_header = [i for i, h in enumerate(o.headers) if _N_HEADER.match(h)]
    if by_header:
        return by_header, None
    n_rows = [i for i, r in enumerate(o.rows) if r and _N_ROW.search(r[0].strip())]
    if len(n_rows) >= 3:
        return list(range(1, len(o.headers))), n_rows
    return [], None


def counts_dip_and_return(pkg):
    out = []
    for o in pkg.outputs:
        if not o.rows or not o.headers:
            continue
        columns, n_rows = _n_columns(o)
        if not columns:
            continue
        if n_rows is None:
            groups = _series_groups(o.rows)
        else:
            groups = [g for g in _series_groups([o.rows[i] for i in n_rows])]
            groups = [[n_rows[k] for k in g] for g in groups]
        if not groups:
            continue
        # One finding per output, not one per column. The review sheet writes
        # the problem once and lists the evidence for every column underneath.
        dips = []
        for ci in columns:
            head = o.headers[ci] if ci < len(o.headers) else "column %d" % ci
            for group in groups:
                vals = [_num(o.rows[i][ci]) if len(o.rows[i]) > ci else None
                        for i in group]
                for k in range(1, len(vals) - 1):
                    a, b, c = vals[k - 1], vals[k], vals[k + 1]
                    if None in (a, b, c):
                        continue
                    if not all(float(v).is_integer() for v in (a, b, c)):
                        continue
                    if b < a and c > b:
                        label = o.rows[group[k]][0].strip()
                        dips.append("%s runs %g, %g then %g at %s"
                                    % (head, a, b, c, label))
        if not dips:
            continue
        cumulative = bool(re.search(r"auc", " ".join(r[0] for r in o.rows), re.I))
        out.append(Flag(
            kind="counts_dip_and_return", area=_area(o), output=o.filename,
            finding="Subject counts fall at one %s and return at the next"
                    % ("partial AUC window" if cumulative else "timepoint"),
            what_is_wrong=("A partial AUC is cumulative, so the table reads as "
                           "though a subject drops out at one window and returns "
                           "at the next. "
                           if cumulative else
                           "The count drops at one timepoint and recovers at the "
                           "next. ")
                          + "The counts may well be right, because a sample that "
                            "was never collected cannot be used for that one "
                            "window. Nothing on the output says so, so the reader "
                            "is left with a number that looks wrong.",
            evidence="%s: %s. No footnote on the output accounts for the "
                     "reduction." % (o.filename, "; ".join(dips)),
            severity="Major",
            detail={"dips": len(dips), "cumulative": cumulative}))
    return out


# ---------------------------------------------------------------------------
# row 25, row 29: a percentage with no denominator anywhere on the page
# ---------------------------------------------------------------------------
_PCT_CELL = re.compile(r"\(\s*\d+(?:\.\d+)?\s*\)")


def percent_without_denominator(pkg):
    out = []
    for o in pkg.outputs:
        heads = " ".join(o.headers)
        if "%" not in heads and not any(_PCT_CELL.search(c)
                                        for r in o.rows for c in r[1:]):
            continue
        foot = o.footnote_text().lower()
        has_denom = bool(re.search(r"\bn\s*=\s*\d+|denominator|percentage[s]? "
                                   r"are based on|out of \d+", foot))
        if has_denom:
            continue
        pct_heads = [h for h in o.headers if "%" in h] or ["the body cells"]
        out.append(Flag(
            kind="percent_without_denominator", area=_area(o),
            output=o.filename,
            finding="%s prints percentages and states no denominator"
                    % (o.titles[1] if len(o.titles) > 1 else o.filename),
            what_is_wrong="The table reports percentages in %s but no footnote "
                          "says what they are a percentage of. The reader cannot "
                          "tell whether the denominator is subjects, events or "
                          "the treatment group." % ", ".join(pct_heads),
            evidence="%s: header reads '%s'. %d footnote line(s), none giving "
                     "an N or a denominator statement."
                     % (o.filename, heads, len(o.footnotes)),
            severity="Major"))
    return out


# ---------------------------------------------------------------------------
# row 26: no treatment columns on a table that should be split by treatment
# ---------------------------------------------------------------------------
def treatment_columns_present(pkg):
    treatments = pkg.spec_list("treatments")
    if not treatments:
        return []
    out = []
    for o in pkg.tables():
        heads = " ".join(o.headers)
        present = [t for t in treatments
                   if re.search(r"\b%s\b" % re.escape(t), heads)]
        if present or not o.headers:
            continue
        if not re.search(r"summary|descriptive", o.full_title, re.I):
            continue
        foot = o.footnote_text()
        says_why = bool(re.search(r"pooled|combined|all treatments|excludes",
                                  foot, re.I))
        if says_why:
            continue
        out.append(Flag(
            kind="treatment_columns_present", area=_area(o), output=o.filename,
            finding="%s has no treatment columns and never says why"
                    % (o.titles[1] if len(o.titles) > 1 else o.filename),
            what_is_wrong="The SAP names %d treatments. This summary table "
                          "carries none of them as a column and no footnote "
                          "says the data are pooled or that a treatment is "
                          "excluded." % len(treatments),
            evidence="%s: header row is '%s'. None of %s appears."
                     % (o.filename, heads, ", ".join(treatments)),
            severity="Major",
            # Plenty of summary tables are pooled on purpose. Code cannot tell
            # which, so this one is put to the model before anyone sees it.
            confidence="candidate"))
    return out


# ---------------------------------------------------------------------------
# row 37: n falls between two visits of the same parameter, with no footnote
# ---------------------------------------------------------------------------
def n_drops_without_footnote(pkg):
    out = []
    for o in pkg.tables():
        ci = next((i for i, h in enumerate(o.headers)
                   if _N_HEADER.match(h)), None)
        if ci is None or not o.rows:
            continue
        foot = o.footnote_text()
        if re.search(r"not (?:all|every)|fewer|missing|only subjects|excluded",
                     foot, re.I):
            continue
        by_param = {}
        for r in o.rows:
            if len(r) <= ci:
                continue
            v = _num(r[ci])
            if v is None or not float(v).is_integer():
                continue
            by_param.setdefault(r[0].strip(), []).append((r[1] if len(r) > 1
                                                          else "", int(v)))
        drops = []
        for param, seq in by_param.items():
            if len(seq) < 2:
                continue
            first, last = seq[0][1], seq[-1][1]
            if last < first:
                drops.append("%s falls from %d at %s to %d at %s"
                             % (param, first, seq[0][0], last, seq[-1][0]))
        if not drops:
            continue
        out.append(Flag(
            kind="n_drops_without_footnote", area=_area(o), output=o.filename,
            finding="Subject numbers fall between visits on %s and no footnote "
                    "explains it"
                    % (o.titles[1] if len(o.titles) > 1 else o.filename),
            what_is_wrong="%d parameter(s) are summarised on fewer subjects at "
                          "the later visit than at baseline. A change from "
                          "baseline computed on that smaller set is not "
                          "comparable with the baseline mean printed beside it, "
                          "and the table carries no footnote saying so."
                          % len(drops),
            evidence="%s: %s." % (o.filename, "; ".join(drops)),
            severity="Major"))
    return out


# ---------------------------------------------------------------------------
# row 11: the denominator is not the population
# ---------------------------------------------------------------------------
def denominator_vs_population(pkg):
    pop = pkg.spec_int("population_n")
    if not pop:
        return []
    out = []
    for o in pkg.tables():
        for ci, head in enumerate(o.headers):
            if not re.fullmatch(r"\s*n\s*", head, re.I):
                continue
            ns = _ints([r[ci] if len(r) > ci else "" for r in o.rows])
            if not ns:
                continue
            low = [n for n in ns if 0 < n < pop * 0.5]
            if len(low) < max(2, len(ns) // 2):
                continue
            foot = o.footnote_text()
            explained = bool(re.search(r"only|abnormal|subset|where |among ",
                                       foot, re.I))
            if explained:
                continue
            out.append(Flag(
                kind="denominator_vs_population", area=_area(o),
                output=o.filename,
                finding="%s summarises far fewer subjects than the population "
                        "and no footnote says which subjects"
                        % (o.titles[1] if len(o.titles) > 1 else o.filename),
                what_is_wrong="The SAP population is %d subjects. The n column "
                              "on this table runs from %d to %d. A mean taken "
                              "on that subset is not a mean for the population, "
                              "and the table does not say which subjects it "
                              "covers." % (pop, min(ns), max(ns)),
                evidence="%s: n values %s against a population of %d. Footnotes "
                         "give no selection rule."
                         % (o.filename, ", ".join(str(n) for n in ns), pop),
                severity="Critical"))
    return out


# ---------------------------------------------------------------------------
# row 28: a code appears in a column that no footnote defines
# ---------------------------------------------------------------------------
_CODEY = re.compile(r"^[A-Z]{2,4}$")


def undefined_code_in_column(pkg):
    out = []
    for o in pkg.outputs:
        if not o.rows or not o.headers:
            continue
        foot = o.footnote_text()
        for ci, head in enumerate(o.headers):
            cells = [str(r[ci]).strip() for r in o.rows if len(r) > ci]
            codes = sorted({c for c in cells if _CODEY.match(c)})
            if not codes:
                continue
            undefined = [c for c in codes
                         if not re.search(r"\b%s\b" % re.escape(c), foot)]
            if not undefined:
                continue
            defined = [c for c in codes if c not in undefined]
            out.append(Flag(
                kind="undefined_code_in_column", area=_area(o),
                output=o.filename,
                finding="Column %s uses the code %s, which no footnote defines"
                        % (head, " and ".join(undefined)),
                what_is_wrong="The %s column prints short codes. %s %s defined "
                              "in a footnote, %s %s not. A reader has no way to "
                              "know what it means."
                              % (head,
                                 ", ".join(defined) or "None are",
                                 "is" if len(defined) == 1 else "are",
                                 " and ".join(undefined),
                                 "is" if len(undefined) == 1 else "are"),
                evidence="%s, column %s: codes present %s. Footnote text "
                         "defines %s."
                         % (o.filename, head, ", ".join(codes),
                            ", ".join(defined) or "none"),
                severity="Minor"))
    return out


# ---------------------------------------------------------------------------
# row 24, row 39: more or fewer digits than the SAP allows
# ---------------------------------------------------------------------------
def decimals_vs_spec(pkg):
    allowed = pkg.spec_int("concentration_significant_digits")
    if not allowed:
        return []
    out = []
    for o in pkg.outputs:
        if not o.rows or not o.headers:
            continue
        if not re.search(r"concentration", o.full_title, re.I):
            continue
        for ci, head in enumerate(o.headers):
            cells = [str(r[ci]).strip() for r in o.rows if len(r) > ci]
            numeric = [c for c in cells if NUM.fullmatch(c)]
            if len(numeric) < 3:
                continue
            over = [c for c in numeric if _sig_digits(c) > allowed]
            if len(over) < len(numeric) / 2:
                continue
            out.append(Flag(
                kind="decimals_vs_spec", area=_area(o), output=o.filename,
                finding="The %s column prints %d significant digits where the "
                        "SAP allows %d" % (head, max(_sig_digits(c) for c in over),
                                           allowed),
                what_is_wrong="The SAP allows up to %d significant digits for "
                              "individual concentrations. The %s column prints "
                              "more on %d of %d values, so it reports a "
                              "precision the assay does not have."
                              % (allowed, head, len(over), len(numeric)),
                evidence="%s, column %s: %s. Allowed %d significant digits."
                         % (o.filename, head, ", ".join(over[:8]), allowed),
                severity="Minor"))
    return out


# ---------------------------------------------------------------------------
# row 31: a measurement carried as a whole number so its range is wrong
# ---------------------------------------------------------------------------
_CONTINUOUS = re.compile(r"bmi|body mass|weight|height|temperature|"
                         r"specific gravity|haematocrit|hematocrit", re.I)


def integer_only_column(pkg):
    out = []
    for o in pkg.tables():
        if not o.rows:
            continue
        for r in o.rows:
            if not r or not _CONTINUOUS.search(r[0]):
                continue
            vals = [c for c in r[1:] if NUM.search(str(c))]
            if not vals:
                continue
            if any(_decimals(NUM.search(str(c)).group()) > 0 for c in vals):
                continue
            # every number on this row is a whole number
            others = [x for x in o.rows
                      if x is not r and len(x) > 1
                      and any(_decimals(NUM.search(str(c)).group()) > 0
                              for c in x[1:] if NUM.search(str(c)))]
            if not others:
                continue
            out.append(Flag(
                kind="integer_only_column", area=_area(o), output=o.filename,
                finding="%s is reported as a whole number while every other "
                        "measurement on the table carries decimals" % r[0].strip(),
                what_is_wrong="%s is a continuous measurement. On this table it "
                              "carries no decimal places, so any range or "
                              "standard deviation taken from it is rounded "
                              "before it is summarised and reads wrong."
                              % r[0].strip(),
                evidence="%s: row '%s' reads %s, all whole numbers. %d other "
                         "row(s) on the same table carry decimals."
                         % (o.filename, r[0].strip(), " / ".join(str(c) for c in r[1:]),
                            len(others)),
                severity="Major"))
    return out


# ---------------------------------------------------------------------------
# row 36: a footnote that belongs to another domain
# ---------------------------------------------------------------------------
_DOMAIN_WORDS = {
    "vital signs": ["vital", "supine", "blood pressure", "pulse"],
    "laboratory": ["haemat", "hemat", "chemistr", "urinalys", "laborator",
                   "haemoglobin", "hemoglobin", "basophil", "eosinophil"],
    "electrocardiogram": ["ecg", "electrocardiogram", "qtc", "rr interval"],
}


def footnote_matches_domain(pkg):
    out = []
    for o in pkg.tables():
        title = o.full_title.lower()
        foot = o.footnote_text().lower()
        if not foot:
            continue
        title_domains = {d for d, words in _DOMAIN_WORDS.items()
                         if any(w in title for w in words)}
        foot_domains = {d for d, words in _DOMAIN_WORDS.items()
                        if any(w in foot for w in words)}
        stray = foot_domains - title_domains
        if not stray or not title_domains:
            continue
        out.append(Flag(
            kind="footnote_matches_domain", area=_area(o), output=o.filename,
            finding="A %s footnote sits on a %s table"
                    % (", ".join(sorted(stray)), ", ".join(sorted(title_domains))),
            what_is_wrong="The footnote describes %s, but the table reports %s. "
                          "The footnote was carried over from another output and "
                          "explains nothing about the numbers underneath it."
                          % (", ".join(sorted(stray)),
                             ", ".join(sorted(title_domains))),
            evidence="%s titled '%s'. Footnote reads: %s"
                     % (o.filename, o.titles[-1] if o.titles else "",
                        o.footnote_text().strip()[:200]),
            severity="Minor"))
    return out


# ---------------------------------------------------------------------------
# row 21: a within-subject comparison resting on two different subject sets
# ---------------------------------------------------------------------------
_IS_COMPARISON = re.compile(r"\bversus\b|\bvs\.?\b|comparison|ratio of", re.I)


def paired_comparison_same_n(pkg):
    if pkg.spec.get("crossover", "").lower() not in ("yes", "y", "true"):
        return []
    out = []
    for o in pkg.tables():
        # Only a table that actually compares two treatments. A concentration
        # table carrying n T1, n T2 and n T3 side by side is not a comparison,
        # and those treatments are allowed to have different subject counts.
        if not _IS_COMPARISON.search(o.full_title):
            continue
        n_cols = [i for i, h in enumerate(o.headers)
                  if re.match(r"\s*n\b", h, re.I)]
        if len(n_cols) != 2:
            continue
        bad = []
        for r in o.rows:
            ns = [_num(r[i]) for i in n_cols if len(r) > i]
            ns = [n for n in ns if n is not None]
            if len(ns) >= 2 and len(set(ns)) > 1:
                bad.append((r[0], ns))
        if not bad:
            continue
        good = len(o.rows) - len(bad)
        detail = "; ".join("%s compares %s"
                           % (lab, " against ".join(str(int(n)) for n in ns))
                           for lab, ns in bad)
        out.append(Flag(
            kind="paired_comparison_same_n", area=_area(o), output=o.filename,
            finding="%s compares two different subject sets in a within-subject "
                    "crossover" % (o.titles[1] if len(o.titles) > 1 else o.filename),
            what_is_wrong="This is a within-subject crossover comparison, so both "
                          "treatments must rest on the same subjects. %d row(s) "
                          "carry different subject counts on the two sides, and "
                          "no footnote says the sets differ."
                          % len(bad),
            evidence="%s: %s. %d other row(s) are balanced."
                     % (o.filename, detail, good),
            severity="Critical"))
    return out


# ---------------------------------------------------------------------------
# row 23: a decision rule stated in a footnote and never applied
# ---------------------------------------------------------------------------
_RULE_WORDS = re.compile(r"will be declared|is declared|success will|"
                         r"criteri[ao] (?:for|is)|is considered successful", re.I)


def rule_stated_not_applied(pkg):
    out = []
    for o in pkg.tables():
        foot = o.footnote_text()
        if not _RULE_WORDS.search(foot):
            continue
        blob = (" ".join(o.headers) + " " + o.full_title + " " +
                " ".join(" ".join(r) for r in o.rows)).lower()
        declared = re.search(r"overall\s+(success|result|outcome)", blob)
        if declared:
            continue
        out.append(Flag(
            kind="rule_stated_not_applied", area=_area(o), output=o.filename,
            finding="%s states the success rule but never applies it"
                    % (o.titles[1] if len(o.titles) > 1 else o.filename),
            what_is_wrong="The footnote states the decision rule in full. No row, "
                          "column or footnote on the output then applies it, so "
                          "the table never says whether overall success was "
                          "declared. The reader has to work it out.",
            evidence="%s: %d body row(s), none labelled Overall. Footnote reads: "
                     "%s" % (o.filename, len(o.rows), foot.strip()[:240]),
            severity="Major"))
    return out


ALL_OUTPUT_CHECKS = [
    source_line_present,
    program_has_path_and_version,
    title_range_vs_values,
    counts_dip_and_return,
    percent_without_denominator,
    treatment_columns_present,
    n_drops_without_footnote,
    denominator_vs_population,
    undefined_code_in_column,
    decimals_vs_spec,
    integer_only_column,
    footnote_matches_domain,
    paired_comparison_same_n,
    rule_stated_not_applied,
]


def run_output_checks(pkg):
    """Every within-output check, with near-duplicates merged into one finding."""
    from .flags import merge_similar
    flags = []
    for check in ALL_OUTPUT_CHECKS:
        try:
            flags.extend(check(pkg))
        except Exception as exc:
            print("check %s failed: %s" % (check.__name__, exc))
    return merge_similar(flags)
