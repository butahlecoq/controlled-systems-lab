#!/usr/bin/env python3
"""Cross-check a saved B06 numerical capture against its integer exhaustive oracle."""
import json
import math
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_capture.py RESULT_DIRECTORY")
    root = Path(sys.argv[1])
    oracle = json.loads((root / "exact-oracle.json").read_text())
    rows = [json.loads(line) for line in (root / "raw-runs.jsonl").read_text().splitlines()]
    if len(rows) != 8 or [r["batch"] for r in rows] != list(range(8)):
        raise SystemExit("expected one excluded warmup and seven ordered measured calls")
    if oracle["plan_count"] != 3125 or oracle["disturbance_histories_per_plan"] != 1024:
        raise SystemExit("exact oracle did not exhaust the declared domain")
    if oracle["source_commit"] != rows[0]["source_commit"] or oracle["fixture_sha256"] != rows[0]["fixture_sha256"]:
        raise SystemExit("exact oracle source or input identity differs from solver capture")
    if len(oracle["oracle_sha256"]) != 64 or len(rows[0]["driver_sha256"]) != 64:
        raise SystemExit("missing executable source hashes")
    if oracle["evaluated_pairs"] != 3_200_000:
        raise SystemExit("exact oracle pair count mismatch")
    if oracle["minimizing_plan_indices"] != [1936] or oracle["printed_l09_plan_index"] != 1936:
        raise SystemExit("exact minimax plan mismatch")
    exact_value = oracle["minimum_objective_squared_numerator"] / oracle["objective_numerator_denominator"]
    for row in rows:
        if row["status"] != "numerical_optimal" or row["assurance"] != "numerical":
            raise SystemExit(f"batch {row['batch']} did not complete with numerical assurance")
        if row["source_commit"] != rows[0]["source_commit"] or row["fixture_sha256"] != rows[0]["fixture_sha256"]:
            raise SystemExit("source or input identity changed during capture")
        if row["plan_count"] != 3125 or row["evaluated_terminal_vertices"] != 3_200_000:
            raise SystemExit(f"batch {row['batch']} did not evaluate all plans and vertices")
        if row["minimizing_plan_indices"] != oracle["minimizing_plan_indices"]:
            raise SystemExit(f"batch {row['batch']} minimizer differs from exact oracle")
        if not math.isclose(row["objective_squared"], exact_value, rel_tol=0, abs_tol=1e-10):
            raise SystemExit(f"batch {row['batch']} objective differs from exact oracle")
        if row["printed_plan_index"] != oracle["printed_l09_plan_index"]:
            raise SystemExit("reported L09 plan index mismatch")
        if not math.isclose(row["printed_plan_worst_squared"], exact_value, rel_tol=0, abs_tol=1e-10):
            raise SystemExit("reported L09 plan did not attain the exact reference optimum")
        if row["driver_sha256"] != rows[0]["driver_sha256"]:
            raise SystemExit("runner source identity changed during capture")
        if row["elapsed_ns"] <= 0:
            raise SystemExit(f"batch {row['batch']} has a nonpositive interval")
    geometry = json.loads((root / "geometry.json").read_text())
    if geometry["source_commit"] != rows[0]["source_commit"] or len(geometry["winner_terminal_vertices"]) != 1024:
        raise SystemExit("geometry capture source or vertex count mismatch")
    if geometry["winner_terminal_vertices"] != geometry["printed_terminal_vertices"]:
        raise SystemExit("printed L09 plan and minimizing plan terminal sets differ")
    print(json.dumps({"status": "passed", "measured_batches": 7,
        "warmup_batches": 1, "plan_count": 3125,
        "evaluated_pairs": oracle["evaluated_pairs"],
        "minimizing_plan_indices": oracle["minimizing_plan_indices"],
        "exact_objective_norm": oracle["objective_norm"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
