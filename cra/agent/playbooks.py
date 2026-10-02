# -*- coding: utf-8 -*-
"""
The offline agent: what runs when there is no API key.

It uses the same tools as the AI agent, in a fixed order for each kind of
finding, and fills in SAS fixes and queries from templates written for that
check. Every step is logged the same way, so the screen looks the same.

It does not reason. It re-checks the evidence with the tools, records a
verdict (confirmed when code proved it, needs_person otherwise), and writes the
fix and the query a programmer would usually write. With a key, the AI agent
replaces this and writes them for the actual case.
"""
import re

from .loop import AgentRun, Step


def _ds_var(f):
    """First dataset and variable named in Output / File, e.g. 'ADVS / CHG'."""
    first = f.output_file.split(",")[0].strip()
    ds, _, var = first.partition("/")
    return ds.strip().upper(), var.strip().upper()


def _datasets_named(f, toolbox):
    names = re.findall(r"[A-Za-z_]+", f.output_file + " " + f.evidence)
    seen = []
    for n in names:
        u = n.upper()
        if u in toolbox.data and u not in seen:
            seen.append(u)
    return seen[:3]


def _do(toolbox, run, name, **args):
    out = toolbox.call(name, args)
    run.steps.append(Step(name, args, out))
    return out


# ---------------------------------------------------------------------------
# SAS fix templates. {ds} {var} {lib} are filled in.
# ---------------------------------------------------------------------------
SAS = {
    "adam_chg": """/* Re-derive change from baseline */
data adam.{ds};
  set adam.{ds};
  if nmiss(aval, base) = 0 then chg = aval - base;
  else chg = .;
run;""",
    "adam_base_constant": """/* One BASE per subject and parameter, from the baseline record */
proc sql;
  create table _base as
  select usubjid, paramcd, aval as base
  from adam.{ds} where ablfl = 'Y';
quit;
data adam.{ds};
  merge adam.{ds}(drop=base) _base;
  by usubjid paramcd;
  if nmiss(aval, base) = 0 then chg = aval - base;
run;""",
    "adam_saffl_no_dose": """/* SAFFL = Y only for subjects with at least one dose in EX */
proc sql;
  create table _dosed as
  select distinct usubjid from sdtm.ex where exdose > 0;
quit;
data adam.adsl;
  merge adam.adsl(in=a) _dosed(in=d);
  by usubjid;
  if a;
  saffl = ifc(d, 'Y', 'N');
run;""",
    "adam_trtsdt_vs_ex": """/* TRTSDT = first dose date from EX */
proc sql;
  create table _first as
  select usubjid, min(input(substr(exstdtc, 1, 10), yymmdd10.)) as trtsdt
         format=date9.
  from sdtm.ex where exdose > 0 group by usubjid;
quit;
data adam.adsl;
  merge adam.adsl(drop=trtsdt in=a) _first;
  by usubjid;
  if a;
run;""",
    "adam_adsl_vs_dm": """/* Take {var} straight from DM, never re-derive it */
data adam.adsl;
  merge adam.adsl(in=a drop={var}) sdtm.dm(keep=usubjid {var});
  by usubjid;
  if a;
run;""",
    "adam_subject_not_in_adsl": """/* Find the {ds} records with no ADSL subject */
proc sql;
  select distinct usubjid from adam.{ds}
  where usubjid not in (select usubjid from adam.adsl);
quit;
/* Then fix the source. Do not just drop them without a reason. */""",
    "adam_dm_not_in_adsl": """/* ADSL must start from DM */
data adam.adsl;
  merge sdtm.dm(in=d) adam.adsl;
  by usubjid;
  if d;
run;""",
    "sdtm_subject_not_in_dm": """/* Records in {ds} whose subject is not in DM */
proc sql;
  select usubjid, count(*) as n from sdtm.{ds}
  where usubjid not in (select usubjid from sdtm.dm)
  group by usubjid;
quit;
/* Usually a typo in the raw subject number, or a USUBJID built with a
   different study prefix. Fix it in the mapping, not in SDTM by hand. */""",
    "sdtm_study_day": """/* Study day: no day 0 */
data sdtm.{ds};
  merge sdtm.{ds}(in=a) sdtm.dm(keep=usubjid rfstdtc);
  by usubjid;
  if a;
  _d = input(substr({dtc}, 1, 10), ?? yymmdd10.);
  _r = input(substr(rfstdtc, 1, 10), ?? yymmdd10.);
  if nmiss(_d, _r) = 0 then {var} = _d - _r + (_d >= _r);
  drop _d _r rfstdtc;
run;""",
    "sdtm_stresn_missing": """/* Numeric standard result whenever STRESC is a number */
data sdtm.{ds};
  set sdtm.{ds};
  if missing({ds}stresn) then {ds}stresn = input({ds}stresc, ?? best32.);
run;""",
    "cdisc_ct": """/* Map to CDISC submission values */
proc format;
  value $ct_{var} (default=40)
    'Mild'='MILD' 'Moderate'='MODERATE' 'Severe'='SEVERE'
    'Male'='M' 'Female'='F';
run;
data sdtm.{ds};
  set sdtm.{ds};
  {var} = put(strip({var}), $ct_{var}.);
run;""",
    "cdisc_iso8601": """/* Convert to ISO 8601 (check the source format first) */
data sdtm.{ds};
  set sdtm.{ds};
  if index({var}, '/') then
    {var} = put(input({var}, ?? ddmmyy10.), yymmdd10.);
run;""",
    "cdisc_seq_unique": """/* Re-number --SEQ within subject */
proc sort data=sdtm.{ds}; by usubjid {ds}stdtc {ds}term; run;
data sdtm.{ds};
  set sdtm.{ds};
  by usubjid;
  if first.usubjid then {ds}seq = 0;
  {ds}seq + 1;
run;""",
    "cdisc_flag_values": """/* Flags take Y, N or blank only */
data adam.{ds};
  set adam.{ds};
  if upcase(substr({var}, 1, 1)) = 'Y' then {var} = 'Y';
  else if upcase(substr({var}, 1, 1)) = 'N' then {var} = 'N';
run;""",
    "cdisc_param_1to1": """/* One PARAM per PARAMCD */
proc format;
  value $param  /* fill from the spec */
    'CMAX' = 'Maximum Concentration';
run;
data adam.{ds};
  set adam.{ds};
  param = put(paramcd, $param.);
run;""",
    "cdisc_required": """/* Add the missing required variable(s) - derive from the spec */
data {ds};
  set {ds};
  length ageu $10;
  ageu = 'YEARS';   /* example for AGEU */
run;""",
    "raw_vs_sdtm_count": """/* Records per subject, raw against SDTM */
proc sql;
  create table _raw as select subjid, count(*) as n_raw
    from (select distinct * from raw.{rawds}) group by subjid;
  create table _sdtm as select scan(usubjid, -1, '-') as subjid,
    count(*) as n_sdtm from sdtm.{ds} group by calculated subjid;
  select * from _raw full join _sdtm on _raw.subjid = _sdtm.subjid
  where coalesce(n_raw, 0) ne coalesce(n_sdtm, 0);
quit;""",
    "tlf_n_above_adam": """/* Re-run the outputs on the current ADaM and compare the Ns */
proc sql;
  select trta, count(distinct usubjid) as n from adam.adpp group by trta;
quit;""",
}

