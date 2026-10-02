# -*- coding: utf-8 -*-
"""
The explain agent.

You click a finding and ask a question about it. This answers, using only that
finding's evidence and the output it came from.

The same rule as everywhere else, enforced in code: any number in the answer
that is not in what the model was given causes the answer to be thrown away.
A wrong explanation is worse than no explanation, because it sounds right.

It is also told, in the prompt and again by the code below, that it may not
tell anyone the data is fine. It can say a finding looks minor. It cannot
clear it. Only a person does that, with the Keep and Reject buttons.
"""
import re
from dataclasses import dataclass, field
from typing import List

from .model import ask_model
from .context import build, invented_numbers

SYSTEM = """You are helping a clinical statistical programmer understand one
finding from a review of study outputs.

You are given the finding, the output it came from, and sometimes a few rules
from the statistical analysis plan. Answer the question using ONLY what you
are given.

Rules you must follow:
- NEVER state a number that is not in the text you were given. Not one.
- If the answer is not in what you were given, say so plainly and say what
  would answer it: which output, which dataset, or which document.
- Two to five sentences. Plain words. Write for someone who knows clinical
  trials but may not be a programmer.
- Do not say the finding is fine, resolved, or not a problem. You are not the
  one who decides that. You may say what would make it a smaller problem.
- If the fix is a footnote, a title or a display format, you may say what the
  corrected wording would be. For anything that needs a decision about which
  number is right, say what the decision is, not what the answer should be.
- No greeting, no sign-off, no repeating the question back."""

# Questions offered as buttons, because most people do not know what to ask.
# (button label, the question actually sent)
SUGGESTED = [
    ("Why it matters", "Why does this matter to whoever reads the output?"),
    ("How to confirm", "What would I have to check to confirm this?"),
    ("Likely cause", "What is the likely cause of this?"),
    ("How to fix", "How would I fix this?"),
]

REFUSAL = ("I could not answer that from the finding and the output alone. "
           "Ask something about what is on the output, or open the output "
           "itself on the Outputs page.")


@dataclass
class Answer:
    text: str
    ok: bool = True
    context_notes: List[str] = field(default_factory=list)
    context_chars: int = 0
    rejected_numbers: List[str] = field(default_factory=list)
    raw: str = ""


# Phrases that would be the agent clearing a finding. It does not get to.
_CLEARING = re.compile(
    r"\b(not (a|an) (real )?(problem|issue|finding)|no (issue|problem) here|"
    r"this is fine|nothing wrong|can be ignored|safe to ignore|"
    r"no action (is )?(needed|required))\b", re.I)


def ask(finding, question, output=None, package=None, other_findings=None,
        level="summary", mode=None):
    """Answer one question about one finding."""
    question = (question or "").strip()
    if not question:
        return Answer("Ask a question first.", ok=False)

    context, notes = build(finding, output=output, package=package,
                           level=level, other_findings=other_findings)

    user = ("%s\n\nQUESTION\n  %s\n\nAnswer using only the text above."
            % (context, question))

    try:
        raw = (ask_model(SYSTEM, user, mode=mode) or "").strip()
    except Exception as exc:
        return Answer("The model could not be reached (%s). Everything else in "
                      "the app still works without it." % exc,
                      ok=False, context_notes=notes, context_chars=len(context))

    if not raw:
        return Answer(REFUSAL, ok=False, context_notes=notes,
                      context_chars=len(context))

    # 1. no number that was not given to it
    bad = invented_numbers(raw, context)
    if bad:
        return Answer(
            "The answer was thrown away because it used %s, which is not "
            "anywhere in the finding or the output. Nothing here invents a "
            "number, so you get no answer rather than a wrong one."
            % (" and ".join(bad[:4])),
            ok=False, context_notes=notes, context_chars=len(context),
            rejected_numbers=bad, raw=raw)

    # 2. it does not get to close a finding
    if _CLEARING.search(raw):
        return Answer(
            "The answer was thrown away because it tried to clear the finding. "
            "Only a person does that, with Keep and Reject.",
            ok=False, context_notes=notes, context_chars=len(context), raw=raw)

    return Answer(raw, ok=True, context_notes=notes,
                  context_chars=len(context), raw=raw)


# ---------------------------------------------------------------------------
def mock_answer(context, question):
    """
    What mock mode replies.

    It does not write an explanation. It repeats the evidence and says the
    model is off. Anything cleverer would make the app look like it is
    reasoning when it is not.
    """
    ev = ""
    for line in context.splitlines():
        if line.strip().startswith("evidence:"):
            ev = line.split("evidence:", 1)[1].strip()
            break
    return ("Model is off, so there is no explanation. The evidence behind "
            "this finding is: %s Turn on \"Use the model for wording\" once a "
            "key is set, and ask again." % ev)
