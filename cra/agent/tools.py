# -*- coding: utf-8 -*-
"""
The agent's tools.

Read tools look at the study and never change it. Write tools only record what
the agent concluded (a verdict, a fix, a query) in agent.json beside the study.
Nothing here can edit a dataset, an output, or a person's Keep / Reject.

Privacy, enforced here and not in a prompt:
  - every subject identifier is replaced by a code (S001, S002 ...) before a
    result leaves this file. The agent works in codes; the screen shows the
    real identifiers again.
  - birth dates, initials and investigator names are never returned.
  - a row tool returns at most 15 rows.
"""
import re
import json
import os
import datetime

import pandas as pd

from . import where as W

MAX_CHARS = 2500
MAX_ROWS = 15
SUBJECT_COLS = ["USUBJID", "SUBJID", "SUBJECT", "SUBJNO", "SUBJ", "PATIENT",
                "PATNO", "PT"]
NEVER = {"BRTHDTC", "BRTHDAT", "BRTHDT", "DOB", "INITIALS", "INIT", "INVNAM",
         "INVNAME", "PATNAME", "NAME"}


def _clip(text):
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "\n...(cut)"


class Masker:
    """Real subject identifier <-> code, the same code for USUBJID and SUBJID."""

    def __init__(self, datasets):
        nums = set()
        self.full = set()
        for d in datasets.values():
            df = d["data"]
            for c in SUBJECT_COLS:
                if c in df.columns:
                    for v in df[c].dropna().astype(str).str.strip():
                        if v:
                            nums.add(v.split("-")[-1])
                            if c == "USUBJID":
                                self.full.add(v)
        self.code = {n: "S%03d" % (i + 1) for i, n in enumerate(sorted(nums))}
        self.back = {v: k for k, v in self.code.items()}
        self.full_by_num = {}
        for u in self.full:
            self.full_by_num.setdefault(u.split("-")[-1], u)

    def mask_value(self, v):
        if v is None:
            return v
        s = str(v).strip()
        return self.code.get(s.split("-")[-1], s)

    def mask_text(self, text):
        """Replace full USUBJIDs anywhere in free text."""
        for u in sorted(self.full, key=len, reverse=True):
            if u in text:
                text = text.replace(u, self.code[u.split("-")[-1]])
        return text

    def unmask_text(self, text):
        def rep(m):
            num = self.back.get(m.group(0))
            if num is None:
                return m.group(0)
            return self.full_by_num.get(num, num)
        return re.sub(r"\bS\d{3}\b", rep, text or "")

    def mask_frame(self, df):
        df = df.drop(columns=[c for c in df.columns if c.upper() in NEVER])
        for c in df.columns:
            if c.upper() in SUBJECT_COLS:
                df[c] = df[c].map(self.mask_value)
        return df


class AgentStore:
    """agent.json in the study folder: what the agent concluded, per finding."""

    def __init__(self, folder):
        self.path = os.path.join(folder, "agent.json")
        try:
            with open(self.path, encoding="utf-8") as fh:
                self.data = json.load(fh)
        except (OSError, ValueError):
            self.data = {}

    def entry(self, key):
        return self.data.setdefault(key, {"verdict": "", "reason": "",
                                          "fixes": [], "queries": [],
                                          "notes": ""})

    def save(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=1, ensure_ascii=False)


# ---------------------------------------------------------------------------
# the tool definitions the model sees. Short descriptions: they are sent on
# every call (and cached).
# ---------------------------------------------------------------------------
_F = {"type": "string", "description": "optional filter, e.g. SAFFL = 'Y' and "
      "AGE > 40. Words: = != > < >= <= in, not in, is missing, and, or, not"}
