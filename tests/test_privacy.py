"""
The most important test in the project.

Whatever else changes, the text we send to the AI must never contain a
patient-level record. This test reads the real demo data, builds the profile,
and confirms no subject identifier appears anywhere in it.
"""
import os
import pytest
from cra.data_io import read_study
from cra.profile import profile_study, profile_to_text

FOLDER = os.path.join("data", "DEMO-BE-101")
pytestmark = pytest.mark.skipif(
    not os.path.isdir(FOLDER),
    reason="Run 'python make_sample_data.py' first")


def test_no_subject_id_reaches_the_profile():
    """
    The profile is the text the AI is sent. It must never list subject ids.
    (A finding may still NAME a subject - "AUCLST is missing for subject 005" -
    because that is the finding. Those come from the code, not from the AI.)
    """
    datasets = read_study(FOLDER)
    text = profile_to_text(profile_study(datasets))
    subjects = datasets["ADSL"]["data"]["USUBJID"].tolist()
    leaked = [s for s in subjects if s in text]
    assert leaked == [], f"These subject ids appear in the AI prompt: {leaked[:5]}"


def test_the_profile_stays_small():
    """If this ever gets huge, something is dumping records into it."""
    text = profile_to_text(profile_study(read_study(FOLDER)))
    assert len(text) < 60_000, f"Profile is {len(text)} characters, too big."


# ---------------------------------------------------------------------------
# The second route to the model: the output checks.
# ---------------------------------------------------------------------------
import json
import re

OUTPUT_FOLDER = os.path.join("outputs", "DEMO-BE-101")


def _model_payload():
    from cra.outputs import read_package
    from cra.checks_output import run_output_checks
    from cra.checks_across import run_across_checks
    from cra.findings import from_flag
    from cra.review import _payload

    pkg = read_package(OUTPUT_FOLDER)
    flags = run_output_checks(pkg) + run_across_checks(pkg)
    return json.dumps(_payload([from_flag(f) for f in flags]))


@pytest.mark.skipif(not os.path.isdir(OUTPUT_FOLDER),
                    reason="Run 'python make_sample_outputs.py' first")
def test_no_output_file_contents_are_sent_to_the_model():
    """
    The model gets the check name, the file name and the counts. It never gets
    the body of an output. If someone starts pasting whole tables into the
    prompt, this fails.
    """
    text = _model_payload()
    assert len(text) < 40_000, "The payload is %d characters. Something is " \
                               "dumping output bodies into it." % len(text)


@pytest.mark.skipif(not os.path.isdir(OUTPUT_FOLDER),
                    reason="Run 'python make_sample_outputs.py' first")
def test_the_model_never_decides_a_number():
    """
    Every number in the wording the model is allowed to write must already be
    in the evidence the code produced. This is the rule that makes the sheet
    checkable, so it is tested, not trusted.
    """
    from cra.review import numbers_not_in_evidence

    evidence = "Table_14_6.rtf: AUC0-45min compares 23 against 24."
    good = "The AUC0-45min row rests on 23 subjects against 24."
    bad = "The AUC0-45min row rests on 19 subjects against 24."
    assert numbers_not_in_evidence(good, evidence) == []
    assert numbers_not_in_evidence(bad, evidence) == ["19"]
