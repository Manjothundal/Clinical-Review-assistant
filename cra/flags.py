# -*- coding: utf-8 -*-
"""
One Flag shape, used by every check.

The fields are deliberately the same five columns the review sheet already uses,
so nothing has to be translated on the way out:

    Area | Finding | Output / File | What is wrong | Evidence

severity and kind are ours. They never appear on the sheet we hand over, but
they drive the sort order and the stable key.
"""
from dataclasses import dataclass, field

# The area names on the team's sheet. Nothing else is allowed.
# The tabs of the scan sheet, in the order a reviewer reads them.
LAYERS = ["Raw Data", "SDTM", "ADaM", "TLF", "SAP", "CDISC Standards",
          "Mock Shells"]

AREAS = ["PK", "PD", "OMAS", "Safety-AE", "Safety-Core", "Safety-Lab",
         "Human Factors", "Cross-cutting"]


@dataclass
class Flag:
    kind: str                      # which check found it
    area: str                      # one of AREAS
    output: str                    # the output file, or the dataset
    finding: str                   # one line, the headline on the sheet
    what_is_wrong: str = ""        # two to four sentences
    evidence: str = ""             # the numbers, produced by code only
    severity: str = "Minor"        # Critical, Major, Minor
    # "certain"   - the code proved it. Goes straight onto the sheet.
    # "candidate" - the code found something that MIGHT be wrong. The model is
    #               asked to keep or drop it before anyone sees it.
    confidence: str = "certain"
    detail: dict = field(default_factory=dict)
    # Which tab of the sheet this lands on: Raw Data, SDTM, ADaM, TLF, SAP,
    # CDISC Standards or Mock Shells. Empty means "work it out" (see layer_for).
    layer: str = ""

    def as_row(self):
        return {"Area": self.area, "Finding": self.finding,
                "Output / File": self.output,
                "What is wrong": self.what_is_wrong, "Evidence": self.evidence}


# ---------------------------------------------------------------------------
# Working out which area a dataset belongs to, so data checks land in the same
# buckets as output checks.
# ---------------------------------------------------------------------------
_DOMAIN_AREA = {
    "AE": "Safety-AE", "ADAE": "Safety-AE",
    "LB": "Safety-Lab", "ADLB": "Safety-Lab",
    "VS": "Safety-Core", "ADVS": "Safety-Core",
    "EG": "Safety-Core", "ADEG": "Safety-Core",
    "DM": "Safety-Core", "ADSL": "Safety-Core",
    "EX": "Safety-Core", "ADEX": "Safety-Core",
    "CM": "Safety-Core", "DS": "Safety-Core", "MH": "Safety-Core",
    "PC": "PK", "ADPC": "PK", "PP": "PK", "ADPP": "PK",
    "PD": "PD", "ADPD": "PD",
    "OM": "OMAS", "ADOM": "OMAS",
}


def area_for_dataset(name):
    key = str(name).upper().replace(".XPT", "").strip()
    if key in _DOMAIN_AREA:
        return _DOMAIN_AREA[key]
    for prefix, area in _DOMAIN_AREA.items():
        if key.startswith(prefix):
            return area
    return "Cross-cutting"


def merge_similar(flags):
    """
    The same problem on three files is one finding, not three.

    The review sheet lists every affected file in the Output / File column and
    writes the problem once. This does the same: flags with the same check and
    the same headline are collapsed, and their file names are joined.
    """
    merged = {}
    order = []
    for f in flags:
        key = (f.kind, f.finding)
        if key not in merged:
            merged[key] = f
            order.append(key)
            continue
        first = merged[key]
        if f.output not in first.output.split(", "):
            first.output = first.output + ", " + f.output
        if f.evidence and f.evidence not in first.evidence:
            first.evidence = first.evidence.rstrip() + " " + f.evidence
    return [merged[k] for k in order]


def area_for_output(filename, title=""):
    """Work out the area of an RTF output from its name and its title."""
    blob = (filename + " " + title).lower()
    pairs = [
        ("omas", "OMAS"),
        ("human factor", "Human Factors"),
        ("adverse event", "Safety-AE"), ("teae", "Safety-AE"), ("_ae", "Safety-AE"),
        ("haemat", "Safety-Lab"), ("hemat", "Safety-Lab"),
        ("urinalys", "Safety-Lab"), ("chemistr", "Safety-Lab"),
        ("laborator", "Safety-Lab"), ("_lb", "Safety-Lab"),
        ("pd_", "PD"), ("pd-", "PD"), ("pharmacodynam", "PD"),
        ("pk_", "PK"), ("conc-", "PK"), ("pharmacokinet", "PK"),
        ("concentration", "PK"), ("meangraph", "PK"), ("sbjgraph", "PK"),
        ("vital", "Safety-Core"), ("electrocardiogram", "Safety-Core"),
        ("ecg", "Safety-Core"), ("demograph", "Safety-Core"),
        ("temperature", "Safety-Core"), ("disintegration", "Safety-Core"),
    ]
    for needle, area in pairs:
        if needle in blob:
            return area
    return "Cross-cutting"


# Output checks that are really about the mock shells or the SAP, not the TLF.
_KIND_LAYER = {"outputs_present_vs_shells": "Mock Shells"}


def layer_for(flag):
    """Which tab a flag belongs on, when the check did not say."""
    if flag.layer:
        return flag.layer
    if flag.kind in _KIND_LAYER:
        return _KIND_LAYER[flag.kind]
    first = str(flag.output).split("/")[0].split(",")[0].strip().upper()
    if first.endswith(".RTF"):
        return "TLF"
    if first.startswith("AD"):
        return "ADaM"
    return "SDTM"
