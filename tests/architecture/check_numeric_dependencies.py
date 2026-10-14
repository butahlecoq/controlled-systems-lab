"""Fail if foundational numeric headers import higher-level contracts transitively."""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[2] / "include"
pending = ["csl/numeric/data.hpp"]
seen = set()
while pending:
    name = pending.pop()
    if name in seen:
        continue
    seen.add(name)
    text = (root / name).read_text(encoding="utf-8")
    pending.extend(re.findall(r"#include\s*[<\"](csl/[^>\"]+)[>\"]", text))
forbidden = sorted(name for name in seen if name == "csl/contracts.hpp" or
                   name.startswith(("csl/synthesis/", "csl/registry/", "csl/geometry/", "csl/problem/")))
if forbidden:
    sys.exit("numeric headers import higher-level contracts: " + ", ".join(forbidden))
print("numeric headers depend only on foundational value contracts")
