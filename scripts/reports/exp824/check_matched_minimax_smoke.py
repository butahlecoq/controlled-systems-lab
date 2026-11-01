#!/usr/bin/env python3
"""Exercise the matched five-track fixed-plan minimax measurement driver."""

from __future__ import annotations

import json
import math
import subprocess
import sys


EXPECTED_METHODS = ["exact_polytope", "box", "zonotope", "parallelotope", "ellipsoid"]
EXPECTED_VALUE = 14.58094225


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_matched_minimax_smoke.py EXECUTABLE")
    completed = subprocess.run([sys.argv[1]], check=True, capture_output=True, text=True)
    record = json.loads(completed.stdout)
    assert record["schema"] == "csl.issue824.matched-minimax-benchmark/1"
    assert record["fixture"]["environment"] == "TwoPointsOnParallelLines"
    assert record["fixture"]["horizon_steps"] == 3
    assert record["methods"] == EXPECTED_METHODS
    assert record["measurement"]["repetitions_per_method"] == 5
    assert record["measurement"]["warmups_per_method"] == 1
    assert len(record["warmups"]) == len(EXPECTED_METHODS)
    assert len(record["samples"]) == 5 * len(EXPECTED_METHODS)
    for warmup in record["warmups"]:
        assert warmup["method"] in EXPECTED_METHODS
        assert warmup["outcome"]["status"] == "completed"
        assert warmup["outcome"]["candidate_plans"] == 27
        assert math.isclose(warmup["outcome"]["replayed_worst_value"], EXPECTED_VALUE,
            rel_tol=0.0, abs_tol=1e-10)
    by_method = {name: [] for name in EXPECTED_METHODS}
    for sample in record["samples"]:
        assert sample["method"] in by_method
        assert sample["elapsed_ns"] > 0
        assert sample["outcome"]["status"] == "completed"
        outcome = sample["outcome"]
        assert outcome["candidate_plans"] == 27
        assert math.isclose(outcome["replayed_worst_value"], EXPECTED_VALUE,
            rel_tol=0.0, abs_tol=1e-10)
        by_method[sample["method"]].append(sample)
    assert all(len(samples) == 5 for samples in by_method.values())
    for summary in record["summaries"]:
        samples = by_method[summary["method"]]
        assert summary["requested_repetitions"] == 5
        assert summary["successful_repetitions"] == 5
        assert summary["failures"] == 0
        assert summary["minimum_ns"] == min(row["elapsed_ns"] for row in samples)
        assert summary["maximum_ns"] == max(row["elapsed_ns"] for row in samples)
        assert summary["median_ns"] in [row["elapsed_ns"] for row in samples]
    print("matched minimax smoke passed: five methods, five rotated repetitions, all 27 plans and replays")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
