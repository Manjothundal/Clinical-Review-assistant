# -*- coding: utf-8 -*-
"""Explore: every finding gets a page; the charts redo the check in code."""
import os
import sys
import subprocess
import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
FOLDER = os.path.join("studies", "DEMO-BE-101")


@pytest.fixture(scope="module")
def setup():
    os.chdir(HERE)
    if not os.path.isdir(FOLDER):
        subprocess.run([sys.executable, "make_sample_study.py"], check=True,
                       capture_output=True)
    from cra.scan_study import scan
    from cra.study import load_study
    return scan(FOLDER), load_study(FOLDER)


def _ev(setup, kind):
    from cra.explore import build
    r, st = setup
    return build(next(f for f in r.findings if f.found_by == kind), st)


def test_every_finding_builds_without_error(setup):
    from cra.explore import build
    r, st = setup
    charts = 0
    for f in r.findings:
        ev = build(f, st)
        assert not any("could not be drawn" in x for x in ev.facts), f.found_by
        charts += ev.chart is not None
    assert charts >= 35


def test_chart_redoes_the_check(setup):
    ev = _ev(setup, "adam_chg")
    assert "2 of" in ev.facts[0]
    assert sorted(x.split("-")[-1] for x in ev.flagged) == ["002", "005"]
    assert (ev.table.Flag == "⚠").sum() == 2


def test_safety_matrix_names_both_subjects(setup):
    ev = _ev(setup, "adam_saffl_no_dose")
    assert {x.split("-")[-1] for x in ev.flagged} == {"012", "048"}


def test_chart_specs_render(setup):
    """Every chart must be valid Vega-Lite (the page would be blank if not)."""
    from cra.explore import build
    r, st = setup
    for f in r.findings:
        ev = build(f, st)
        if ev.chart is not None:
            ev.chart.to_dict()


def test_explanation_review_trail(setup, tmp_path):
    import shutil
    from cra.agent.tasks import save_explanation, results
    folder = str(tmp_path / "s")
    os.makedirs(folder)
    save_explanation(folder, "k1", "**How to read**\ntext", "draft")
    save_explanation(folder, "k1", status="submitted")
    x = save_explanation(folder, "k1", status="approved", by="lead")
    assert x["status"] == "approved"
    assert [h["status"] for h in x["history"]] == ["draft", "submitted",
                                                   "approved"]
    from cra.explore import split_sections
    assert split_sections(results(folder)["k1"]["explanation"]["text"]) == [
        ("How to read", "text")]
