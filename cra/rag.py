# -*- coding: utf-8 -*-
"""
RAG: find the right paragraph in the study documents, with its citation.

What is searched:
    the study:   sap/ (SAP, protocol), shells/, specs/
    the library: library/ beside the app, shared by every study: past review
                 sheets, CDISC Controlled Terminology files, guidance you have
                 the right to use

How:
    1. every document is cut into chunks along its numbered sections
       ("8.2 Missing data"), long sections into overlapping windows, every
       spreadsheet row into one chunk
    2. BM25 ranks the chunks for a question. Plain Python, no package, no
       model, works offline, costs no tokens. A few clinical synonyms are
       added to the question (baseline -> pre-dose, AE -> adverse event).
    3. each hit carries a citation: file, section, page

It finds text. It never counts. Numbers still come from the data checks.
"""
import os
import re
import glob
import math
from dataclasses import dataclass, field
from typing import List

LIBRARY = "library"
WORDS_PER_CHUNK = 160
OVERLAP = 40
MAX_ROWS = 5000

_STOP = set("""a an the of to in on for by with and or is are be will was were
this that these those as at from it its into than then if not no any all each
per which who whom what when where how shall should may can must been being
has have had do does did""".split())

SYNONYMS = {
    "baseline": ["predose", "pre-dose"], "predose": ["baseline"],
    "ae": ["adverse", "event"], "teae": ["treatment-emergent", "adverse"],
    "pk": ["pharmacokinetic"], "pd": ["pharmacodynamic"],
    "pharmacokinetic": ["pk"], "pharmacodynamic": ["pd"],
    "subject": ["patient"], "patient": ["subject"],
    "missing": ["imputed", "imputation"], "impute": ["missing"],
    "decimal": ["significant", "digits", "precision"],
    "digits": ["significant", "decimal"], "rounding": ["significant", "decimal"],
    "population": ["set"], "set": ["population"],
    "exclude": ["excluded", "exclusion"], "exclusion": ["excluded"],
    "chg": ["change"], "change": ["chg"], "saffl": ["safety", "population"],
    "pkfl": ["pk", "population"], "denominator": ["percentages", "based"],
}

_HEADING = re.compile(r"^(\d+(?:\.\d+){0,4})\.?\s+([A-Z][^.]{1,80})$")


