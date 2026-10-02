# -*- coding: utf-8 -*-
"""
The full scan of one study: raw, SDTM, ADaM, TLF, SAP, CDISC and mock shells.

    load the study folder
    Engine 1   every check, plain code, exact counts
    Engine 2   (optional) the model keeps or drops candidates, writes wording
    the sheet  one tab per layer, same five columns as the review sheet

Decisions (Keep / Reject) are saved in the study folder as decisions.json, so a
rejected finding stays rejected on the next run.
"""
import os
import json
import datetime
from dataclasses import dataclass, field
from typing import Dict, List

from .study import load_study
from .flags import Flag, area_for_dataset, LAYERS
from .findings import order, drop_decided
from .checks_output import run_output_checks, ALL_OUTPUT_CHECKS
from .checks_across import run_across_checks, ALL_ACROSS_CHECKS
from .checks_layers import run_layer_checks, ALL_LAYER_CHECKS
from .review import judge

NOT_CHECKED = [
    "The SAP is read for population names and output numbers only. Its "
    "detailed rules are taken from sap/spec.txt, copied out by hand.",
    "CDISC Controlled Terminology is a small built-in subset (SEX, RACE, "
    "ETHNIC, AGEU, AESEV, AEOUT, No Yes). It is not the full NCI library, and "
    "MedDRA and WHODrug are not checked.",
    "The define.xml, the ADRG and the cSDRG.",
    "Figure images. A figure is read for its titles and footnotes only.",
    "TLF outputs in Word or PDF. Only RTF is read.",
    "Most Pinnacle 21 rules. Only the CDISC checks on the CDISC tab are run.",
]

# dataset scan checks that prove something (see pipeline.py)
CERTAIN_DATA_CHECKS = {
    "Same answer written two ways", "Combination that cannot happen",
    "Dates out of order", "Missing for a few subjects only",
    "Label disagrees with the values", "Ratio far from the rest",
}


QUIET_CONSTANT = {"PARAM", "PARAMCD", "AESER", "AESDTH", "AESCONG", "AESDISAB",
                  "AESHOSP", "AESLIFE", "AESMIE", "DTHFL", "COUNTRY", "AGEU",
                  "RFSTDTC", "RFENDTC", "EXDOSU", "EXTRT"}


@dataclass
class ScanResult:
    study: str
    folder: str
    findings: List = field(default_factory=list)   # every finding, all layers
    log: List[str] = field(default_factory=list)
    checks_run: List[str] = field(default_factory=list)
    inputs: Dict[str, int] = field(default_factory=dict)
    model_mode: str = "off"
    run_at: str = ""
    tlf_compare: List = field(default_factory=list)   # old vs new TLF

    def by_layer(self, layer):
        return [f for f in self.findings if f.layer == layer]

    def counts(self):
        out = {}
        for f in self.findings:
            out.setdefault(f.layer, {}).setdefault(f.severity, 0)
            out[f.layer][f.severity] += 1
        return out


# ---------------------------------------------------------------------------
def _dataset_scan(datasets):
    """The original dataset scan (scan.py), on SDTM and ADaM together."""
    from .scan import run_scan
    out = []
    for f in run_scan(datasets):
        # One value on every record is normal for units, parameter names in a
        # one-parameter dataset, and Y/N variables. Only noise here.
        if f.kind == "One value on every record" and (
                f.variable.endswith("U") or f.variable in QUIET_CONSTANT):
            continue
        where = f.dataset + (" / %s" % f.variable if f.variable else "")
        out.append(Flag(
            kind=f.kind.lower().replace(" ", "_"),
            layer="ADaM" if f.dataset.upper().startswith("AD") else "SDTM",
            area=area_for_dataset(f.dataset), output=where,
            finding=f.headline, what_is_wrong=f.headline, evidence=f.evidence,
            severity="Major" if f.kind in CERTAIN_DATA_CHECKS else "Minor",
            confidence=("certain" if f.kind in CERTAIN_DATA_CHECKS
                        else "candidate"),
            detail=dict(f.detail)))
    return out


def decisions_path(folder):
    return os.path.join(folder, "decisions.json")


