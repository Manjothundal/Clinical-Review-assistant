"""
Creates demo study data so the app has something to run on.

Makes three studies:
  DEMO-BE-101   the study we are reviewing. Problems are planted in it on purpose.
  DEMO-BE-097   a finished study, done correctly
  DEMO-BE-098   a finished study, done correctly

Run this once:   python make_sample_data.py
"""
import os
import numpy as np
import pandas as pd
import pyreadstat

RNG = np.random.default_rng(7)
OUT = "data"

# Each dataset gets variable labels, the way a real .xpt does.
LABELS = {
    "STUDYID": "Study Identifier", "USUBJID": "Unique Subject Identifier",
    "SUBJID": "Subject Identifier for the Study", "SITEID": "Study Site Identifier",
    "AGE": "Age", "SEX": "Sex", "SAFFL": "Safety Population Flag",
    "PKFL": "Pharmacokinetic Population Flag", "TRT01A": "Actual Treatment for Period 01",
    "APERIOD": "Period", "TRTA": "Actual Treatment", "PARAMCD": "Parameter Code",
    "PARAM": "Parameter", "AVAL": "Analysis Value", "AVALU": "Analysis Value Unit",
    "ATPTN": "Analysis Timepoint Number", "EXROUTE": "Route of Administration",
    "EXDOSFRM": "Dose Form", "EXLOC": "Location of Dose Administration",
    "EXDIR": "Directionality", "EXLAT": "Laterality", "EXSTDTC": "Start Date/Time of Treatment",
    "EXENDTC": "End Date/Time of Treatment", "EXDOSE": "Dose per Administration",
    "AETERM": "Reported Term for the Adverse Event", "AEDECOD": "Dictionary-Derived Term",
    "AEBODSYS": "Body System or Organ Class", "AEREL": "Causality",
    "AESEV": "Severity/Intensity", "AESTDTC": "Start Date/Time of Adverse Event",
    "AEENDTC": "End Date/Time of Adverse Event",
}


def write(df, name, study):
    """Write one dataset as a .xpt file, with variable labels."""
    folder = os.path.join(OUT, study)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + ".xpt")
    labels = [LABELS.get(c, c) for c in df.columns]
    pyreadstat.write_xport(df, path, column_labels=labels, table_name=name.upper()[:8])
    print("  wrote", path, len(df), "records")


