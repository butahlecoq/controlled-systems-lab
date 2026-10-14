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
allowed_values = {"csl/core/values.hpp", "csl/core/diagnostics.hpp"}
forbidden = sorted(name for name in seen
                   if name not in allowed_values and not name.startswith("csl/numeric/"))
if forbidden:
    sys.exit("numeric headers import higher-level contracts: " + ", ".join(forbidden))
print("numeric headers depend only on foundational value contracts")