TOOLS = [
    ("overview", "Inputs, datasets with record and subject counts, outputs, "
     "and findings per layer.", {}),
    ("describe", "Variables of one dataset: label, type, missing, distinct.",
     {"dataset": {"type": "string"}}),
    ("count", "Records and subjects in a dataset, optionally filtered and "
     "grouped by up to 2 variables.",
     {"dataset": {"type": "string"}, "where": _F,
      "by": {"type": "string", "description": "VAR or VAR1,VAR2"}}),
    ("values", "Most common values of one variable, with counts.",
     {"dataset": {"type": "string"}, "variable": {"type": "string"},
      "where": _F}),
    ("stats", "n, mean, min, max of a numeric variable, optionally by group.",
     {"dataset": {"type": "string"}, "variable": {"type": "string"},
      "where": _F, "by": {"type": "string"}}),
    ("subjects_diff", "Subjects in dataset a but not b, and in b but not a.",
     {"a": {"type": "string"}, "b": {"type": "string"},
      "where_a": _F, "where_b": _F}),
    ("rows", "Up to 15 matching rows. Subject IDs are codes like S012.",
     {"dataset": {"type": "string"}, "where": _F,
      "columns": {"type": "string", "description": "comma separated"}}),
    ("list_outputs", "Every TLF output with its number and title.", {}),
    ("output", "One TLF output: titles, columns, footnotes and up to 15 rows.",
     {"filename": {"type": "string"}}),
    ("search_docs", "Search the SAP, protocol, mock shells, specs and the "
     "reference library (past review findings, CDISC terminology). Returns the "
     "best passages, each with a citation to quote as [file §section].",
     {"text": {"type": "string", "description": "what to look for"},
      "where": {"type": "string",
                "enum": ["all", "sap", "shells", "specs", "library"]}}),
    ("findings", "List findings. Optional layer or status filter.",
     {"layer": {"type": "string"}, "status": {"type": "string",
                                              "description": "certain or candidate"}}),
    ("finding", "One finding in full.", {"key": {"type": "string"}}),
    ("set_verdict", "Record your verdict on a finding. You cannot reject; only "
     "a person can.",
     {"key": {"type": "string"},
      "verdict": {"type": "string",
                  "enum": ["confirmed", "likely_false_alarm", "needs_person"]},
      "reason": {"type": "string", "description": "2-4 sentences with the "
                 "evidence you found"}}),
    ("propose_fix", "Record a suggested fix for a finding.",
     {"key": {"type": "string"},
      "kind": {"type": "string",
               "enum": ["sas", "r", "spec", "footnote", "title", "process"]},
      "text": {"type": "string", "description": "the code or wording"}}),
    ("draft_query", "Record a draft query or message about a finding.",
     {"key": {"type": "string"},
      "to": {"type": "string",
             "enum": ["site", "data_management", "sponsor", "programmer"]},
      "subject": {"type": "string"}, "text": {"type": "string"}}),
]
REQUIRED = {"describe": ["dataset"], "count": ["dataset"],
            "values": ["dataset", "variable"], "stats": ["dataset", "variable"],
            "subjects_diff": ["a", "b"], "rows": ["dataset"],
            "output": ["filename"], "search_docs": ["text"], "finding": ["key"],
            "set_verdict": ["key", "verdict", "reason"],
            "propose_fix": ["key", "kind", "text"],
            "draft_query": ["key", "to", "subject", "text"]}
WRITE_TOOLS = {"set_verdict", "propose_fix", "draft_query"}


def tool_specs():
    """Neutral form: name, description, JSON schema."""
    return [{"name": n, "description": d,
             "schema": {"type": "object", "properties": p,
                        "required": REQUIRED.get(n, [])}}
            for n, d, p in TOOLS]


