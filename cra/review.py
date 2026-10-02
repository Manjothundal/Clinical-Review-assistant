# -*- coding: utf-8 -*-
"""
Engine 2: judgement.

The model has exactly two jobs here, and neither of them is arithmetic.

    1. Decide keep or drop, for candidate flags only. A candidate is something
       code noticed but cannot be sure about, for example a summary table with
       no treatment columns, which is sometimes wrong and sometimes on purpose.

    2. Write the "What is wrong" sentences in house wording.

Every number on the sheet comes from Engine 1. If the model writes a number that
is not in the evidence the code produced, the rewrite is thrown away and the
code's own wording is used instead. That rule is in code, not in the prompt,
because a prompt is a request and this has to be a guarantee.

The model is never sent a patient record.
"""
import json
import re
from .model import ask_model
from .findings import Finding, from_flag, order

# Kept short on purpose: it is sent on every call, so every word costs tokens.
SYSTEM = """You review clinical study outputs for a statistical programmer.
Each item is something code noticed but could not prove. Decide if it is worth
a programmer's time, and word it the way a reviewer would.
Rules:
- NEVER write a number that is not in the item's "ev".
- 2 to 4 plain sentences: what is wrong and why it matters to a reader.
- Drop an item unless the output or data would genuinely mislead.
- sev: Critical if a result or conclusion could be wrong, Major if an output or
  submission document is wrong, Minor if untidy only.
Reply with a JSON list only, one object per item:
{"i":0,"keep":true,"sev":"Major","why":"..."}"""


def _payload(flags):
    """
    The smallest thing that lets the model judge an item: the check name, the
    headline and the code's evidence. Short keys, because every key repeats
    once per item.
    """
    return [{"i": i, "chk": f.found_by, "conf": f.confidence,
             "find": f.finding, "ev": f.evidence}
            for i, f in enumerate(flags)]


def _parse_json(text):
    """Models sometimes wrap JSON in ```json fences. Pull the list out either way."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("The model did not return a JSON list.")
    return json.loads(text[start:end + 1])


def numbers_not_in_evidence(wording, evidence):
    """
    Safety net. Every number in the model's wording must also appear in the
    evidence the code produced. Returns the ones it could not find.
    """
    nums = set(re.findall(r"\d+(?:\.\d+)?", wording or ""))
    have = set(re.findall(r"\d+(?:\.\d+)?", evidence or ""))
    return sorted(nums - have)


def judge(flags, mode=None, keep_code_wording=False, reword_certain=False):
    """
    flags: a list of Flag objects from Engine 1.
    Returns a list of Findings, ready for the sheet.

    Only candidates go to the model. Certain findings were proved by code and
    keep the code's wording, which is what saves most of the tokens. Pass
    reword_certain=True to send those too, for house wording.
    """
    findings = [from_flag(f) for f in flags]
    findings = [f for f in findings if f.is_valid()]
    if not findings or keep_code_wording:
        return order(findings)

    send = [f for f in findings
            if f.confidence == "candidate" or reword_certain]
    if not send:
        return order(findings)

    user = "ITEMS_JSON:\n" + json.dumps(_payload(send), separators=(",", ":"),
                                         ensure_ascii=False)
    try:
        verdicts = {}
        for v in _parse_json(ask_model(SYSTEM, user, mode=mode)):
            verdicts[v.get("i", v.get("index"))] = v
    except Exception as exc:
        # A broken model must never lose a finding. Candidates stay, unjudged,
        # and the screen shows them as "To check".
        print("model judgement unavailable (%s). Using the code wording." % exc)
        for f in send:
            f.detail["unjudged"] = True
        return order(findings)

    dropped = set()
    for i, f in enumerate(send):
        v = verdicts.get(i)
        if v is None:
            if f.confidence == "candidate":
                f.detail["unjudged"] = True
            continue
        if f.confidence == "candidate" and not v.get("keep", False):
            dropped.add(id(f))
            continue
        if f.confidence == "certain" and not v.get("keep", True):
            # The model does not get to delete something code proved. It can
            # only soften it, so it drops to Minor and stays on the sheet.
            f.severity = "Minor"
        new_words = (v.get("why") or v.get("what_is_wrong") or "").strip()
        if new_words:
            bad = numbers_not_in_evidence(new_words, f.evidence)
            if bad:
                f.detail["rejected_wording"] = new_words
                f.detail["invented_numbers"] = bad
            else:
                f.what_is_wrong = new_words
        sev = v.get("sev") or v.get("severity")
        if sev in ("Critical", "Major", "Minor") and f.confidence == "candidate":
            f.severity = sev
        if f.confidence == "candidate":
            f.detail["judged"] = True

    return order([f for f in findings if id(f) not in dropped])
