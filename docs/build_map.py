# -*- coding: utf-8 -*-
"""
Maps every one of the 38 real AQ109109 findings to the check that should catch
it, and to the engine that can do it. This is the specification the checks are
written from, so it lives in the repo.

engine:
  code   - plain code can find it on its own
  code+  - code finds the candidate, the model writes it up
  model  - only judgement can spot it (needs the SAP or the shells)
  human  - needs knowledge the package does not contain
"""
import pandas as pd

M = {
 2:  ("missing_assessment",        "code",  "checks_data.missing_visit_for_some_subjects"),
 3:  ("records_in_one_output_only","code",  "checks_across.records_in_one_output_only"),
 4:  ("sap_rule_not_followed",     "model", "checks_sap.exclusion_rule_vs_sap"),
 5:  ("endpoint_not_assessed",     "model", "checks_sap.every_comparison_in_sap_present"),
 6:  ("records_dropped_silently",  "code",  "checks_across.n_consistent_across_outputs"),
 7:  ("listing_contradicts_table", "code",  "checks_across.exclusion_applied_consistently"),
 8:  ("wrong_study_or_protocol",   "code",  "checks_across.study_and_protocol_consistent"),
 9:  ("title_vs_unit_of_count",    "code+", "checks_output.title_vs_unit_of_count"),
 10: ("baseline_rule_vs_sap",      "model", "checks_sap.baseline_definition"),
 11: ("denominator_wrong",         "code",  "checks_output.denominator_vs_population"),
 12: ("no_program_provenance",     "code",  "checks_output.source_line_present"),
 13: ("no_source_line",            "code",  "checks_output.source_line_present"),
 14: ("missing_key_variable",      "code",  "checks_data.missing_key_variable"),
 15: ("predose_counted_postdose",  "code",  "checks_data.predose_finding_recounted"),
 16: ("title_range_vs_values",     "code",  "checks_output.title_range_vs_values"),
 17: ("duplicate_title",           "code",  "checks_across.duplicate_titles"),
 18: ("count_dips_and_returns",    "code",  "checks_output.counts_dip_and_return"),
 19: ("output_missing_vs_shells",  "code",  "checks_shells.outputs_present_vs_shells"),
 20: ("exclusion_not_applied",     "code",  "checks_across.exclusion_applied_consistently"),
 21: ("unpaired_crossover",        "code",  "checks_output.paired_comparison_same_n"),
 22: ("figure_n_vs_table_n",       "code",  "checks_across.n_consistent_across_outputs"),
 23: ("rule_stated_not_applied",   "code+", "checks_output.rule_stated_not_applied"),
 24: ("too_many_significant_digits","code", "checks_output.decimals_vs_spec"),
 25: ("no_denominator",            "code",  "checks_output.percent_without_denominator"),
 26: ("no_treatment_split",        "code+", "checks_output.treatment_columns_present"),
 27: ("contradictory_fields",      "code",  "checks_data.contradictory_fields"),
 28: ("undefined_code",            "code",  "checks_output.undefined_code_in_column"),
 29: ("category_not_defined",      "code+", "checks_output.percent_without_denominator"),
 30: ("no_footer",                 "code",  "checks_output.source_line_present"),
 31: ("integer_only_column",       "code",  "checks_output.integer_only_column"),
 32: ("value_contradicts_value",   "code",  "checks_data.derived_value_disagrees"),
 33: ("wrong_records_per_unit",    "code",  "checks_data.records_per_unit"),
 34: ("timepoint_never_collected", "code",  "checks_data.missing_visit_for_some_subjects"),
 35: ("bare_program_name",         "code",  "checks_output.program_has_path_and_version"),
 36: ("footnote_wrong_domain",     "code+", "checks_output.footnote_matches_domain"),
 37: ("n_drops_no_footnote",       "code",  "checks_output.counts_dip_and_return"),
 38: ("censored_values_dropped",   "code",  "checks_data.censored_values_dropped"),
 39: ("rounding_erases_result",    "code",  "checks_output.decimals_vs_spec"),
}

src = pd.read_pickle("/home/claude/find/findings.pkl")
rows = []
for _, r in src.iterrows():
    n = int(r["Row in source sheet"])
    family, engine, check = M[n]
    rows.append({"Source row": n, "Area": r["Area"], "Finding": r["Finding"],
                 "Check family": family, "Engine": engine, "Check": check})

df = pd.DataFrame(rows)
df.to_csv("findings_map.csv", index=False)

print(df["Engine"].value_counts().to_string())
print()
print("distinct checks needed:", df["Check"].nunique())
print(df.groupby("Check").size().sort_values(ascending=False).to_string())
