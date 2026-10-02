# -*- coding: utf-8 -*-
"""
Checks that only work when you read several outputs together.

This is the family that matters most. Seven of the thirty-eight findings on the
AQ109109 sheet are of this shape: each output is fine on its own, and they only
disagree when you put them side by side.

Examples from that sheet:
    a figure title declaring 48 subjects while the table beside it reports 47
    an exclusion applied to one output family and not to the other four
    two different listings carrying one identical title
    a figure carrying a different study number from the rest of the package

Plain Python. No AI.
"""
import os
import re
from collections import defaultdict
from .flags import Flag, area_for_output

NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _area(o):
    return area_for_output(o.filename, o.full_title)


def _norm_title(t):
    return re.sub(r"\s+", " ", t).strip().lower()


# ---------------------------------------------------------------------------
# row 17: two different outputs carrying one identical title
# ---------------------------------------------------------------------------
def duplicate_titles(pkg):
    seen = defaultdict(list)
    for o in pkg.outputs:
        # the descriptive title, not the study banner and not the table number
        body = [t for t in o.titles
                if not re.match(r"^\s*(table|figure|listing|appendix)\s+[\d.\-]+\s*$",
                                t, re.I)
                and pkg.study.lower() not in t.lower()]
        if not body:
            continue
        seen[_norm_title(" ".join(body))].append(o)

    out = []
    for title, group in seen.items():
        if len(group) < 2:
            continue
        files = ", ".join(sorted(g.filename for g in group))
        shapes = []
        for g in sorted(group, key=lambda x: x.filename):
            shapes.append("%s has %d row(s), first two columns after the keys "
                          "labelled %s"
                          % (g.filename, len(g.rows),
                             " and ".join(g.headers[4:6]) or "nothing"))
        out.append(Flag(
            kind="duplicate_titles", area=_area(group[0]), output=files,
            finding="%d outputs carry one identical title" % len(group),
            what_is_wrong="These outputs share the same title word for word but "
                          "hold different content. A reader looking for one of "
                          "them in the appendix cannot tell which is which, and "
                          "a title that describes one of them does not describe "
                          "the other.",
            evidence="Title in all %d: \"%s\". %s."
                     % (len(group), group[0].titles[-1], ". ".join(shapes)),
            severity="Major"))
    return out


# ---------------------------------------------------------------------------
# row 8: an output carrying a different study or protocol from the rest
# ---------------------------------------------------------------------------
# A study number is either hyphenated (DEMO-BE-101) or run together (AQ109109).
_STUDY = re.compile(r"\b([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+|[A-Z]{2,4}\d{4,8})\b")
_PROTOCOL = re.compile(r"protocol\s+([\w\-]+)", re.I)


def study_and_protocol_consistent(pkg):
    studies, protocols = defaultdict(list), defaultdict(list)
    for o in pkg.outputs:
        head = " ".join(o.titles[:2])
        for m in _STUDY.finditer(head):
            token = m.group(1).upper()
            if any(ch.isdigit() for ch in token):
                studies[token].append(o.filename)
                break
        p = _PROTOCOL.search(head)
        if p:
            protocols[p.group(1)].append(o.filename)

    def odd_ones(groups):
        """file -> the value it carries, for every file not carrying the usual one."""
        if len(groups) < 2:
            return None, {}
        ranked = sorted(groups.items(), key=lambda kv: -len(kv[1]))
        main = ranked[0][0]
        odd = {}
        for value, files in ranked[1:]:
            for f in files:
                odd[f] = value
        return main, odd

    main_study, odd_study = odd_ones(studies)
    main_proto, odd_proto = odd_ones(protocols)

    # One finding per file, naming whichever of the two is wrong. The review
    # sheet writes this as a single finding, not one per identifier.
    out = []
    for fname in sorted(set(odd_study) | set(odd_proto)):
        wrong, evid = [], []
        if fname in odd_study:
            wrong.append("study %s" % odd_study[fname])
            evid.append("carries study %s where the other %d output(s) carry %s"
                        % (odd_study[fname], len(studies[main_study]), main_study))
        if fname in odd_proto:
            wrong.append("protocol %s" % odd_proto[fname])
            evid.append("carries protocol %s where the other %d output(s) carry %s"
                        % (odd_proto[fname], len(protocols[main_proto]), main_proto))
        out.append(Flag(
            kind="study_and_protocol_consistent",
            area=area_for_output(fname), output=fname,
            finding="%s carries %s, not this study's" % (fname, " and ".join(wrong)),
            what_is_wrong="Every output in a delivery must carry the same study "
                          "and protocol on its banner. This one does not, so it "
                          "reads as belonging to another study and would be "
                          "filed against the wrong submission.",
            evidence="%s %s." % (fname, "; ".join(evid)),
            severity="Critical"))
    return out


