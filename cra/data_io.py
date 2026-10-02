"""
Reading study data.

One job: open every .xpt file in a study folder and hand back plain pandas tables,
plus the variable labels that came with them.
"""
import os
import glob
import pandas as pd
import pyreadstat


def read_dataset(path):
    """
    Read one .xpt file.
    Returns (table, labels) where labels is {variable name: label text}.
    """
    df, meta = pyreadstat.read_xport(path)
    labels = dict(zip(meta.column_names, meta.column_labels))
    labels = {k: (v if v else k) for k, v in labels.items()}
    # SAS text often carries trailing spaces. Strip them once, here.
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.strip().replace({"nan": None})
    return df, labels


def read_study(folder):
    """
    Read every .xpt file in a folder.
    Returns {dataset name (upper case): {"data": table, "labels": {...}, "path": ...}}
    """
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"No such folder: {folder}")
    out = {}
    for path in sorted(glob.glob(os.path.join(folder, "*.xpt"))):
        name = os.path.splitext(os.path.basename(path))[0].upper()
        df, labels = read_dataset(path)
        out[name] = {"data": df, "labels": labels, "path": path}
    if not out:
        raise FileNotFoundError(f"No .xpt files found in {folder}")
    return out


def study_name(folder):
    """Use the folder name as the study name."""
    return os.path.basename(os.path.normpath(folder))