def load_decisions(folder):
    try:
        with open(decisions_path(folder), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_decision(folder, key, decision):
    d = load_decisions(folder)
    if decision is None:
        d.pop(key, None)
    else:
        d[key] = decision
    with open(decisions_path(folder), "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1)
    return d


def history_path(folder):
    return os.path.join(folder, "history.json")


def load_history(folder):
    try:
        with open(history_path(folder), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def _save_history(folder, flags):
    """One line per scan: counts by layer and severity, for the trend chart."""
    from .flags import layer_for
    counts = {}
    for f in flags:
        k = "%s|%s" % (layer_for(f), f.severity)
        counts[k] = counts.get(k, 0) + 1
    h = load_history(folder)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    if h and h[-1]["at"] == now:
        h = h[:-1]
    h.append({"at": now, "counts": counts})
    with open(history_path(folder), "w", encoding="utf-8") as fh:
        json.dump(h[-50:], fh)


def scan(folder, use_model=False, mode=None, show_rejected=False):
    """Scan one study folder and return a ScanResult."""
    st = load_study(folder)
    res = ScanResult(study=st.name, folder=folder,
                     run_at=datetime.datetime.now().strftime("%d %b %Y %H:%M"))
    pkg = st.package
    res.inputs = {"raw": len(st.raw), "sdtm": len(st.sdtm), "adam": len(st.adam),
                  "tlf": len(pkg.outputs) if pkg else 0,
                  "sap": len(st.sap_files) + (1 if st.rules else 0),
                  "shells": len(st.shells),
                  "specs": 0 if st.specs is None else
                  int(st.specs["Dataset"].nunique())}

    flags = []
    if pkg is not None and pkg.outputs:
        flags += run_output_checks(pkg) + run_across_checks(pkg)
        res.checks_run += [c.__name__ for c in ALL_OUTPUT_CHECKS
                           + ALL_ACROSS_CHECKS]
        res.log.append("TLF: read %d output(s)" % len(pkg.outputs))
    else:
        res.log.append("TLF: no outputs uploaded, TLF checks did not run")

    data = dict(st.sdtm)
    data.update(st.adam)
    if data:
        try:
            flags += _dataset_scan(data)
            res.checks_run.append("dataset scan (scan.py)")
        except Exception as exc:
            res.log.append("dataset scan did not run: %s" % exc)

    more, errs = run_layer_checks(st)
    flags += more
    res.log += errs
    res.checks_run += [c.__name__ for c in ALL_LAYER_CHECKS]

    for kind, n, word in (("raw", len(st.raw), "raw file(s)"),
                          ("sdtm", len(st.sdtm), "SDTM dataset(s)"),
                          ("adam", len(st.adam), "ADaM dataset(s)")):
        res.log.append("%s: %s" % ({"raw": "Raw", "sdtm": "SDTM",
                                    "adam": "ADaM"}[kind],
                                   "read %d %s" % (n, word) if n
                                   else "nothing uploaded"))
    res.log.append("SAP: %s" % (", ".join(st.sap_files + (["spec.txt"]
                                if st.rules else [])) or "nothing uploaded"))
    res.log.append("Mock shells: %s" % ("%d output(s) listed" % len(st.shells)
                                        if st.shells else "nothing uploaded"))

    old_tlf = os.path.join(folder, "tlf_old")
    if os.path.isdir(old_tlf) and any(f.lower().endswith(".rtf")
                                      for f in os.listdir(old_tlf)):
        from .compare_tlf import compare, totals
        res.tlf_compare = compare(old_tlf, os.path.join(folder, "tlf"))
        t = totals(res.tlf_compare)
        res.log.append("TLF compare: %d changed, %d new, %d removed, %d the "
                       "same as the previous delivery"
                       % (t["changed"], t["new"], t["removed"], t["same"]))
    _save_history(folder, flags)

    res.model_mode = (mode or os.environ.get("CRA_MODEL_MODE", "mock")) \
        if use_model else "off"
    judged = judge(flags, mode=mode, keep_code_wording=not use_model)
    if not show_rejected:
        judged = drop_decided(judged, load_decisions(folder))
    decisions = load_decisions(folder)
    for f in judged:
        f.decision = decisions.get(f.key, "open")
    res.findings = order(judged)
    res.log.append("%d finding(s) in total" % len(res.findings))
    return res


LAYER_ORDER = LAYERS
