"""
Engine 1: the scan.

Plain Python. No AI here at all.

Every function below takes the study data and returns a list of Flags.
A Flag is something that looks odd, with the exact numbers behind it.
It is not a finding yet. The AI decides which flags matter, and a person decides
whether to keep them.
"""
from dataclasses import dataclass, field
from typing import List
import numpy as np
import pandas as pd

# Values that mean "a place on the outside of the body".
# A tablet or a film should never carry one of these.
BODY_SURFACE = {
    "THIGH", "ARM", "UPPER ARM", "ABDOMEN", "BUTTOCK", "DELTOID",
    "GLUTEAL", "SHOULDER", "HIP", "BACK", "CHEST", "FOREARM",
}
ORAL_ROUTES = {"ORAL", "SUBLINGUAL", "BUCCAL", "TRANSMUCOSAL"}


@dataclass
class Flag:
    """One thing that looks odd."""
    kind: str                    # which check found it
    dataset: str                 # which dataset
    variable: str = ""           # which variable, if it is about one variable
    headline: str = ""           # one line, in plain words
    evidence: str = ""           # the numbers
    detail: dict = field(default_factory=dict)   # anything the AI might want

    def as_row(self):
        return {"Check": self.kind, "Dataset": self.dataset, "Variable": self.variable,
                "What was noticed": self.headline, "Evidence": self.evidence}


# ------------------------------------------------------------------ checks

def check_constant(datasets):
    """A variable that holds the same value on every single record."""
    out = []
    for ds, d in datasets.items():
        df = d["data"]
        for col in df.columns:
            s = df[col].dropna()
            if len(s) < 10 or s.nunique() != 1:
                continue
            if col in ID_VARS or col == "DOMAIN":   # these are meant to be constant
                continue
            val = s.iloc[0]
            if str(val).strip() == "":
                continue
            out.append(Flag(
                kind="One value on every record", dataset=ds, variable=col,
                headline=f"{col} holds '{val}' on all {len(s)} records.",
                evidence=f"{ds}: {col} = '{val}' on {len(s)} of {len(df)} records, "
                         f"0 other values. Label: {d['labels'].get(col, col)}.",
                detail={"value": str(val), "n": int(len(s))}))
    return out


def check_case_variants(datasets):
    """The same answer written two ways, for example RELATED and Related."""
    out = []
    for ds, d in datasets.items():
        df = d["data"]
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                continue
            s = df[col].dropna().astype(str).str.strip()
            s = s[s != ""]
            if s.empty:
                continue
            groups = s.groupby(s.str.upper())
            for upper_val, grp in groups:
                forms = grp.value_counts()
                if len(forms) > 1:
                    listed = ", ".join(f"'{k}' on {v}" for k, v in forms.items())
                    out.append(Flag(
                        kind="Same answer written two ways", dataset=ds, variable=col,
                        headline=f"{col} holds '{upper_val}' written {len(forms)} "
                                 f"different ways.",
                        evidence=f"{ds}: {col} holds {listed}. "
                                 f"These are one answer, not {len(forms)}.",
                        detail={"forms": {str(k): int(v) for k, v in forms.items()}}))
    return out


def check_route_vs_location(datasets):
    """A tablet or film cannot be given on the thigh."""
    out = []
    for ds, d in datasets.items():
        df = d["data"]
        cols = set(df.columns)
        route_col = next((c for c in ("EXROUTE", "CMROUTE") if c in cols), None)
        loc_col = next((c for c in ("EXLOC", "CMLOC") if c in cols), None)
        if not route_col or not loc_col:
            continue
        r = df[route_col].astype(str).str.upper().str.strip()
        l = df[loc_col].astype(str).str.upper().str.strip()
        bad = df[(r.isin(ORAL_ROUTES)) & (l.isin(BODY_SURFACE))]
        if len(bad):
            routes = ", ".join(sorted(bad[route_col].astype(str).unique()))
            locs = ", ".join(sorted(bad[loc_col].astype(str).unique()))
            out.append(Flag(
                kind="Combination that cannot happen", dataset=ds, variable=loc_col,
                headline=f"{len(bad)} records give an oral or sublingual route "
                         f"but a body-surface location.",
                evidence=f"{ds}: {len(bad)} of {len(df)} records hold "
                         f"{route_col} in ({routes}) together with {loc_col} in ({locs}).",
                detail={"n": int(len(bad))}))
    return out


def check_date_order(datasets):
    """An end date before its start date."""
    out = []
    pairs = [("EXSTDTC", "EXENDTC"), ("AESTDTC", "AEENDTC"), ("CMSTDTC", "CMENDTC"),
             ("ASTDT", "AENDT"), ("TRTSDT", "TRTEDT")]
    for ds, d in datasets.items():
        df = d["data"]
        for start, end in pairs:
            if start not in df.columns or end not in df.columns:
                continue
            s = pd.to_datetime(df[start], errors="coerce")
            e = pd.to_datetime(df[end], errors="coerce")
            bad = df[(s.notna()) & (e.notna()) & (e < s)]
            if len(bad):
                ex = bad.iloc[0]
                out.append(Flag(
                    kind="Dates out of order", dataset=ds, variable=end,
                    headline=f"{len(bad)} records have {end} before {start}.",
                    evidence=f"{ds}: {len(bad)} of {len(df)} records. First one is "
                             f"{ex.get('USUBJID', 'subject unknown')}, "
                             f"{start}={ex[start]}, {end}={ex[end]}.",
                    detail={"n": int(len(bad))}))
    return out


