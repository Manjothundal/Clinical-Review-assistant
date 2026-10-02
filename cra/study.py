# -*- coding: utf-8 -*-
"""
One study, everything in it.

A study is one folder with a sub-folder for each kind of input:

    studies/DEMO-BE-101/
        raw/      raw EDC extracts      .csv .xpt .sas7bdat
        sdtm/     SDTM datasets         .xpt .sas7bdat .csv
        adam/     ADaM datasets         .xpt .sas7bdat .csv
        tlf/      delivered outputs     .rtf
        tlf_old/  the previous delivery .rtf, compared against tlf/
        sap/      the SAP               .docx .pdf .txt, plus spec.txt (rules)
        shells/   the mock shells       .docx .pdf .rtf .txt, or shells.txt
        specs/    SDTM / ADaM specs     .xlsx .csv

Every folder is optional. A check that needs a missing folder does not run, and
the run log says so.

classify() decides which folder an uploaded file belongs in, so the screen can
offer one upload box for everything.
"""
import os
import re
import glob
import zipfile
import shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

KINDS = ["raw", "sdtm", "adam", "tlf", "tlf_old", "sap", "shells", "specs"]
KIND_LABEL = {"raw": "Raw data", "sdtm": "SDTM", "adam": "ADaM", "tlf": "TLF",
              "tlf_old": "Previous TLF", "sap": "SAP", "shells": "Mock shells",
              "specs": "Specs"}
_OLD_WORDS = {"old", "prev", "previous", "prior", "tlf_old", "last"}

DATA_EXT = (".xpt", ".sas7bdat", ".csv")
DOC_EXT = (".docx", ".pdf", ".txt", ".md", ".rtf")

# SDTM domain names. A two-letter file name is also taken as SDTM.
SDTM_DOMAINS = {
    "DM", "AE", "CM", "EX", "EC", "MH", "VS", "LB", "EG", "PE", "DS", "SV", "SE",
    "TA", "TE", "TI", "TS", "TV", "PC", "PP", "DA", "DV", "IE", "QS", "SC", "SU",
    "FA", "MB", "MS", "PR", "RELREC", "CO", "OM", "IS", "CE", "HO",
}


# ---------------------------------------------------------------------------
# where an uploaded file goes
# ---------------------------------------------------------------------------
def classify(path):
    """
    Guess which folder a file belongs in, from its path and name.
    Returns one of KINDS, or None if there is no sensible guess.
    """
    parts = [p.lower() for p in re.split(r"[\\/]", path)]
    name = parts[-1]
    stem, ext = os.path.splitext(name)

    # A zip that already has raw/ sdtm/ adam/ folders keeps its own sorting.
    for p in parts[:-1]:
        if p in KINDS:
            return p
    if ext == ".rtf" and (any(p in _OLD_WORDS for p in parts[:-1])
                          or re.search(r"(^|[_\- ])(old|prev|previous|prior)"
                                       r"([_\- .]|$)", stem)):
        return "tlf_old"

    if name == "spec.txt":
        return "sap"
    if name == "shells.txt" or "shell" in stem or "mock" in stem:
        return "shells"
    if re.search(r"(^|[_\- ])sap([_\- .]|$)|statistical.analysis.plan", stem):
        return "sap"
    if "spec" in stem and ext in (".xlsx", ".xls", ".csv"):
        return "specs"
    if ext == ".rtf":
        return "tlf"
    if ext in DATA_EXT:
        if "raw" in stem:
            return "raw"
        up = stem.upper()
        if up.startswith("AD"):
            return "adam"
        if up in SDTM_DOMAINS or up.startswith("SUPP") or len(up) == 2:
            return "sdtm"
        return "raw"
    if ext in (".docx", ".pdf", ".txt", ".md"):
        return "sap"
    return None


def save_upload(study_folder, filename, data, kind=None):
    """Write one uploaded file into the right sub-folder. Returns the kind."""
    kind = kind or classify(filename) or "sap"
    folder = os.path.join(study_folder, kind)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, os.path.basename(filename)), "wb") as fh:
        fh.write(data)
    return kind


