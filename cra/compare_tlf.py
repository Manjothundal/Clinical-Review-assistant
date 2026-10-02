# -*- coding: utf-8 -*-
"""
Old TLF delivery against new.

Put the previous delivery in tlf_old/ and the current one in tlf/. Each output
is matched by file name, or failing that by its number (Table 14-3). For every
pair it reports what changed:

    titles, column headers, footnotes, body cells, rows added or removed,
    and the program or run date on the Source line (reported apart, because a
    new run date on its own is not a change in content)

Plain code. Nothing is judged right or wrong here: a change is a change, and a
reviewer decides whether it was meant.
"""
import os
import re
from dataclasses import dataclass, field
from typing import List

from .outputs import read_package
from .study import output_id

_STAMP = re.compile(r"\b\d{1,2}[A-Z]{3}\d{2,4}(\s+\d{1,2}:\d{2}(:\d{2})?)?\b|"
                    r"\b\d{4}-\d{2}-\d{2}(T[\d:]+)?\b|version\s+[\d.]+", re.I)


def _is_source(line):
    return bool(re.match(r"\s*(source|program|pgm)\b", line, re.I))


def _norm(line):
    return re.sub(r"\s+", " ", line).strip()


@dataclass
class Change:
    kind: str          # title, header, footnote, cell, row added, row removed,
                       # source
    where: str
    old: str = ""
    new: str = ""


@dataclass
class OutputDiff:
    new_file: str
    old_file: str
    output_id: str
    status: str                    # same, changed, new, removed
    changes: List[Change] = field(default_factory=list)

    @property
    def n_cells(self):
        return sum(1 for c in self.changes if c.kind == "cell")

    def counts(self):
        out = {}
        for c in self.changes:
            out[c.kind] = out.get(c.kind, 0) + 1
        return out

    def summary(self):
        if self.status in ("new", "removed"):
            return "output %s" % ("added" if self.status == "new" else "removed")
        if not self.changes:
            return "no change"
        return ", ".join("%d %s" % (n, k + ("s" if n > 1 and k != "source"
                                            else ""))
                         for k, n in self.counts().items())


def _row_key(row, i):
    """Label a body row by its first two cells, so rows match when shifted."""
    cells = [_norm(c) for c in row[:2]]
    return " / ".join(c for c in cells if c) or "row %d" % (i + 1)


def _diff_lists(kind, old, new):
    out = []
    so, sn = set(old), set(new)
    for x in new:
        if x not in so:
            # pair with an old line in the same position if there is one
            i = new.index(x)
            o = old[i] if i < len(old) and old[i] not in sn else ""
            out.append(Change(kind, "line %d" % (i + 1), o, x))
    for i, x in enumerate(old):
        if x not in sn and not any(c.old == x for c in out):
            out.append(Change(kind, "line %d" % (i + 1), x, ""))
    return out


def diff_outputs(old, new):
    ch = []
    ch += _diff_lists("title", [_norm(t) for t in old.titles],
                      [_norm(t) for t in new.titles])
    if [_norm(h) for h in old.headers] != [_norm(h) for h in new.headers]:
        ch.append(Change("header", "column headers", " | ".join(old.headers),
                         " | ".join(new.headers)))

    of = [_norm(f) for f in old.footnotes if not _is_source(f)]
    nf = [_norm(f) for f in new.footnotes if not _is_source(f)]
    ch += _diff_lists("footnote", of, nf)
    os_ = [_norm(f) for f in old.footnotes if _is_source(f)]
    ns_ = [_norm(f) for f in new.footnotes if _is_source(f)]
    if [_STAMP.sub("", s) for s in os_] != [_STAMP.sub("", s) for s in ns_]:
        ch.append(Change("source", "program", "; ".join(os_), "; ".join(ns_)))

    # body: match rows by label, then compare cell by cell
    heads = new.headers or old.headers
    old_rows, new_rows = {}, {}
    for i, r in enumerate(old.rows):
        k = _row_key(r, i)
        while k in old_rows:
            k += " +"
        old_rows[k] = r
    for i, r in enumerate(new.rows):
        k = _row_key(r, i)
        while k in new_rows:
            k += " +"
        new_rows[k] = r
    for k, r in new_rows.items():
        if k not in old_rows:
            ch.append(Change("row added", k, "", " | ".join(r)))
            continue
        o = old_rows[k]
        for ci in range(max(len(o), len(r))):
            a = _norm(o[ci]) if ci < len(o) else ""
            b = _norm(r[ci]) if ci < len(r) else ""
            if a != b:
                col = heads[ci] if ci < len(heads) else "column %d" % (ci + 1)
                ch.append(Change("cell", "%s, %s" % (k, col), a, b))
    for k, r in old_rows.items():
        if k not in new_rows:
            ch.append(Change("row removed", k, " | ".join(r), ""))
    return ch


def _oid(o):
    for t in o.titles:
        i = output_id(t)
        if i:
            return i
    return ""


def compare(old_folder, new_folder):
    """Every output in either delivery, with what changed."""
    old = read_package(old_folder).outputs if os.path.isdir(old_folder) else []
    new = read_package(new_folder).outputs if os.path.isdir(new_folder) else []
    used = set()
    out = []
    by_name = {o.filename.lower(): o for o in old}
    for n in new:
        o = by_name.get(n.filename.lower())
        if o is None:
            # same number and same last title line, under a new file name
            cand = [x for x in old if x.filename not in used and _oid(x)
                    and _oid(x) == _oid(n)
                    and _norm(x.titles[-1] if x.titles else "")
                    == _norm(n.titles[-1] if n.titles else "")]
            o = cand[0] if cand else None
        if o is None:
            out.append(OutputDiff(n.filename, "", _oid(n), "new"))
            continue
        used.add(o.filename)
        ch = diff_outputs(o, n)
        out.append(OutputDiff(n.filename, o.filename, _oid(n),
                              "changed" if ch else "same", ch))
    for o in old:
        if o.filename not in used and o.filename.lower() not in \
                {n.filename.lower() for n in new}:
            out.append(OutputDiff("", o.filename, _oid(o), "removed"))
    order = {"removed": 0, "new": 1, "changed": 2, "same": 3}
    return sorted(out, key=lambda d: (order[d.status], d.new_file or d.old_file))


def totals(diffs):
    t = {"same": 0, "changed": 0, "new": 0, "removed": 0, "cells": 0}
    for d in diffs:
        t[d.status] += 1
        t["cells"] += d.n_cells
    return t