def build_study(study, n_subjects, plant_problems):
    print(study)
    subs = [f"{study}-{i:03d}" for i in range(1, n_subjects + 1)]

    # ---------- ADSL : one row per subject ----------
    adsl = pd.DataFrame({
        "STUDYID": study,
        "USUBJID": subs,
        "SUBJID": [s.split("-")[-1] for s in subs],
        "SITEID": RNG.choice(["01", "02"], n_subjects),
        "AGE": RNG.integers(19, 55, n_subjects).astype(float),
        "SEX": RNG.choice(["M", "F"], n_subjects),
        "SAFFL": "Y",
        "PKFL": "Y",
    })
    write(adsl, "adsl", study)

    # ---------- ADPP : PK parameters, one row per subject / treatment / parameter ----------
    rows = []
    for s in subs:
        for trt in ["Test", "Reference"]:
            base_auc = float(np.exp(RNG.normal(np.log(520), 0.26)))
            base_cmax = float(np.exp(RNG.normal(np.log(62), 0.28)))
            if trt == "Test":
                base_auc *= float(np.exp(RNG.normal(np.log(0.98), 0.115)))
                base_cmax *= float(np.exp(RNG.normal(np.log(0.95), 0.155)))
            rows += [
                dict(STUDYID=study, USUBJID=s, TRTA=trt, APERIOD=1 if trt == "Test" else 2,
                     PARAMCD="AUCLST", PARAM="AUC from zero to last (h*ng/mL)",
                     AVAL=round(base_auc, 2), AVALU="h*ng/mL", PKFL="Y"),
                dict(STUDYID=study, USUBJID=s, TRTA=trt, APERIOD=1 if trt == "Test" else 2,
                     PARAMCD="CMAX", PARAM="Maximum Concentration (ng/mL)",
                     AVAL=round(base_cmax, 2), AVALU="ng/mL", PKFL="Y"),
            ]
    adpp = pd.DataFrame(rows)

    if plant_problems:
        # PROBLEM 1: three subjects have no AUCLST at all (late samples missing)
        drop = adpp[(adpp.USUBJID.isin(subs[4:7])) & (adpp.PARAMCD == "AUCLST")].index
        adpp = adpp.drop(drop).reset_index(drop=True)
        # PROBLEM 2: one subject has a Test AUC far above Reference
        i = adpp[(adpp.USUBJID == subs[7]) & (adpp.PARAMCD == "AUCLST") &
                 (adpp.TRTA == "Test")].index
        adpp.loc[i, "AVAL"] = adpp.loc[i, "AVAL"] * 1.62
        # PROBLEM 3: the label says per mg but the values are not divided by dose
        adpp.loc[adpp.PARAMCD == "CMAX", "PARAM"] = "Maximum Concentration ((ng/mL)/mg)"
    write(adpp, "adpp", study)

    # ---------- ADPC : concentration over time ----------
    times = [0, 0.25, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 12, 16, 24]
    rows = []
    for s in subs:
        for trt in ["Test", "Reference"]:
            for t in times:
                ka, ke = 1.6, 0.16
                c = 0.0 if t == 0 else 60 * ka / (ka - ke) * (np.exp(-ke * t) - np.exp(-ka * t)) / 10
                c *= float(np.exp(RNG.normal(0, 0.15)))
                rows.append(dict(STUDYID=study, USUBJID=s, TRTA=trt,
                                 APERIOD=1 if trt == "Test" else 2, ATPTN=float(t),
                                 PARAMCD="CONC", PARAM="Plasma Concentration (ng/mL)",
                                 AVAL=round(float(c), 3), AVALU="ng/mL", PKFL="Y"))
    write(pd.DataFrame(rows), "adpc", study)

    # ---------- EX : exposure ----------
    rows = []
    for s in subs:
        for period, (route, form) in enumerate(
                [("SUBLINGUAL", "FILM, SOLUBLE"), ("INTRAMUSCULAR", "SOLUTION")], start=1):
            day = 1 if period == 1 else 8
            rows.append(dict(
                STUDYID=study, USUBJID=s, APERIOD=period, EXROUTE=route, EXDOSFRM=form,
                EXDOSE=12.0,
                EXSTDTC=f"2026-03-{day:02d}", EXENDTC=f"2026-03-{day:02d}",
                EXLOC="", EXDIR="", EXLAT="",
            ))
    ex = pd.DataFrame(rows)
    if plant_problems:
        # PROBLEM 4: every record says THIGH, even the sublingual films
        ex["EXLOC"] = "THIGH"
        ex["EXDIR"] = "ANTEROLATERAL"
        ex.loc[ex.EXROUTE == "INTRAMUSCULAR", "EXLAT"] = "LEFT"
        # PROBLEM 5: one record ends before it starts
        ex.loc[3, "EXENDTC"] = "2026-02-27"
    else:
        # done correctly: oral location for the film, nothing for the injection
        ex.loc[ex.EXROUTE == "SUBLINGUAL", "EXLOC"] = "MUCOSA, TONGUE"
        ex.loc[ex.EXROUTE == "INTRAMUSCULAR", "EXDIR"] = "ANTEROLATERAL"
        ex.loc[ex.EXROUTE == "INTRAMUSCULAR", "EXLAT"] = "LEFT"
    write(ex, "ex", study)

    # ---------- AE : adverse events ----------
    terms = [("HEADACHE", "Headache", "Nervous system disorders"),
             ("NAUSEA", "Nausea", "Gastrointestinal disorders"),
             ("DIZZINESS", "Dizziness", "Nervous system disorders"),
             ("FATIGUE", "Fatigue", "General disorders and administration site conditions")]
    rows = []
    for s in subs:
        for _ in range(int(RNG.integers(0, 4))):
            t = terms[int(RNG.integers(0, len(terms)))]
            rows.append(dict(
                STUDYID=study, USUBJID=s, AETERM=t[0], AEDECOD=t[1], AEBODSYS=t[2],
                AEREL=str(RNG.choice(["RELATED", "NOT RELATED"], p=[0.3, 0.7])),
                AESEV=str(RNG.choice(["MILD", "MODERATE", "SEVERE"], p=[0.6, 0.3, 0.1])),
                AESTDTC="2026-03-05", AEENDTC="2026-03-07",
            ))
    ae = pd.DataFrame(rows)
    if plant_problems and len(ae) > 20:
        # PROBLEM 6: the same two answers written four ways
        idx = ae.sample(n=min(14, len(ae)), random_state=3).index
        ae.loc[idx, "AEREL"] = ae.loc[idx, "AEREL"].str.title()
        # PROBLEM 7: Dizziness put under the wrong system organ class
        ae.loc[ae.AEDECOD == "Dizziness", "AEBODSYS"] = "Ear and labyrinth disorders"
    write(ae, "ae", study)


if __name__ == "__main__":
    print("Building demo study data...\n")
    build_study("DEMO-BE-101", 36, plant_problems=True)
    build_study("DEMO-BE-097", 30, plant_problems=False)
    build_study("DEMO-BE-098", 24, plant_problems=False)
    print("\nDone. The data is in the 'data' folder.")
