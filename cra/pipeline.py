# -*- coding: utf-8 -*-
"""
One review, start to finish.

    read the outputs   ->  RTF files, the shell list, the SAP rules
    read the data      ->  .xpt files, if a data folder is there
    Engine 1           ->  every check, plain code, exact counts
    Engine 2           ->  keep or drop candidates, write the wording
    the sheet          ->  Area | Finding | Output / File | What is wrong | Evidence

Nothing in here calls a model except the judge step, and that step can be turned
off completely with keep_code_wording=True. The app must still produce a full
sheet with no API key at all.
"""
import os
from dataclasses import dataclass, field
from typing import List

from .outputs import read_package
from .checks_output import run_output_checks, ALL_OUTPUT_CHECKS
from .checks_across import run_across_checks, ALL_ACROSS_CHECKS
from .flags import Flag, area_for_dataset
from .findings import order, from_flag
from .review import judge

# Things this version does not look at. Printed on the Read me tab of the sheet,
# because a reviewer must be able to see what was NOT covered.
NOT_CHECKED = [
    "The SAP itself. The app reads spec.txt, which holds only the few rules "
    "someone has copied out of it by hand.",
    "CDISC controlled terminology and MedDRA. Coded values are not checked "
    "against a dictionary yet.",
    "The define.xml, the ADRG and the cSDRG.",
    "Figure images. A figure is read for its titles and footnotes only, never "
    "for the picture.",
    "Anything written in Word or PDF rather than RTF.",
]


# Which dataset checks prove something, and which only raise a question.
# A date out of order is a fact. A variable that never changes usually is not.
CERTAIN_DATA_CHECKS = {
    "Same answer written two ways",
    "Combination that cannot happen",
    "Dates out of order",
    "Missing for a few subjects only",
    "Label disagrees with the values",
    "Ratio far from the rest",
}


@dataclass
class Result:
    study: str
    findings: List = field(default_factory=list)
    candidates: List = field(default_factory=list)
    n_outputs: int = 0
    n_datasets: int = 0
    n_records: int = 0
    flags_found: int = 0
    checks_run: List[str] = field(default_factory=list)
    model_mode: str = "off"
    log: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# the dataset checks, adapted to the shared Flag shape
# ---------------------------------------------------------------------------
def _data_flags(data_folder, compare_folders=None):
    """Run the dataset scan and translate its flags into the shared shape."""
    from .data_io import read_study, study_name
    from .profile import profile_study
    from .scan import run_scan

    datasets = read_study(data_folder)
    name = study_name(data_folder)
    prof = profile_study(datasets)

    others = {}
    for folder in compare_folders or []:
        if os.path.isdir(folder):
            others[study_name(folder)] = profile_study(read_study(folder))

    raw = run_scan(datasets, prof, others, name)

    out = []
    for f in raw:
        where = f.dataset + (" / %s" % f.variable if f.variable else "")
        out.append(Flag(
            kind=f.kind.lower().replace(" ", "_"),
            area=area_for_dataset(f.dataset),
            output=where,
            finding=f.headline,
            what_is_wrong=f.headline,
            evidence=f.evidence,
            severity="Major" if f.kind in CERTAIN_DATA_CHECKS else "Minor",
            confidence=("certain" if f.kind in CERTAIN_DATA_CHECKS
                        else "candidate"),
            detail=dict(f.detail)))
    records = sum(len(d["data"]) for d in datasets.values())
    return out, len(datasets), records


# ---------------------------------------------------------------------------
def review(outputs_folder, data_folder=None, compare_folders=None,
           mode=None, keep_code_wording=False, decisions=None):
    """Review one delivery and return a Result."""
    from .findings import drop_decided

    res = Result(study=os.path.basename(os.path.normpath(outputs_folder)))

    pkg = read_package(outputs_folder)
    res.n_outputs = len(pkg.outputs)
    res.log.append("read %d output(s) from %s" % (len(pkg.outputs),
                                                  outputs_folder))
    if not pkg.spec:
        res.log.append("no spec.txt found, so the checks that need a SAP rule "
                       "did not run")
    if not pkg.shells:
        res.log.append("no shells.txt found, so nothing was checked against the "
                       "mock shells")

    flags = run_output_checks(pkg) + run_across_checks(pkg)
    res.checks_run = [c.__name__ for c in ALL_OUTPUT_CHECKS + ALL_ACROSS_CHECKS]
    res.log.append("output checks noticed %d thing(s)" % len(flags))

    if data_folder and os.path.isdir(data_folder):
        try:
            data, n_ds, n_rec = _data_flags(data_folder, compare_folders)
            flags += data
            res.n_datasets, res.n_records = n_ds, n_rec
            res.log.append("dataset checks noticed %d thing(s) across %d dataset(s)"
                           % (len(data), n_ds))
        except Exception as exc:
            res.log.append("dataset checks did not run: %s" % exc)

    res.flags_found = len(flags)

    res.model_mode = ("off" if keep_code_wording
                      else (mode or os.environ.get("CRA_MODEL_MODE", "mock")))
    judged = judge(flags, mode=mode, keep_code_wording=keep_code_wording)

    # With no model, nothing has decided the candidates. They are real enough to
    # keep but not proved, so they go on their own tab instead of muddying the
    # sheet a reviewer is meant to trust.
    if keep_code_wording:
        res.findings = [f for f in judged if f.confidence == "certain"]
        res.candidates = [f for f in judged if f.confidence != "certain"]
        res.log.append("model off, so %d unproved item(s) were moved to the "
                       "'To look at' tab" % len(res.candidates))
    else:
        # anything the model did not get to judge stays on 'To look at'
        res.candidates = [f for f in judged if f.detail.get("unjudged")]
        res.findings = [f for f in judged if not f.detail.get("unjudged")]
        if res.candidates:
            res.log.append("the model did not judge %d item(s), so they are on "
                           "the 'To look at' tab" % len(res.candidates))

    if decisions:
        before = len(res.findings)
        res.findings = drop_decided(res.findings, decisions)
        res.candidates = drop_decided(res.candidates, decisions)
        res.log.append("%d finding(s) hidden because they were rejected before"
                       % (before - len(res.findings)))

    res.findings = order(res.findings)
    res.candidates = order(res.candidates)
    res.log.append("%d finding(s) on the sheet" % len(res.findings))
    return res