def check_missing_for_some_subjects(datasets):
    """
    A parameter that exists for most subjects but is missing entirely for a few.
    This is how "no AUC for 3 subjects" shows up.
    """
    out = []
    for ds, d in datasets.items():
        df = d["data"]
        if not {"USUBJID", "PARAMCD"}.issubset(df.columns):
            continue
        all_subs = set(df["USUBJID"].dropna().unique())
        if len(all_subs) < 5:
            continue
        for param, grp in df.groupby("PARAMCD"):
            have = set(grp["USUBJID"].dropna().unique())
            missing = all_subs - have
            if 0 < len(missing) <= max(3, 0.2 * len(all_subs)):
                listed = ", ".join(sorted(missing)[:6])
                out.append(Flag(
                    kind="Missing for a few subjects only", dataset=ds, variable="PARAMCD",
                    headline=f"{param} is missing for {len(missing)} of "
                             f"{len(all_subs)} subjects.",
                    evidence=f"{ds}: {param} is present for {len(have)} subjects and "
                             f"absent for {len(missing)}: {listed}. Other parameters in "
                             f"the same dataset cover all {len(all_subs)}.",
                    detail={"param": str(param), "missing": sorted(missing)}))
    return out


def check_label_vs_values(datasets):
    """
    A label that promises something the values do not show,
    for example "per mg" on values that were never divided by a dose.
    """
    out = []
    markers = ["/mg", "per mg", "/kg", "per kg", "normalised", "normalized"]
    for ds, d in datasets.items():
        df = d["data"]
        if not {"PARAM", "AVAL"}.issubset(df.columns):
            continue
        for param, grp in df.groupby("PARAM"):
            text = str(param).lower()
            if not any(m in text for m in markers):
                continue
            vals = pd.to_numeric(grp["AVAL"], errors="coerce").dropna()
            if vals.empty:
                continue
            out.append(Flag(
                kind="Label disagrees with the values", dataset=ds, variable="PARAM",
                headline=f"'{param}' says the values are normalised by dose.",
                evidence=f"{ds}: {len(vals)} records. Values run from {vals.min():.2f} "
                         f"to {vals.max():.2f}, mean {vals.mean():.2f}. Check whether "
                         f"these were actually divided by the dose, because the label "
                         f"and the unit text go straight into table headers.",
                detail={"param": str(param), "mean": float(vals.mean())}))
    return out


def check_outliers(datasets):
    """A value a long way from all the others, using median absolute deviation."""
    out = []
    for ds, d in datasets.items():
        df = d["data"]
        if not {"PARAMCD", "AVAL"}.issubset(df.columns):
            continue
        for param, grp in df.groupby("PARAMCD"):
            v = pd.to_numeric(grp["AVAL"], errors="coerce").dropna()
            if len(v) < 20:
                continue
            med = v.median()
            mad = (v - med).abs().median()
            if mad == 0:
                continue
            score = 0.6745 * (v - med).abs() / mad
            far = v[score > 6]
            if len(far) and len(far) <= max(3, 0.05 * len(v)):
                worst_i = score.idxmax()
                sub = grp.loc[worst_i].get("USUBJID", "unknown")
                out.append(Flag(
                    kind="Value far from the rest", dataset=ds, variable="AVAL",
                    headline=f"{len(far)} {param} values sit far outside the rest.",
                    evidence=f"{ds}: {param} median {med:.2f}. The furthest is "
                             f"{v.loc[worst_i]:.2f} for {sub}, which is "
                             f"{score.loc[worst_i]:.1f} times the usual spread away. "
                             f"{len(far)} of {len(v)} values are beyond 6 times.",
                    detail={"param": str(param), "n": int(len(far))}))
    return out


