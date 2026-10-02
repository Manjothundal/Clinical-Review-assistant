# -*- coding: utf-8 -*-
"""
How much of the real review sheet does this app reproduce?

Reads docs/findings_map.csv, which names the check each of the 38 AQ109109
findings needs, and reports three things per finding:

    built    the check exists in the code
    fires    the check actually raises it on the sample delivery
    -        not built yet

Run it after any change to the checks:
    python docs/score.py
"""
import os
import sys
import csv

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from cra.outputs import read_package
from cra.checks_output import run_output_checks, ALL_OUTPUT_CHECKS
from cra.checks_across import run_across_checks, ALL_ACROSS_CHECKS

BUILT = {c.__name__ for c in ALL_OUTPUT_CHECKS + ALL_ACROSS_CHECKS}
# dataset checks live in scan.py under their own names
DATA_BUILT = {
    "checks_data.missing_visit_for_some_subjects",
    "checks_data.contradictory_fields",
    "checks_data.missing_key_variable",
}

pkg = read_package(os.path.join(os.path.dirname(HERE), "outputs", "DEMO-BE-101"))
FIRED = {f.kind for f in run_output_checks(pkg) + run_across_checks(pkg)}

rows = list(csv.DictReader(open(os.path.join(HERE, "findings_map.csv"))))

built = fires = 0
print()
print("%-5s %-14s %-46s %-9s %s" % ("Row", "Area", "Check", "Engine", "State"))
print("-" * 100)
for r in rows:
    short = r["Check"].split(".")[-1]
    if short in FIRED:
        state, mark = "fires", 2
    elif short in BUILT:
        state, mark = "built", 1
    elif r["Check"] in DATA_BUILT:
        state, mark = "built (data)", 1
    else:
        state, mark = "-", 0
    built += 1 if mark >= 1 else 0
    fires += 1 if mark == 2 else 0
    print("%-5s %-14s %-46s %-9s %s"
          % (r["Source row"], r["Area"], short, r["Engine"], state))

print("-" * 100)
n = len(rows)
print("%d of %d findings have a check written      (%d%%)" % (built, n, 100*built//n))
print("%d of %d are reproduced on the sample data  (%d%%)" % (fires, n, 100*fires//n))
print()
missing = sorted({r["Check"].split(".")[-1] for r in rows
                  if r["Check"].split(".")[-1] not in BUILT
                  and r["Check"] not in DATA_BUILT})
print("Still to write (%d):" % len(missing))
for m in missing:
    who = [r["Source row"] for r in rows if r["Check"].endswith(m)]
    print("   %-40s rows %s" % (m, ", ".join(who)))
print()
