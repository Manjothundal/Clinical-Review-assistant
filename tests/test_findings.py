# -*- coding: utf-8 -*-
"""
Findings, the stable key, and the sheet that comes out at the end.
"""
import os
import tempfile

from openpyxl import load_workbook

from cra.findings import (Finding, make_key, order, to_dataframe, drop_decided,
                          COLUMNS)
from cra.excel_out import write_findings


def a_finding(**kw):
    base = dict(area="PK", finding="Something is wrong",
                output_file="Table_14_6.rtf",
                what_is_wrong="The table says one thing and does another.",
                evidence="Table_14_6.rtf: 23 against 24.",
                found_by="paired_comparison_same_n", severity="Critical")
    base.update(kw)
    return Finding(**base)


def test_the_sheet_has_the_five_columns_in_the_teams_order():
    assert COLUMNS == ["Area", "Finding", "Output / File", "What is wrong",
                       "Evidence"]


def test_a_finding_with_no_evidence_is_not_valid():
    assert a_finding().is_valid()
    assert not a_finding(evidence="").is_valid()
    assert not a_finding(output_file="  ").is_valid()


def test_the_key_ignores_the_counts():
    """
    The same problem with different numbers is the same problem. If the key
    moved when a count changed, a finding rejected last week would come back as
    brand new this week.
    """
    a = make_key("counts_dip_and_return", "PK_DesStats.rtf", "Counts fall")
    b = make_key("counts_dip_and_return", "PK_DesStats.rtf", "Counts fall")
    assert a == b
    c = make_key("counts_dip_and_return", "PK_Other.rtf", "Counts fall")
    assert a != c


def test_a_rejected_finding_does_not_come_back():
    f = a_finding()
    assert drop_decided([f], {f.key: "rejected"}) == []
    assert drop_decided([f], {f.key: "accepted"}) == [f]


def test_findings_sort_by_area_then_severity():
    items = [a_finding(area="Safety-Lab", severity="Minor", finding="c"),
             a_finding(area="PK", severity="Minor", finding="b"),
             a_finding(area="PK", severity="Critical", finding="a")]
    got = [(f.area, f.severity) for f in order(items)]
    assert got == [("PK", "Critical"), ("PK", "Minor"), ("Safety-Lab", "Minor")]


def test_the_workbook_has_the_findings_tab_and_a_read_me():
    items = [a_finding(), a_finding(area="PD", severity="Major", finding="other")]
    cands = [a_finding(area="Safety-AE", severity="Minor",
                       finding="not proved", confidence="candidate")]
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "findings.xlsx")
        write_findings(items, path, study="DEMO-BE-101",
                       checks_run=["source_line_present"],
                       not_checked=["the SAP itself"], candidates=cands)
        wb = load_workbook(path)
        assert wb.sheetnames[0] == "Findings"
        assert "Read me" in wb.sheetnames
        assert "To look at" in wb.sheetnames

        ws = wb["Findings"]
        assert [c.value for c in ws[1]] == COLUMNS
        assert ws.max_row == 3          # header plus two findings
        assert ws.freeze_panes == "C2"

        # the gaps must be written down, or a reader assumes there are none
        text = " ".join(str(c.value) for row in wb["Read me"].iter_rows()
                        for c in row)
        assert "the SAP itself" in text


def test_the_dataframe_keeps_our_columns_out_of_the_sheet():
    df = to_dataframe([a_finding()])
    assert list(df.columns) == COLUMNS
    assert "Severity" not in df.columns
    full = to_dataframe([a_finding()], internal=True)
    assert "Severity" in full.columns and "Key" in full.columns
