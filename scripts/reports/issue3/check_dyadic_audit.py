"""Check the optional public product's per-plan B08 audit against exact dyadics."""

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "docs/research/tools"))
from check_issue3_b08_dyadic import audit, saved_b08_row


def main(executable):
    run = subprocess.run([executable, "--audit-b08"], capture_output=True, text=True, check=True)
    if run.stderr:
        raise RuntimeError(run.stderr)
    product = json.loads(run.stdout)
    result = audit(saved_b08_row(), product)
    if result["product_plan_rows_checked"] != 625:
        raise RuntimeError("not every public plan was audited")
    record = ROOT / "docs/research/evidence/issue3-b08-dyadic.json"
    if result != json.loads(record.read_text(encoding="utf-8")):
        raise RuntimeError("saved exact-dyadic sidecar differs from public product")
    print("Issue 3 B08 exact-dyadic per-plan audit passed: 625 plans, 160000 corners")


if __name__ == "__main__":
    main(sys.argv[1])