def check_treatment_ratio_outlier(datasets):
    """
    One subject whose Test over Reference ratio sits a long way from everyone
    else's.

    In a crossover study each subject is their own control, so the ratio is the
    number a reviewer actually looks at. A raw outlier on AVAL is much weaker:
    a subject can have high exposure on both treatments and be perfectly normal.
    That is why check_outliers, which works on AVAL, misses this.
    """
    out = []
    for ds, d in datasets.items():
        df = d["data"]
        need = {"USUBJID", "TRTA", "PARAMCD", "AVAL"}
        if not need.issubset(df.columns):
            continue
        trts = [str(t).strip() for t in df["TRTA"].dropna().unique()]
        test = next((t for t in trts if t.lower().startswith("test")), None)
        ref = next((t for t in trts if t.lower().startswith("ref")), None)
        if not test or not ref:
            continue

        for param, grp in df.groupby("PARAMCD"):
            wide = grp.pivot_table(index="USUBJID", columns="TRTA",
                                   values="AVAL", aggfunc="first")
            if test not in wide.columns or ref not in wide.columns:
                continue
            pair = wide[[test, ref]].dropna()
            pair = pair[pair[ref] > 0]
            if len(pair) < 12:
                continue

            ratio = pair[test] / pair[ref]
            med = ratio.median()
            mad = (ratio - med).abs().median()
            if mad == 0:
                continue
            score = 0.6745 * (ratio - med).abs() / mad
            far = score[score > 5]
            if not len(far) or len(far) > max(3, 0.05 * len(ratio)):
                continue

            worst = score.idxmax()
            out.append(Flag(
                kind="Ratio far from the rest", dataset=ds, variable="AVAL",
                headline=f"{len(far)} subject(s) have a {param} "
                         f"{test}/{ref} ratio far from every other subject.",
                evidence=f"{ds}: across {len(ratio)} subjects the median {param} "
                         f"{test}/{ref} ratio is {med:.2f}. "
                         f"{worst} reads {ratio.loc[worst]:.2f} "
                         f"({pair.loc[worst, test]:.1f} against "
                         f"{pair.loc[worst, ref]:.1f}), which is "
                         f"{score.loc[worst]:.1f} times the usual spread away. "
                         f"{len(far)} of {len(ratio)} subjects are beyond 5 times.",
                detail={"param": str(param), "n": int(len(far)),
                        "median_ratio": float(med)}))
    return out


def check_digit_preference(datasets):
    """
    Too many readings ending in 0 or 5. Usually rounding at the bedside,
    not an error, but worth knowing before any small-change analysis.
    """
    out = []
    for ds, d in datasets.items():
        df = d["data"]
        if not {"PARAMCD", "AVAL"}.issubset(df.columns):
            continue
        for param, grp in df.groupby("PARAMCD"):
            v = pd.to_numeric(grp["AVAL"], errors="coerce").dropna()
            v = v[v == v.round()]              # whole numbers only
            if len(v) < 100:
                continue
            last = (v.abs().astype(int) % 10).value_counts(normalize=True)
            p0 = last.get(0, 0)
            if p0 > 0.25:
                out.append(Flag(
                    kind="Digit rounding", dataset=ds, variable="AVAL",
                    headline=f"{p0*100:.0f}% of {param} readings end in 0.",
                    evidence=f"{ds}: of {len(v)} whole-number {param} readings, "
                             f"{p0*100:.0f}% end in 0 against about 10% expected. "
                             f"This is normal rounding rather than an error, but it "
                             f"limits how small a change can be trusted.",
                    detail={"param": str(param), "pct_zero": float(p0)}))
    return out


# ------------------------------------------------------------------ cross-study

# Identifiers are different in every study by definition. Never compare them.
ID_VARS = {"STUDYID", "USUBJID", "SUBJID", "SITEID", "SPDEVID", "POOLID"}


def check_against_other_studies(profile_this, profiles_other, this_name):
    """
    Engine 3 in the design: compare this study with the finished ones.
    Where the others all agree and this one does not, say so.
    """
    out = []
    if not profiles_other:
        return out
    for ds, p in profile_this.items():
        for var, v in p["variables"].items():
            if v["type"] != "text" or "values" not in v:
                continue
            if var in ID_VARS:
                continue
            mine = set(v["values"].keys())
            others, agree = {}, 0
            for name, op in profiles_other.items():
                ov = op.get(ds, {}).get("variables", {}).get(var)
                if not ov or "values" not in ov:
                    continue
                theirs = set(ov["values"].keys())
                others[name] = theirs
                if theirs & mine:
                    agree += 1
            if len(others) >= 2 and agree == 0:
                lines = "; ".join(f"{n} holds {sorted(s)}" for n, s in others.items())
                out.append(Flag(
                    kind="Different from our other studies", dataset=ds, variable=var,
                    headline=f"{var} holds values no other study uses.",
                    evidence=f"{this_name} holds {sorted(mine)} in {ds}.{var}. "
                             f"{lines}. No value is shared with any of the "
                             f"{len(others)} finished studies checked.",
                    detail={"mine": sorted(mine),
                            "others": {k: sorted(s) for k, s in others.items()}}))
    return out


# ------------------------------------------------------------------ runner

ALL_CHECKS = [
    check_constant,
    check_case_variants,
    check_route_vs_location,
    check_date_order,
    check_missing_for_some_subjects,
    check_label_vs_values,
    check_outliers,
    check_treatment_ratio_outlier,
    check_digit_preference,
]


def run_scan(datasets, profile_this=None, profiles_other=None, this_name=""):
    """Run every check and return one list of flags."""
    flags = []
    for check in ALL_CHECKS:
        flags.extend(check(datasets))
    if profile_this and profiles_other:
        flags.extend(check_against_other_studies(profile_this, profiles_other, this_name))
    return flags
