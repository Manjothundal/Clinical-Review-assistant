# -*- coding: utf-8 -*-
"""
Builds a small package of RTF outputs to practise on.

Every output in here has a defect planted in it on purpose, and every planted
defect is copied from a real finding on the AQ109109 review sheet. The number in
the comment above each one is the row of that sheet, so you can always check the
app against the real thing.

Run it once:
    python make_sample_outputs.py
"""
import os

STUDY = "DEMO-BE-101"
PROTOCOL = "2026-6050"
OUT = os.path.join("outputs", STUDY)

# --------------------------------------------------------------------------
# a very small RTF writer
# --------------------------------------------------------------------------
HEAD = (r"{\rtf1\ansi\ansicpg1252\deff0"
        r"{\fonttbl{\f0\froman\fcharset0 Times New Roman;}}"
        r"\paperw15840\paperh12240\landscape\margl720\margr720"
        "\n")


def _para(text, bold=False, center=True):
    s = r"\pard" + (r"\qc" if center else r"\ql") + r"\fs18 "
    if bold:
        s += r"\b "
    s += _esc(text)
    if bold:
        s += r"\b0 "
    return s + r"\par" + "\n"


def _esc(text):
    return (text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
            .replace("≤", r"蠄?").replace("µ", r"\u181?"))


def _row(cells, widths, bold=False):
    s = r"\trowd\trgaph60"
    x = 0
    for w in widths:
        x += w
        s += r"\cellx%d" % x
    s += "\n"
    for c in cells:
        s += r"\pard\intbl\qc\fs18 "
        if bold:
            s += r"\b "
        s += _esc(str(c))
        if bold:
            s += r"\b0 "
        s += r"\cell "
    return s + r"\row" + "\n"


def write_rtf(name, titles, headers, rows, footnotes):
    os.makedirs(OUT, exist_ok=True)
    body = HEAD
    for i, t in enumerate(titles):
        body += _para(t, bold=(i == 1))
    if headers:
        widths = [2400] + [1500] * (len(headers) - 1)
        body += _row(headers, widths, bold=True)
        for r in rows:
            body += _row(r, widths)
    for f in footnotes:
        body += _para(f, center=False)
    body += "}"
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="latin-1", errors="replace") as fh:
        fh.write(body)
    return path


def banner(study=STUDY, protocol=PROTOCOL):
    return ["%s   Protocol %s" % (study, protocol)]


SRC = "Source: /prod/%s/pgm/%%s   version 1.2   29SEP2026 09:14" % STUDY


