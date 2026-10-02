# -*- coding: utf-8 -*-
"""
A small, safe filter language for the agent's tools.

    SAFFL = 'Y'
    AESEV in ('MILD', 'Mild') and AESER != 'Y'
    AVAL > 100 or CHG is missing
    not (TRTA = 'T3')

Only column names, quoted text, numbers and these words are allowed:
    = == != <> > < >= <= in, not in, is missing, is not missing, and, or, not

Nothing is ever passed to eval or pandas.query, so a model cannot run code
through a filter.
"""
import re
import pandas as pd

_TOKEN = re.compile(r"""\s*(?:
    (?P<str>'[^']*'|"[^"]*") |
    (?P<num>-?\d+(?:\.\d+)?) |
    (?P<op>==|!=|<>|>=|<=|=|>|<) |
    (?P<punct>[(),]) |
    (?P<word>[A-Za-z_][A-Za-z0-9_]*)
)""", re.X)


class FilterError(ValueError):
    pass


def _tokens(text):
    pos, out = 0, []
    text = text.strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise FilterError("cannot read the filter near: %r" % text[pos:pos + 20])
        kind = m.lastgroup
        val = m.group(kind)
        if kind == "str":
            val = val[1:-1]
        elif kind == "num":
            val = float(val)
        elif kind == "word":
            val = val.upper()
        out.append((kind, val))
        pos = m.end()
    return out


class _Parser:
    def __init__(self, toks, df):
        self.t, self.i, self.df = toks, 0, df

    def peek(self, k=0):
        return self.t[self.i + k] if self.i + k < len(self.t) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expect(self, kind, val=None):
        k, v = self.take()
        if k != kind or (val is not None and v != val):
            raise FilterError("expected %s %s, got %s" % (kind, val or "", v))
        return v

    def parse(self):
        m = self.expr()
        if self.i != len(self.t):
            raise FilterError("unexpected %r" % (self.peek()[1],))
        return m

    def expr(self):
        m = self.term()
        while self.peek() in (("word", "AND"), ("word", "OR")):
            op = self.take()[1]
            r = self.term()
            m = (m & r) if op == "AND" else (m | r)
        return m

    def term(self):
        if self.peek() == ("word", "NOT"):
            self.take()
            return ~self.term()
        if self.peek() == ("punct", "("):
            self.take()
            m = self.expr()
            self.expect("punct", ")")
            return m
        col = self.expect("word")
        if col not in self.df.columns:
            raise FilterError("no variable %s. Variables: %s"
                              % (col, ", ".join(self.df.columns[:40])))
        s = self.df[col]
        k, v = self.peek()
        if (k, v) == ("word", "IS"):
            self.take()
            neg = False
            if self.peek() == ("word", "NOT"):
                self.take()
                neg = True
            self.expect("word", "MISSING")
            miss = s.isna() | (s.astype(str).str.strip().isin(["", "nan", "None"]))
            return ~miss if neg else miss
        neg = False
        if (k, v) == ("word", "NOT"):
            self.take()
            neg = True
            k, v = self.peek()
        if (k, v) == ("word", "IN"):
            self.take()
            self.expect("punct", "(")
            vals = []
            while True:
                kk, vv = self.take()
                if kk not in ("str", "num"):
                    raise FilterError("a list holds quoted text or numbers")
                vals.append(vv)
                kk, vv = self.take()
                if (kk, vv) == ("punct", ")"):
                    break
                if (kk, vv) != ("punct", ","):
                    raise FilterError("expected , or )")
            m = self._in(s, vals)
            return ~m if neg else m
        if neg:
            raise FilterError("NOT must be followed by IN here")
        op = self.expect("op")
        kk, val = self.take()
        if kk not in ("str", "num"):
            raise FilterError("compare with quoted text or a number")
        return self._cmp(s, op, val)

    @staticmethod
    def _in(s, vals):
        if all(isinstance(v, float) for v in vals):
            return pd.to_numeric(s, errors="coerce").isin(vals)
        return s.astype(str).str.strip().isin([str(v) for v in vals])

    @staticmethod
    def _cmp(s, op, val):
        if isinstance(val, float):
            x = pd.to_numeric(s, errors="coerce")
        else:
            x = s.astype(str).str.strip()
        if op in ("=", "=="):
            return (x == val).fillna(False)
        if op in ("!=", "<>"):
            return (x != val).fillna(True)
        res = {">": x > val, "<": x < val, ">=": x >= val, "<=": x <= val}[op]
        return res.fillna(False)


def apply(df, where):
    """Rows of df that match the filter. Empty or None means every row."""
    if where is None or not str(where).strip():
        return df
    mask = _Parser(_tokens(str(where)), df).parse()
    return df[mask.astype(bool)]
