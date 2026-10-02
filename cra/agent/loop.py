# -*- coding: utf-8 -*-
"""
The agent loop.

    the model reads the task, picks a tool, gets the result, picks the next
    tool ... until it writes its answer or runs out of steps.

Works with Anthropic or OpenAI tool calling, through plain HTTP. Every step is
kept so the screen can show exactly what the agent looked at.

Two rules, in code:
  - the answer may not contain a number that is not in the task or in some
    tool result. If it does, the answer is withheld and you are told which
    number.
  - it stops after CRA_AGENT_STEPS tool rounds (default 10), so a confused
    agent cannot run up a bill.
"""
import os
import re
import json
from dataclasses import dataclass, field
from typing import List

from ..model import _post, _setting, current_mode, DEFAULT_MODEL
from .tools import tool_specs

MAX_STEPS = int(os.environ.get("CRA_AGENT_STEPS", "10"))
MAX_TOKENS = int(os.environ.get("CRA_AGENT_MAX_TOKENS", "1500"))


def live():
    """True when a real model can be called."""
    return current_mode() in ("openai", "anthropic") and bool(_setting("CRA_API_KEY"))


def agent_model(mode):
    return (_setting("CRA_AGENT_MODEL") or _setting("CRA_MODEL_NAME")
            or DEFAULT_MODEL[mode])


@dataclass
class Step:
    tool: str
    args: dict
    result: str


@dataclass
class AgentRun:
    answer: str = ""
    ok: bool = True
    steps: List[Step] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    engine: str = ""
    note: str = ""


# ---------------------------------------------------------------------------
# one model call, in a neutral shape:  {"text": str, "calls": [...], "usage"}
# messages: {"role": "user", "content": str}
#           {"role": "assistant", "text": str, "calls": [{id, name, args}]}
#           {"role": "tool", "results": [{id, name, content}]}
# ---------------------------------------------------------------------------
def _anthropic(system, messages, tools):
    base = (_setting("CRA_API_BASE") or "https://api.anthropic.com").rstrip("/")
    msgs = []
    for m in messages:
        if m["role"] == "user":
            msgs.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            blocks = [{"type": "text", "text": m["text"]}] if m["text"] else []
            blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"],
                        "input": c["args"]} for c in m["calls"]]
            msgs.append({"role": "assistant", "content": blocks})
        else:
            msgs.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": r["id"],
                 "content": r["content"]} for r in m["results"]]})
    tl = [{"name": t["name"], "description": t["description"],
           "input_schema": t["schema"]} for t in tools]
    if tl:
        tl[-1]["cache_control"] = {"type": "ephemeral"}   # tools + system cached
    r = _post(base + "/v1/messages",
              {"x-api-key": _setting("CRA_API_KEY"),
               "anthropic-version": "2023-06-01",
               "Content-Type": "application/json"},
              {"model": agent_model("anthropic"), "max_tokens": MAX_TOKENS,
               "temperature": 0,
               "system": [{"type": "text", "text": system,
                           "cache_control": {"type": "ephemeral"}}],
               "tools": tl, "messages": msgs})
    text = "".join(b.get("text", "") for b in r["content"] if b["type"] == "text")
    calls = [{"id": b["id"], "name": b["name"], "args": b.get("input") or {}}
             for b in r["content"] if b["type"] == "tool_use"]
    u = r.get("usage", {})
    return {"text": text, "calls": calls,
            "usage": (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                      + u.get("cache_creation_input_tokens", 0),
                      u.get("output_tokens", 0))}


def _openai(system, messages, tools):
    base = (_setting("CRA_API_BASE") or "https://api.openai.com/v1").rstrip("/")
    msgs = [{"role": "system", "content": system}]
    for m in messages:
        if m["role"] == "user":
            msgs.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            msg = {"role": "assistant", "content": m["text"] or None}
            if m["calls"]:
                msg["tool_calls"] = [{"id": c["id"], "type": "function",
                                      "function": {"name": c["name"],
                                                   "arguments": json.dumps(c["args"])}}
                                     for c in m["calls"]]
            msgs.append(msg)
        else:
            for r in m["results"]:
                msgs.append({"role": "tool", "tool_call_id": r["id"],
                             "content": r["content"]})
    r = _post(base + "/chat/completions",
              {"Authorization": "Bearer " + _setting("CRA_API_KEY"),
               "api-key": _setting("CRA_API_KEY"),
               "Content-Type": "application/json"},
              {"model": agent_model("openai"), "temperature": 0,
               "max_tokens": MAX_TOKENS, "messages": msgs,
               "tools": [{"type": "function",
                          "function": {"name": t["name"],
                                       "description": t["description"],
                                       "parameters": t["schema"]}}
                         for t in tools]})
    msg = r["choices"][0]["message"]
    calls = []
    for c in msg.get("tool_calls") or []:
        try:
            args = json.loads(c["function"]["arguments"] or "{}")
        except ValueError:
            args = {}
        calls.append({"id": c["id"], "name": c["function"]["name"], "args": args})
    u = r.get("usage", {})
    return {"text": msg.get("content") or "", "calls": calls,
            "usage": (u.get("prompt_tokens", 0), u.get("completion_tokens", 0))}


def _numbers(text):
    return set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", text or ""))


def run(system, task, toolbox, tools=None, max_steps=None, caller=None):
    """
    Run the agent on one task. Returns an AgentRun.
    caller is for tests: a function(system, messages, tools) -> neutral reply.
    """
    tools = tools or tool_specs()
    mode = current_mode()
    call = caller or (_anthropic if mode == "anthropic" else _openai)
    res = AgentRun(engine="test" if caller else "%s %s" % (mode,
                                                           agent_model(mode)))
    messages = [{"role": "user", "content": task}]
    steps = max_steps or MAX_STEPS
    reply = None

    for i in range(steps + 1):
        try:
            reply = call(system, messages, tools if i < steps else [])
        except Exception as exc:
            res.ok = False
            res.answer = ("The model could not be reached (%s). The offline "
                          "agent still works: turn the model off and run "
                          "again." % exc)
            return res
        res.tokens_in += reply["usage"][0]
        res.tokens_out += reply["usage"][1]
        if not reply["calls"]:
            break
        messages.append({"role": "assistant", "text": reply["text"],
                         "calls": reply["calls"]})
        results = []
        for c in reply["calls"]:
            out = toolbox.call(c["name"], c["args"])
            res.steps.append(Step(c["name"], c["args"], out))
            results.append({"id": c["id"], "name": c["name"], "content": out})
        messages.append({"role": "tool", "results": results})
        if i == steps - 1:
            messages.append({"role": "user", "content":
                             "Step limit reached. Write your answer now from "
                             "what you have."})

    answer = (reply or {}).get("text", "").strip()
    known = _numbers(task) | _numbers(system)
    for s in toolbox.seen:
        known |= _numbers(s)
    for st in res.steps:
        known |= _numbers(json.dumps(st.args))
    bad = sorted(_numbers(answer) - known, key=lambda x: float(x))
    if bad:
        res.ok = False
        res.note = "withheld: used %s, found in no tool result" % ", ".join(bad[:5])
        res.answer = ("The answer was withheld because it used %s, which no "
                      "tool returned. Every step it took is listed below."
                      % ", ".join(bad[:5]))
        return res
    res.answer = toolbox.mask.unmask_text(answer) or "(no answer)"
    return res
