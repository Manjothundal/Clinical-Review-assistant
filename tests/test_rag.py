# -*- coding: utf-8 -*-
"""RAG: the right SAP section comes back, with its citation, offline."""
import os
import sys
import shutil
import subprocess
import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
FOLDER = os.path.join("studies", "DEMO-BE-101")


@pytest.fixture(scope="module")
def idx():
    os.chdir(HERE)
    if not os.path.isdir(FOLDER) or not os.path.isdir("library"):
        subprocess.run([sys.executable, "make_sample_study.py"], check=True,
                       capture_output=True)
    from cra.rag import index_for
    return index_for(FOLDER)


@pytest.mark.parametrize("q,section", [
    ("how is baseline defined", "8.1"),
    ("what happens when the predose value is missing", "8.2"),
    ("denominator for safety percentages", "10"),
    ("significant digits for concentrations", "7.2"),
    ("which PK parameters", "7.1"),
])
def test_finds_the_right_sap_section(idx, q, section):
    top = idx.search(q, 1, {"sap"})[0]
    assert top.chunk.section == section, (q, top.cite)
    assert "§" + section in top.cite


def test_synonyms_help(idx):
    """'predose' finds the section that says 'baseline' and 'pre-dose'."""
    hits = idx.search("predose definition", 2, {"sap"})
    assert {"8.1", "8.2"} & {h.chunk.section for h in hits}


def test_past_reviews_are_searchable(idx):
    top = idx.search("treatment columns missing on the AE table", 1,
                     {"library"})[0]
    assert "past_review" in top.cite and "no treatment columns" in top.chunk.text


def test_rules_read_from_the_sap_match_the_hand_written_ones():
    from cra.rag import suggest_rules
    from cra.study import read_spec_rules
    sugg = suggest_rules(FOLDER)
    hand = read_spec_rules(os.path.join(FOLDER, "sap"))
    for k in ("population_n", "treatments", "pk_parameters",
              "concentration_significant_digits", "crossover"):
        assert sugg[k]["value"].replace(" ", "") == hand[k].replace(" ", ""), k
        assert sugg[k]["cite"].startswith("DEMO-BE-101_SAP.docx §")


def test_write_rules_merges(tmp_path):
    from cra.rag import write_rules
    from cra.study import read_spec_rules
    d = str(tmp_path)
    os.makedirs(os.path.join(d, "sap"))
    write_rules(d, {"a": "1"})
    write_rules(d, {"b": "2"})
    assert read_spec_rules(os.path.join(d, "sap")) == {"a": "1", "b": "2"}


def test_agent_tool_returns_citations(idx):
    from cra.scan_study import scan
    from cra.agent.tasks import Agent
    a = Agent(FOLDER, scan(FOLDER).findings, use_model=False)
    out = a.tb.call("search_docs", {"text": "baseline definition"})
    assert "[DEMO-BE-101_SAP.docx §8.1 Baseline]" in out
    ans = a.chat("how is baseline defined in the SAP").answer
    assert "§8.1" in ans


def test_explore_shows_the_sap_passage():
    from cra.scan_study import scan
    from cra.explore import related
    r = scan(FOLDER)
    f = next(x for x in r.findings if x.found_by == "decimals_vs_spec")
    docs, past = related(f, FOLDER)
    assert docs and docs[0].chunk.section == "7.2"
    assert past and "past_review" in past[0].cite
