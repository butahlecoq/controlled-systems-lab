"""Run the GEO-05 driver once per fixture; output remains smoke-only."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from report import SCENARIOS, bind_fixture_identity, strict_json_loads


def validate_smoke(stdout: str) -> list[dict]:
    rows = [bind_fixture_identity(strict_json_loads(line)) for line in stdout.splitlines() if line.strip()]
    if len(rows) != len(SCENARIOS) or {row.get("scenario") for row in rows} != set(SCENARIOS):
        raise ValueError("smoke scenario matrix differs from the pinned catalog")
    if any(row.get("purpose") != "smoke" or row.get("repetition") != 0 or row.get("status") != "passed"
           or row.get("oracle_scope") != "numeric_literal_samples"
           or row.get("oracle_passed") is not True or row.get("work_observed") is not True for row in rows):
        raise ValueError("smoke contains a failed or incomplete fixture")
    row = next(item for item in rows if item["scenario"] == "integrator_predecessor")
    if row.get("input_rows") != 6 or row.get("output_rows") != 4 or row.get("expected_fm_peak_rows") != 6:
        raise ValueError("integrator row evidence differs from the pinned fixture")
    for trial in rows:
        expected_limit = None if trial["scenario"] == "v_projection_preserves_ray" else 128
        if trial.get("max_rows") != expected_limit:
            raise ValueError("per-call provider row limit differs from the pinned fixture profile")
        expected_kind = {"singular_a": "h", "unreachable_equality_target": "h", "integrator_predecessor": "h", "v_projection_preserves_ray": "v"}[trial["scenario"]]
        if trial.get("result_kind") != expected_kind:
            raise ValueError("fixture returned an unexpected representation kind")
        if trial["scenario"] == "unreachable_equality_target" and trial.get("result_encoding") != "h_contradiction_row":
            raise ValueError("unreachable equality must return the observed H contradiction encoding")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    args = parser.parse_args()
    completed = subprocess.run([str(args.exe), "--smoke"], text=True, capture_output=True, timeout=60)
    if completed.returncode:
        raise SystemExit(f"smoke executable failed ({completed.returncode}): {completed.stderr}")
    rows = validate_smoke(completed.stdout)
    for row in rows:
        print(f"{row['scenario']}: {row['status']} (smoke only; timings discarded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
