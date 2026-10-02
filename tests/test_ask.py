# -*- coding: utf-8 -*-
"""
The explain agent.

Two things have to be true, whatever the model says:
    it cannot state a number it was not given
    it cannot clear a finding
Both are tested by handing it a model that tries to do exactly that.
"""
import os
import pytest

from cra import ask as ask_mod
from cra.ask import ask, SUGGESTED
from cra.context import build, invented_numbers, leaked_identifiers
from cra.findings import Finding

OUTPUTS = os.path.join("outputs", "DEMO-BE-101")
DATA = os.path.join("data", "DEMO-BE-101")


def a_finding():
    return Finding(
        area="PK",
        finding="Table 14-6 compares two different subject sets",
        output_file="PK_Primary_Endpoints_EPIN_adj_6050_T2_vs_R.rtf",
        what_is_wrong="Both treatments must rest on the same subjects.",
        evidence="PK_Primary_Endpoints_EPIN_adj_6050_T2_vs_R.rtf: "
                 "AUC0-45min compares 23 against 24.",
        found_by="paired_comparison_same_n", severity="Critical")


@pytest.fixture
def pkg():
    if not os.path.isdir(OUTPUTS):
        pytest.skip("run make_sample_outputs.py first")
    from cra.outputs import read_package
    return read_package(OUTPUTS)


def _with_model(monkeypatch, reply):
    monkeypatch.setattr(ask_mod, "ask_model",
                        lambda system, user, mode=None: reply)


# ------------------------------------------------------------------ guards
def test_an_invented_number_throws_the_answer_away(monkeypatch):
    _with_model(monkeypatch,
                "The table compares 23 against 24, and 19 subjects were "
                "excluded for protocol deviations.")
    a = ask(a_finding(), "why does this matter?", mode="fake")
    assert a.ok is False
    assert "19" in a.rejected_numbers
    assert "19" not in a.text.split("because it used")[0]
    # the real wording is kept for debugging, but not shown as an answer
    assert "19 subjects were excluded" in a.raw


def test_a_number_that_was_given_is_allowed(monkeypatch):
    _with_model(monkeypatch,
                "One treatment rests on 23 subjects and the other on 24, so "
                "the comparison is not like for like.")
    a = ask(a_finding(), "why does this matter?", mode="fake")
    assert a.ok is True
    assert "23" in a.text


def test_the_agent_cannot_clear_a_finding(monkeypatch):
    _with_model(monkeypatch,
                "This is fine and no action is needed, the counts are simply "
                "how the table was built.")
    a = ask(a_finding(), "is this a real problem?", mode="fake")
    assert a.ok is False
    assert "Only a person does that" in a.text


def test_a_model_that_cannot_be_reached_does_not_break_the_app(monkeypatch):
    def boom(system, user, mode=None):
        raise RuntimeError("no key")
    monkeypatch.setattr(ask_mod, "ask_model", boom)
    a = ask(a_finding(), "why?", mode="fake")
    assert a.ok is False
    assert "still works without it" in a.text


def test_an_empty_question_asks_for_one():
    a = ask(a_finding(), "   ", mode="mock")
    assert a.ok is False


# ----------------------------------------------------------------- context
def test_the_default_context_has_no_table_rows(pkg):
    f = a_finding()
    out = next(o for o in pkg.outputs if o.filename == f.output_file)
    text, notes = build(f, output=out, package=pkg)
    assert "344.5" not in text, "a body row reached the default context"
    assert "body rows: 5" in text, "it should say how many rows there are"
    assert not any("table rows" in n for n in notes)


def test_asking_for_the_table_redacts_the_identifier_column(pkg):
    out = next(o for o in pkg.outputs
               if o.filename == "Conc-by-Trt_LISTING_IBA_adj_6050.rtf")
    f = a_finding()
    f.output_file = out.filename
    text, notes = build(f, output=out, package=pkg, level="table")
    assert "10.77" in text, "the values should be there at this level"
    assert "(id)" in text, "the Subject column should be blanked out"
    assert any("blanked out" in n for n in notes)


@pytest.mark.skipif(not os.path.isdir(DATA),
                    reason="run make_sample_data.py first")
def test_no_subject_identifier_ever_reaches_the_context(pkg):
    """
    Whatever level is used, a subject id from the study data must not appear.
    This is the same guarantee as test_privacy.py, on the second route out.
    """
    from cra.data_io import read_study
    datasets = read_study(DATA)
    f = a_finding()
    for out in pkg.outputs:
        for level in ("summary", "table"):
            text, _ = build(f, output=out, package=pkg, level=level)
            leaked = leaked_identifiers(text, datasets)
            assert leaked == [], "%s at level %s leaked %s" % (
                out.filename, level, leaked[:3])


def test_mock_mode_answers_without_a_key(pkg):
    f = a_finding()
    out = next(o for o in pkg.outputs if o.filename == f.output_file)
    a = ask(f, SUGGESTED[0][1], output=out, package=pkg, mode="mock")
    assert a.ok is True
    assert "23 against 24" in a.text          # it repeats the real evidence
    assert "Model is off" in a.text           # and admits it is not explaining


def test_invented_numbers_helper():
    assert invented_numbers("23 and 24", "compares 23 against 24") == []
    assert invented_numbers("19 subjects", "compares 23 against 24") == ["19"]
