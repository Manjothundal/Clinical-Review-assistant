# -*- coding: utf-8 -*-
"""
The scan: checks for each layer of a study.

    Raw Data          raw extracts against SDTM: lost subjects, lost records,
                      dates and numbers that will not map cleanly
    SDTM              data problems and cross-domain discrepancies
    ADaM              traceability back to SDTM, and derivations re-done
    TLF               numbers on the outputs against the ADaM data
    SAP               what the SAP promises against what the data holds
    CDISC Standards   structure, required variables, names, labels, ISO 8601
                      dates, controlled terminology (a small built-in subset)
    Mock Shells       shells against the delivered outputs

Plain code. Every number in every Evidence line is counted here. Each function
takes a Study (see study.py) and returns a list of Flags.
"""
import re
import pandas as pd

from .flags import Flag, area_for_dataset
from .study import output_id

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
ISO8601 = re.compile(
    r"^\d{4}(-(\d{2}|-)(-(\d{2}|-)(T\d{2}(:\d{2}(:\d{2}(\.\d+)?)?)?)?)?)?$")
SUBJECT_COLS = ["USUBJID", "SUBJID", "SUBJECT", "SUBJNO", "SUBJ", "PATIENT",
                "PATNO", "PT"]
NUM_RE = re.compile(r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$")


def _flag(kind, layer, ds, finding, wrong, evidence, severity="Major",
          confidence="certain", output=None, **detail):
    # Every number in the headline must also be in the evidence, because the
    # model is only allowed to use numbers that are in the evidence.
    missing = sorted(set(re.findall(r"\d+(?:\.\d+)?", finding))
                     - set(re.findall(r"\d+(?:\.\d+)?", evidence)),
                     key=lambda x: float(x))
    if "8601" in missing:
        evidence += " Expected format: ISO 8601."
        missing.remove("8601")
    if missing:
        evidence = "Count: %s. %s" % (", ".join(missing), evidence)
    return Flag(kind=kind, layer=layer, area=area_for_dataset(ds),
                output=output or ds, finding=finding, what_is_wrong=wrong,
                evidence=evidence, severity=severity, confidence=confidence,
                detail=detail)


def _examples(items, n=5):
    items = sorted(str(i) for i in items)
    more = len(items) - n
    return ", ".join(items[:n]) + (" and %d more" % more if more > 0 else "")


def _df(d):
    return d["data"] if isinstance(d, dict) else d


def _subjects(df):
    if "USUBJID" in df.columns:
        return set(df["USUBJID"].dropna().astype(str))
    return set()


def _subject_col(df):
    for c in SUBJECT_COLS:
        if c in df.columns:
            return c
    return None


def _is_text(s):
    return not pd.api.types.is_numeric_dtype(s)


def _bds(datasets):
    """ADaM datasets with a PARAMCD, i.e. the BDS ones."""
    return {k: v for k, v in datasets.items() if "PARAMCD" in _df(v).columns}


def _domain_of(name):
    """AE from AE, AE_RAW, RAW_AE, AERAW."""
    up = name.upper()
    for token in re.split(r"[_\-\s]+", up):
        if token not in ("RAW", "") and len(token) <= 4:
            return token
    return re.sub(r"RAW", "", up)[:2]


# ===========================================================================
# CDISC Standards
# ===========================================================================
# A small subset of CDISC Controlled Terminology. Enough to catch the usual
# slips (lower case, a free-text spelling). It is not the NCI library.
CT = {
    "SEX": {"M", "F", "U", "UNDIFFERENTIATED"},
    "AGEU": {"YEARS", "MONTHS", "WEEKS", "DAYS", "HOURS"},
    "RACE": {"AMERICAN INDIAN OR ALASKA NATIVE", "ASIAN",
             "BLACK OR AFRICAN AMERICAN",
             "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER", "WHITE", "MULTIPLE",
             "OTHER", "UNKNOWN", "NOT REPORTED"},
    "ETHNIC": {"HISPANIC OR LATINO", "NOT HISPANIC OR LATINO", "NOT REPORTED",
               "UNKNOWN"},
    "AESEV": {"MILD", "MODERATE", "SEVERE"},
    "AEOUT": {"RECOVERED/RESOLVED", "RECOVERING/RESOLVING",
              "NOT RECOVERED/NOT RESOLVED", "RECOVERED/RESOLVED WITH SEQUELAE",
              "FATAL", "UNKNOWN"},
}
NY = {"Y", "N", "U", "NA"}
NY_VARS = {"AESER", "AESCONG", "AESDISAB", "AESDTH", "AESHOSP", "AESLIFE",
           "AESMIE", "AECONTRT", "DTHFL"}

SDTM_REQUIRED = {
    "DM": ["STUDYID", "DOMAIN", "USUBJID", "SUBJID", "SITEID", "SEX",
           "COUNTRY", "ARMCD", "ARM", "ACTARMCD", "ACTARM"],
    "AE": ["AESEQ", "AETERM", "AEDECOD"],
    "EX": ["EXSEQ", "EXTRT"],
    "VS": ["VSSEQ", "VSTESTCD", "VSTEST"],
    "LB": ["LBSEQ", "LBTESTCD", "LBTEST"],
    "EG": ["EGSEQ", "EGTESTCD", "EGTEST"],
    "CM": ["CMSEQ", "CMTRT"],
    "MH": ["MHSEQ", "MHTERM"],
    "DS": ["DSSEQ", "DSTERM", "DSDECOD"],
    "PC": ["PCSEQ", "PCTESTCD", "PCTEST"],
    "PP": ["PPSEQ", "PPTESTCD", "PPTEST"],
}
SDTM_ALWAYS = ["STUDYID", "DOMAIN", "USUBJID"]
TRIAL_DESIGN = {"TA", "TE", "TI", "TS", "TV", "RELREC"}

ADSL_REQUIRED = ["STUDYID", "USUBJID", "SUBJID", "SITEID", "AGE", "AGEU", "SEX",
                 "RACE", "ARM", "TRT01P"]
BDS_REQUIRED = ["STUDYID", "USUBJID", "PARAMCD", "PARAM"]


def _structure(ds, d, layer_word):
    """Name and label lengths, which every SAS transport file must keep to."""
    out = []
    df, labels = _df(d), d.get("labels", {}) if isinstance(d, dict) else {}
    if len(ds) > 8:
        out.append(_flag("cdisc_dataset_name", "CDISC Standards", ds,
                         "%s dataset name %s is longer than 8 characters"
                         % (layer_word, ds),
                         "SAS V5 transport files allow dataset names of at most "
                         "8 characters. This dataset cannot be submitted as is.",
                         "%s: name is %d characters." % (ds, len(ds))))
    long_names = [c for c in df.columns if len(c) > 8]
    if long_names:
        out.append(_flag("cdisc_variable_name", "CDISC Standards", ds,
                         "%d variable name(s) in %s are longer than 8 characters"
                         % (len(long_names), ds),
                         "Variable names must be 8 characters or fewer for SAS V5 "
                         "transport and for the define.xml.",
                         "%s: %s." % (ds, _examples(long_names))))
    long_labels = [c for c, l in labels.items() if l and len(str(l)) > 40]
    if long_labels:
        out.append(_flag("cdisc_label_length", "CDISC Standards", ds,
                         "%d variable label(s) in %s are longer than 40 "
                         "characters" % (len(long_labels), ds),
                         "Labels over 40 characters are cut off in the "
                         "transport file, so the define.xml and the data will "
                         "disagree.",
                         "%s: %s." % (ds, "; ".join(
                             "%s (%d chars)" % (c, len(labels[c]))
                             for c in long_labels[:5])),
                         severity="Minor"))
    bad_case = [c for c in df.columns if c != c.upper()
                or not re.match(r"^[A-Z][A-Z0-9_]*$", c.upper())]
    if bad_case:
        out.append(_flag("cdisc_variable_case", "CDISC Standards", ds,
                         "%d variable name(s) in %s are not upper-case "
                         "letters, digits and underscores" % (len(bad_case), ds),
                         "CDISC variable names are upper case, start with a "
                         "letter and hold only letters, digits and underscores.",
                         "%s: %s." % (ds, _examples(bad_case)), severity="Minor"))
    return out


def _ct_checks(ds, df):
    out = []
    for var, allowed in CT.items():
        if var not in df.columns:
            continue
        vals = df[var].dropna().astype(str)
        vals = vals[vals.str.strip() != ""]
        bad = vals[~vals.isin(allowed)]
        if len(bad):
            forms = bad.value_counts()
            out.append(_flag("cdisc_ct", "CDISC Standards", ds,
                             "%s in %s holds %d value(s) outside CDISC "
                             "Controlled Terminology" % (var, ds, len(bad)),
                             "%s must use the CDISC submission values exactly, "
                             "upper case. Anything else fails Pinnacle 21 and "
                             "breaks counts that group on this variable." % var,
                             "%s: %s." % (ds, "; ".join(
                                 "'%s' on %d record(s)" % (v, n)
                                 for v, n in forms.head(5).items())),
                             output="%s / %s" % (ds, var)))
    for var in sorted(NY_VARS & set(df.columns)):
        vals = df[var].dropna().astype(str)
        vals = vals[vals.str.strip() != ""]
        bad = vals[~vals.isin(NY)]
        if len(bad):
            out.append(_flag("cdisc_ct", "CDISC Standards", ds,
                             "%s in %s holds %d value(s) outside the No Yes "
                             "codelist" % (var, ds, len(bad)),
                             "%s takes Y, N, U or NA only." % var,
                             "%s: %s." % (ds, "; ".join(
                                 "'%s' on %d record(s)" % (v, n)
                                 for v, n in bad.value_counts().head(5).items())),
                             output="%s / %s" % (ds, var)))
    return out


def _iso_dates(ds, df):
    out = []
    for c in [c for c in df.columns if c.endswith("DTC")]:
        vals = df[c].dropna().astype(str)
        vals = vals[vals.str.strip() != ""]
        bad = vals[~vals.str.match(ISO8601)]
        if len(bad):
            out.append(_flag("cdisc_iso8601", "CDISC Standards", ds,
                             "%d %s value(s) in %s are not ISO 8601"
                             % (len(bad), c, ds),
                             "SDTM --DTC variables must be ISO 8601 text "
                             "(YYYY-MM-DD, with time if collected). Other "
                             "formats fail validation and break every study day "
                             "and ADaM date derived from them.",
                             "%s: %d of %d values. Examples: %s."
                             % (ds, len(bad), len(vals),
                                _examples(set(bad), 3)),
                             output="%s / %s" % (ds, c)))
    return out


def cdisc_sdtm(st):
    out = []
    for ds, d in st.sdtm.items():
        df = _df(d)
        out += _structure(ds, d, "SDTM")
        dom = ds[:2] if ds.startswith("SUPP") is False else ds
        if ds in TRIAL_DESIGN:
            continue
        need = list(SDTM_ALWAYS)
        if ds in SDTM_REQUIRED:
            need += [v for v in SDTM_REQUIRED[ds] if v not in need]
        elif ds != "DM" and not ds.startswith("SUPP"):
            need.append(ds + "SEQ")
        missing = [v for v in need if v not in df.columns]
        if missing:
            out.append(_flag("cdisc_required", "CDISC Standards", ds,
                             "%s is missing %d required variable(s)"
                             % (ds, len(missing)),
                             "SDTMIG marks these variables Required. A dataset "
                             "without them fails conformance checks.",
                             "%s: missing %s." % (ds, ", ".join(missing)),
                             severity="Critical" if "USUBJID" in missing
                             else "Major"))
        if "DOMAIN" in df.columns and not ds.startswith("SUPP"):
            vals = set(df["DOMAIN"].dropna().astype(str)) - {ds}
            if vals:
                n = int(df["DOMAIN"].astype(str).isin(vals).sum())
                out.append(_flag("cdisc_domain_value", "CDISC Standards", ds,
                                 "DOMAIN does not match the dataset name on %d "
                                 "record(s) of %s" % (n, ds),
                                 "DOMAIN must equal the two-letter dataset name.",
                                 "%s: DOMAIN holds %s on %d record(s)."
                                 % (ds, _examples(vals), n)))
        seq = ds + "SEQ"
        if seq in df.columns and "USUBJID" in df.columns:
            dup = df[df.duplicated(["USUBJID", seq], keep=False)]
            if len(dup):
                out.append(_flag("cdisc_seq_unique", "CDISC Standards", ds,
                                 "%s is not unique within subject on %d record(s)"
                                 % (seq, len(dup)),
                                 "--SEQ must identify one record per subject. "
                                 "SUPP-- and RELREC links break when it repeats.",
                                 "%s: %d records share a USUBJID and %s. First: "
                                 "%s %s=%s." % (ds, len(dup), seq,
                                                dup.iloc[0]["USUBJID"], seq,
                                                dup.iloc[0][seq]),
                                 output="%s / %s" % (ds, seq)))
        out += _ct_checks(ds, df)
        out += _iso_dates(ds, df)
    return out


def cdisc_adam(st):
    out = []
    for ds, d in st.adam.items():
        df = _df(d)
        out += _structure(ds, d, "ADaM")
        out += _ct_checks(ds, df)
        need = ADSL_REQUIRED if ds == "ADSL" else (
            BDS_REQUIRED if "PARAMCD" in df.columns else ["STUDYID", "USUBJID"])
        missing = [v for v in need if v not in df.columns]
        if "PARAMCD" in df.columns and not {"AVAL", "AVALC"} & set(df.columns):
            missing.append("AVAL or AVALC")
        if missing:
            out.append(_flag("cdisc_required", "CDISC Standards", ds,
                             "%s is missing %d required variable(s)"
                             % (ds, len(missing)),
                             "ADaMIG marks these variables Required for this "
                             "class of dataset.",
                             "%s: missing %s." % (ds, ", ".join(missing))))
        for c in [c for c in df.columns if c.endswith("FL")]:
            vals = df[c].dropna().astype(str)
            vals = vals[vals.str.strip() != ""]
            bad = vals[~vals.isin({"Y", "N"})]
            if len(bad):
                out.append(_flag("cdisc_flag_values", "CDISC Standards", ds,
                                 "%s in %s holds %d value(s) other than Y, N or "
                                 "blank" % (c, ds, len(bad)),
                                 "ADaM flags take Y, N or null only. Any other "
                                 "value is silently dropped by a WHERE "
                                 "%s='Y' and the population count changes." % c,
                                 "%s: %s." % (ds, "; ".join(
                                     "'%s' on %d record(s)" % (v, n)
                                     for v, n in bad.value_counts().head(5)
                                     .items())),
                                 output="%s / %s" % (ds, c)))
        if "PARAMCD" in df.columns:
            codes = df["PARAMCD"].dropna().astype(str).unique()
            bad = [c for c in codes if len(c) > 8
                   or not re.match(r"^[A-Z][A-Z0-9_]*$", c)]
            if bad:
                out.append(_flag("cdisc_paramcd", "CDISC Standards", ds,
                                 "%d PARAMCD value(s) in %s break the naming "
                                 "rule" % (len(bad), ds),
                                 "PARAMCD is at most 8 characters, upper case, "
                                 "starts with a letter, letters digits and "
                                 "underscores only.",
                                 "%s: %s." % (ds, _examples(bad)),
                                 output="%s / PARAMCD" % ds))
            if "PARAM" in df.columns:
                pairs = df[["PARAMCD", "PARAM"]].dropna().drop_duplicates()
                multi_p = pairs.groupby("PARAMCD")["PARAM"].nunique()
                multi_c = pairs.groupby("PARAM")["PARAMCD"].nunique()
                bad_c = multi_p[multi_p > 1].index.tolist()
                bad_p = multi_c[multi_c > 1].index.tolist()
                if bad_c or bad_p:
                    ev = []
                    for c in bad_c[:3]:
                        ev.append("PARAMCD %s has PARAM %s" % (c, " and ".join(
                            "'%s'" % p for p in pairs[pairs.PARAMCD == c].PARAM)))
                    for p in bad_p[:3]:
                        ev.append("PARAM '%s' has PARAMCD %s" % (p, " and ".join(
                            pairs[pairs.PARAM == p].PARAMCD)))
                    out.append(_flag("cdisc_param_1to1", "CDISC Standards", ds,
                                     "PARAM and PARAMCD are not one-to-one in %s"
                                     % ds,
                                     "Each PARAMCD must map to exactly one PARAM "
                                     "and the other way round. Tables that group "
                                     "on one and print the other will split or "
                                     "merge rows.",
                                     "%s: %s." % (ds, "; ".join(ev)),
                                     output="%s / PARAMCD" % ds))
    return out


# ===========================================================================
# SDTM
# ===========================================================================
def _study_day(dtc, ref):
    d = pd.to_datetime(dtc.astype(str).str[:10], errors="coerce", format="%Y-%m-%d")
    r = pd.to_datetime(ref.astype(str).str[:10], errors="coerce", format="%Y-%m-%d")
    diff = (d - r).dt.days
    return diff.where(diff < 0, diff + 1)


def sdtm_checks(st):
    out = []
    dm = _df(st.sdtm["DM"]) if "DM" in st.sdtm else None
    dm_subs = _subjects(dm) if dm is not None else set()

    if dm is not None and "USUBJID" in dm.columns:
        dup = dm[dm.duplicated("USUBJID", keep=False)]
        if len(dup):
            out.append(_flag("sdtm_dm_unique", "SDTM", "DM",
                             "DM holds %d record(s) for subjects that appear "
                             "more than once" % len(dup),
                             "DM must have one record per subject. Every merge "
                             "on DM will duplicate that subject's records.",
                             "DM: %d records over %d subject(s): %s."
                             % (len(dup), dup.USUBJID.nunique(),
                                _examples(set(dup.USUBJID))),
                             severity="Critical"))

    for ds, d in st.sdtm.items():
        df = _df(d)
        if ds == "DM" or dm is None or "USUBJID" not in df.columns:
            continue
        orphans = _subjects(df) - dm_subs
        if orphans:
            n = int(df["USUBJID"].isin(orphans).sum())
            out.append(_flag("sdtm_subject_not_in_dm", "SDTM", ds,
                             "%d subject(s) in %s are not in DM"
                             % (len(orphans), ds),
                             "Every subject in a findings, events or "
                             "interventions domain must exist in DM. These "
                             "records will fall out of any analysis joined to "
                             "DM or ADSL.",
                             "%s: %d record(s) for %s, none of them in DM."
                             % (ds, n, _examples(orphans)),
                             output="%s / USUBJID" % ds))

    # --STRESC numeric but --STRESN missing
    for ds, d in st.sdtm.items():
        df = _df(d)
        c, n = ds + "STRESC", ds + "STRESN"
        if c in df.columns and n in df.columns:
            sc = df[c].astype(str).str.strip()
            looks_num = sc.str.match(NUM_RE)
            miss = df[looks_num & pd.to_numeric(df[n], errors="coerce").isna()]
            if len(miss):
                out.append(_flag("sdtm_stresn_missing", "SDTM", ds,
                                 "%s is numeric but %s is empty on %d record(s)"
                                 % (c, n, len(miss)),
                                 "When the standard result is a number it must "
                                 "also be in %s. Summary tables read %s, so these "
                                 "results are silently left out." % (n, n),
                                 "%s: %d record(s). First: %s %s='%s'."
                                 % (ds, len(miss), miss.iloc[0].get("USUBJID", ""),
                                    c, miss.iloc[0][c]),
                                 output="%s / %s" % (ds, n)))

    # study day against RFSTDTC
    if dm is not None and "RFSTDTC" in dm.columns:
        ref = dm.drop_duplicates("USUBJID").set_index("USUBJID")["RFSTDTC"]
        for ds, d in st.sdtm.items():
            df = _df(d)
            if ds == "DM" or "USUBJID" not in df.columns:
                continue
            for dy in [c for c in df.columns if c.endswith("DY")]:
                dtc = dy[:-2] + "DTC"
                if dtc not in df.columns:
                    continue
                expect = _study_day(df[dtc], df["USUBJID"].map(ref))
                have = pd.to_numeric(df[dy], errors="coerce")
                bad = df[expect.notna() & have.notna() & (expect != have)]
                if len(bad):
                    r = bad.iloc[0]
                    i = bad.index[0]
                    out.append(_flag("sdtm_study_day", "SDTM", ds,
                                     "%s does not match %s and RFSTDTC on %d "
                                     "record(s)" % (dy, dtc, len(bad)),
                                     "Study day is date minus RFSTDTC, plus one "
                                     "on or after day 1, with no day 0. A wrong "
                                     "study day moves records between visit "
                                     "windows.",
                                     "%s: %d record(s). First: %s %s=%s, "
                                     "RFSTDTC=%s, %s=%d, expected %d."
                                     % (ds, len(bad), r["USUBJID"], dtc, r[dtc],
                                        ref.get(r["USUBJID"]), dy, int(have[i]),
                                        int(expect[i])),
                                     output="%s / %s" % (ds, dy)))

    # treated per DM against EX
    if dm is not None and "EX" in st.sdtm and "ACTARMCD" in dm.columns:
        ex_subs = _subjects(_df(st.sdtm["EX"]))
        not_treated = dm["ACTARMCD"].astype(str).str.upper().isin(
            {"NOTTRT", "SCRNFAIL", "NOTASSGN", ""})
        should = set(dm.loc[~not_treated, "USUBJID"].astype(str))
        no_ex = should - ex_subs
        if no_ex:
            out.append(_flag("sdtm_treated_no_ex", "SDTM", "DM",
                             "%d subject(s) have an actual arm in DM but no "
                             "record in EX" % len(no_ex),
                             "DM says these subjects were treated, EX says they "
                             "were never dosed. One of the two is wrong, and "
                             "the safety population depends on it.",
                             "DM ACTARMCD is set and EX has 0 records for %s."
                             % _examples(no_ex), output="DM, EX"))
        dosed_nt = set(dm.loc[not_treated, "USUBJID"].astype(str)) & ex_subs
        if dosed_nt:
            out.append(_flag("sdtm_not_treated_has_ex", "SDTM", "DM",
                             "%d subject(s) are not treated in DM but have "
                             "dosing in EX" % len(dosed_nt),
                             "ACTARMCD says not treated while EX records a "
                             "dose.",
                             "Subjects: %s." % _examples(dosed_nt),
                             output="DM, EX"))
    return out


# ===========================================================================
# ADaM
# ===========================================================================
def adam_checks(st):
    out = []
    adsl = _df(st.adam["ADSL"]) if "ADSL" in st.adam else None
    dm = _df(st.sdtm["DM"]) if "DM" in st.sdtm else None

    if adsl is not None and "USUBJID" in adsl.columns:
        dup = adsl[adsl.duplicated("USUBJID", keep=False)]
        if len(dup):
            out.append(_flag("adam_adsl_unique", "ADaM", "ADSL",
                             "ADSL has more than one record for %d subject(s)"
                             % dup.USUBJID.nunique(),
                             "ADSL is one record per subject. Every population "
                             "count and every merge onto ADSL is wrong while it "
                             "repeats.",
                             "ADSL: %d records for %s." % (len(dup), _examples(
                                 set(dup.USUBJID))), severity="Critical"))

    if adsl is not None and dm is not None:
        a, d = _subjects(adsl), _subjects(dm)
        if d - a:
            out.append(_flag("adam_dm_not_in_adsl", "ADaM", "ADSL",
                             "%d subject(s) in DM are missing from ADSL"
                             % len(d - a),
                             "ADSL should hold every subject in DM, screen "
                             "failures aside. These subjects cannot appear in "
                             "any population.",
                             "DM has %d subjects, ADSL has %d. Missing: %s."
                             % (len(d), len(a), _examples(d - a)),
                             output="ADSL, DM"))
        if a - d:
            out.append(_flag("adam_adsl_not_in_dm", "ADaM", "ADSL",
                             "%d subject(s) in ADSL are not in DM" % len(a - d),
                             "An ADSL subject with no DM record has no source. "
                             "Traceability to SDTM fails.",
                             "Not in DM: %s." % _examples(a - d),
                             output="ADSL, DM", severity="Critical"))
        both = adsl.drop_duplicates("USUBJID").merge(
            dm.drop_duplicates("USUBJID"), on="USUBJID", suffixes=("_A", "_D"))
        for var in ("AGE", "SEX", "RACE", "SITEID", "ARM", "ACTARM", "COUNTRY"):
            if var + "_A" not in both.columns or var + "_D" not in both.columns:
                continue
            x, y = both[var + "_A"].astype(str), both[var + "_D"].astype(str)
            if var == "AGE":
                x = pd.to_numeric(both[var + "_A"], errors="coerce").astype(str)
                y = pd.to_numeric(both[var + "_D"], errors="coerce").astype(str)
            bad = both[x != y]
            if len(bad):
                r = bad.iloc[0]
                out.append(_flag("adam_adsl_vs_dm", "ADaM", "ADSL",
                                 "%s in ADSL differs from DM for %d subject(s)"
                                 % (var, len(bad)),
                                 "%s is copied from DM. A difference means one "
                                 "of them was changed after the other was "
                                 "built, and the demographics table will not "
                                 "match the SDTM data." % var,
                                 "%d subject(s). First: %s ADSL.%s=%s, DM.%s=%s."
                                 % (len(bad), r["USUBJID"], var, r[var + "_A"],
                                    var, r[var + "_D"]),
                                 output="ADSL / %s, DM / %s" % (var, var)))

    if adsl is not None:
        a = _subjects(adsl)
        for ds, d in st.adam.items():
            df = _df(d)
            if ds == "ADSL" or "USUBJID" not in df.columns:
                continue
            orphan = _subjects(df) - a
            if orphan:
                out.append(_flag("adam_subject_not_in_adsl", "ADaM", ds,
                                 "%d subject(s) in %s are not in ADSL"
                                 % (len(orphan), ds),
                                 "Every ADaM subject must be in ADSL, or "
                                 "population flags merged from ADSL are blank "
                                 "for them.",
                                 "%s: %s." % (ds, _examples(orphan)),
                                 output="%s / USUBJID" % ds))

    # safety flag against dosing
    if adsl is not None and "SAFFL" in adsl.columns and "EX" in st.sdtm:
        ex_subs = _subjects(_df(st.sdtm["EX"]))
        saf = set(adsl.loc[adsl.SAFFL.astype(str) == "Y", "USUBJID"].astype(str))
        nsaf = _subjects(adsl) - saf
        if saf - ex_subs:
            out.append(_flag("adam_saffl_no_dose", "ADaM", "ADSL",
                             "%d subject(s) have SAFFL=Y but no dose in EX"
                             % len(saf - ex_subs),
                             "The safety population is subjects who took at "
                             "least one dose. These subjects have none.",
                             "SAFFL=Y and 0 EX records: %s."
                             % _examples(saf - ex_subs),
                             output="ADSL / SAFFL, EX", severity="Critical"))
        if nsaf & ex_subs:
            out.append(_flag("adam_dosed_not_saffl", "ADaM", "ADSL",
                             "%d dosed subject(s) are left out of the safety "
                             "population" % len(nsaf & ex_subs),
                             "These subjects have dosing in EX but SAFFL is not "
                             "Y. Every safety table is missing them unless the "
                             "SAP says why.",
                             "SAFFL not Y but dosed in EX: %s."
                             % _examples(nsaf & ex_subs),
                             output="ADSL / SAFFL, EX", severity="Critical"))

    # first dose date against EX
    if adsl is not None and "TRTSDT" in adsl.columns and "EX" in st.sdtm:
        ex = _df(st.sdtm["EX"])
        if "EXSTDTC" in ex.columns:
            first = pd.to_datetime(ex["EXSTDTC"].astype(str).str[:10],
                                   errors="coerce").groupby(ex["USUBJID"]).min()
            tr = adsl.drop_duplicates("USUBJID").set_index("USUBJID")["TRTSDT"]
            trd = pd.to_datetime(tr, errors="coerce")
            if pd.api.types.is_numeric_dtype(tr):
                trd = pd.to_datetime("1960-01-01") + pd.to_timedelta(tr, unit="D")
            j = pd.DataFrame({"adsl": trd, "ex": first}).dropna()
            bad = j[j.adsl != j.ex]
            if len(bad):
                s = bad.index[0]
                out.append(_flag("adam_trtsdt_vs_ex", "ADaM", "ADSL",
                                 "TRTSDT differs from the first EXSTDTC for %d "
                                 "subject(s)" % len(bad),
                                 "TRTSDT is the first dose date. Treatment-"
                                 "emergent flags and study days built on it are "
                                 "shifted for these subjects.",
                                 "%d subject(s). First: %s TRTSDT=%s, first "
                                 "EXSTDTC=%s." % (len(bad), s,
                                                  bad.loc[s, "adsl"].date(),
                                                  bad.loc[s, "ex"].date()),
                                 output="ADSL / TRTSDT, EX"))

    # BASE and CHG re-derived
    for ds, d in _bds(st.adam).items():
        df = _df(d)
        if not {"USUBJID", "PARAMCD", "BASE"} <= set(df.columns):
            continue
        keys = ["USUBJID", "PARAMCD"] + [k for k in ("APERIOD",) if k in df.columns]
        base = pd.to_numeric(df["BASE"], errors="coerce")
        n_base = base.groupby([df[k] for k in keys]).nunique()
        bad = n_base[n_base > 1]
        if len(bad):
            first = bad.index[0]
            out.append(_flag("adam_base_constant", "ADaM", ds,
                             "BASE changes within subject and parameter in %s "
                             "for %d group(s)" % (ds, len(bad)),
                             "BASE is one value per subject and parameter. "
                             "When it changes the change-from-baseline values "
                             "are measured from different starting points.",
                             "%s: %d group(s). First: %s."
                             % (ds, len(bad), " / ".join(str(x) for x in first)),
                             output="%s / BASE" % ds))
        if {"AVAL", "CHG"} <= set(df.columns):
            aval = pd.to_numeric(df["AVAL"], errors="coerce")
            chg = pd.to_numeric(df["CHG"], errors="coerce")
            ok = aval.notna() & base.notna() & chg.notna()
            wrong = df[ok & ((aval - base - chg).abs() > 1e-6)]
            if len(wrong):
                r = wrong.iloc[0]
                out.append(_flag("adam_chg", "ADaM", ds,
                                 "CHG is not AVAL minus BASE on %d record(s) of "
                                 "%s" % (len(wrong), ds),
                                 "Change from baseline must equal AVAL minus "
                                 "BASE. Every change summary built on these "
                                 "records is wrong.",
                                 "%s: %d record(s). First: %s %s AVAL=%s "
                                 "BASE=%s CHG=%s." % (ds, len(wrong),
                                                      r["USUBJID"], r["PARAMCD"],
                                                      r["AVAL"], r["BASE"],
                                                      r["CHG"]),
                                 output="%s / CHG" % ds, severity="Critical"))

    # ADAE against AE
    if "ADAE" in st.adam and "AE" in st.sdtm:
        n_a, n_s = len(_df(st.adam["ADAE"])), len(_df(st.sdtm["AE"]))
        if n_a != n_s:
            out.append(_flag("adam_adae_vs_ae", "ADaM", "ADAE",
                             "ADAE has %d records and AE has %d" % (n_a, n_s),
                             "ADAE is normally one record per AE record. A "
                             "difference means events were added or lost.",
                             "ADAE %d records, AE %d records." % (n_a, n_s),
                             output="ADAE, AE",
                             confidence="candidate" if n_a > n_s else "certain"))
    return out


# ===========================================================================
# Raw data
# ===========================================================================
def raw_checks(st):
    out = []
    dm = _df(st.sdtm["DM"]) if "DM" in st.sdtm else None
    dm_ids = set()
    if dm is not None:
        for c in ("USUBJID", "SUBJID"):
            if c in dm.columns:
                dm_ids |= set(dm[c].dropna().astype(str))

    def in_dm(i):
        return i in dm_ids or any(u.endswith("-" + i) for u in dm_ids)

    for name, d in st.raw.items():
        df = _df(d)
        sc = _subject_col(df)
        dom = _domain_of(name)
        area_ds = dom if dom in ("AE", "LB", "VS", "EG", "EX", "DM", "PC", "CM") \
            else name

        if sc:
            blank = df[sc].isna() | (df[sc].astype(str).str.strip() == "")
            if blank.any():
                out.append(_flag("raw_blank_subject", "Raw Data", area_ds,
                                 "%d record(s) in %s have no subject number"
                                 % (int(blank.sum()), name),
                                 "A record without a subject cannot be mapped to "
                                 "SDTM and is lost.",
                                 "%s: %d of %d records have %s blank."
                                 % (name, int(blank.sum()), len(df), sc),
                                 output="%s / %s" % (name, sc)))

        extra = df[df.duplicated()]
        if len(extra):
            out.append(_flag("raw_duplicates", "Raw Data", area_ds,
                             "%s holds %d extra copy(ies) of a record"
                             % (name, len(extra)),
                             "Identical rows are usually a double export or a "
                             "double entry. Mapped as they are, they double "
                             "count in SDTM.",
                             "%s: %d record(s) repeat an earlier record exactly. "
                             "Subjects: %s." % (name, len(extra), _examples(
                                 set(extra[sc].astype(str))) if sc else "n/a"),
                             output=name))

        # dates that will not convert
        for c in df.columns:
            if not re.search(r"(DAT|DATE|DTC|DT)$", c.upper()):
                continue
            vals = df[c].dropna().astype(str).str.strip()
            vals = vals[vals != ""]
            if vals.empty:
                continue
            parsed = pd.to_datetime(vals, errors="coerce", format="mixed",
                                    dayfirst=False)
            bad = vals[parsed.isna()]
            if len(bad):
                out.append(_flag("raw_bad_dates", "Raw Data", area_ds,
                                 "%d %s value(s) in %s are not valid dates"
                                 % (len(bad), c, name),
                                 "These cannot be converted to ISO 8601 as they "
                                 "are. Partial dates need an imputation rule in "
                                 "the spec, and impossible dates need a query to "
                                 "the site.",
                                 "%s: %d of %d values. Examples: %s."
                                 % (name, len(bad), len(vals),
                                    _examples(set(bad), 4)),
                                 output="%s / %s" % (name, c)))

        # numbers stored with text in them
        for c in df.columns:
            if c == sc or not _is_text(df[c]):
                continue
            vals = df[c].dropna().astype(str).str.strip()
            vals = vals[vals != ""]
            if len(vals) < 5:
                continue
            is_num = vals.str.match(NUM_RE)
            if 0.8 <= is_num.mean() < 1:
                bad = vals[~is_num]
                out.append(_flag("raw_text_in_numbers", "Raw Data", area_ds,
                                 "%d value(s) in the numeric field %s of %s are "
                                 "text" % (len(bad), c, name),
                                 "Most values are numbers, these are not. They "
                                 "will be empty in --STRESN unless the mapping "
                                 "handles them, for example a below-limit rule.",
                                 "%s: %d of %d values. Examples: %s."
                                 % (name, len(bad), len(vals),
                                    _examples(set(bad), 4)),
                                 output="%s / %s" % (name, c),
                                 severity="Minor", confidence="candidate"))

        if dm is None or not sc:
            continue
        ids = set(df[sc].dropna().astype(str).str.strip()) - {""}
        lost = {i for i in ids if not in_dm(i)}
        if lost:
            out.append(_flag("raw_subject_not_in_sdtm", "Raw Data", area_ds,
                             "%d subject(s) in raw %s are not in SDTM DM"
                             % (len(lost), name),
                             "These subjects have raw data but no DM record. "
                             "If they are screen failures that is expected and "
                             "should be documented. Otherwise they were lost in "
                             "mapping.",
                             "%s: %s." % (name, _examples(lost)),
                             output="%s, DM" % name))

        # raw domain to SDTM domain record counts
        if dom in st.sdtm and dom != "DM":
            s_df = _df(st.sdtm[dom])
            n_raw, n_sdtm = len(df.drop_duplicates()), len(s_df)
            if n_raw != n_sdtm:
                per_raw = df.drop_duplicates()[sc].astype(str).value_counts()
                per_sdtm = s_df["USUBJID"].astype(str).str.split("-").str[-1] \
                    .value_counts() if "USUBJID" in s_df.columns else pd.Series()
                diff = [s for s in per_raw.index
                        if per_raw[s] != per_sdtm.get(s.split("-")[-1], 0)]
                out.append(_flag("raw_vs_sdtm_count", "Raw Data", dom,
                                 "Raw %s has %d records and SDTM %s has %d"
                                 % (name, n_raw, dom, n_sdtm),
                                 "After duplicates are removed every raw record "
                                 "should map to one SDTM record. %s"
                                 % ("Records were lost in mapping."
                                    if n_raw > n_sdtm else
                                    "SDTM has more, which can be correct if "
                                    "records were split, but needs a reason."),
                                 "%s %d records, %s %d records. Subjects whose "
                                 "counts differ: %s."
                                 % (name, n_raw, dom, n_sdtm,
                                    _examples(diff) or "none found by subject"),
                                 output="%s, %s" % (name, dom),
                                 confidence="certain" if n_raw > n_sdtm
                                 else "candidate"))

    if dm is not None and st.raw:
        raw_ids = set()
        for d in st.raw.values():
            sc = _subject_col(_df(d))
            if sc:
                raw_ids |= set(_df(d)[sc].dropna().astype(str).str.strip())
        if raw_ids and "USUBJID" in dm.columns:
            no_raw = [u for u in dm["USUBJID"].dropna().astype(str)
                      if u not in raw_ids and u.split("-")[-1] not in raw_ids
                      and ("SUBJID" not in dm.columns
                           or str(dm.loc[dm.USUBJID == u, "SUBJID"].iloc[0])
                           not in raw_ids)]
            if no_raw:
                out.append(_flag("sdtm_subject_not_in_raw", "Raw Data", "DM",
                                 "%d subject(s) in SDTM DM have no raw data"
                                 % len(no_raw),
                                 "An SDTM subject must trace back to collected "
                                 "data. These have none in the raw files "
                                 "supplied.",
                                 "DM subjects not found in raw: %s."
                                 % _examples(no_raw), output="DM"))
    return out


# ===========================================================================
# Specs (lands on the SDTM or ADaM tab)
# ===========================================================================
def spec_checks(st):
    out = []
    if st.specs is None or st.specs.empty:
        return out
    data = dict(st.sdtm)
    data.update(st.adam)
    for ds, grp in st.specs.groupby("Dataset"):
        layer = "ADaM" if ds.startswith("AD") else "SDTM"
        src = grp["File"].iloc[0]
        if ds not in data:
            if (layer == "ADaM" and st.adam) or (layer == "SDTM" and st.sdtm):
                out.append(_flag("spec_dataset_missing", layer, ds,
                                 "%s is in the spec but was not delivered" % ds,
                                 "The spec promises this dataset. It is not in "
                                 "the %s folder." % layer,
                                 "%s lists %d variable(s) for %s."
                                 % (src, len(grp), ds), output="%s, %s" % (ds, src)))
            continue
        df, labels = _df(data[ds]), data[ds].get("labels", {})
        spec_vars = list(grp["Variable"])
        missing = [v for v in spec_vars if v not in df.columns]
        extra = [c for c in df.columns if c not in spec_vars]
        if missing:
            out.append(_flag("spec_variable_missing", layer, ds,
                             "%d variable(s) in the %s spec are missing from the "
                             "dataset" % (len(missing), ds),
                             "The spec says these variables are in the dataset. "
                             "They are not, so the define.xml will describe "
                             "variables that do not exist.",
                             "%s: %s." % (ds, _examples(missing)),
                             output="%s, %s" % (ds, src)))
        if extra:
            out.append(_flag("spec_variable_extra", layer, ds,
                             "%d variable(s) in %s are not in the spec"
                             % (len(extra), ds),
                             "Variables in the data with no spec entry have no "
                             "documented derivation.",
                             "%s: %s." % (ds, _examples(extra)),
                             output="%s, %s" % (ds, src), severity="Minor"))
        diffs = []
        for _, r in grp.iterrows():
            v, lab = r["Variable"], str(r["Label"]).strip()
            if v in labels and lab and lab.lower() != "nan" \
                    and lab.lower() != str(labels[v]).strip().lower():
                diffs.append("%s spec '%s', data '%s'" % (v, lab, labels[v]))
        if diffs:
            out.append(_flag("spec_label_mismatch", layer, ds,
                             "%d label(s) in %s differ from the spec"
                             % (len(diffs), ds),
                             "The define.xml takes labels from the spec. The "
                             "data will not match it.",
                             "%s: %s." % (ds, "; ".join(diffs[:4])),
                             output="%s, %s" % (ds, src), severity="Minor"))
        tdiffs = []
        for _, r in grp.iterrows():
            v, t = r["Variable"], str(r["Type"]).lower()
            if v not in df.columns or t in ("", "nan"):
                continue
            want_num = t.startswith(("num", "int", "float"))
            is_num = pd.api.types.is_numeric_dtype(df[v])
            if want_num != is_num:
                tdiffs.append("%s spec %s, data %s" % (v, t, "numeric"
                                                       if is_num else "text"))
        if tdiffs:
            out.append(_flag("spec_type_mismatch", layer, ds,
                             "%d variable type(s) in %s differ from the spec"
                             % (len(tdiffs), ds),
                             "A numeric variable stored as text, or the other "
                             "way, breaks merges and sorts downstream.",
                             "%s: %s." % (ds, "; ".join(tdiffs[:4])),
                             output="%s, %s" % (ds, src)))
    return out


# ===========================================================================
# SAP
# ===========================================================================
POPULATIONS = [
    (r"safety", "SAFFL"), (r"pharmacokinetic|pk", "PKFL"),
    (r"pharmacodynamic|pd", "PDFL"), (r"intent[- ]to[- ]treat|itt", "ITTFL"),
    (r"full analysis", "FASFL"), (r"per[- ]protocol", "PPROTFL"),
    (r"randomi[sz]ed", "RANDFL"), (r"enrolled", "ENRLFL"),
]


def _trt_codes(values):
    return {str(v).strip().upper() for v in values if str(v).strip()}


def _adam_treatments(st):
    """Subjects per actual treatment, across every ADaM dataset with TRTA."""
    per = {}
    for ds, d in st.adam.items():
        df = _df(d)
        if "TRTA" not in df.columns or "USUBJID" not in df.columns:
            continue
        for t, g in df.groupby(df["TRTA"].astype(str).str.upper()):
            per.setdefault(t, set()).update(g["USUBJID"].astype(str))
    return per


def sap_checks(st):
    out = []
    text = st.sap_text or ""
    adsl = _df(st.adam["ADSL"]) if "ADSL" in st.adam else None
    where = ", ".join(st.sap_files) or "spec.txt"

    if text and adsl is not None:
        for pat, flag in POPULATIONS:
            m = re.search(r"\b(%s)\s+(population|analysis set|set)\b" % pat,
                          text, re.I)
            if m and flag not in adsl.columns:
                out.append(_flag("sap_population_flag", "SAP", "ADSL",
                                 "The SAP defines the %s but ADSL has no %s"
                                 % (m.group(0).strip(), flag),
                                 "Every population named in the SAP needs its "
                                 "flag in ADSL, or the outputs for that "
                                 "population cannot be traced to the data.",
                                 "%s mentions '%s'. ADSL variables: %s."
                                 % (where, m.group(0).strip(),
                                    ", ".join(c for c in adsl.columns
                                              if c.endswith("FL")) or "no flags"),
                                 output="ADSL / %s, %s" % (flag, where)))

    pop_n = st.rules.get("population_n")
    if pop_n and adsl is not None and "SAFFL" in adsl.columns:
        n = int((adsl.drop_duplicates("USUBJID").SAFFL.astype(str) == "Y").sum())
        if str(n) != pop_n.strip():
            out.append(_flag("sap_population_n", "SAP", "ADSL",
                             "The SAP population is %s subjects but ADSL has %d "
                             "with SAFFL=Y" % (pop_n, n),
                             "Every denominator in the safety tables comes from "
                             "this count. Either the flag is wrong or the SAP "
                             "rule copied into spec.txt is out of date.",
                             "spec.txt population_n = %s. ADSL SAFFL=Y: %d "
                             "subjects." % (pop_n, n),
                             output="ADSL / SAFFL", severity="Critical"))

    trts = st.rules.get("treatments")
    per = _adam_treatments(st)
    if trts and per:
        want = _trt_codes(trts.split(","))
        have = set(per)
        if want - have or have - want:
            out.append(_flag("sap_treatments", "SAP", "ADSL",
                             "Treatments in ADaM do not match the SAP",
                             "The SAP lists the treatments to be compared. The "
                             "ADaM data holds a different set, so at least one "
                             "comparison cannot be produced as planned.",
                             "SAP: %s. ADaM TRTA: %s.%s%s"
                             % (", ".join(sorted(want)), ", ".join(sorted(have)),
                                " Missing from ADaM: %s." % ", ".join(
                                    sorted(want - have)) if want - have else "",
                                " Not in SAP: %s." % ", ".join(
                                    sorted(have - want)) if have - want else ""),
                             output="ADaM / TRTA"))

    params = st.rules.get("pk_parameters")
    if params:
        want = _trt_codes(params.split(","))
        have = set()
        for ds, d in _bds(st.adam).items():
            if ds in ("ADPP",) or ds.startswith("ADPP"):
                have |= _trt_codes(_df(d)["PARAMCD"].dropna().unique())
        if have and want - have:
            out.append(_flag("sap_pk_parameters", "SAP", "ADPP",
                             "%d PK parameter(s) named in the SAP are not in "
                             "ADPP" % len(want - have),
                             "The SAP promises these parameters. Without them in "
                             "ADPP the parameter tables cannot show them.",
                             "SAP: %s. ADPP PARAMCD: %s. Missing: %s."
                             % (", ".join(sorted(want)), ", ".join(sorted(have)),
                                ", ".join(sorted(want - have))),
                             output="ADPP / PARAMCD"))

    if text and st.shells:
        sap_ids = {output_id(l) for l in text.splitlines()
                   if re.match(r"\s*(Table|Listing|Figure)\s+\d", l, re.I)}
        sap_ids.discard(None)
        shell_ids = {s["id"] for s in st.shells if s["id"]}
        gone = sap_ids - shell_ids
        if gone:
            out.append(_flag("sap_output_not_in_shells", "SAP", "SAP",
                             "%d output(s) planned in the SAP have no mock shell"
                             % len(gone),
                             "The SAP lists these outputs. No shell exists for "
                             "them, so nobody has agreed how they look.",
                             "In SAP, not in shells: %s." % _examples(gone),
                             output=where, severity="Minor"))
    return out


# ===========================================================================
# Mock shells
# ===========================================================================
def shell_checks(st):
    out = []
    if not st.shells or st.package is None:
        return out
    delivered = {}
    for o in st.package.outputs:
        for t in o.titles:
            oid = output_id(t)
            if oid:
                delivered.setdefault(oid, []).append(o)
                break
    shell_ids = {s["id"] for s in st.shells if s["id"]}

    # shells with no file name are matched on their number
    missing = sorted({s["id"] for s in st.shells
                      if s["id"] and not s["file"] and s["id"] not in delivered})
    if missing:
        out.append(_flag("shell_not_delivered", "Mock Shells", "TLF",
                         "%d output(s) in the mock shells were not delivered"
                         % len(missing),
                         "The shells promise these outputs. Nothing in the TLF "
                         "folder carries their number.",
                         "Not delivered: %s." % _examples(missing),
                         output="mock shells", severity="Critical"))

    extra = sorted(set(delivered) - shell_ids)
    if extra:
        files = [o.filename for i in extra for o in delivered[i]]
        out.append(_flag("shell_extra_output", "Mock Shells", "TLF",
                         "%d delivered output(s) have no mock shell"
                         % len(files),
                         "These outputs were delivered but no shell describes "
                         "them. Either a shell is missing or the number on the "
                         "output is wrong.",
                         "Numbers with no shell: %s. Files: %s."
                         % (", ".join(extra), _examples(files, 4)),
                         output=", ".join(files[:6]), severity="Minor"))

    diffs = []
    for s in st.shells:
        if not s["title"] or s["id"] not in delivered:
            continue
        want = re.sub(r"\W+", " ", s["title"]).strip().lower()
        for o in delivered[s["id"]]:
            got = " ".join(o.titles).lower()
            got = re.sub(r"\W+", " ", got)
            if want and want not in got:
                diffs.append((o.filename, s["id"], s["title"],
                              o.titles[-1] if o.titles else ""))
    if diffs:
        out.append(_flag("shell_title_differs", "Mock Shells", "TLF",
                         "%d output title(s) differ from the mock shell"
                         % len(diffs),
                         "The title on the output does not carry the wording "
                         "the shell agreed. Reviewers and the CSR cross-reference "
                         "by title.",
                         "; ".join("%s: shell '%s', output '%s'" % (f, t, g)
                                   for f, _, t, g in diffs[:4]) + ".",
                         output=", ".join(sorted({d[0] for d in diffs})),
                         severity="Minor"))
    return out


# ===========================================================================
# TLF against ADaM
# ===========================================================================
_TRT_HEAD = re.compile(r"\b(T\d+|R|Test|Reference|Placebo)\b", re.I)
_N_TITLE = re.compile(r"\b(?:Treatment\s+)?(T\d+|R)\s*\(N\s*=\s*(\d+)\)", re.I)
_POP_NOTE = re.compile(r"(Safety|PK|Pharmacokinetic|PD|Pharmacodynamic)"
                       r"\s+Population\s+comprises\s+(\d+)\s+subjects", re.I)
_POP_FLAG = {"safety": "SAFFL", "pk": "PKFL", "pharmacokinetic": "PKFL",
             "pd": "PDFL", "pharmacodynamic": "PDFL"}


def tlf_vs_adam(st):
    out = []
    if st.package is None or not st.adam:
        return out
    per = {t: len(s) for t, s in _adam_treatments(st).items()}
    adsl = _df(st.adam["ADSL"]) if "ADSL" in st.adam else None

    over = []
    for o in st.package.tables():
        for ci, head in enumerate(o.headers):
            m = _TRT_HEAD.search(head)
            if not m or m.group(1).upper() not in per:
                continue
            trt = m.group(1).upper()
            # only count cells that are n, not means: an 'n' column or 'n' row
            is_n_col = head.strip().lower().startswith("n ")
            vals = []
            for r in o.rows:
                if len(r) <= ci or not r[ci]:
                    continue
                row_is_n = bool(re.search(r"(^|\s)n$", str(r[0]).strip()))
                if not (is_n_col or row_is_n):
                    continue
                v = re.match(r"^\s*(\d+)\s*$", str(r[ci]))
                if v:
                    vals.append(int(v.group(1)))
            if vals and max(vals) > per[trt]:
                over.append((o.filename, trt, max(vals), per[trt]))
    if over:
        out.append(_flag("tlf_n_above_adam", "TLF", "ADaM",
                         "%d output(s) report more subjects than ADaM holds for "
                         "the treatment" % len({x[0] for x in over}),
                         "An output cannot count more subjects than the analysis "
                         "data contains. Either the output was run on old data "
                         "or the ADaM was changed after the output.",
                         "; ".join("%s: %s n=%d, ADaM has %d subjects"
                                   % x for x in over[:12]) + ".",
                         output=", ".join(sorted({x[0] for x in over})),
                         severity="Critical"))

    for fig in st.package.figures():
        clash = []
        for trt, n in _N_TITLE.findall(" ".join(fig.titles)):
            t = trt.upper()
            if t in per and int(n) != per[t]:
                clash.append("%s N=%s, ADaM %d" % (t, n, per[t]))
        if clash:
            out.append(_flag("tlf_figure_n_vs_adam", "TLF", "ADaM",
                             "%s declares subject counts ADaM does not have"
                             % fig.filename,
                             "The N in the figure title should be the number "
                             "of subjects in the analysis data for each "
                             "treatment.",
                             "%s: %s." % (fig.filename, "; ".join(clash)),
                             output=fig.filename))

    if adsl is not None:
        for o in st.package.outputs:
            for note in o.footnotes:
                m = _POP_NOTE.search(note)
                if not m:
                    continue
                flag = _POP_FLAG.get(m.group(1).lower())
                if flag not in adsl.columns:
                    continue
                n = int((adsl.drop_duplicates("USUBJID")[flag].astype(str)
                         == "Y").sum())
                if n != int(m.group(2)):
                    out.append(_flag("tlf_population_note_vs_adsl", "TLF",
                                     "ADSL",
                                     "%s says the %s Population is %s subjects "
                                     "but ADSL has %d" % (o.filename,
                                                          m.group(1), m.group(2),
                                                          n),
                                     "The footnote states the population size. "
                                     "ADSL does not agree, so the footnote or "
                                     "the flag is wrong.",
                                     "%s footnote: '%s'. ADSL %s=Y: %d subjects."
                                     % (o.filename, note.strip(), flag, n),
                                     output=o.filename, severity="Critical"))
    return out


ALL_LAYER_CHECKS = [raw_checks, sdtm_checks, adam_checks, spec_checks,
                    cdisc_sdtm, cdisc_adam, sap_checks, shell_checks,
                    tlf_vs_adam]


def run_layer_checks(st):
    flags, log = [], []
    for check in ALL_LAYER_CHECKS:
        try:
            got = check(st)
        except Exception as exc:          # one broken check never stops a scan
            log.append("%s did not run: %s" % (check.__name__, exc))
            continue
        flags += got
    return flags, log