FOOTNOTE = {
    "tlf_population_note_vs_adsl": "Note: The Safety Population comprises "
                                   "<N from ADSL> subjects.",
    "percent_without_denominator": "Note: Percentages are based on the number "
                                   "of subjects in the <population> "
                                   "(N=<n>).",
    "treatment_columns_present": "Note: Results are pooled across treatments "
                                 "as specified in SAP Section <x>.",
    "n_drops_without_footnote": "Note: n is the number of subjects with a "
                                "result at that visit.",
    "source_line_present": "Source: /prod/<study>/pgm/<program>.sas "
                           "version <x>  <run date>",
}

QUERY_TO = {"Raw Data": "site", "SDTM": "data_management",
            "ADaM": "programmer", "TLF": "programmer", "SAP": "sponsor",
            "CDISC Standards": "programmer", "Mock Shells": "sponsor"}
SITE_KINDS = {"raw_bad_dates", "raw_text_in_numbers", "raw_blank_subject",
              "raw_subject_not_in_sdtm", "sdtm_treated_no_ex"}


def _query(f, codes_text):
    to = "site" if f.found_by in SITE_KINDS else QUERY_TO.get(f.layer,
                                                             "programmer")
    if to == "site":
        text = ("Please review: %s. Details: %s Please confirm the correct "
                "value in the eCRF, or confirm the data is correct as entered."
                % (f.finding, codes_text))
    elif to == "sponsor":
        text = ("For your confirmation: %s. %s What we see: %s Please confirm "
                "how you would like this handled before final delivery."
                % (f.finding, f.what_is_wrong, codes_text))
    else:
        text = ("%s. %s Evidence: %s Please correct and re-run the affected "
                "datasets and outputs, or reply with the reason it is "
                "correct." % (f.finding, f.what_is_wrong, codes_text))
    return to, "%s: %s" % (f.layer, f.finding[:80]), text


