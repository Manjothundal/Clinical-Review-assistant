# -*- coding: utf-8 -*-
"""
Explore one finding: the chart, the data behind it, and a draft explanation.

For each kind of check there is a builder that goes back to the data, redoes
the check in plain pandas, and returns:

    chart        an Altair chart with the flagged records in orange and the
                 rest in grey (one accent, so the problem is what you see)
    table        the records behind it, flagged ones first, with a Flag column
    how_to_read  one paragraph on reading the chart
    facts        what the data shows, every number counted here by code
    flagged      the subjects to look at
    code         the pandas that produced it, for the execution log

A model never computes anything shown here. It may only word the explanation,
under the same number rule as everywhere else.
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd
import altair as alt

from .viz import _theme, INK, MUTED, SURFACE

FLAG = "#eb6834"      # accent: the records the finding is about
REST = "#bdbcb4"      # de-emphasis grey: everything else
BLUE = "#2a78d6"
DIAG = "#898781"


@dataclass
class Evidence:
    title: str = ""
    chart: Optional[object] = None
    table: Optional[pd.DataFrame] = None
    table_source: str = ""
    how_to_read: str = ""
    facts: List[str] = field(default_factory=list)
    flagged: List[str] = field(default_factory=list)
    code: str = ""
    datasets: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _all_data(st):
    out = {}
    for group in (st.raw, st.sdtm, st.adam):
        for k, v in group.items():
            out[k.upper()] = v["data"]
    return out


def _ds_var(f):
    first = f.output_file.split(",")[0].strip()
    ds, _, var = first.partition("/")
    return ds.strip().upper(), var.strip().upper()


def _short(u):
    return str(u).split("-")[-1] if u is not None else ""


def _flag_col(mask):
    return mask.map({True: "Flagged", False: "Agrees"})


def _color(title="", domain=("Flagged", "Agrees")):
    return alt.Color("Flag:N", scale=alt.Scale(domain=list(domain),
                                               range=[FLAG, REST]),
                     legend=alt.Legend(title=title or None))


def _table(df, mask, cols, n_rest=6):
    """Flagged rows first, then a few that agree, for context."""
    cols = [c for c in cols if c in df.columns]
    t = df.loc[:, cols].copy()
    t.insert(0, "Flag", mask.map({True: "⚠", False: ""}))
    flagged = t[mask.values]
    rest = t[~mask.values].head(n_rest)
    return pd.concat([flagged.head(40), rest])


def diag_scatter(d, x, y, xt, yt, label="Subject"):
    """x against y with the line of equality. Off the line = flagged."""
    lo = float(min(d[x].min(), d[y].min()))
    hi = float(max(d[x].max(), d[y].max()))
    pad = (hi - lo) * 0.06 or 1
    line = pd.DataFrame({x: [lo - pad, hi + pad], y: [lo - pad, hi + pad]})
    sc = alt.Scale(domain=[lo - pad, hi + pad], nice=False)
    rule = alt.Chart(line).mark_line(color=DIAG, strokeWidth=1,
                                     strokeDash=[4, 3]).encode(
        x=alt.X(x, scale=sc), y=alt.Y(y, scale=sc))
    pts = alt.Chart(d).mark_circle(size=90, opacity=1, stroke=SURFACE,
                                   strokeWidth=2).encode(
        x=alt.X("%s:Q" % x, title=xt, scale=sc),
        y=alt.Y("%s:Q" % y, title=yt, scale=sc),
        color=_color(), order=alt.Order("Flag:N", sort="descending"),
        tooltip=[label, alt.Tooltip(x, title=xt), alt.Tooltip(y, title=yt),
                 "Flag"])
    lab = alt.Chart(d[d.Flag == "Flagged"].head(4)).mark_text(
        align="left", dx=9, dy=-9, color=INK, fontSize=12,
        fontWeight="bold").encode(x="%s:Q" % x, y="%s:Q" % y,
                                  text="%s:N" % label)
    # where several records sit on one spot, say how many
    stack = d.groupby([x, y]).size().reset_index(name="k")
    stack = stack[stack.k > 1]
    stack["txt"] = stack.k.map(lambda k: "×%d" % k)
    many = alt.Chart(stack).mark_text(align="left", dx=9, dy=10, color=MUTED,
                                      fontSize=11).encode(
        x="%s:Q" % x, y="%s:Q" % y, text="txt:N")
    return _theme(alt.layer(rule, pts, lab, many), 300)


def flag_bars(t, cat, val, title, sort="-x"):
    """One bar per category, flagged ones in the accent."""
    base = alt.Chart(t).encode(y=alt.Y("%s:N" % cat, sort=sort, title=None))
    bars = base.mark_bar(cornerRadiusEnd=4, height={"band": 0.6}).encode(
        x=alt.X("%s:Q" % val, title=title, axis=alt.Axis(tickMinStep=1)),
        color=_color(), tooltip=[cat, val, "Flag"])
    lab = base.mark_text(align="left", dx=6, color=INK).encode(
        x="%s:Q" % val, text="%s:Q" % val)
    return _theme(alt.layer(bars, lab), max(190, 42 * len(t) + 60))


def pair_bars(t, cat, series, val, title, domain):
    """Two real series side by side, e.g. what the output says and what ADaM
    holds. Blue and orange, the first two validated slots, with a legend."""
    base = alt.Chart(t).encode(y=alt.Y("%s:N" % cat, title=None, sort=None,
                                       axis=alt.Axis(labelLimit=260)),
                               yOffset=alt.YOffset("%s:N" % series,
                                                   sort=domain))
    bars = base.mark_bar(cornerRadiusEnd=4, height={"band": 0.8}).encode(
        x=alt.X("%s:Q" % val, title=title, axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("%s:N" % series,
                        scale=alt.Scale(domain=domain, range=[BLUE, FLAG]),
                        legend=alt.Legend(title=None, orient="bottom",
                                          labelLimit=0)),
        tooltip=[cat, series, val])
    lab = base.mark_text(align="left", dx=5, color=INK, fontSize=11).encode(
        x="%s:Q" % val, text="%s:Q" % val)
    return _theme(alt.layer(bars, lab), 52 * t[cat].nunique() + 50)


def matrix(t, x, y, n, xt, yt):
    """2 x 2 counts, the off-diagonal cells are the finding."""
    base = alt.Chart(t).encode(x=alt.X("%s:N" % x, title=xt,
                                       axis=alt.Axis(labelAngle=0)),
                               y=alt.Y("%s:N" % y, title=yt))
    cells = base.mark_rect(cornerRadius=4, stroke=SURFACE,
                           strokeWidth=3).encode(
        color=_color(), tooltip=[x, y, n])
    text = base.mark_text(fontSize=20, fontWeight="bold").encode(
        text="%s:Q" % n,
        color=alt.condition("datum.Flag == 'Flagged'", alt.value("#ffffff"),
                            alt.value(INK)))
    return _theme(alt.layer(cells, text), 230)


# ---------------------------------------------------------------------------
# builders, one per kind of check
# ---------------------------------------------------------------------------
def _chg(f, st, data):
    ds, _ = _ds_var(f)
    df = data[ds].copy()
    for c in ("AVAL", "BASE", "CHG"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["AVAL", "BASE", "CHG"])
    df["Expected"] = (df.AVAL - df.BASE).round(6)
    m = (df.Expected - df.CHG).abs() > 1e-6
    df["Flag"], df["Subject"] = _flag_col(m), df.USUBJID.map(_short)
    return Evidence(
        title="CHG against AVAL minus BASE, %s" % ds,
        chart=diag_scatter(df, "Expected", "CHG", "AVAL − BASE (re-derived)",
                           "CHG in %s" % ds),
        table=_table(df, m, ["USUBJID", "PARAMCD", "AVISIT", "AVAL", "BASE",
                             "CHG", "Expected"]),
        table_source=ds,
        how_to_read="Each dot is one record. Across is the change re-derived "
                    "as AVAL minus BASE; up is the CHG stored in %s. On the "
                    "dashed line the two agree. A dot off the line is a record "
                    "whose stored change is wrong." % ds,
        facts=["%d of %d records with AVAL, BASE and CHG sit off the line."
               % (m.sum(), len(df))],
        flagged=sorted(df.loc[m, "USUBJID"].unique()),
        code="d = %s.dropna(subset=['AVAL','BASE','CHG'])\n"
             "flag = (d.AVAL - d.BASE - d.CHG).abs() > 1e-6" % ds.lower(),
        datasets=[ds])


def _adsl_vs_dm(f, st, data):
    var = f.finding.split(" ")[0].upper()
    a = data["ADSL"].drop_duplicates("USUBJID")[["USUBJID", var]]
    d = data["DM"].drop_duplicates("USUBJID")[["USUBJID", var]]
    j = a.merge(d, on="USUBJID", suffixes=("_ADSL", "_DM"))
    num = pd.api.types.is_numeric_dtype(j[var + "_ADSL"])
    if num:
        m = (pd.to_numeric(j[var + "_ADSL"]) != pd.to_numeric(j[var + "_DM"]))
    else:
        m = j[var + "_ADSL"].astype(str) != j[var + "_DM"].astype(str)
    j["Flag"], j["Subject"] = _flag_col(m), j.USUBJID.map(_short)
    ev = Evidence(
        title="%s in ADSL against DM" % var, table=_table(
            j, m, ["USUBJID", var + "_DM", var + "_ADSL"]),
        table_source="ADSL, DM",
        facts=["%d of %d subjects carry a different %s in ADSL."
               % (m.sum(), len(j), var)],
        flagged=sorted(j.loc[m, "USUBJID"]),
        code="j = adsl.merge(dm, on='USUBJID')\n"
             "flag = j.%s_ADSL != j.%s_DM" % (var, var),
        datasets=["ADSL", "DM"])
    if num:
        j[var + "_ADSL"] = pd.to_numeric(j[var + "_ADSL"])
        j[var + "_DM"] = pd.to_numeric(j[var + "_DM"])
        ev.chart = diag_scatter(j, var + "_DM", var + "_ADSL",
                                "%s in DM" % var, "%s in ADSL" % var)
        ev.how_to_read = ("Each dot is one subject: %s in DM across, in ADSL "
                          "up. ADSL copies DM, so every dot should sit on the "
                          "dashed line." % var)
    else:
        t = pd.DataFrame({"Result": ["Same as DM", "Differs from DM"],
                          "Subjects": [int((~m).sum()), int(m.sum())],
                          "Flag": ["Agrees", "Flagged"]})
        ev.chart = flag_bars(t, "Result", "Subjects", "Subjects", sort=None)
        ev.how_to_read = "Subjects whose %s matches DM, and those whose does not." % var
    return ev


def _trtsdt(f, st, data):
    adsl, ex = data["ADSL"].drop_duplicates("USUBJID"), data["EX"]
    first = pd.to_datetime(ex.EXSTDTC.astype(str).str[:10], errors="coerce") \
        .groupby(ex.USUBJID).min()
    tr = adsl.set_index("USUBJID")["TRTSDT"]
    trd = pd.to_datetime("1960-01-01") + pd.to_timedelta(
        pd.to_numeric(tr, errors="coerce"), unit="D") \
        if pd.api.types.is_numeric_dtype(tr) else pd.to_datetime(tr, errors="coerce")
    j = pd.DataFrame({"TRTSDT": trd, "First EXSTDTC": first}).dropna()
    j.index.name = "USUBJID"
    j = j.reset_index()
    day0 = j[["TRTSDT", "First EXSTDTC"]].min().min()
    j["TRTSDT day"] = (j.TRTSDT - day0).dt.days
    j["First dose day"] = (j["First EXSTDTC"] - day0).dt.days
    m = j["TRTSDT day"] != j["First dose day"]
    j["Flag"], j["Subject"] = _flag_col(m), j.USUBJID.map(_short)
    j["TRTSDT"] = j.TRTSDT.dt.date.astype(str)
    j["First EXSTDTC"] = j["First EXSTDTC"].dt.date.astype(str)
    return Evidence(
        title="TRTSDT against the first dose in EX",
        chart=diag_scatter(j, "First dose day", "TRTSDT day",
                           "First EXSTDTC (days from %s)" % day0.date(),
                           "TRTSDT (days from %s)" % day0.date()),
        table=_table(j, m, ["USUBJID", "First EXSTDTC", "TRTSDT"]),
        table_source="ADSL, EX",
        how_to_read="Each dot is one subject: the first dose date in EX across, "
                    "TRTSDT in ADSL up, both as days from the earliest date. "
                    "Off the dashed line, TRTSDT is not the first dose.",
        facts=["%d of %d subjects have TRTSDT on a different day from their "
               "first dose." % (m.sum(), len(j))],
        flagged=sorted(j.loc[m, "USUBJID"]),
        code="first = ex.groupby('USUBJID').EXSTDTC.min()\n"
             "flag = adsl.TRTSDT != first",
        datasets=["ADSL", "EX"])


def _saffl(f, st, data):
    adsl = data["ADSL"].drop_duplicates("USUBJID")
    n_ex = data["EX"].groupby("USUBJID").size()
    a = adsl[["USUBJID", "SAFFL"]].copy()
    a["EX records"] = a.USUBJID.map(n_ex).fillna(0).astype(int)
    a["Dosed"] = (a["EX records"] > 0).map({True: "Dosed in EX",
                                           False: "No dose in EX"})
    a["SAFFL"] = a.SAFFL.fillna("").replace("", "(blank)")
    a["Safety population"] = a.SAFFL.map(lambda v: "SAFFL = Y" if v == "Y"
                                      else "SAFFL not Y")
    m = ((a["Safety population"] == "SAFFL = Y") & (a.Dosed == "No dose in EX")) | \
        ((a["Safety population"] == "SAFFL not Y") & (a.Dosed == "Dosed in EX"))
    t = a.groupby(["Safety population", "Dosed"]).size().reindex(
        pd.MultiIndex.from_product([["SAFFL = Y", "SAFFL not Y"],
                                    ["Dosed in EX", "No dose in EX"]]),
        fill_value=0).reset_index()
    t.columns = ["Safety population", "Dosed", "Subjects"]
    t["Flag"] = (((t["Safety population"] == "SAFFL = Y") & (t.Dosed != "Dosed in EX"))
                 | ((t["Safety population"] != "SAFFL = Y")
                    & (t.Dosed == "Dosed in EX"))).map(
        {True: "Flagged", False: "Agrees"})
    return Evidence(
        title="Safety population against dosing",
        chart=matrix(t, "Dosed", "Safety population", "Subjects", None, None),
        table=_table(a, m, ["USUBJID", "SAFFL", "EX records"]),
        table_source="ADSL, EX",
        how_to_read="Subjects counted by their SAFFL and by whether EX holds "
                    "a dose. The safety population is every dosed subject, so "
                    "only the grey cells should hold anyone. The orange cells "
                    "are the subjects to look at.",
        facts=["%d subject(s) sit in an orange cell." % m.sum(),
               "%d subjects have SAFFL = Y." % (a.SAFFL == "Y").sum()],
        flagged=sorted(a.loc[m, "USUBJID"]),
        code="dosed = ex.USUBJID.unique()\n"
             "flag = (adsl.SAFFL=='Y') != adsl.USUBJID.isin(dosed)",
        datasets=["ADSL", "EX"])


def _membership(f, st, data):
    """Subjects in one dataset and not the other."""
    pair = {"sdtm_subject_not_in_dm": None, "adam_subject_not_in_adsl": "ADSL",
            "adam_dm_not_in_adsl": ("DM", "ADSL"),
            "adam_adsl_not_in_dm": ("ADSL", "DM"),
            "raw_subject_not_in_sdtm": None, "sdtm_subject_not_in_raw": None,
            "sdtm_treated_no_ex": ("DM", "EX")}[f.found_by]
    ds, _ = _ds_var(f)
    if f.found_by == "sdtm_subject_not_in_dm":
        a, b = ds, "DM"
    elif f.found_by == "adam_subject_not_in_adsl":
        a, b = ds, "ADSL"
    elif f.found_by == "raw_subject_not_in_sdtm":
        a, b = ds, "DM"
    elif f.found_by == "sdtm_subject_not_in_raw":
        a = "DM"
        b = next((k for k in st.raw if "DM" in k.upper()), next(iter(st.raw)))
        b = b.upper()
    else:
        a, b = pair
    da, db = data[a], data[b]

    def ids(df):
        for c in ("USUBJID", "SUBJID", "SUBJECT", "SUBJNO", "PATIENT"):
            if c in df.columns:
                return df[c].dropna().astype(str).map(_short)
        return pd.Series([], dtype=str)
    sa, sb = ids(da), ids(db)
    A, B = set(sa), set(sb)
    t = pd.DataFrame({"Group": ["In both", "Only in %s" % a, "Only in %s" % b],
                      "Subjects": [len(A & B), len(A - B), len(B - A)]})
    t["Flag"] = ["Agrees", "Flagged" if A - B else "Agrees",
                 "Flagged" if (B - A and f.found_by in ("sdtm_treated_no_ex",
                                                        "adam_dm_not_in_adsl",
                                                        "sdtm_subject_not_in_raw"))
                 else "Agrees"]
    focus = (A - B) if t.Flag[1] == "Flagged" else (B - A)
    cnt_a, cnt_b = sa.value_counts(), sb.value_counts()
    tab = pd.DataFrame({"Subject": sorted(A | B)})
    tab["Records in %s" % a] = tab.Subject.map(cnt_a).fillna(0).astype(int)
    tab["Records in %s" % b] = tab.Subject.map(cnt_b).fillna(0).astype(int)
    m = tab.Subject.isin(focus)
    return Evidence(
        title="Subjects in %s and %s" % (a, b),
        chart=flag_bars(t, "Group", "Subjects", "Subjects", sort=None),
        table=_table(tab, m, list(tab.columns)), table_source="%s, %s" % (a, b),
        how_to_read="Subjects counted by where they appear. Every subject "
                    "should be in both; the orange bar is the set that is "
                    "not.",
        facts=["%d subjects in both, %d only in %s, %d only in %s."
               % (len(A & B), len(A - B), a, len(B - A), b)],
        flagged=sorted(focus),
        code="only = set(%s.subject) - set(%s.subject)" % (a.lower(), b.lower()),
        datasets=[a, b])


def _raw_count(f, st, data):
    raw = next(k for k in data if k in f.output_file.upper().split(", ")[0]
               .split(" ")[0] or f.output_file.upper().startswith(k))
    dom = f.output_file.split(",")[-1].strip().upper()
    r, s = data[raw].drop_duplicates(), data[dom]
    sc = next(c for c in ("SUBJID", "SUBJECT", "SUBJNO", "USUBJID")
              if c in r.columns)
    nr = r[sc].astype(str).map(_short).value_counts()
    ns = s.USUBJID.astype(str).map(_short).value_counts()
    t = pd.DataFrame({"Raw": nr, "SDTM": ns}).fillna(0).astype(int)
    t.index.name = "Subject"
    t = t.reset_index()
    m = t.Raw != t.SDTM
    t["Flag"] = _flag_col(m)
    return Evidence(
        title="Records per subject, raw %s against SDTM %s" % (raw, dom),
        chart=diag_scatter(t, "Raw", "SDTM", "Records in raw %s" % raw,
                           "Records in SDTM %s" % dom),
        table=_table(t, m, ["Subject", "Raw", "SDTM"]),
        table_source="%s, %s" % (raw, dom),
        how_to_read="Each dot is one subject: records in the raw file across, "
                    "in SDTM up (duplicates removed). On the dashed line every "
                    "raw record was mapped once. Below it, records were lost; "
                    "above it, records were added.",
        facts=["%d of %d subjects have a different record count."
               % (m.sum(), len(t)),
               "Raw %d records, SDTM %d records." % (len(r), len(s))],
        flagged=sorted(t.loc[m, "Subject"]),
        code="raw.drop_duplicates().groupby(subject).size() vs "
             "sdtm.groupby('USUBJID').size()",
        datasets=[raw, dom])


def _values(f, st, data):
    """A variable whose values break a rule: CT, Y/N flags, case."""
    ds, var = _ds_var(f)
    if not var:
        m = re.match(r"(\w+) (in|holds)", f.finding)
        var = m.group(1).upper() if m else ""
    df = data[ds]
    s = df[var].fillna("(missing)").astype(str)
    vc = s.value_counts().reset_index()
    vc.columns = ["Value", "Records"]
    bad = set(re.findall(r"'([^']+)' on", f.evidence))
    vc["Flag"] = vc.Value.isin(bad).map({True: "Flagged", False: "Agrees"})
    m = s.isin(bad)
    return Evidence(
        title="Values of %s in %s" % (var, ds),
        chart=flag_bars(vc.head(15), "Value", "Records", "Records"),
        table=_table(df, m, ["USUBJID", var] + [c for c in df.columns
                                               if c.endswith("SEQ")][:1]),
        table_source=ds,
        how_to_read="Every value %s takes, with how many records hold it. "
                    "The orange bars are values outside the allowed list." % var,
        facts=["%d of %d records hold a value outside the list."
               % (m.sum(), len(s))],
        flagged=sorted(df.loc[m, "USUBJID"].dropna().unique())
        if "USUBJID" in df.columns else [],
        code="%s.%s.value_counts()" % (ds.lower(), var), datasets=[ds])


def _bad_text(f, st, data):
    """Dates that are not dates, numbers that are text, missing STRESN."""
    ds, var = _ds_var(f)
    df = data[ds]
    if f.found_by == "sdtm_stresn_missing":
        c = ds + "STRESC"
        m = df[c].astype(str).str.match(r"^-?\d+(\.\d+)?$") & \
            pd.to_numeric(df[ds + "STRESN"], errors="coerce").isna()
        cols, what = ["USUBJID", ds + "TESTCD", c, ds + "STRESN"], \
            "numeric %s with %sSTRESN empty" % (c, ds)
    else:
        vals = df[var].astype(str).str.strip()
        bad = set(re.findall(r"Examples: (.+?)\.$", f.evidence)[0]
                  .split(", ")) if "Examples:" in f.evidence else set()
        m = vals.isin(bad)
        sc = next((c for c in ("USUBJID", "SUBJID", "SUBJECT") if c in df),
                  None)
        cols, what = [c for c in (sc, var) if c], "values that cannot be read"
    t = pd.DataFrame({"Records": ["Can be used", what.capitalize()],
                      "n": [int((~m).sum()), int(m.sum())],
                      "Flag": ["Agrees", "Flagged"]})
    sc = next((c for c in ("USUBJID", "SUBJID", "SUBJECT") if c in df), None)
    return Evidence(
        title=f.finding, chart=flag_bars(t, "Records", "n", "Records", sort=None),
        table=_table(df, m, cols), table_source=ds,
        how_to_read="Records that can be used as they are, against the %s."
                    % what,
        facts=["%d of %d records: %s." % (m.sum(), len(df), what)],
        flagged=sorted(df.loc[m, sc].astype(str).unique()) if sc else [],
        code="flag = ~%s.%s.str.match(<valid pattern>)" % (ds.lower(),
                                                           var or "STRESC"),
        datasets=[ds])


def _study_day(f, st, data):
    ds, dy = _ds_var(f)
    df, dm = data[ds].copy(), data["DM"].drop_duplicates("USUBJID")
    dtc = dy[:-2] + "DTC"
    ref = df.USUBJID.map(dm.set_index("USUBJID").RFSTDTC)
    d = pd.to_datetime(df[dtc].astype(str).str[:10], errors="coerce")
    r = pd.to_datetime(ref.astype(str).str[:10], errors="coerce")
    diff = (d - r).dt.days
    df["Expected"] = diff.where(diff < 0, diff + 1)
    df[dy] = pd.to_numeric(df[dy], errors="coerce")
    df = df.dropna(subset=["Expected", dy])
    m = df.Expected != df[dy]
    df["Flag"], df["Subject"] = _flag_col(m), df.USUBJID.map(_short)
    df["RFSTDTC"] = df.USUBJID.map(dm.set_index("USUBJID").RFSTDTC)
    return Evidence(
        title="%s against %s and RFSTDTC" % (dy, dtc),
        chart=diag_scatter(df, "Expected", dy, "Study day re-derived", dy),
        table=_table(df, m, ["USUBJID", dtc, "RFSTDTC", dy, "Expected"]),
        table_source="%s, DM" % ds,
        how_to_read="Each dot is one record: the study day re-derived from %s "
                    "and RFSTDTC across, the stored %s up. Off the dashed line "
                    "the stored day is wrong." % (dtc, dy),
        facts=["%d of %d records sit off the line." % (m.sum(), len(df))],
        flagged=sorted(df.loc[m, "USUBJID"].unique()),
        code="dy = date - rfstdtc + (date >= rfstdtc)", datasets=[ds, "DM"])


def _tlf_vs_adam(f, st, data):
    rows = re.findall(r"([\w\-.]+\.rtf): (T\d+|R) n=(\d+), ADaM has (\d+)",
                      f.evidence) or [
        (f.output_file, t, n, a) for t, n, a in
        re.findall(r"(T\d+|R) N=(\d+), ADaM (\d+)", f.evidence)]
    from .study import output_id
    num = {}
    for o in (st.package.outputs if st.package else []):
        num[o.filename] = next((output_id(x) for x in o.titles
                                if output_id(x)), o.filename)
    t = []
    for file, trt, n, a in rows[:8]:
        key = "%s · %s" % (trt, num.get(file, re.sub(r"\.rtf$", "", file)[:24]))
        t += [{"Output": key, "Source": "Output says", "Subjects": int(n)},
              {"Output": key, "Source": "ADaM holds", "Subjects": int(a)}]
    t = pd.DataFrame(t)
    tab = pd.DataFrame([{"Output": r[0], "Treatment": r[1], "Output n": int(r[2]),
                         "ADaM subjects": int(r[3])} for r in rows])
    m = tab["Output n"] != tab["ADaM subjects"]
    return Evidence(
        title="Subjects on the outputs against ADaM",
        chart=pair_bars(t, "Output", "Source", "Subjects", "Subjects",
                        ["ADaM holds", "Output says"]),
        table=_table(tab, m, list(tab.columns)), table_source="TLF, ADaM",
        how_to_read="For each output and treatment, the largest n the output "
                    "prints next to the number of subjects ADaM holds for that "
                    "treatment. An output can never count more subjects than "
                    "the data has.",
        facts=["%d output and treatment pairs print more subjects than ADaM "
               "holds%s." % (m.sum(), ", the first %d are charted" % len(rows[:8])
                             if len(rows) > 8 else "")],
        code="adam.groupby('TRTA').USUBJID.nunique() vs max(n) per column",
        datasets=["ADaM"])


def _pop_n(f, st, data):
    stated = re.findall(r"(?:population_n = |comprises )(\d+)", f.evidence)
    adsl = data["ADSL"].drop_duplicates("USUBJID")
    flag = "SAFFL"
    n = int((adsl[flag].astype(str) == "Y").sum())
    t = pd.DataFrame({"Source": ["Stated", "ADSL %s = Y" % flag],
                      "Subjects": [int(stated[0]) if stated else 0, n]})
    t["Flag"] = ["Flagged", "Agrees"]
    m = adsl[flag].astype(str) != "Y"
    return Evidence(
        title="Population size stated against ADSL",
        chart=flag_bars(t, "Source", "Subjects", "Subjects", sort=None),
        table=_table(adsl, m, ["USUBJID", flag, "PKFL"]), table_source="ADSL",
        how_to_read="The population size written in the %s, against the "
                    "subjects ADSL flags. The table lists the subjects ADSL "
                    "leaves out." % ("SAP" if f.layer == "SAP" else "footnote"),
        facts=["Stated %s, ADSL has %d with %s = Y."
               % (stated[0] if stated else "?", n, flag)],
        flagged=sorted(adsl.loc[m, "USUBJID"]),
        code="(adsl.SAFFL == 'Y').sum()", datasets=["ADSL"])


def _tlf_profile(f, st, data):
    """n across the rows of an output, one line per treatment column."""
    if st.package is None:
        return None
    names = re.findall(r"[\w\-]+\.rtf", f.output_file)
    o = next((x for n in names for x in st.package.outputs
              if x.filename == n and x.headers), None)
    if o is None:
        return None
    cols = [i for i, h in enumerate(o.headers)
            if re.search(r"\b(T\d+|R)\b|^n\b", h)]
    rows = []
    for ri, r in enumerate(o.rows):
        lab = " ".join(str(x) for x in r[:1])
        is_n_row = bool(re.search(r"(^|\s)n$", str(r[0]).strip())) or \
            any(o.headers[i].lower().startswith("n") for i in cols)
        if not is_n_row:
            continue
        for ci in cols:
            if ci < len(r) and re.match(r"^\d+$", str(r[ci]).strip()):
                rows.append({"Row": "%02d %s" % (ri + 1, lab),
                             "Column": o.headers[ci], "n": int(r[ci])})
    if not rows:
        return None
    t = pd.DataFrame(rows)
    # a dip: lower than the value either side
    t["Flag"] = "Agrees"
    for c, g in t.groupby("Column"):
        v = g.n.values
        for k in range(1, len(v) - 1):
            if v[k] < v[k - 1] and v[k] < v[k + 1]:
                t.loc[g.index[k], "Flag"] = "Flagged"
        if len(v) >= 2 and v[-1] < v[0] * 0.5:
            t.loc[g.index[-1], "Flag"] = "Flagged"
    base = alt.Chart(t).encode(
        x=alt.X("Row:N", title=None, sort=None,
                axis=alt.Axis(labelAngle=-35, labelLimit=110,
                              labelExpr="slice(datum.label, 3)")),
        y=alt.Y("n:Q", title="n", axis=alt.Axis(tickMinStep=1)),
        detail="Column:N")
    lines = base.mark_line(strokeWidth=2, color=REST)
    pts = base.mark_circle(size=80, opacity=1, stroke=SURFACE,
                           strokeWidth=2).encode(
        color=_color(), tooltip=["Column", "Row", "n", "Flag"])
    # one end label per line; lines that end on the same value share a label
    last = t.groupby("Column").tail(1)
    last = last.groupby(["Row", "n"]).Column.apply(
        lambda c: ", ".join(sorted(c))).reset_index()
    ends = alt.Chart(last).mark_text(align="left", dx=8, color=MUTED,
                                     fontSize=11).encode(
        x=alt.X("Row:N", sort=None), y="n:Q", text="Column:N")
    table = pd.DataFrame([dict(zip(o.headers, r)) for r in o.rows])
    flagged_rows = set(t.loc[t.Flag == "Flagged", "Row"].str[3:])
    mm = table.iloc[:, 0].astype(str).isin(flagged_rows)
    return Evidence(
        title="Counts down %s" % o.filename,
        chart=_theme(alt.layer(lines, pts, ends), 300),
        table=_table(table, mm, list(table.columns), n_rest=30),
        table_source=o.filename,
        how_to_read="Each line is one count column of the output, read down "
                    "its rows. Orange points are where a count drops and comes "
                    "back, or falls by more than half, with no footnote to say "
                    "why.",
        facts=["%d point(s) flagged on %d line(s)."
               % ((t.Flag == "Flagged").sum(), t.Column.nunique())],
        code="n per column down the rows of the RTF table", datasets=[o.filename])


BUILDERS = {
    "adam_chg": _chg, "adam_adsl_vs_dm": _adsl_vs_dm,
    "adam_trtsdt_vs_ex": _trtsdt, "adam_saffl_no_dose": _saffl,
    "adam_dosed_not_saffl": _saffl,
    "sdtm_subject_not_in_dm": _membership, "adam_subject_not_in_adsl": _membership,
    "adam_dm_not_in_adsl": _membership, "adam_adsl_not_in_dm": _membership,
    "raw_subject_not_in_sdtm": _membership, "sdtm_subject_not_in_raw": _membership,
    "sdtm_treated_no_ex": _membership,
    "raw_vs_sdtm_count": _raw_count,
    "cdisc_ct": _values, "cdisc_flag_values": _values,
    "one_value_on_every_record": _values,
    "same_answer_written_two_ways": _values,
    "raw_bad_dates": _bad_text, "cdisc_iso8601": _bad_text,
    "raw_text_in_numbers": _bad_text, "sdtm_stresn_missing": _bad_text,
    "sdtm_study_day": _study_day,
    "tlf_n_above_adam": _tlf_vs_adam, "tlf_figure_n_vs_adam": _tlf_vs_adam,
    "sap_population_n": _pop_n, "tlf_population_note_vs_adsl": _pop_n,
}


def build(f, st):
    """Evidence for one finding. Falls back to the output table, or nothing."""
    data = _all_data(st)
    ev = None
    fn = BUILDERS.get(f.found_by)
    try:
        if fn:
            ev = fn(f, st, data)
        elif ".rtf" in f.output_file:
            ev = _tlf_profile(f, st, data)
    except Exception as exc:                 # a chart must never break the page
        ev = Evidence(title=f.finding, facts=["The chart could not be drawn: %s"
                                              % exc])
    if ev is None:
        ev = Evidence(title=f.finding)
        ds, var = _ds_var(f)
        if ds in data:
            ev.table = data[ds].head(20)
            ev.table_source = ds
        elif st.package is not None:
            m = re.search(r"[\w\-]+\.rtf", f.output_file)
            o = next((x for x in st.package.outputs
                      if m and x.filename == m.group(0)), None)
            if o is not None and o.headers:
                ev.table = pd.DataFrame([dict(zip(o.headers, r))
                                         for r in o.rows])
                ev.table_source = o.filename
        ev.how_to_read = ("This check has no chart. The finding rests on the "
                          "text and counts in its evidence.")
    if not ev.facts:
        ev.facts = [f.evidence]
    return ev


# What to look up in the SAP for each kind of check. Plain words beat the
# finding's own text, which is about the data rather than the rule.
TOPIC = {
    "adam_chg": "baseline change from baseline", "adam_base_constant":
    "baseline defined", "sdtm_study_day": "first dose", "adam_trtsdt_vs_ex":
    "first dose", "adam_saffl_no_dose": "safety population dose",
    "adam_dosed_not_saffl": "safety population dose", "sap_population_n":
    "subjects enrolled safety population", "tlf_population_note_vs_adsl":
    "safety population subjects", "sap_population_flag": "population",
    "sap_pk_parameters": "pk parameters derived", "sap_treatments":
    "treatments", "decimals_vs_spec": "significant digits presented",
    "integer_only_column": "significant digits presented",
    "percent_without_denominator": "percentages based number subjects",
    "denominator_vs_population": "percentages based number subjects safety",
    "treatment_columns_present": "tables present results by treatment",
    "exclusion_applied_consistently": "missing pre-dose excluded",
    "counts_dip_and_return": "missing values imputed",
    "n_drops_without_footnote": "missing values imputed",
    "paired_comparison_same_n": "crossover treatments", "sap_output_not_in_shells":
    "planned outputs", "shell_not_delivered": "planned outputs",
    "tlf_n_above_adam": "pk population evaluable", "tlf_figure_n_vs_adam":
    "pk population evaluable",
}


def related(f, folder, k=2, min_score=4.0):
    """
    The SAP passages and past review findings closest to a finding.
    Spec rows only for spec and CDISC findings, matched on dataset and
    variable, because a spec row is about one variable, not a rule.
    """
    from .rag import index_for, Hit
    idx = index_for(folder)
    docs = []
    topic = TOPIC.get(f.found_by)
    if topic:
        docs = [h for h in idx.search(topic, k=k, kinds={"sap", "shells"})
                if h.score >= min_score]
    if f.found_by.startswith(("spec_", "cdisc_")):
        ds, var = _ds_var(f)
        if not var:
            m = re.match(r"(\w+) (in|holds)", f.finding)
            var = m.group(1).upper() if m else ""
        if ds and var:
            docs += [h for h in idx.search("Dataset %s Variable %s" % (ds, var),
                                           k=3, kinds={"specs"})
                     if "Dataset: %s;" % ds in h.chunk.text
                     and "Variable: %s;" % var in h.chunk.text][:1]
    # a past review row that names this very check is an exact link
    past = [Hit(c, 99.0) for c in idx.chunks if c.kind == "library"
            and re.search(r"Check: [\w.]*\b%s\b" % re.escape(f.found_by),
                          c.text)][:1]
    if not past:
        q = "%s %s" % (f.finding, f.what_is_wrong)
        past = [h for h in idx.search(q, k=1, kinds={"library"})
                if h.score >= 12.0]
    return docs, past


def draft_explanation(f, ev, agent_entry=None, docs=None):
    """The code-written draft. Every number comes from the evidence."""
    sections = [
        ("How to read the figure", ev.how_to_read),
        ("What the data shows", " ".join(ev.facts)),
        ("Why it matters", f.what_is_wrong),
    ]
    obs = ""
    if ev.flagged:
        obs = ("Look at %s. Check the source records before deciding on a "
               "fix. The cause cannot be set from this chart alone."
               % ", ".join(ev.flagged[:6]) + (" and %d more" % (len(ev.flagged) - 6)
                                               if len(ev.flagged) > 6 else ""))
    else:
        obs = "Check the source of this finding before deciding on a fix."
    if agent_entry and agent_entry.get("fixes"):
        obs += " A suggested fix is on the Agent page."
    if docs:
        h = docs[0]
        sections.insert(3, ("What the documents say",
                            "%s [%s]" % (h.chunk.text[:320]
                                         + ("..." if len(h.chunk.text) > 320
                                            else ""), h.cite)))
    sections.append(("Observation for review", obs))
    return sections


def tidy(df):
    """Whole numbers without .000000, other numbers to 3 decimals, for display."""
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_float_dtype(out[c]):
            v = out[c].dropna()
            if len(v) and (v == v.round()).all():
                out[c] = out[c].astype("Int64")
            else:
                out[c] = out[c].round(3)
    return out


def split_sections(text):
    """'**Heading**\nbody' blocks back into (heading, body) pairs."""
    parts = re.split(r"\*\*(.+?)\*\*\s*\n?", text or "")
    if len(parts) < 3:
        return [("Explanation", (text or "").strip())]
    return [(parts[i].strip(), parts[i + 1].strip())
            for i in range(1, len(parts) - 1, 2)]
