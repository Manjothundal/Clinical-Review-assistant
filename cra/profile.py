"""
Building the profile.

The profile is a short summary of every variable in every dataset:
how many records, how many different values, what those values are, and so on.

This matters for two reasons:
  1. All the simple checks read the profile instead of the raw records, so they are fast.
  2. The profile is the ONLY thing the AI is ever sent. Never the records themselves.
"""
import numpy as np
import pandas as pd

# If a variable has more distinct values than this, we do not list them all.
MAX_VALUES_LISTED = 12

# Identifier variables. We record HOW MANY there are and never list them,
# because a list of subject identifiers is not something the AI needs and
# it would put patient-level detail into the prompt.
ID_VARS = {"USUBJID", "SUBJID", "SPDEVID", "REFID", "AESPID", "EXSPID",
           "LBSPID", "VSSPID", "CMSPID", "SITEID", "INVID", "INVNAM"}


def profile_variable(series, label, name=""):
    """Summarise one column. Identifier columns are counted but never listed."""
    n = len(series)
    non_null = series.dropna()
    n_missing = n - len(non_null)
    is_num = pd.api.types.is_numeric_dtype(series)

    info = {
        "label": label,
        "type": "number" if is_num else "text",
        "n_records": int(n),
        "n_missing": int(n_missing),
        "pct_missing": round(100 * n_missing / n, 1) if n else 0.0,
        "n_distinct": int(non_null.nunique()),
    }

    if is_num and len(non_null):
        info.update({
            "min": float(non_null.min()), "max": float(non_null.max()),
            "mean": round(float(non_null.mean()), 4),
            "median": round(float(non_null.median()), 4),
        })
    if name in ID_VARS:
        info["note"] = "identifier - values deliberately not listed"
        return info

    if not is_num and len(non_null):
        counts = non_null.value_counts()
        if len(counts) <= MAX_VALUES_LISTED:
            info["values"] = {str(k): int(v) for k, v in counts.items()}
        else:
            info["top_values"] = {str(k): int(v) for k, v in counts.head(6).items()}
    return info


def profile_dataset(df, labels):
    """Summarise every column in one dataset."""
    return {
        "n_records": int(len(df)),
        "n_variables": int(len(df.columns)),
        "variables": {c: profile_variable(df[c], labels.get(c, c), c)
                      for c in df.columns},
    }


def profile_study(datasets):
    """Summarise a whole study. `datasets` is what read_study() returned."""
    return {name: profile_dataset(d["data"], d["labels"]) for name, d in datasets.items()}


def profile_to_text(study_profile, only_datasets=None):
    """
    Turn the profile into plain text, which is what gets sent to the AI.
    Looks like a data listing summary a person would read.
    """
    lines = []
    for ds, p in study_profile.items():
        if only_datasets and ds not in only_datasets:
            continue
        lines.append(f"=== {ds}  ({p['n_records']} records, {p['n_variables']} variables)")
        for var, v in p["variables"].items():
            head = f"  {var:<10} {v['label'][:44]:<46} {v['type']}"
            lines.append(head)
            bits = [f"{v['n_distinct']} distinct"]
            if v["n_missing"]:
                bits.append(f"{v['n_missing']} missing ({v['pct_missing']}%)")
            if "values" in v:
                vals = ", ".join(f"'{k}' ({n})" for k, n in v["values"].items())
                bits.append("values: " + vals)
            elif "top_values" in v:
                vals = ", ".join(f"'{k}' ({n})" for k, n in v["top_values"].items())
                bits.append("most common: " + vals)
            if "note" in v:
                bits.append(v["note"])
            if "min" in v:
                bits.append(f"min {v['min']}, max {v['max']}, mean {v['mean']}")
            lines.append("             " + "  |  ".join(bits))
        lines.append("")
    return "\n".join(lines)