# --------------------------------------------------------------------------
def build():
    made = []

    # -- row 18: the count falls at one window and comes back at the next ---
    made.append(write_rtf(
        "PK_DesStats_EPIN_adj_6050.rtf",
        banner() + ["Table 14-3",
                    "Descriptive Statistics of Baseline-corrected Epinephrine "
                    "Pharmacokinetic Parameters"],
        ["Parameter", "T1", "T2", "T3", "R"],
        [["Cmax n", "48", "24", "24", "48"],
         ["AUC0-5min n", "48", "24", "24", "48"],
         ["AUC0-10min n", "48", "24", "23", "48"],
         ["AUC0-15min n", "48", "24", "24", "48"],
         ["AUC0-20min n", "48", "24", "24", "47"],
         ["AUC0-30min n", "48", "24", "24", "48"],
         ["AUC0-35min n", "48", "23", "24", "48"],
         ["AUC0-45min n", "48", "23", "24", "48"],
         ["AUC0-60min n", "48", "24", "24", "48"]],
        [SRC % "t_pk_desstats.sas"]))

    # -- row 21 and row 23: unpaired crossover, and a rule never applied -----
    made.append(write_rtf(
        "PK_Primary_Endpoints_EPIN_adj_6050_T2_vs_R.rtf",
        banner() + ["Table 14-6",
                    "Primary Endpoint Comparison, Treatment T2 versus Treatment R"],
        ["Parameter", "n T2", "Geometric Mean T2", "n R", "Geometric Mean R",
         "Success"],
        [["Cmax", "24", "344.5", "24", "323.6", "Yes"],
         ["AUC0-10min", "24", "11.11", "24", "4.661", "Yes"],
         ["AUC0-20min", "24", "44.76", "24", "14.70", "Yes"],
         ["AUC0-30min", "24", "71.93", "24", "31.94", "Yes"],
         ["AUC0-45min", "23", "95.97", "24", "75.61", "Yes"]],
        ["Note: Overall success will be declared with an observed 'successful' "
         "outcome for Cmax and at least three of the four partial AUCs for "
         "Treatment T2 versus Treatment R.",
         SRC % "t_pk_primary.sas"]))

    # -- row 16: the title names a window the values run past ---------------
    for p, code in [("Systolic Blood Pressure", "SBP"),
                    ("Diastolic Blood Pressure", "DBP"),
                    ("Pulse Rate", "PR")]:
        maxima = {"SBP": ["60.6", "58.2", "60.3", "60.4"],
                  "DBP": ["57.9", "59.1", "63.1", "60.7"],
                  "PR":  ["55.4", "58.8", "63.1", "60.0"]}[code]
        made.append(write_rtf(
            "PD_Parameter_DesStats_%s_adj_6050.rtf" % code,
            banner() + ["Table 14-12",
                        "Descriptive Statistics of Baseline-corrected %s "
                        "Pharmacodynamic Parameters From 0 to 60 Minutes" % p],
            ["Statistic", "T1", "T2", "T3", "R"],
            [["n", "48", "24", "24", "48"],
             ["TEmax Mean", "22.4", "24.1", "25.8", "23.0"],
             ["TEmax Maximum"] + maxima],
            [SRC % "t_pd_parameter.sas"]))

    # -- row 17: two different listings carry one title ---------------------
    dup_title = ("Listing of Baseline-corrected Systolic Blood Pressure "
                 "Pharmacodynamics Measurements (mmHg)")
    made.append(write_rtf(
        "PD-by-Trt_LISTING_SBP_adj_6050_adj.rtf",
        banner() + ["Appendix 16.2.5.5", dup_title],
        ["Subject", "Sequence", "Period", "Treatment", "Baseline", "0", "5", "10"],
        [["01", "T1RT3", "1", "T1", "0.0", "0.0", "4.0", "7.0"],
         ["02", "RT3T1", "1", "R", "0.0", "0.0", "-2.0", "1.0"]],
        [SRC % "l_pd_sbp.sas"]))
    made.append(write_rtf(
        "PD-by-Trt_LISTING_SBP_adj_6050_adj_exclude.rtf",
        banner() + ["Appendix 16.2.5.5", dup_title],
        ["Subject", "Sequence", "Period", "Treatment", "-10", "-5", "5", "10"],
        [["43", "T1RT3", "1", "T1", "110.0", "112.0", "157.0", "149.0"],
         ["43", "T1RT3", "2", "R", "108.0", "109.0", "121.0", "118.0"]],
        [SRC % "l_pd_sbp_excl.sas"]))

    # -- rows 25, 26, 29: a percent with no denominator and no treatments ---
    made.append(write_rtf(
        "Table_12_3_Summary_of_All_TEAEs.rtf",
        banner() + ["Table 12-3",
                    "Summary of All Treatment-emergent Adverse Events by "
                    "System Organ Class and Preferred Term"],
        ["System Organ Class / Preferred Term", "E (%)", "Severe E (%)"],
        [["Gastrointestinal disorders", "7 (14.6)", "0"],
         ["   Mouth ulceration", "7 (14.6)", "0"],
         ["General disorders", "38 (79.2)", "1 (2.1)"],
         ["   Application site erythema", "15 (31.3)", "0"],
         ["   Application site exfoliation", "38 (79.2)", "1 (2.1)"],
         ["   Application site pallor", "9 (18.8)", "0"]],
        ["Note: E is the number of events.",
         SRC % "t_ae_summary.sas"]))

    # -- row 13: no Source line at all --------------------------------------
    made.append(write_rtf(
        "Table_12_7_Human_Factors.rtf",
        banner() + ["Table 12-7", "Summary of Human Factors Observations"],
        ["Observation", "n (%)"],
        [["Film placed correctly", "46 (95.8)"],
         ["Film repositioned once", "2 (4.2)"]],
        []))

    # -- row 35: a bare program name, no path and no version ----------------
    made.append(write_rtf(
        "Appendix_16_2_5_3_Vital_Signs.rtf",
        banner() + ["Appendix 16.2.5.3",
                    "Listing of Individual Vital Signs Measurements"],
        ["Subject", "Period", "Timepoint", "Systolic", "Diastolic", "Pulse"],
        [["01", "1", "Pre-dose", "118", "76", "64"],
         ["01", "1", "30 min", "121", "78", "68"]],
        ["Source: l_vs.sas"]))

    # -- row 20: the exclusion is applied to one output family only ---------
    made.append(write_rtf(
        "Conc-by-Trt_DesStats_IBA_adj_6050.rtf",
        banner() + ["Table 14-8",
                    "Descriptive Statistics of Baseline-corrected Isobutyric "
                    "Acid Concentrations"],
        ["Timepoint", "n T1", "n T2", "n T3"],
        [["0 min", "44", "23", "19"],
         ["5 min", "44", "23", "19"],
         ["10 min", "44", "23", "19"]],
        [SRC % "t_conc_iba_adj.sas"]))
    made.append(write_rtf(
        "Conc-by-Trt_DesStats_IBA_meas_6050.rtf",
        banner() + ["Table 14-9",
                    "Descriptive Statistics of Measured Isobutyric Acid "
                    "Concentrations"],
        ["Timepoint", "n T1", "n T2", "n T3"],
        [["0 min", "48", "24", "24"],
         ["5 min", "48", "24", "24"],
         ["10 min", "48", "24", "24"]],
        [SRC % "t_conc_iba_meas.sas"]))

    # -- row 22: a figure panel declares an N the table contradicts ---------
    made.append(write_rtf(
        "MeanGraphs_EPIN_adj_6050.rtf",
        banner() + ["Figure 14-19",
                    "Mean Baseline-corrected Epinephrine Concentration-time "
                    "Profile, Linear Scale",
                    "Treatment T1 (N=48), Treatment T2 (N=24), "
                    "Treatment T3 (N=24), Treatment R (N=48)"],
        [], [],
        [SRC % "f_meangraphs_epin.sas"]))
    made.append(write_rtf(
        "Conc-by-Trt_DesStats_EPIN_adj_6050.rtf",
        banner() + ["Table 14-2",
                    "Descriptive Statistics of Baseline-corrected Epinephrine "
                    "Concentrations"],
        ["Timepoint", "n T1", "n T2", "n T3", "n R"],
        [["8 min", "48", "24", "23", "48"],
         ["10 min", "48", "24", "23", "48"],
         ["12 min", "47", "24", "24", "48"],
         ["25 min", "48", "24", "24", "47"],
         ["45 min", "48", "23", "24", "48"]],
        ["Note: n counts non-missing values.",
         SRC % "t_conc_epin_adj.sas"]))

    # -- row 8: an output carrying the wrong study and protocol -------------
    made.append(write_rtf(
        "SbjGraphs_IBA_adj_6050.rtf",
        banner("DEMO-BE-097", "2022-5310")
        + ["Appendix 16.2.6.1",
           "Individual Baseline-corrected Isobutyric Acid "
           "Concentration-time Profiles, Excluded Subjects"],
        [], [],
        [SRC % "f_sbjgraphs_iba.sas"]))

    # -- row 31: a measurement listed only as a whole number ----------------
    made.append(write_rtf(
        "Table_12_10_Demographics.rtf",
        banner() + ["Table 12-10", "Summary of Demographic Characteristics"],
        ["Characteristic", "Statistic", "All Subjects"],
        [["Age (years)", "Mean", "34.2"],
         ["Age (years)", "Range", "19 to 55"],
         ["Weight (kg)", "Mean", "72.4"],
         ["Weight (kg)", "Range", "51.2 to 98.6"],
         ["BMI (kg/m2)", "Mean", "25"],
         ["BMI (kg/m2)", "Range", "19 to 31"]],
        [SRC % "t_demog.sas"]))

    # -- row 28: a code in the table that no footnote defines ---------------
    made.append(write_rtf(
        "Listing_16_2_7_1_Adverse_Events.rtf",
        banner() + ["Appendix 16.2.7.1", "Listing of All Adverse Events"],
        ["Subject", "Preferred Term", "Severity", "Duration", "Outcome"],
        [["01", "Mouth ulceration", "Mild", "2 h 15 min", "RV"],
         ["03", "Haemoglobin decreased", "Mild", "Unknown", "NV"],
         ["14", "Application site erythema", "Mild", "Unknown", "RV"],
         ["16", "Application site pallor", "Mild", "Unknown", "RV"]],
        ["Outcome: RV = Recovered/Resolved.",
         SRC % "l_ae.sas"]))

    # -- row 24: more significant digits than the SAP allows ----------------
    made.append(write_rtf(
        "Conc-by-Trt_LISTING_IBA_adj_6050.rtf",
        banner() + ["Appendix 16.2.6.2",
                    "Listing of Individual Baseline-corrected Isobutyric Acid "
                    "Concentrations (ug/mL)"],
        ["Subject", "Treatment", "Baseline", "5 min", "10 min"],
        [["01", "T1", "10.77", "12.4", "14.1"],
         ["02", "T1", "11.63", "13.0", "15.2"],
         ["03", "T1", "14.57", "16.8", "18.0"],
         ["05", "T1", "11.67", "12.9", "13.8"],
         ["06", "T1", "19.73", "21.2", "22.6"],
         ["10", "T1", "11.97", "13.3", "14.4"]],
        [SRC % "l_conc_iba.sas"]))

    # -- row 11: a denominator that is not the population -------------------
    made.append(write_rtf(
        "Table_12_5_Urinalysis.rtf",
        banner() + ["Table 12-5",
                    "Summary of Urinalysis Results, Safety Population"],
        ["Parameter", "Visit", "n", "Mean", "SD"],
        [["Specific gravity", "Baseline", "12", "1.018", "0.006"],
         ["Specific gravity", "End of Study", "2", "1.021", "0.004"],
         ["pH", "Baseline", "9", "6.1", "0.7"],
         ["pH", "End of Study", "4", "6.3", "0.5"]],
        ["Note: The Safety Population comprises 48 subjects.",
         SRC % "t_urinalysis.sas"]))

    # -- row 36: a vital signs footnote sitting on a laboratory table -------
    made.append(write_rtf(
        "Table_12_6_Haematology.rtf",
        banner() + ["Table 12-6",
                    "Summary of Haematology Results and Change from Baseline"],
        ["Parameter", "Visit", "n", "Mean", "Change Mean"],
        [["Haemoglobin (g/L)", "Baseline", "48", "142.1", ""],
         ["Haemoglobin (g/L)", "End of Study", "48", "140.8", "-1.3"],
         ["Basophils (%)", "Baseline", "48", "0.6", ""],
         ["Basophils (%)", "End of Study", "31", "0.5", "-0.1"],
         ["Eosinophils (%)", "Baseline", "48", "2.4", ""],
         ["Eosinophils (%)", "End of Study", "29", "2.2", "-0.2"]],
        ["Note: Vital signs were measured after the subject had been supine "
         "for five minutes.",
         SRC % "t_haematology.sas"]))

    # -- row 19: the shell list, so the app can see what did not arrive -----
    shells = os.path.join(OUT, "shells.txt")
    with open(shells, "w", encoding="utf-8") as fh:
        fh.write("# One line per output the mock shells require.\n")
        fh.write("# name | title\n")
        for name, title in [
            ("PK_DesStats_EPIN_adj_6050.rtf", "Table 14-3"),
            ("PK_Primary_Endpoints_EPIN_adj_6050_T2_vs_R.rtf", "Table 14-6"),
            ("PD_Parameter_DesStats_SBP_adj_6050.rtf", "Table 14-12"),
            ("PD_Parameter_DesStats_DBP_adj_6050.rtf", "Table 14-12"),
            ("PD_Parameter_DesStats_PR_adj_6050.rtf", "Table 14-12"),
            ("Conc-by-Trt_DesStats_EPIN_adj_6050.rtf", "Table 14-2"),
            ("Conc-by-Trt_DesStats_IBA_adj_6050.rtf", "Table 14-8"),
            ("Conc-by-Trt_DesStats_IBA_meas_6050.rtf", "Table 14-9"),
            ("Conc-by-Trt_DesStats_DEPIN_6050.rtf", "Table 14-10"),
            ("Conc-by-Trt_LISTING_DEPIN_6050.rtf", "Appendix 16.2.6.1"),
            ("PK_Parameter_DesStats_DEPIN_6050.rtf", "Table 14-11"),
            ("PK_LISTING_DEPIN_6050.rtf", "Appendix 16.2.6.1"),
            ("MeanGraphs_DEPIN_6050.rtf", "Figure 14-21"),
            ("GeoMeanGraphs_DEPIN_6050.rtf", "Figure 14-22"),
            ("MeanGraphs_EPIN_adj_6050.rtf", "Figure 14-19"),
            ("Table_12_3_Summary_of_All_TEAEs.rtf", "Table 12-3"),
            ("Table_12_5_Urinalysis.rtf", "Table 12-5"),
            ("Table_12_6_Haematology.rtf", "Table 12-6"),
            ("Table_12_7_Human_Factors.rtf", "Table 12-7"),
            ("Table_12_10_Demographics.rtf", "Table 12-10"),
        ]:
            fh.write("%s | %s\n" % (name, title))
    made.append(shells)

    # -- the small bit of the SAP the checks are allowed to rely on ---------
    spec = os.path.join(OUT, "spec.txt")
    with open(spec, "w", encoding="utf-8") as fh:
        fh.write("# Rules taken from the SAP. One per line, key = value.\n")
        fh.write("population_n = 48\n")
        fh.write("concentration_significant_digits = 3\n")
        fh.write("treatments = T1, T2, T3, R\n")
        fh.write("crossover = yes\n")
    made.append(spec)

    return made


if __name__ == "__main__":
    files = build()
    print("Wrote %d files into %s" % (len(files), OUT))
    for f in files:
        print("  ", os.path.basename(f))
