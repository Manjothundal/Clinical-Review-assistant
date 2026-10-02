"""
Turning a check into R code.  ---  NOT BUILT YET, this is the shape it will take.

Why this file exists now: the plan is for every check and every figure to come
with the R code that reproduces it, so a second programmer can run the same
thing in a different language and compare. Keeping this stub here means the
rest of the app is written so that step drops in without a rewrite.

The rule will be the same as everywhere else: the R code is produced by our own
template from a check definition. The AI never writes code that we run.
"""


def check_to_r(flag):
    """Return R code that reproduces one check. Not implemented yet."""
    raise NotImplementedError(
        "R output is the next piece. See README.md, 'What is coming next'.")


def figure_to_r(chart_spec):
    """Return R code (haven + dplyr + ggplot2) for one figure. Not implemented yet."""
    raise NotImplementedError(
        "R output is the next piece. See README.md, 'What is coming next'.")