def save_zip(study_folder, zip_path):
    """Unpack a zip into the study, sorting each file. Returns {kind: n}."""
    counts = {}
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir() or os.path.basename(info.filename).startswith("."):
                continue
            if "__macosx" in info.filename.lower():
                continue
            kind = classify(info.filename)
            if not kind:
                continue
            save_upload(study_folder, info.filename, z.read(info), kind)
            counts[kind] = counts.get(kind, 0) + 1
    return counts


def remove_file(study_folder, kind, filename):
    path = os.path.join(study_folder, kind, os.path.basename(filename))
    if os.path.exists(path):
        os.remove(path)


def studies(root="studies"):
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)))


def inventory(study_folder):
    """{kind: [file names]} for the Overview page."""
    out = {}
    for k in KINDS:
        folder = os.path.join(study_folder, k)
        out[k] = sorted(f for f in os.listdir(folder)
                        if not f.startswith(".")) if os.path.isdir(folder) else []
    return out


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------
def _clean(df):
    for col in df.columns:
        if df[col].dtype == object or str(df[col].dtype).startswith("str"):
            df[col] = df[col].astype(str).str.strip().replace(
                {"nan": None, "None": None})
    return df


def read_data_file(path):
    """Read .xpt, .sas7bdat or .csv. Returns (table, {variable: label})."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        df = df.replace({"": None})
        return _clean(df), {c: c for c in df.columns}
    import pyreadstat
    if ext == ".xpt":
        df, meta = pyreadstat.read_xport(path)
    else:
        df, meta = pyreadstat.read_sas7bdat(path)
    labels = {k: (v or k) for k, v in zip(meta.column_names, meta.column_labels)}
    return _clean(df), labels


def read_data_folder(folder):
    """{NAME: {"data", "labels", "path"}} for every data file in a folder."""
    out = {}
    if not os.path.isdir(folder):
        return out
    for path in sorted(glob.glob(os.path.join(folder, "*"))):
        if not path.lower().endswith(DATA_EXT):
            continue
        name = os.path.splitext(os.path.basename(path))[0].upper()
        try:
            df, labels = read_data_file(path)
        except Exception as exc:
            print("could not read %s: %s" % (path, exc))
            continue
        out[name] = {"data": df, "labels": labels, "path": path}
    return out


def read_text(path):
    """Plain text out of a .txt, .docx, .pdf or .rtf. Empty if it cannot."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".txt", ".md"):
            with open(path, encoding="utf-8", errors="replace") as fh:
                return fh.read()
        if ext == ".docx":
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf-8", "replace")
            xml = re.sub(r"</w:p>", "\n", xml)
            xml = re.sub(r"<w:tab/>", "\t", xml)
            text = re.sub(r"<[^>]+>", "", xml)
            for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                         ("&quot;", '"'), ("&apos;", "'")):
                text = text.replace(a, b)
            return text
        if ext == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError:
                return ""
            return "\n".join((p.extract_text() or "")
                             for p in PdfReader(path).pages)
        if ext == ".rtf":
            from .rtf import read_output
            o = read_output(path)
            lines = list(o.titles) + [" | ".join(o.headers)]
            lines += [" | ".join(r) for r in o.rows] + list(o.footnotes)
            return "\n".join(lines)
    except Exception as exc:
        print("could not read %s: %s" % (path, exc))
    return ""


_SHELL_ID = re.compile(
    r"\b(Table|Listing|Figure|Appendix)\s+(\d+(?:[.\-]\d+)*)\s*[:.\-–]?\s*(.*)",
    re.I)


def output_id(text):
    """'Table 14-3' style id from a title line, normalised. None if absent."""
    m = _SHELL_ID.search(text or "")
    if not m:
        return None
    return "%s %s" % (m.group(1).title(), m.group(2).replace(".", "-"))


def parse_shells(folder):
    """
    Every output the mock shells promise, as dicts: id, title, file.
    shells.txt (name | id) gives file names. A document gives ids and titles.
    """
    out, seen = [], set()
    if not os.path.isdir(folder):
        return out
    for path in sorted(glob.glob(os.path.join(folder, "*"))):
        base = os.path.basename(path).lower()
        if base == "shells.txt":
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    name, _, rest = line.partition("|")
                    out.append({"id": output_id(rest) or output_id(name),
                                "title": "", "file": name.strip()})
            continue
        if not base.endswith(DOC_EXT):
            continue
        for line in read_text(path).splitlines():
            m = _SHELL_ID.search(line.strip())
            if not m or not line.strip().lower().startswith(m.group(1).lower()):
                continue
            oid = output_id(line)
            title = m.group(3).strip()
            if oid in seen and not title:
                continue
            seen.add(oid)
            out.append({"id": oid, "title": title, "file": ""})
    return out