# ---------------------------------------------------------------------------
# row 22: a figure panel declares an N the table contradicts
# ---------------------------------------------------------------------------
_N_IN_TITLE = re.compile(r"([A-Za-z0-9]+)\s*\(\s*N\s*=\s*(\d+)\s*\)", re.I)


def _counts_by_treatment(table):
    """Largest count seen for each treatment column on a table."""
    found = {}
    for ci, head in enumerate(table.headers):
        m = re.search(r"\b(T\d|R|Test|Reference)\b", head)
        if not m:
            continue
        vals = []
        for r in table.rows:
            if len(r) <= ci:
                continue
            v = NUM.search(str(r[ci]))
            if v and float(v.group()).is_integer():
                vals.append(int(float(v.group())))
        if vals:
            found[m.group(1).upper()] = (max(vals), min(vals))
    return found


def n_consistent_across_outputs(pkg):
    """A figure that names its N, checked against the tables in the same family."""
    out = []
    for fig in pkg.figures():
        declared = {t.upper(): int(n) for t, n in _N_IN_TITLE.findall(fig.full_title)}
        if not declared:
            continue
        stem = re.sub(r"^(mean|geomean|sbj)graphs?_", "",
                      os.path.splitext(fig.filename)[0], flags=re.I)
        family = [t for t in pkg.tables()
                  if re.search(re.escape(stem.split("_")[0]), t.filename, re.I)]
        if not family:
            continue
        clashes, clashing_files = [], set()
        for table in family:
            counts = _counts_by_treatment(table)
            for trt, n in declared.items():
                if trt not in counts:
                    continue
                biggest, smallest = counts[trt]
                if smallest < n:
                    clashes.append("%s declares %s N=%d, %s reports as few as %d"
                                   % (fig.filename, trt, n, table.filename,
                                      smallest))
                    clashing_files.add(table.filename)
        if not clashes:
            continue
        out.append(Flag(
            kind="n_consistent_across_outputs", area=_area(fig),
            # only the files that actually disagree, never the whole family
            output=fig.filename + ", " + ", ".join(sorted(clashing_files)),
            finding="A figure declares a subject count the concentration table "
                    "contradicts",
            what_is_wrong="The figure title declares one fixed subject count per "
                          "treatment for the whole profile. The table in the same "
                          "package reports fewer subjects at some timepoints. At "
                          "those timepoints the figure overstates how many "
                          "subjects contribute to the mean.",
            evidence="; ".join(clashes) + ".",
            severity="Major"))
    return out


# ---------------------------------------------------------------------------
# row 7 and row 20: an exclusion applied to one output family and not another
# ---------------------------------------------------------------------------
_FAMILY = re.compile(r"(IBA|EPIN|DEPIN|SBP|DBP|PR)", re.I)


def exclusion_applied_consistently(pkg):
    """
    Two tables that summarise the same analyte, one baseline-corrected and one
    measured, must rest on the same subjects. When one is smaller, an exclusion
    was applied to one and not to the other.
    """
    pairs = defaultdict(dict)
    for t in pkg.tables():
        m = _FAMILY.search(t.filename)
        if not m:
            continue
        analyte = m.group(1).upper()
        if re.search(r"_adj", t.filename, re.I):
            pairs[analyte]["adj"] = t
        elif re.search(r"_meas", t.filename, re.I):
            pairs[analyte]["meas"] = t

    out = []
    for analyte, both in pairs.items():
        if "adj" not in both or "meas" not in both:
            continue
        a, m = both["adj"], both["meas"]
        ca, cm = _counts_by_treatment(a), _counts_by_treatment(m)
        gaps = []
        for trt in sorted(set(ca) & set(cm)):
            if ca[trt][0] < cm[trt][0]:
                gaps.append("%s reports %d %s against %d in %s"
                            % (a.filename, ca[trt][0], trt, cm[trt][0], m.filename))
        if not gaps:
            continue
        note = a.footnote_text() + " " + m.footnote_text()
        if re.search(r"exclud", note, re.I):
            continue
        out.append(Flag(
            kind="exclusion_applied_consistently", area=_area(a),
            output="%s, %s" % (a.filename, m.filename),
            finding="The %s exclusion is applied to the baseline-corrected "
                    "outputs only" % analyte,
            what_is_wrong="The excluded administrations are removed from the "
                          "baseline-corrected outputs and still counted in the "
                          "measured outputs. The package therefore carries two "
                          "different analysis sets for the same analyte, and "
                          "neither output says which one it used.",
            evidence="; ".join(gaps) + ". Neither output carries a footnote "
                                       "mentioning an exclusion.",
            severity="Critical"))
    return out


