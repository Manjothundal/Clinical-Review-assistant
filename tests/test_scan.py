"""
Tests for the scan.

Each test builds a tiny table by hand, runs one check, and confirms it finds
what it should. No study data is used, so these run anywhere in a second.

Run them with:   pytest
"""
import pandas as pd
import pytest
from cra.scan import (check_constant, check_case_variants, check_route_vs_location,
                      check_date_order, check_missing_for_some_subjects,
                      check_label_vs_values, check_against_other_studies)


def ds(name, df, labels=None):
    """Wrap a table the way read_study() does."""
    return {name: {"data": df, "labels": labels or {c: c for c in df.columns},
                   "path": name + ".xpt"}}


# ---------------------------------------------------------------- constant

def test_constant_is_found():
    df = pd.DataFrame({"USUBJID": [f"S{i}" for i in range(20)],
                       "EXLOC": ["THIGH"] * 20})
    flags = check_constant(ds("EX", df))
    assert len(flags) == 1
    assert "THIGH" in flags[0].evidence
    assert "20" in flags[0].evidence          # the count must be real


def test_constant_not_flagged_when_it_varies():
    df = pd.DataFrame({"USUBJID": [f"S{i}" for i in range(20)],
                       "EXLOC": ["THIGH"] * 10 + ["ARM"] * 10})
    assert check_constant(ds("EX", df)) == []


# ---------------------------------------------------------------- case variants

def test_case_variants_are_found():
    df = pd.DataFrame({"AEREL": ["RELATED"] * 8 + ["Related"] * 3})
    flags = check_case_variants(ds("AE", df))
    assert len(flags) == 1
    assert "'RELATED' on 8" in flags[0].evidence
    assert "'Related' on 3" in flags[0].evidence


def test_case_variants_ignores_genuinely_different_values():
    df = pd.DataFrame({"AEREL": ["RELATED"] * 8 + ["NOT RELATED"] * 3})
    assert check_case_variants(ds("AE", df)) == []


# ---------------------------------------------------------------- route vs location

def test_sublingual_at_the_thigh_is_found():
    df = pd.DataFrame({"EXROUTE": ["SUBLINGUAL"] * 5 + ["INTRAMUSCULAR"] * 5,
                       "EXLOC": ["THIGH"] * 10})
    flags = check_route_vs_location(ds("EX", df))
    assert len(flags) == 1
    assert "5 of 10" in flags[0].evidence      # only the sublingual ones count


def test_injection_at_the_thigh_is_fine():
    df = pd.DataFrame({"EXROUTE": ["INTRAMUSCULAR"] * 10, "EXLOC": ["THIGH"] * 10})
    assert check_route_vs_location(ds("EX", df)) == []


# ---------------------------------------------------------------- dates

def test_end_before_start_is_found():
    df = pd.DataFrame({"USUBJID": ["S1", "S2"],
                       "EXSTDTC": ["2026-03-08", "2026-03-01"],
                       "EXENDTC": ["2026-02-27", "2026-03-02"]})
    flags = check_date_order(ds("EX", df))
    assert len(flags) == 1
    assert "S1" in flags[0].evidence


def test_dates_in_order_are_fine():
    df = pd.DataFrame({"USUBJID": ["S1"], "EXSTDTC": ["2026-03-01"],
                       "EXENDTC": ["2026-03-02"]})
    assert check_date_order(ds("EX", df)) == []


# ---------------------------------------------------------------- missing for a few

def test_parameter_missing_for_a_few_subjects_is_found():
    rows = []
    for i in range(20):
        rows.append({"USUBJID": f"S{i}", "PARAMCD": "CMAX", "AVAL": 1.0})
        if i < 17:                       # three subjects have no AUCLST
            rows.append({"USUBJID": f"S{i}", "PARAMCD": "AUCLST", "AVAL": 2.0})
    flags = check_missing_for_some_subjects(ds("ADPP", pd.DataFrame(rows)))
    assert len(flags) == 1
    assert "AUCLST" in flags[0].headline
    assert "3" in flags[0].evidence