class Toolbox:
    def __init__(self, study, findings, folder, allow_rows=True, by="agent"):
        self.st = study
        self.findings = {f.key: f for f in findings}
        self.folder = folder
        self.allow_rows = allow_rows
        self.by = by
        self.data = {}
        for layer, group in (("raw", study.raw), ("sdtm", study.sdtm),
                             ("adam", study.adam)):
            for name, d in group.items():
                self.data[name.upper()] = d
        self.mask = Masker(self.data)
        self.store = AgentStore(folder)
        self.seen = []            # every tool result, for the number check

    # -------------------------------------------------------------- helpers
    def _df(self, name):
        key = str(name).upper().replace(".XPT", "").replace(".CSV", "").strip()
        if key not in self.data:
            raise KeyError("no dataset %s. Have: %s"
                           % (name, ", ".join(sorted(self.data))))
        return self.data[key]["data"]

    def _where(self, name, where):
        df = self._df(name)
        if where:
            where = self.mask.unmask_text(where)
        return W.apply(df, where)

    @staticmethod
    def _subj(df):
        if "USUBJID" in df.columns:
            return df["USUBJID"]
        for c in SUBJECT_COLS:
            if c in df.columns:
                return df[c]
        return None

    def _n_subj(self, df):
        s = self._subj(df)
        return int(s.dropna().astype(str).str.split("-").str[-1].nunique()) \
            if s is not None else 0

    # -------------------------------------------------------------- dispatch
    def call(self, name, args):
        """Run one tool. Always returns text, never raises."""
        args = args or {}
        fn = getattr(self, "t_" + name, None)
        if fn is None:
            out = "error: no tool %s" % name
        else:
            try:
                out = fn(**{k: v for k, v in args.items() if v not in (None, "")})
            except TypeError as exc:
                out = "error: wrong arguments for %s (%s)" % (name, exc)
            except (KeyError, W.FilterError, ValueError) as exc:
                out = "error: %s" % (exc.args[0] if exc.args else exc)
            except Exception as exc:              # a tool must never crash a run
                out = "error: %s" % exc
        out = _clip(self.mask.mask_text(str(out)))
        self.seen.append(out)
        return out

    # -------------------------------------------------------------- read
    def t_overview(self):
        st = self.st
        lines = ["study %s" % st.name]
        for label, group in (("raw", st.raw), ("SDTM", st.sdtm),
                             ("ADaM", st.adam)):
            if group:
                lines.append("%s: %s" % (label, ", ".join(
                    "%s (%d rec, %d subj)" % (n, len(d["data"]),
                                              self._n_subj(d["data"]))
                    for n, d in sorted(group.items()))))
            else:
                lines.append("%s: none" % label)
        pkg = st.package
        lines.append("TLF outputs: %d" % (len(pkg.outputs) if pkg else 0))
        lines.append("SAP: %s" % (", ".join(st.sap_files) or "none")
                     + ("; rules: " + "; ".join("%s=%s" % kv
                                               for kv in st.rules.items())
                        if st.rules else ""))
        lines.append("mock shells: %d listed" % len(st.shells))
        by = {}
        for f in self.findings.values():
            by.setdefault(f.layer, [0, 0])
            by[f.layer][0 if f.confidence == "certain" else 1] += 1
        lines.append("findings: " + "; ".join(
            "%s %d confirmed %d to check" % (k, v[0], v[1])
            for k, v in by.items()))
        return "\n".join(lines)

    def t_describe(self, dataset):
        df = self._df(dataset)
        labels = self.data[str(dataset).upper()].get("labels", {})
        lines = ["%s: %d records, %d subjects" % (dataset.upper(), len(df),
                                                  self._n_subj(df))]
        for c in df.columns:
            if c.upper() in NEVER:
                lines.append("%s: (withheld)" % c)
                continue
            s = df[c]
            miss = int(s.isna().sum() + (s.astype(str).str.strip() == "").sum())
            lines.append("%s | %s | %s | missing %d | distinct %d" % (
                c, labels.get(c, c),
                "num" if pd.api.types.is_numeric_dtype(s) else "char",
                miss, s.nunique()))
        return "\n".join(lines)

    def t_count(self, dataset, where=None, by=None):
        df = self._where(dataset, where)
        head = "%d records, %d subjects" % (len(df), self._n_subj(df))
        if not by:
            return head
        cols = [c.strip().upper() for c in by.split(",")][:2]
        for c in cols:
            if c not in df.columns:
                raise KeyError("no variable %s in %s" % (c, dataset))
        subj = self._subj(df)
        g = df.assign(_s=subj.astype(str) if subj is not None else "") \
            .groupby(cols, dropna=False)
        tab = pd.DataFrame({"records": g.size(), "subjects": g["_s"].nunique()})
        tab = tab.reset_index()
        for c in cols:
            if c.upper() in SUBJECT_COLS:
                tab[c] = tab[c].map(self.mask.mask_value)
        return head + "\n" + tab.head(30).to_string(index=False)

    def t_values(self, dataset, variable, where=None):
        df = self._where(dataset, where)
        v = variable.upper()
        if v in NEVER:
            return "withheld"
        if v not in df.columns:
            raise KeyError("no variable %s in %s" % (v, dataset))
        s = df[v]
        if v in SUBJECT_COLS:
            s = s.map(self.mask.mask_value)
        vc = s.fillna("(missing)").astype(str).value_counts()
        return "%d distinct\n" % len(vc) + "\n".join(
            "%s: %d" % (k, n) for k, n in vc.head(15).items())

    def t_stats(self, dataset, variable, where=None, by=None):
        df = self._where(dataset, where)
        v = variable.upper()
        x = pd.to_numeric(df[v], errors="coerce")
        if by:
            b = by.strip().upper()
            g = x.groupby(df[b])
            tab = pd.DataFrame({"n": g.count(), "mean": g.mean().round(3),
                                "min": g.min(), "max": g.max()}).head(30)
            return tab.to_string()
        return "n %d, missing %d, mean %s, min %s, max %s" % (
            x.count(), x.isna().sum(), round(x.mean(), 3) if x.count() else "-",
            x.min(), x.max())

    def t_subjects_diff(self, a, b, where_a=None, where_b=None):
        sa = self._subj(self._where(a, where_a))
        sb = self._subj(self._where(b, where_b))
        if sa is None or sb is None:
            return "error: one of the datasets has no subject variable"
        na = set(sa.dropna().astype(str).str.split("-").str[-1])
        nb = set(sb.dropna().astype(str).str.split("-").str[-1])
        code = lambda s: ", ".join(sorted(self.mask.code.get(x, x) for x in s)[:15])
        return ("%s: %d subjects, %s: %d subjects, in both: %d\n"
                "only in %s (%d): %s\nonly in %s (%d): %s"
                % (a.upper(), len(na), b.upper(), len(nb), len(na & nb),
                   a.upper(), len(na - nb), code(na - nb) or "-",
                   b.upper(), len(nb - na), code(nb - na) or "-"))

    def t_rows(self, dataset, where=None, columns=None):
        if not self.allow_rows:
            return "row access is off for this run. Use count, values or stats."
        df = self._where(dataset, where)
        if columns:
            cols = [c.strip().upper() for c in columns.split(",")
                    if c.strip().upper() in df.columns]
            df = df[cols] if cols else df
        out = self.mask.mask_frame(df.head(MAX_ROWS).copy())
        return "%d matching rows, first %d:\n%s" % (
            len(df), min(len(df), MAX_ROWS),
            out.to_string(index=False, max_colwidth=30))

    def t_list_outputs(self):
        pkg = self.st.package
        if not pkg or not pkg.outputs:
            return "no outputs"
        return "\n".join("%s | %s" % (o.filename, " / ".join(o.titles[:2]))
                         for o in pkg.outputs)

    def t_output(self, filename):
        pkg = self.st.package
        o = next((x for x in (pkg.outputs if pkg else [])
                  if filename.lower() in x.filename.lower()), None)
        if o is None:
            return "error: no output like %s" % filename
        lines = ["file: %s (%s)" % (o.filename, o.kind)]
        lines += ["title: %s" % t for t in o.titles]
        if o.headers:
            lines.append("columns: " + " | ".join(o.headers))
            id_cols = [i for i, h in enumerate(o.headers)
                       if re.search(r"subject|patient|usubjid", h, re.I)]
            for r in o.rows[:MAX_ROWS if self.allow_rows else 0]:
                lines.append("  " + " | ".join(
                    self.mask.mask_value(c) if i in id_cols else str(c)
                    for i, c in enumerate(r)))
            lines.append("body rows: %d" % len(o.rows))
        lines += ["footnote: %s" % f for f in o.footnotes]
        return "\n".join(lines)

    def t_search_docs(self, text, where="all"):
        from ..rag import index_for
        idx = index_for(self.folder)
        kinds = None if where in (None, "", "all") else {where}
        hits = idx.search(text, k=5, kinds=kinds)
        out = []
        if self.st.rules and where in (None, "", "all", "sap"):
            words = [w.lower() for w in re.findall(r"\w+", text) if len(w) > 2]
            for k, v in self.st.rules.items():
                if any(w in (k + " " + v).lower() for w in words):
                    out.append("[spec.txt] %s = %s" % (k, v))
        for h in hits:
            out.append("[%s] %s" % (h.cite, h.chunk.text[:600]))
        return "\n\n".join(out) or "nothing in the documents matches '%s'" % text

    def t_sap(self, text):
        """Older name, kept so saved runs still replay."""
        return self.t_search_docs(text, "sap")

    def _old_sap(self, text):
        words = [w.lower() for w in re.findall(r"\w+", text) if len(w) > 2]
        out = []
        for k, v in self.st.rules.items():
            if any(w in (k + " " + v).lower() for w in words):
                out.append("rule: %s = %s" % (k, v))
        paras = [p.strip() for p in re.split(r"\n\s*\n|\n", self.st.sap_text or "")
                 if p.strip()]
        scored = sorted(((sum(p.lower().count(w) for w in words), p)
                         for p in paras), key=lambda t: -t[0])
        out += ["sap: %s" % p[:400] for s, p in scored[:5] if s > 0]
        return "\n".join(out) or "nothing in the SAP matches '%s'" % text

    def t_findings(self, layer=None, status=None):
        rows = []
        for f in self.findings.values():
            if layer and layer.lower() not in f.layer.lower():
                continue
            if status and status.lower() != f.confidence:
                continue
            rows.append("%s | %s | %s | %s | %s" % (f.key, f.layer, f.severity,
                                                    f.confidence, f.finding))
        return "\n".join(rows[:40]) or "none"

    def t_finding(self, key):
        f = self.findings.get(key)
        if f is None:
            return "error: no finding %s" % key
        return ("key: %s\nlayer: %s\narea: %s\nseverity: %s\nstatus: %s\n"
                "check: %s\nfinding: %s\nfile: %s\nwhat is wrong: %s\n"
                "evidence: %s" % (f.key, f.layer, f.area, f.severity,
                                  f.confidence, f.found_by, f.finding,
                                  f.output_file, f.what_is_wrong, f.evidence))

    # -------------------------------------------------------------- write
    def _stamp(self, e):
        e["by"] = self.by
        e["at"] = datetime.datetime.now().strftime("%d %b %Y %H:%M")

    def t_set_verdict(self, key, verdict, reason):
        if key not in self.findings:
            return "error: no finding %s" % key
        if verdict not in ("confirmed", "likely_false_alarm", "needs_person"):
            return "error: verdict must be confirmed, likely_false_alarm or " \
                   "needs_person"
        f = self.findings[key]
        if f.confidence == "certain" and verdict == "likely_false_alarm":
            verdict = "needs_person"       # code proved it; the agent cannot
        e = self.store.entry(key)
        e["verdict"], e["reason"] = verdict, self.mask.unmask_text(reason)
        self._stamp(e)
        self.store.save()
        return "saved verdict %s for %s" % (verdict, key)

    def t_propose_fix(self, key, kind, text):
        if key not in self.findings:
            return "error: no finding %s" % key
        e = self.store.entry(key)
        e["fixes"] = [x for x in e["fixes"] if x["kind"] != kind]
        e["fixes"].append({"kind": kind, "text": self.mask.unmask_text(text)})
        self._stamp(e)
        self.store.save()
        return "saved %s fix for %s" % (kind, key)

    def t_draft_query(self, key, to, subject, text):
        if key not in self.findings:
            return "error: no finding %s" % key
        e = self.store.entry(key)
        e["queries"] = [q for q in e["queries"] if q["to"] != to]
        e["queries"].append({"to": to, "subject": self.mask.unmask_text(subject),
                             "text": self.mask.unmask_text(text)})
        self._stamp(e)
        self.store.save()
        return "saved query to %s for %s" % (to, key)
