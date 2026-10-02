# -*- coding: utf-8 -*-
"""
The four jobs the agent does, and which engine does them.

    investigate   check a finding with the tools, record a verdict
    fix           write the SAS (or R) fix, footnote, title or spec change
    query         draft the query to the site, data management, sponsor or
                  programmer
    chat          answer any question about the study

With an API key (CRA_MODEL_MODE openai or anthropic, and CRA_API_KEY) the AI
agent does them. Without one, the offline playbooks do the first three and the
chat answers a small set of plain questions.
"""
import re

from ..study import load_study
from .tools import Toolbox, AgentStore
from .loop import run, live, AgentRun, Step
from .playbooks import run_offline

SYSTEM = """You are a review agent for clinical statistical programming, on
study {study}. Your tools read the raw data, SDTM, ADaM, TLF outputs, SAP and
mock shells. They cannot change anything. Subject IDs appear as codes like
S012: use them as given.

Rules:
- Check with the tools before you conclude. Prefer count, values and
  subjects_diff to rows. Use as few calls as you need.
- Never state a number that no tool returned and the task does not contain.
- You cannot reject a finding or change data. Record conclusions with
  set_verdict, propose_fix and draft_query.
- SAS fixes: Base SAS and PROC SQL, short, commented, real dataset and
  variable names, libraries sdtm. adam. raw. Fix the cause, not the symptom.
- Queries: one issue, the subject codes and values involved, one clear
  question. No greetings.
- When the SAP, protocol, specs or a past review matter, use search_docs and
  cite what you used as [file §section]. Never cite a passage you did not get.
- Finish with 2 to 6 plain sentences.

Study at a glance:
{overview}"""

JOB_TEXT = {
    "investigate": "Investigate it with the tools and call set_verdict: "
                   "confirmed, likely_false_alarm (only if the evidence does "
                   "not hold up), or needs_person.",
    "fix": "Call propose_fix with the fix: SAS code, and a footnote, title or "
           "spec change if that is the real fix.",
    "query": "Call draft_query with the query to whoever must act: site or "
             "data_management for collected data, programmer for derivations "
             "and outputs, sponsor for SAP or shell decisions.",
}


class Agent:
    """One agent per study and scan result."""

    def __init__(self, folder, findings, allow_rows=True, use_model=True):
        self.folder = folder
        self.study = load_study(folder)
        self.findings = findings
        self.use_model = use_model and live()
        self.tb = Toolbox(self.study, findings, folder, allow_rows=allow_rows,
                          by="AI agent" if self.use_model else "offline agent")
        self._system = None

    @property
    def engine(self):
        return "AI agent" if self.use_model else "offline agent (no API key)"

    def system(self):
        if self._system is None:
            self._system = SYSTEM.format(study=self.study.name,
                                         overview=self.tb.t_overview())
        return self._system

    # ------------------------------------------------------------------
    def work(self, finding, jobs=("investigate", "fix", "query"), caller=None):
        """Investigate, fix and/or query one finding. One run for all three."""
        if not (self.use_model or caller):
            return run_offline(finding, self.tb, jobs)
        task = ("Finding %s\n%s\n\n%s" % (
            finding.key, self.tb.t_finding(finding.key),
            "\n".join("- " + JOB_TEXT[j] for j in jobs)))
        return run(self.system(), self.tb.mask.mask_text(task), self.tb,
                   caller=caller)

    def work_many(self, findings, jobs=("investigate", "fix", "query"),
                  progress=None):
        runs = []
        for i, f in enumerate(findings):
            runs.append((f, self.work(f, jobs)))
            if progress:
                progress(i + 1, len(findings), f)
        return runs

    def chat(self, question, history=None, caller=None):
        if not (self.use_model or caller):
            return self._offline_chat(question)
        convo = ""
        for q, a in (history or [])[-3:]:            # short memory, few tokens
            convo += "Earlier question: %s\nYour answer: %s\n\n" % (q, a)
        task = convo + "Question: " + question
        return run(self.system(), self.tb.mask.mask_text(task), self.tb,
                   caller=caller)

    # ------------------------------------------------------------------
    def _offline_chat(self, q):
        """A few plain questions, answered with the tools. No AI."""
        res = AgentRun(engine="offline agent")
        low = q.lower()

        def do(name, **args):
            out = self.tb.call(name, args)
            res.steps.append(Step(name, args, out))
            return out

        names = [n for n in self.tb.data if re.search(r"\b%s\b" % n.lower(), low)]
        m = re.search(r"\b([A-Za-z0-9_]+)\.rtf\b|table\s+(\d+[\-.]\d+)", q, re.I)
        docs_q = re.search(r"\b(sap|protocol|plan|defin\w*|baseline|"
                           r"spec|shells?|past|before|rules?|says?|"
                           r"how (is|are|should))\b", low)
        if docs_q and not names:
            res.answer = do("search_docs", text=q)
        elif re.search(r"^(overview|summary)\b|what\b.*\b(uploaded|is in "
                       r"(this|the) study)", low):
            res.answer = do("overview")
        elif re.search(r"critical|finding|issue", low) and not names:
            res.answer = do("findings", status="certain" if "confirm" in low
                            else None)
        elif names and re.search(r"subject|how many|count|records", low):
            res.answer = "\n\n".join(do("count", dataset=n) for n in names[:3])
        elif len(names) >= 2 and re.search(r"missing|not in|differ|compare", low):
            res.answer = do("subjects_diff", a=names[0], b=names[1])
        elif names:
            res.answer = do("describe", dataset=names[0])
        elif m:
            res.answer = do("output", filename=m.group(1) or
                            "Table_" + m.group(2).replace("-", "_"))
        elif re.search(r"sap|protocol|population|plan|defin|baseline|missing|"
                       r"spec|shell|before|past|rule|how (is|are|should)", low):
            res.answer = do("search_docs", text=q)
        else:
            res.answer = ("Without an API key the agent answers plain "
                          "questions only, for example: 'overview', 'how many "
                          "subjects in ADSL', 'compare ADSL and DM', "
                          "'describe ADVS', 'show Table 12-5', 'what does the "
                          "SAP say about populations', 'how is baseline "
                          "defined', 'list critical findings'. Add a key for "
                          "anything else.")
        res.answer = self.tb.mask.unmask_text(res.answer)
        return res


def results(folder):
    """What the agent recorded, per finding key."""
    return AgentStore(folder).data


def save_explanation(folder, key, text=None, status=None, by="reviewer",
                     note="", ai=None):
    """
    The explanation for one finding, and its review state:
    draft -> submitted -> approved, or sent back. Every change is kept.
    """
    import datetime
    store = AgentStore(folder)
    e = store.entry(key)
    x = e.setdefault("explanation", {"text": "", "status": "draft",
                                     "history": []})
    if text is not None:
        x["text"] = text
    if status:
        x["status"] = status
    if ai is not None:
        x["ai"] = ai
    x["history"].append({"at": datetime.datetime.now().strftime(
        "%d %b %Y %H:%M"), "by": by, "status": x["status"], "note": note})
    store.save()
    return x