def test_nothing_flagged_when_every_subject_has_everything():
    rows = [{"USUBJID": f"S{i}", "PARAMCD": p, "AVAL": 1.0}
            for i in range(20) for p in ("CMAX", "AUCLST")]
    assert check_missing_for_some_subjects(ds("ADPP", pd.DataFrame(rows))) == []


# ---------------------------------------------------------------- label vs values

def test_per_mg_label_is_flagged():
    df = pd.DataFrame({"PARAM": ["Maximum Effect ((mmHg)/mg)"] * 5,
                       "AVAL": [10.0, 14.0, 62.0, 8.0, 11.0]})
    flags = check_label_vs_values(ds("ADPD", df))
    assert len(flags) == 1
    assert "62.00" in flags[0].evidence


def test_plain_label_is_not_flagged():
    df = pd.DataFrame({"PARAM": ["Maximum Effect (mmHg)"] * 5,
                       "AVAL": [10.0, 14.0, 62.0, 8.0, 11.0]})
    assert check_label_vs_values(ds("ADPD", df)) == []


# ---------------------------------------------------------------- cross-study

def _prof(values):
    return {"EX": {"n_records": sum(values.values()), "n_variables": 1,
                   "variables": {"EXLOC": {"label": "Location", "type": "text",
                                           "n_records": sum(values.values()),
                                           "n_missing": 0, "pct_missing": 0.0,
                                           "n_distinct": len(values),
                                           "values": values}}}}


def test_a_value_no_other_study_uses_is_found():
    mine = _prof({"THIGH": 235})
    others = {"S-097": _prof({"MUCOSA, TONGUE": 497}),
              "S-098": _prof({"MUCOSA, TONGUE": 312})}
    flags = check_against_other_studies(mine, others, "S-101")
    assert len(flags) == 1
    assert "THIGH" in flags[0].evidence


def test_a_normal_value_is_not_flagged():
    mine = _prof({"MUCOSA, TONGUE": 235})
    others = {"S-097": _prof({"MUCOSA, TONGUE": 497}),
              "S-098": _prof({"MUCOSA, TONGUE": 312})}
    assert check_against_other_studies(mine, others, "S-101") == []


def test_identifiers_are_never_compared_between_studies():
    """STUDYID is different in every study by design. It must never be flagged."""
    def p(v):
        return {"EX": {"n_records": 10, "n_variables": 1,
                       "variables": {"STUDYID": {"label": "Study", "type": "text",
                                                 "n_records": 10, "n_missing": 0,
                                                 "pct_missing": 0.0, "n_distinct": 1,
                                                 "values": {v: 10}}}}}
    flags = check_against_other_studies(p("S-101"), {"a": p("S-097"), "b": p("S-098")},
                                        "S-101")
    assert flags == []


# ---------------------------------------------------------------------------
# The within-subject ratio check.
# ---------------------------------------------------------------------------
def test_the_planted_ratio_outlier_is_found():
    """
    One subject was given a Test AUC far above their own Reference. The raw
    outlier check on AVAL misses it, because that subject's absolute values are
    not extreme. In a crossover the ratio is the number that matters.
    """
    import os
    import pytest as _pytest
    folder = os.path.join("data", "DEMO-BE-101")
    if not os.path.isdir(folder):
        _pytest.skip("run make_sample_data.py first")

    from cra.data_io import read_study
    from cra.scan import check_treatment_ratio_outlier, check_outliers

    ds = read_study(folder)
    flags = check_treatment_ratio_outlier(ds)
    assert flags, "the ratio check found nothing"

    f = flags[0]
    assert "AUCLST" in f.headline
    assert "3.26" in f.evidence          # the planted subject's ratio
    assert "1.01" in f.evidence          # the median ratio it is judged against

    # and the reason this check had to exist
    assert check_outliers(ds) == [], \
        "check_outliers now fires too, so this test no longer proves the gap"
