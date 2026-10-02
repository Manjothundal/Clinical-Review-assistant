# -*- coding: utf-8 -*-
"""
Run a review from the command line and write the findings sheet.

  python run_review.py
  python run_review.py --no-model            (no API key needed, code wording)
  python run_review.py --outputs outputs/DEMO-BE-101 --data data/DEMO-BE-101
"""
import argparse
import os
import time

from cra.pipeline import review, NOT_CHECKED
from cra.excel_out import write_findings


def main():
    ap = argparse.ArgumentParser(
        description="Review a delivery of outputs and write a findings sheet.")
    ap.add_argument("--outputs", default="outputs/DEMO-BE-101",
                    help="Folder holding the delivered .rtf outputs")
    ap.add_argument("--data", default="data/DEMO-BE-101",
                    help="Folder holding this study's .xpt files, if you have them")
    ap.add_argument("--compare", nargs="*",
                    default=["data/DEMO-BE-097", "data/DEMO-BE-098"],
                    help="Finished studies to compare against")
    ap.add_argument("--out", default="out/findings.xlsx",
                    help="Where to write the sheet")
    ap.add_argument("--mode", default=None, help="mock, openai or anthropic")
    ap.add_argument("--no-model", action="store_true",
                    help="Skip the model entirely and use the code wording")
    ap.add_argument("--internal", action="store_true",
                    help="Also write our own columns: severity, check, key")
    args = ap.parse_args()

    t0 = time.time()
    print("\nReviewing %s" % args.outputs)

    res = review(args.outputs,
                 data_folder=args.data,
                 compare_folders=args.compare,
                 mode=args.mode,
                 keep_code_wording=args.no_model)

    for line in res.log:
        print("   ", line)

    write_findings(res.findings, args.out, study=res.study,
                   checks_run=res.checks_run, not_checked=NOT_CHECKED,
                   internal=args.internal, candidates=res.candidates)
    print("\n  written to %s   (%.1f seconds)\n" % (args.out, time.time() - t0))

    area = None
    for f in res.findings:
        if f.area != area:
            area = f.area
            print("  %s" % area)
        print("    [%-8s] %s" % (f.severity, f.finding[:96]))
    print()


if __name__ == "__main__":
    main()
