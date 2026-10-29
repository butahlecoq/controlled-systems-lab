#!/usr/bin/env python3
"""Run the EXP-03 native smoke and its independent inclusion oracle."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from check_two_points_approximation import check
from build_comparison_records import build_records, validate_record


def main():
    if len(sys.argv) != 6:
        raise SystemExit(
            "usage: check_two_points_approximation_smoke.py DRIVER REFERENCE_BUILDER "
            "FIGURE_DATA RESULT REFERENCE_OUTPUT"
        )
    driver, builder, figure_data, result, reference_output = map(Path, sys.argv[1:])
    subprocess.run([
        sys.executable, str(builder), "--figure-data", str(figure_data),
        "--result", str(result), "--output", str(reference_output),
    ], check=True, capture_output=True, text=True)
    run = subprocess.run([str(driver), "smoke", str(reference_output)],
                         check=True, capture_output=True, text=True)
    reference = json.loads(reference_output.read_text(encoding="utf-8"))
    raw = json.loads(run.stdout)
    checked = check(reference, raw)
    if len(checked["results"]) != 10:
        raise SystemExit("Expected five exact/outer methods on both phase planes")
    if any(item["status"] != "verified" for item in checked["results"]):
        raise SystemExit("Independent inclusion oracle did not verify every method")
    minimax = checked["finite_minimax_reference"]
    if (minimax["value_numerator"] != 58_323_769 or
            minimax["value_denominator"] != 4_000_000 or
            minimax["minimizing_control_sequences_codes"] != [[-1, -1, -1]] or
            minimax["achievable_policy_witness"]["selected_worst_disturbance_sequence_codes"] != [-1, -1, -1]):
        raise SystemExit("Independent finite minimax oracle changed from the analytic fixture")
    bounds = {item["method"]: item for item in checked["objective_bounds"]}
    if (not checked["objective_bounds_checks_complete"] or
            bounds["directional-ellipsoid"]["lower_bound"]["status"] != "verified" or
            bounds["directional-ellipsoid"]["upper_bound"]["status"] != "verified" or
            bounds["zonotope-axis-cover"]["lower_bound"]["status"] != "verified" or
            bounds["zonotope-axis-cover"]["upper_bound"]["status"] != "verified" or
            bounds["rotated-parallelotope"]["lower_bound"]["status"] != "inconclusive" or
            bounds["rotated-parallelotope"]["upper_bound"]["status"] != "verified"):
        raise SystemExit("Approximation-based minimax bounds lost their inclusion-gated outcomes")
    records = build_records(reference, raw, checked)
    if len(records) != 2 or any(len(record["attempts"]) != 5 for record in records):
        raise SystemExit("Comparison-record packaging omitted a phase plane or method")
    for record in records:
        validate_record(record)
    print(json.dumps({
        "schema": checked["schema"],
        "case_id": checked["case_id"],
        "verified_results": len(checked["results"]),
        "finite_minimax_value": minimax["value"],
        "comparison_records": len(records),
        "objective_bounds": {method: {
            "lower": bound["lower_bound"]["status"],
            "upper": bound["upper_bound"]["status"],
        } for method, bound in bounds.items()},
        "methods": sorted({item["method"] for item in checked["results"]}),
        "directions": sorted({item["relation"] for item in checked["results"]}),
    }, indent=2))


if __name__ == "__main__":
    main()
