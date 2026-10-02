# -*- coding: utf-8 -*-
"""
Loads a whole delivery of outputs, plus the two small text files that tell the
checks what was supposed to be delivered and what the SAP asked for.

    outputs/DEMO-BE-101/*.rtf      the delivered outputs
    outputs/DEMO-BE-101/shells.txt what the mock shells require
    outputs/DEMO-BE-101/spec.txt   the few SAP rules a check may rely on

Keeping the SAP rules in a plain file means a check never has to guess. If the
file is not there, the checks that need it simply do not run, and they say so.
"""
import os
import glob
from dataclasses import dataclass, field
from typing import Dict, List

from .rtf import read_output, Output


@dataclass
class Package:
    folder: str
    study: str
    outputs: List[Output] = field(default_factory=list)
    shells: List[tuple] = field(default_factory=list)   # (filename, title)
    spec: Dict[str, str] = field(default_factory=dict)

    def by_name(self, fragment):
        low = fragment.lower()
        return [o for o in self.outputs if low in o.filename.lower()]

    def tables(self):
        return [o for o in self.outputs if o.kind == "table"]

    def figures(self):
        return [o for o in self.outputs if o.kind == "figure"]

    def listings(self):
        return [o for o in self.outputs if o.kind == "listing"]

    # ---- spec helpers ----------------------------------------------------
    def spec_int(self, key):
        try:
            return int(str(self.spec.get(key, "")).strip())
        except ValueError:
            return None

    def spec_list(self, key):
        raw = self.spec.get(key, "")
        return [v.strip() for v in raw.split(",") if v.strip()]


def _read_shells(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" in line:
                name, title = line.split("|", 1)
                rows.append((name.strip(), title.strip()))
            else:
                rows.append((line, ""))
    return rows


def _read_spec(path):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def read_package(folder):
    """Read every .rtf in a folder, plus shells.txt and spec.txt if present."""
    study = os.path.basename(os.path.normpath(folder))
    pkg = Package(folder=folder, study=study)
    for path in sorted(glob.glob(os.path.join(folder, "*.rtf"))):
        try:
            pkg.outputs.append(read_output(path))
        except Exception as exc:                      # never lose the whole run
            print("could not read %s: %s" % (os.path.basename(path), exc))
    pkg.shells = _read_shells(os.path.join(folder, "shells.txt"))
    pkg.spec = _read_spec(os.path.join(folder, "spec.txt"))
    return pkg


def packages(root="outputs"):
    """Every study folder under outputs/."""
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)))
