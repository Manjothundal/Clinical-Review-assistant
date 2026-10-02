# -*- coding: utf-8 -*-
"""
The output checks.

Each test names the row of the AQ109109 review sheet it comes from, so a check
that stops working tells you which real finding you would have missed.
"""
import os
import pytest

from cra.outputs import read_package
from cra.checks_output import run_output_checks
from cra.checks_across import run_across_checks
from cra.rtf import read_output

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(HERE, "outputs", "DEMO-BE-101")


@pytest.fixture(scope="module")
def pkg():
    if not os.path.isdir(FOLDER):
        pytest.skip("run make_sample_outputs.py first")
    return read_package(FOLDER)


@pytest.fixture(scope="module")
def kinds(pkg):
    flags = run_output_checks(pkg) + run_across_checks(pkg)
    return {f.kind for f in flags}, flags


# ------------------------------------------------------------------ reader
def test_reader_finds_titles_headers_rows_and_footnotes(pkg):
    o = next(x for x in pkg.outputs
             if x.filename == "PK_Primary_Endpoints_EPIN_adj_6050_T2_vs_R.rtf")
    assert "Table 14-6" in o.titles
    assert o.headers[0] == "Parameter"
    assert len(o.rows) == 5
    assert o.rows[-1][0] == "AUC0-45min"
    assert o.source_line and "t_pk_primary.sas" in o.source_line


def test_reader_handles_an_output_with_no_table(pkg):
    o = next(x for x in pkg.outputs if x.filename == "MeanGraphs_EPIN_adj_6050.rtf")
    assert o.kind == "figure"
    assert o.rows == []
    assert o.source_line is not None


# ------------------------------------------------- one check, one real row
def test_row_13_missing_source_line(kinds):
    names, flags = kinds
    assert "source_line_present" in names
    f = next(x for x in flags if x.kind == "source_line_present")
    assert "Table_12_7" in f.output


def test_row_16_title_range_vs_values(kinds):
    names, flags = kinds
    assert "title_range_vs_values" in names
    f = next(x for x in flags if x.kind == "title_range_vs_values")
    # all three PD parameter tables, written as one finding
    assert f.output.count(".rtf") == 3
    assert "63.1" in f.evidence


def test_row_17_duplicate_titles(kinds):
    names, flags = kinds
    assert "duplicate_titles" in names


def test_row_18_counts_dip_and_return(kinds):
    names, flags = kinds
    f = next(x for x in flags
             if x.kind == "counts_dip_and_return" and "PK_DesStats" in x.output)
    assert "partial AUC window" in f.finding
    assert "24, 23 then 24" in f.evidence


def test_row_19_output_missing_against_the_shells(kinds):
    names, flags = kinds
    f = next(x for x in flags if x.kind == "outputs_present_vs_shells")
    assert "DEPIN" in f.finding
    assert f.severity == "Critical"


def test_row_20_exclusion_applied_to_one_family_only(kinds):
    names, flags = kinds
    f = next(x for x in flags if x.kind == "exclusion_applied_consistently")
    assert "44" in f.evidence and "48" in f.evidence


def test_row_21_unpaired_crossover_comparison(kinds):
    names, flags = kinds
    f = next(x for x in flags if x.kind == "paired_comparison_same_n")
    assert "AUC0-45min" in f.evidence
    assert f.severity == "Critical"


def test_row_21_does_not_fire_on_a_plain_concentration_table(kinds):
    """
    A concentration table with n T1, n T2 and n T3 side by side is not a
    comparison. Those treatments are allowed to differ, and flagging them was
    the first false positive this check produced.
    """
    names, flags = kinds
    bad = [f for f in flags
           if f.kind == "paired_comparison_same_n"
           and "Conc-by-Trt" in f.output]
    assert bad == []


def test_row_22_figure_n_against_table_n(kinds):
    names, flags = kinds
    f = next(x for x in flags if x.kind == "n_consistent_across_outputs")
    assert "MeanGraphs" in f.output


def test_row_23_rule_stated_but_never_applied(kinds):
    names, flags = kinds
    f = next(x for x in flags if x.kind == "rule_stated_not_applied")
    assert "Overall success" in f.evidence


def test_row_24_significant_digits_against_the_sap(kinds):
    names, flags = kinds
    f = next(x for x in flags if x.kind == "decimals_vs_spec")
    assert "10.77" in f.evidence


def test_row_25_percent_with_no_denominator(kinds):
    names, flags = kinds
    assert "percent_without_denominator" in names


def test_row_28_undefined_code(kinds):
    names, flags = kinds
    f = next(x for x in flags if x.kind == "undefined_code_in_column")
    assert "NV" in f.finding and "RV" in f.evidence


def test_row_8_wrong_study_number(kinds):
    names, flags = kinds
    f = next(x for x in flags if x.kind == "study_and_protocol_consistent")
    assert "SbjGraphs" in f.output
    assert "2022-5310" in f.evidence


def test_row_35_bare_program_name(kinds):
    names, flags = kinds
    f = next(x for x in flags if x.kind == "program_has_path_and_version")
    assert "l_vs.sas" in f.evidence


def test_row_36_footnote_from_another_domain(kinds):
    names, flags = kinds
    f = next(x for x in flags if x.kind == "footnote_matches_domain")
    assert "Haematology" in f.output


def test_row_37_n_falls_between_visits(kinds):
    names, flags = kinds
    f = next(x for x in flags
             if x.kind == "n_drops_without_footnote" and "12_6" in x.output)
    assert "Basophils" in f.evidence or "Eosinophils" in f.evidence


# ------------------------------------------------------------ no false hits
def test_a_clean_table_raises_nothing_about_dips(pkg):
    """
    Table 12-5 alternates Baseline and End of Study for two parameters. The
    count changes between parameters, and that is not a dip. Treating it as one
    was the first false positive this check produced.
    """
    flags = run_output_checks(pkg)
    dips = [f for f in flags
            if f.kind == "counts_dip_and_return" and "12_5" in f.output]
    assert dips == []


def test_every_finding_carries_an_output_and_evidence(kinds):
    names, flags = kinds
    for f in flags:
        assert f.output.strip(), f.kind
        assert f.evidence.strip(), f.kind
        assert f.area, f.kind


def test_a_demographics_table_is_not_read_as_a_figure(pkg):
    """
    'Demographic' contains the letters of 'graph'. Matching on the letters
    rather than the whole word filed the demographics table as a figure, and
    every table check skipped it.
    """
    o = next(x for x in pkg.outputs if "Demographics" in x.filename)
    assert o.kind == "table"
    assert o in pkg.tables()


def test_row_31_a_measurement_carried_as_a_whole_number(kinds):
    names, flags = kinds
    f = next(x for x in flags if x.kind == "integer_only_column")
    assert "BMI" in f.finding