def run_offline(f, toolbox, jobs=("investigate", "fix", "query")):
    """The offline agent on one finding."""
    run = AgentRun(engine="offline playbook")
    _do(toolbox, run, "finding", key=f.key)
    ds, var = _ds_var(f)
    datasets = _datasets_named(f, toolbox)

    # ---- investigate: re-check with the tools -----------------------------
    for d in datasets[:2]:
        _do(toolbox, run, "count", dataset=d)
    if ds in toolbox.data and var and var in toolbox.data[ds]["data"].columns:
        _do(toolbox, run, "values", dataset=ds, variable=var)
    if f.found_by in ("adam_saffl_no_dose", "adam_dosed_not_saffl") \
            and {"ADSL", "EX"} <= set(toolbox.data):
        _do(toolbox, run, "subjects_diff", a="ADSL", b="EX",
            where_a="SAFFL = 'Y'")
    if f.found_by in ("sdtm_subject_not_in_dm", "adam_subject_not_in_adsl",
                      "adam_dm_not_in_adsl", "adam_adsl_not_in_dm") \
            and len(datasets) >= 1:
        ref = "DM" if f.layer == "SDTM" or "DM" in datasets else "ADSL"
        other = next((d for d in datasets if d != ref), ds)
        if ref in toolbox.data and other in toolbox.data:
            _do(toolbox, run, "subjects_diff", a=other, b=ref)
    if f.found_by == "adam_chg" and ds in toolbox.data:
        _do(toolbox, run, "stats", dataset=ds, variable="CHG")
    if f.found_by.startswith("tlf_") and "ADPP" in toolbox.data:
        _do(toolbox, run, "count", dataset="ADPP", by="TRTA")
    rtf = re.search(r"[\w\-]+\.rtf", f.output_file)
    if rtf:
        _do(toolbox, run, "output", filename=rtf.group(0))
    if f.layer == "SAP":
        _do(toolbox, run, "search_docs", text=f.finding, where="sap")
    # has this come up in a past review?
    _do(toolbox, run, "search_docs", text=f.finding, where="library")

    codes = toolbox.mask.mask_text(f.evidence)
    if "investigate" in jobs:
        if f.confidence == "certain":
            verdict, reason = "confirmed", (
                "Proved by code and re-checked with the tools. %s"
                % f.evidence)
        else:
            verdict, reason = "needs_person", (
                "Code noticed this but cannot prove it is wrong. A person "
                "should decide. %s" % f.evidence)
        _do(toolbox, run, "set_verdict", key=f.key, verdict=verdict,
            reason=toolbox.mask.mask_text(reason))

    # ---- fix ---------------------------------------------------------------
    if "fix" in jobs:
        tmpl = SAS.get(f.found_by)
        if tmpl:
            raw = next((d for d in datasets if "RAW" in d), "<raw>")
            sas = tmpl.format(ds=ds.lower() or "<ds>",
                              var=(var or "<var>").lower(),
                              dtc=(var[:-2] + "DTC").lower() if var else "<dtc>",
                              rawds=raw.lower())
            _do(toolbox, run, "propose_fix", key=f.key, kind="sas", text=sas)
        if f.found_by in FOOTNOTE:
            _do(toolbox, run, "propose_fix", key=f.key, kind="footnote",
                text=FOOTNOTE[f.found_by])
        if f.found_by.startswith("spec_"):
            _do(toolbox, run, "propose_fix", key=f.key, kind="spec",
                text="Update the spec or the dataset so they agree: %s"
                     % codes)
        if f.found_by.startswith("shell_"):
            _do(toolbox, run, "propose_fix", key=f.key, kind="title",
                text="Align the output number and title with the agreed mock "
                     "shell, or update the shell with sponsor agreement. %s"
                     % codes)
        if not tmpl and f.found_by not in FOOTNOTE and \
                not f.found_by.startswith(("spec_", "shell_")):
            _do(toolbox, run, "propose_fix", key=f.key, kind="process",
                text="Correct the program behind %s, re-run, and re-check: %s"
                     % (f.output_file, f.what_is_wrong))

    # ---- query -------------------------------------------------------------
    if "query" in jobs:
        to, subj, text = _query(f, codes)
        _do(toolbox, run, "draft_query", key=f.key, to=to, subject=subj,
            text=text)

    run.answer = toolbox.mask.unmask_text(
        "Offline agent (no API key). %s %s"
        % ("Confirmed: code proved it." if f.confidence == "certain"
           else "Needs a person: code could not prove it.",
           "Fix and query drafted from the template for this check."
           if {"fix", "query"} & set(jobs) else ""))
    return run
