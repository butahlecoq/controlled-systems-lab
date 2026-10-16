"""Check the public finite-action minimax report driver's JSONL surface."""
import json
import subprocess
import sys


def main() -> None:
    completed = subprocess.run([sys.argv[1], "--smoke"], capture_output=True, text=True, check=True)
    assert completed.stderr == "", completed.stderr
    rows = [json.loads(line) for line in completed.stdout.splitlines()]
    assert len(rows) == 7
    by_fixture = {row["fixture"]: row for row in rows}
    assert set(by_fixture) == {"l19", "integrator", "all_infeasible", "empty_catalogue",
                               "no_scenarios", "cancelled", "b08_rounded"}
    for row in rows:
        assert row["schema"] == "csl.issue3-raw-trial/1"
        assert row["source_commit"] == "6c1cde0fcaabf40b8fdcb5973f36465cdccdcaf4"
        assert len(row["harness_commit"]) == 40
        assert row["checked_calls"] == row["batch"] == 1
        assert row["elapsed_ns"] > 0
    assert by_fixture["l19"]["result"] == {
        "status": "numerical_optimal", "value": 1, "plan_count": 1,
        "minimizing_plan_indices": [0], "evaluated_vertices": 3,
        "sampled_objective_values": [1, 0, 1],
    }
    assert by_fixture["integrator"]["result"] == {
        "status": "numerical_optimal", "value": 1, "plan_count": 2,
        "minimizing_plan_indices": [0], "worst_values": [1, 4],
    }
    assert by_fixture["all_infeasible"]["result"] == {
        "status": "infeasible", "rejected_plans": 2, "violating_stage": 1,
    }
    assert by_fixture["empty_catalogue"]["result"] == {"status": "empty_catalogue"}
    assert by_fixture["no_scenarios"]["result"] == {"status": "no_scenarios"}
    assert by_fixture["cancelled"]["result"] == {"status": "stopped", "reason": "cancelled"}
    b08 = by_fixture["b08_rounded"]["result"]
    assert b08["status"] == "numerical_optimal"
    assert b08["plan_count"] == 625
    assert b08["evaluated_vertices"] == 160000
    assert b08["minimizing_plan_indices"] == [17, 33, 129]
    assert abs(b08["value"] - 67.150601101407) < 1e-8


if __name__ == "__main__":
    main()