def _stem(w):
    for suf in ("ations", "ation", "ings", "ing", "ies", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[:-len(suf)] + ("y" if suf == "ies" else "")
    return w


def tokens(text):
    return [_stem(w) for w in re.findall(r"[a-z0-9][a-z0-9\-]*",
                                          (text or "").lower())
            if w not in _STOP and len(w) > 1]


@dataclass
class Chunk:
    id: int
    doc: str            # file name
    kind: str           # sap, shells, specs, library
    section: str        # "8.2"
    title: str          # "Missing data"
    page: int           # 0 when unknown
    text: str
    toks: List[str] = field(default_factory=list)

    @property
    def cite(self):
        s = self.doc
        if self.section:
            s += " §%s" % self.section
        if self.title:
            s += " %s" % self.title
        if self.page:
            s += ", p.%d" % self.page
        return s


# ---------------------------------------------------------------------------
# reading documents into chunks
# ---------------------------------------------------------------------------
def _pages(path):
    """[(page number, text)]. Page 0 means the format has no pages."""
    from .study import read_text
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            return [(i + 1, p.extract_text() or "")
                    for i, p in enumerate(PdfReader(path).pages)]
        except Exception:
            return []
    return [(0, read_text(path))]


def _windows(words):
    if len(words) <= WORDS_PER_CHUNK:
        return [words]
    out, step = [], WORDS_PER_CHUNK - OVERLAP
    for i in range(0, len(words), step):
        out.append(words[i:i + WORDS_PER_CHUNK])
        if i + WORDS_PER_CHUNK >= len(words):
            break
    return out


def chunk_text_doc(path, kind, start_id=0):
    doc = os.path.basename(path)
    chunks, sec, title, buf, page = [], "", "", [], 0

    def flush():
        words = " ".join(buf).split()
        for w in _windows(words):
            if not w:
                continue
            text = " ".join(w)
            head = ("%s %s" % (sec, title)).strip()
            chunks.append(Chunk(start_id + len(chunks), doc, kind, sec, title,
                                page, text, tokens(head + " " + text)))

    for pg, text in _pages(path):
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = _HEADING.match(line)
            if m and len(line.split()) <= 12:
                flush()
                buf, sec, title, page = [], m.group(1), m.group(2).strip(), pg
                continue
            if not buf:
                page = pg
            buf.append(line)
    flush()
    return chunks


def chunk_table(path, kind, start_id=0):
    """One chunk per row: 'Column: value; Column: value'."""
    import pandas as pd
    doc = os.path.basename(path)
    try:
        if path.lower().endswith(".csv"):
            sheets = {"": pd.read_csv(path, dtype=str)}
        else:
            sheets = pd.read_excel(path, sheet_name=None, dtype=str)
    except Exception:
        return []
    out = []
    for name, df in sheets.items():
        df = df.fillna("")
        for i, row in df.head(MAX_ROWS).iterrows():
            text = "; ".join("%s: %s" % (c, v) for c, v in row.items()
                             if str(v).strip())
            if not text:
                continue
            out.append(Chunk(start_id + len(out), doc, kind,
                             "%s row %d" % (name, i + 2) if name else
                             "row %d" % (i + 2), "", 0, text, tokens(text)))
    return out


def chunk_file(path, kind, start_id=0):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls", ".csv"):
        return chunk_table(path, kind, start_id)
    if ext in (".docx", ".pdf", ".txt", ".md", ".rtf"):
        return chunk_text_doc(path, kind, start_id)
    return []


# ---------------------------------------------------------------------------
# the index
# ---------------------------------------------------------------------------
@dataclass
class Hit:
    chunk: Chunk
    score: float

    @property
    def cite(self):
        return self.chunk.cite


class Index:
    K1, B = 1.4, 0.75

    def __init__(self, chunks):
        self.chunks = chunks
        self.df = {}
        for c in chunks:
            for t in set(c.toks):
                self.df[t] = self.df.get(t, 0) + 1
        self.n = len(chunks)
        self.avg = (sum(len(c.toks) for c in chunks) / self.n) if self.n else 1

    def _idf(self, t):
        d = self.df.get(t, 0)
        return math.log(1 + (self.n - d + 0.5) / (d + 0.5))

    def search(self, query, k=5, kinds=None):
        q = tokens(query)
        extra = []
        for t in q:
            for s in SYNONYMS.get(t, []):
                extra += tokens(s)
        weights = {t: 1.0 for t in q}
        for t in extra:
            weights.setdefault(t, 0.5)
        hits = []
        for c in self.chunks:
            if kinds and c.kind not in kinds:
                continue
            if not c.toks:
                continue
            tf = {}
            for t in c.toks:
                if t in weights:
                    tf[t] = tf.get(t, 0) + 1
            if not tf:
                continue
            norm = self.K1 * (1 - self.B + self.B * len(c.toks) / self.avg)
            score = sum(weights[t] * self._idf(t) * f * (self.K1 + 1) / (f + norm)
                        for t, f in tf.items())
            hits.append(Hit(c, score))
        hits.sort(key=lambda h: -h.score)
        return hits[:k]


_CACHE = {}


def _sources(study_folder, library=LIBRARY):
    out = []
    for kind in ("sap", "shells", "specs"):
        for p in sorted(glob.glob(os.path.join(study_folder, kind, "*"))):
            if os.path.basename(p).lower() in ("spec.txt", "shells.txt"):
                continue
            out.append((p, kind))
    if library and os.path.isdir(library):
        for p in sorted(glob.glob(os.path.join(library, "**", "*"),
                                  recursive=True)):
            if os.path.isfile(p):
                out.append((p, "library"))
    return out


def index_for(study_folder, library=LIBRARY):
    """The index for one study plus the library, rebuilt when a file changes."""
    src = _sources(study_folder, library)
    key = tuple((p, os.path.getmtime(p)) for p, _ in src)
    if key in _CACHE:
        return _CACHE[key]
    chunks = []
    for p, kind in src:
        chunks += chunk_file(p, kind, len(chunks))
    idx = Index(chunks)
    _CACHE.clear()
    _CACHE[key] = idx
    return idx


def stats(idx):
    by = {}
    for c in idx.chunks:
        by.setdefault((c.kind, c.doc), 0)
        by[(c.kind, c.doc)] += 1
    return by


# ---------------------------------------------------------------------------
# SAP rules, suggested from the text, each with its citation
# ---------------------------------------------------------------------------
_TRT = r"(?:T\d+|R)"
RULE_PATTERNS = [
    ("population_n", r"\b(\d+)\s+subjects\s+will\s+be\s+(?:enrolled|randomi[sz]ed|"
                     r"dosed|included)", lambda m: m.group(1)),
    ("treatments", r"treatments?\s+(%s(?:\s*,\s*%s)*(?:,?\s+and\s+%s)?)"
                   % (_TRT, _TRT, _TRT),
     lambda m: ", ".join(re.findall(_TRT, m.group(1)))),
    ("pk_parameters", r"PARAMCD\s+([A-Z0-9]+(?:\s*,\s*[A-Z0-9]+)+)",
     lambda m: ", ".join(x.strip() for x in m.group(1).split(","))),
    ("concentration_significant_digits",
     r"[Cc]oncentrations\s+will\s+be\s+presented\s+to\s+(\d+)\s+significant",
     lambda m: m.group(1)),
    ("crossover", r"\bcross-?over\b", lambda m: "yes"),
]


def suggest_rules(study_folder, library=None):
    """
    Rules for spec.txt found in the SAP and protocol, by pattern, with the
    passage each came from. A person approves each one before it is used.
    """
    idx = index_for(study_folder, library)
    out = {}
    for c in idx.chunks:
        if c.kind != "sap":
            continue
        for key, pat, val in RULE_PATTERNS:
            if key in out:
                continue
            m = re.search(pat, c.text)
            if m:
                out[key] = {"value": val(m), "cite": c.cite,
                            "quote": c.text[max(0, m.start() - 60):
                                            m.end() + 60].strip()}
    return out


def write_rules(study_folder, rules):
    """Merge approved rules into sap/spec.txt, keeping what is there."""
    from .study import read_spec_rules
    folder = os.path.join(study_folder, "sap")
    os.makedirs(folder, exist_ok=True)
    have = read_spec_rules(folder)
    have.update(rules)
    with open(os.path.join(folder, "spec.txt"), "w", encoding="utf-8") as fh:
        fh.write("# Rules taken from the SAP. One per line, key = value.\n")
        for k, v in have.items():
            fh.write("%s = %s\n" % (k, v))
    return have