def read_spec_rules(folder):
    """key = value lines from sap/spec.txt."""
    rules = {}
    path = os.path.join(folder, "spec.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    rules[k.strip()] = v.strip()
    return rules


def read_specs(folder):
    """
    Variable-level specs as one table: Dataset, Variable, Label, Type, Length.
    Any sheet that has Dataset and Variable columns is used.
    """
    frames = []
    if not os.path.isdir(folder):
        return None
    for path in sorted(glob.glob(os.path.join(folder, "*"))):
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".csv":
                sheets = {"csv": pd.read_csv(path, dtype=str)}
            elif ext in (".xlsx", ".xls"):
                sheets = pd.read_excel(path, sheet_name=None, dtype=str)
            else:
                continue
        except Exception as exc:
            print("could not read %s: %s" % (path, exc))
            continue
        for sheet, df in sheets.items():
            cols = {str(c).strip().lower(): c for c in df.columns}
            ds = cols.get("dataset") or cols.get("domain")
            var = cols.get("variable") or cols.get("variable name")
            if not ds or not var:
                continue
            keep = pd.DataFrame({
                "Dataset": df[ds].astype(str).str.strip().str.upper(),
                "Variable": df[var].astype(str).str.strip().str.upper(),
                "Label": df[cols["label"]].astype(str).str.strip()
                if "label" in cols else "",
                "Type": df[cols["type"]].astype(str).str.strip().str.lower()
                if "type" in cols else "",
                "File": os.path.basename(path)})
            frames.append(keep[keep["Variable"].ne("") & keep["Variable"].ne("NAN")])
    return pd.concat(frames, ignore_index=True) if frames else None


@dataclass
class Study:
    name: str
    folder: str
    raw: Dict = field(default_factory=dict)
    sdtm: Dict = field(default_factory=dict)
    adam: Dict = field(default_factory=dict)
    package: Optional[object] = None          # the TLF Package
    sap_text: str = ""
    sap_files: List[str] = field(default_factory=list)
    shells: List[dict] = field(default_factory=list)
    specs: Optional[pd.DataFrame] = None
    rules: Dict[str, str] = field(default_factory=dict)


def load_study(folder):
    """Read everything in a study folder."""
    from .outputs import read_package, Package
    name = os.path.basename(os.path.normpath(folder))
    st = Study(name=name, folder=folder)
    st.raw = read_data_folder(os.path.join(folder, "raw"))
    st.sdtm = read_data_folder(os.path.join(folder, "sdtm"))
    st.adam = read_data_folder(os.path.join(folder, "adam"))

    sap = os.path.join(folder, "sap")
    st.rules = read_spec_rules(sap)
    if os.path.isdir(sap):
        for p in sorted(glob.glob(os.path.join(sap, "*"))):
            if os.path.basename(p).lower() == "spec.txt":
                continue
            if p.lower().endswith(DOC_EXT):
                st.sap_files.append(os.path.basename(p))
                st.sap_text += "\n" + read_text(p)

    st.shells = parse_shells(os.path.join(folder, "shells"))
    st.specs = read_specs(os.path.join(folder, "specs"))

    tlf = os.path.join(folder, "tlf")
    st.package = read_package(tlf) if os.path.isdir(tlf) else Package(tlf, name)
    st.package.study = name
    # the TLF checks read the shell list and the SAP rules off the package
    st.package.spec = dict(st.rules)
    st.package.shells = [(s["file"], s["id"] or "") for s in st.shells
                         if s["file"]]
    return st


def new_study(root, name):
    folder = os.path.join(root, re.sub(r"[^A-Za-z0-9_\-]", "_", name.strip()))
    for k in KINDS:
        os.makedirs(os.path.join(folder, k), exist_ok=True)
    return folder


def delete_study(folder):
    shutil.rmtree(folder, ignore_errors=True)