# ---------------------------------------------------------------------------
# row 19: an output the shells require that is not in the delivery
# ---------------------------------------------------------------------------
def outputs_present_vs_shells(pkg):
    if not pkg.shells:
        return []
    have = {o.filename.lower() for o in pkg.outputs}
    missing = [(n, t) for n, t in pkg.shells if n.lower() not in have]
    if not missing:
        return []

    # group them, because a whole analyte going missing is one finding
    groups = defaultdict(list)
    for name, title in missing:
        m = _FAMILY.search(name)
        groups[m.group(1).upper() if m else "other"].append((name, title))

    out = []
    for analyte, items in groups.items():
        names = ", ".join(n for n, _ in sorted(items))
        delivered = [o.filename for o in pkg.outputs
                     if analyte != "other" and analyte.lower() in o.filename.lower()]
        out.append(Flag(
            kind="outputs_present_vs_shells",
            area=area_for_output(items[0][0], items[0][1]),
            output=names,
            finding="%d output(s) the shells require are not in the delivery%s"
                    % (len(items),
                       " for %s" % analyte if analyte != "other" else ""),
            what_is_wrong="The mock shells require these outputs. They are not "
                          "in the delivery and no document states that they were "
                          "dropped or judged not feasible."
                          + (" Only %d %s output(s) arrived."
                             % (len(delivered), analyte) if delivered else ""),
            evidence="Shells list %d output(s). %d arrived. Missing: %s.%s"
                     % (len(pkg.shells), len(pkg.shells) - len(missing), names,
                        (" Delivered for %s: %s." % (analyte, ", ".join(delivered)))
                        if delivered else ""),
            severity="Critical"))
    return out


# ---------------------------------------------------------------------------
# row 3 and row 6: records that appear in one output and in no other
# ---------------------------------------------------------------------------
def records_in_one_output_only(pkg):
    """
    Subject identifiers that appear in one listing of a family and are missing
    from the other listings of the same family.
    """
    listings = defaultdict(list)
    for o in pkg.listings():
        # An exclusion listing is meant to hold different subjects from the main
        # listing, so it is never compared against it.
        if re.search(r"exclu", o.filename, re.I):
            continue
        m = _FAMILY.search(o.filename)
        if m:
            listings[m.group(1).upper()].append(o)

    out = []
    for analyte, group in listings.items():
        if len(group) < 2:
            continue
        subjects = {}
        for o in group:
            col = o.column_by_header("subject")
            subjects[o.filename] = {c.strip() for c in col if c.strip()}
        everywhere = set.intersection(*subjects.values()) if subjects else set()
        # No subject at all in common means these are two different populations
        # by design, not a listing with records missing from it.
        if not everywhere:
            continue
        for name, ids in subjects.items():
            others = set.union(*[v for k, v in subjects.items() if k != name])
            only_here = ids - others
            if not only_here:
                continue
            out.append(Flag(
                kind="records_in_one_output_only", area=area_for_output(name),
                output=name,
                finding="%d subject(s) appear in %s and in no other %s listing"
                        % (len(only_here), name, analyte),
                what_is_wrong="These subjects are printed in one listing of the "
                              "family and are absent from the others. Either "
                              "they were dropped from the others without a "
                              "footnote, or they should not be here.",
                evidence="%s holds %d subject(s) not in the other %d listing(s): "
                         "%s. %d subject(s) appear in all of them."
                         % (name, len(only_here), len(group) - 1,
                            ", ".join(sorted(only_here)[:10]), len(everywhere)),
                severity="Major"))
    return out


ALL_ACROSS_CHECKS = [
    duplicate_titles,
    study_and_protocol_consistent,
    n_consistent_across_outputs,
    exclusion_applied_consistently,
    outputs_present_vs_shells,
    records_in_one_output_only,
]


def run_across_checks(pkg):
    from .flags import merge_similar
    flags = []
    for check in ALL_ACROSS_CHECKS:
        try:
            flags.extend(check(pkg))
        except Exception as exc:
            print("check %s failed: %s" % (check.__name__, exc))
    return merge_similar(flags)
