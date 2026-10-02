# -*- coding: utf-8 -*-
"""
A finding, and how findings get written to Excel.

The five columns are the ones the review sheet already uses. They are not ours
to change:

    Area | Finding | Output / File | What is wrong | Evidence

A flag becomes a finding only when it survives two tests:
    1. it names the output it is about
    2. it carries evidence, and that evidence was produced by code
Anything without both is dropped before anyone sees it.
"""
import hashlib
from dataclasses import dataclass, field
from typing import List
import pandas as pd

SEVERITY_ORDER = {"Critical": 0, "Major": 1, "Minor": 2}

# The sheet we hand over. Do not change this order.
COLUMNS = ["Area", "Finding", "Output / File", "What is wrong", "Evidence"]

# What we keep for ourselves. Never goes on the sheet above.
INTERNAL = ["Layer", "Severity", "Found by", "Confidence", "Key", "Decision"]

AREA_ORDER = ["PK", "PD", "OMAS", "Safety-AE", "Safety-Core", "Safety-Lab",
              "Human Factors", "Cross-cutting"]


@dataclass
class Finding:
    area: str
    finding: str
    output_file: str
    what_is_wrong: str
    evidence: str
    found_by: str = ""
    severity: str = "Minor"
    confidence: str = "certain"
    decision: str = "open"
    key: str = ""
    detail: dict = field(default_factory=dict)
    layer: str = "TLF"

    def __post_init__(self):
        if not self.key:
            self.key = make_key(self.found_by, self.output_file, self.finding)

    def is_valid(self):
        """No output and no evidence means it is not shown at all."""
        return bool(str(self.output_file).strip()) and bool(str(self.evidence).strip())

    def as_row(self):
        return {"Area": self.area, "Finding": self.finding,
                "Output / File": self.output_file,
                "What is wrong": self.what_is_wrong, "Evidence": self.evidence}

    def as_full_row(self):
        row = self.as_row()
        row.update({"Layer": self.layer, "Severity": self.severity, "Found by": self.found_by,
                    "Confidence": self.confidence, "Key": self.key,
                    "Decision": self.decision})
        return row


def make_key(check, output_file, finding):
    """
    A stable name for this issue, so a finding you rejected last week is not
    raised as brand new next week. Deliberately does NOT include the counts:
    the same problem with different numbers is still the same problem.
    """
    raw = "%s|%s|%s" % (check, output_file, finding)
    return hashlib.sha1(raw.lower().encode()).hexdigest()[:12]


def from_flag(flag):
    from .flags import layer_for
    return Finding(
        layer=layer_for(flag),
        area=flag.area, finding=flag.finding, output_file=flag.output,
        what_is_wrong=flag.what_is_wrong or flag.finding,
        evidence=flag.evidence, found_by=flag.kind,
        severity=flag.severity, confidence=flag.confidence,
        detail=dict(flag.detail))


def order(findings):
    """Area first, the way the sheet is sorted, then severity inside an area."""
    def key(f):
        a = AREA_ORDER.index(f.area) if f.area in AREA_ORDER else 99
        return (a, SEVERITY_ORDER.get(f.severity, 9), f.finding)
    return sorted(findings, key=key)


def to_dataframe(findings, internal=False):
    cols = COLUMNS + INTERNAL if internal else COLUMNS
    rows = [f.as_full_row() if internal else f.as_row() for f in findings]
    return pd.DataFrame(rows, columns=cols)


def drop_decided(findings, decisions):
    """
    Remove anything a person has already rejected.

    `decisions` is {key: "rejected" | "accepted" | ...}. Keys are stable across
    runs, so a finding turned down once does not come back next week.
    """
    return [f for f in findings if decisions.get(f.key) != "rejected"]
