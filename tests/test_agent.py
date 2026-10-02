# -*- coding: utf-8 -*-
"""
The agent: safe filters, masked subject IDs, the tool loop, the number rule,
and the offline mode. No API key is needed for any of these.
"""
import os
import sys
import json
import subprocess
import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
FOLDER = os.path.join("studies", "DEMO-BE-101")


@pytest.fixture(scope="module")
def agent():
    os.chdir(HERE)
    if not os.path.isdir(FOLDER):
        subprocess.run([sys.executable, "make_sample_study.py"], check=True,
                       capture_output=True)
    from cra.scan_study import scan
    from cra.agent.tasks import Agent
    r = scan(FOLDER)
    a = Agent(FOLDER, r.findings, use_model=False)
    yield a
    p = os.path.join(FOLDER, "agent.json")
    if os.path.exists(p):
        os.remove(p)


def _f(agent, kind):
    return next(f for f in agent.findings if f.found_by == kind)


def test_filter_cannot_run_code():
    import pandas as pd
    from cra.agent.where import apply, FilterError
    df = pd.DataFrame({"A": ["Y", "N"]})
    for bad in ["__import__('os')", "A = Y", "A.str.len() > 0", "@x"]:
        with pytest.raises(FilterError):
            apply(df, bad)
    assert len(apply(df, "A = 'Y' or A is missing")) == 1


def test_no_real_subject_id_leaves_a_tool(agent):
    tb = agent.tb
    outs = [tb.call("rows", {"dataset": "ADSL"}),
            tb.call("subjects_diff", {"a": "ADSL", "b": "EX"}),
            tb.call("finding", {"key": _f(agent, "adam_saffl_no_dose").key}),
            tb.call("values", {"dataset": "DM", "variable": "USUBJID"})]
    for o in outs:
        assert "DEMO-BE-101-0" not in o, o[:200]


def test_codes_can_be_used_in_a_filter(agent):
    tb = agent.tb
    code = tb.mask.code["048"]
    assert "1 matching" in tb.call("rows", {"dataset": "ADSL",
                                            "where": "USUBJID = '%s'" % code})


def test_offline_agent_does_all_three_jobs(agent):
    from cra.agent.tasks import results
    f = _f(agent, "adam_chg")
    run = agent.work(f)
    e = results(FOLDER)[f.key]
    assert e["verdict"] == "confirmed"
    assert any(x["kind"] == "sas" and "chg = aval - base" in x["text"]
               for x in e["fixes"])
    assert e["queries"] and e["queries"][0]["to"] == "programmer"
    assert run.steps


def test_raw_problem_goes_to_the_site(agent):
    from cra.agent.tasks import results
    f = _f(agent, "raw_bad_dates")
    agent.work(f)
    assert results(FOLDER)[f.key]["queries"][0]["to"] == "site"


def test_agent_cannot_clear_a_proved_finding(agent):
    f = _f(agent, "adam_chg")
    agent.tb.call("set_verdict", {"key": f.key, "verdict": "likely_false_alarm",
                                  "reason": "looks fine"})
    from cra.agent.tasks import results
    assert results(FOLDER)[f.key]["verdict"] == "needs_person"


def _script(*replies):
    """A fake model that plays back replies, one per call."""
    it = iter(replies)

    def caller(system, messages, tools):
        return next(it)
    return caller


def test_tool_loop_runs_tools_and_unmasks_the_answer(agent):
    f = _f(agent, "adam_saffl_no_dose")
    code = agent.tb.mask.code["048"]
    caller = _script(
        {"text": "", "usage": (100, 10), "calls": [
            {"id": "1", "name": "subjects_diff",
             "args": {"a": "ADSL", "b": "EX", "where_a": "SAFFL = 'Y'"}}]},
        {"text": "", "usage": (100, 10), "calls": [
            {"id": "2", "name": "set_verdict",
             "args": {"key": f.key, "verdict": "confirmed",
                      "reason": "%s has SAFFL=Y and no EX." % code}}]},
        {"text": "Confirmed. %s is flagged safety but was never dosed." % code,
         "usage": (100, 10), "calls": []})
    run = agent.work(f, caller=caller)
    assert run.ok
    assert [s.tool for s in run.steps] == ["subjects_diff", "set_verdict"]
    assert "DEMO-BE-101-048" in run.answer          # shown to you unmasked
    assert run.tokens_in == 300


def test_invented_number_is_withheld(agent):
    caller = _script({"text": "There are 9999 subjects.", "usage": (1, 1),
                      "calls": []})
    run = agent.chat("how many subjects?", caller=caller)
    assert not run.ok and "9999" in run.answer and "withheld" in run.answer


def test_step_limit_stops_the_loop(agent):
    def caller(system, messages, tools):
        if not tools:
            return {"text": "done", "usage": (1, 1), "calls": []}
        return {"text": "", "usage": (1, 1), "calls": [
            {"id": "x", "name": "overview", "args": {}}]}
    from cra.agent import loop
    run = loop.run("s", "t", agent.tb, caller=caller, max_steps=3)
    assert len(run.steps) == 3 and run.answer == "done"


def test_anthropic_request_shape(agent, monkeypatch):
    from cra.agent import loop
    sent = {}

    def fake_post(url, headers, body):
        sent.update(url=url, body=body)
        return {"content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 5, "output_tokens": 1}}
    monkeypatch.setattr(loop, "_post", fake_post)
    monkeypatch.setenv("CRA_API_KEY", "x")
    loop._anthropic("sys", [{"role": "user", "content": "hi"}],
                    [{"name": "overview", "description": "d",
                      "schema": {"type": "object", "properties": {}}}])
    assert sent["url"].endswith("/v1/messages")
    assert sent["body"]["tools"][-1]["cache_control"]["type"] == "ephemeral"
    assert sent["body"]["system"][0]["cache_control"]["type"] == "ephemeral"


def test_openai_request_shape(agent, monkeypatch):
    from cra.agent import loop
    sent = {}

    def fake_post(url, headers, body):
        sent.update(body=body)
        return {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "c1", "function": {"name": "overview",
                                      "arguments": "{}"}}]}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1}}
    monkeypatch.setattr(loop, "_post", fake_post)
    r = loop._openai("sys", [{"role": "user", "content": "hi"}],
                     [{"name": "overview", "description": "d",
                       "schema": {"type": "object", "properties": {}}}])
    assert r["calls"][0]["name"] == "overview"
    assert sent["body"]["messages"][0]["role"] == "system"


def test_offline_chat_answers_plain_questions(agent):
    assert "48 subjects" in agent.chat("how many subjects in ADSL").answer
    assert "only in" in agent.chat("compare ADSL and EX").answer
