"""Check the public finite-action minimax report driver's JSONL surface."""
import json
import hashlib
from pathlib import Path
import subprocess
import sys


def main() -> None:
    completed = subprocess.run([sys.argv[1], "--smoke"], capture_output=True, text=True, check=True)
    assert completed.stderr == "", completed.stderr
    rows = [json.loads(line) for line in completed.stdout.splitlines()]
    assert len(rows) == 8
    by_fixture = {row["fixture"]: row for row in rows}
    assert set(by_fixture) == {"l19", "integrator", "all_infeasible", "empty_catalogue",
                               "no_scenarios", "unsupported", "cancelled", "b08_rounded"}
    driver = Path(__file__).resolve().parents[3] / "benchmarks/reporting/issue3/finite_catalogue_driver.cpp"
    fixture_hash = hashlib.sha256(driver.read_bytes()).hexdigest()
    for row in rows:
        assert row["schema"] == "csl.issue3-raw-trial/1"
        assert row["source_commit"] == "6c1cde0fcaabf40b8fdcb5973f36465cdccdcaf4"
        assert len(row["harness_commit"]) == 40
        assert row["checked_calls"] == row["batch"] == 1
        assert row["elapsed_ns"] > 0
        assert row["fixture_sha256"] == fixture_hash
        assert hashlib.sha256(row["input_canonical"].encode()).hexdigest() == row["input_sha256"]
        assert isinstance(json.loads(row["input_canonical"]), dict)
        assert row["problem_id"] and row["request_id"]
        assert row["limits"]["max_plans"] >= 1
        assert row["objective_convention"]
        assert row["checks"]["passed"] is True
        assert row["checks"]["observed"] == row["result"]
        assert row["checks"]["expected"]["status"] == row["result"]["status"]
        assert row["assurance"] == ("numerical" if row["fixture"] in
            {"l19", "integrator", "all_infeasible", "b08_rounded"} else None)
        assert row["plan_count"] == ({"l19": 2, "integrator": 2,
            "all_infeasible": 2, "empty_catalogue": 0,
            "b08_rounded": 625}.get(row["fixture"]))
        assert row["evaluated_terminal_rows"] == ({"l19": 4, "integrator": 4,
            "all_infeasible": 0, "empty_catalogue": 0,
            "b08_rounded": 160000}.get(row["fixture"]))
    assert by_fixture["l19"]["result"] == {
        "status": "numerical_optimal", "value": 1, "plan_count": 2,
        "minimizing_plan_indices": [0, 1], "evaluated_vertices": 4,
        "worst_values": [1, 1], "maximizers": [[0], [2]],
        "sampled_objective_values": [1, 0, 1],
    }
    assert by_fixture["integrator"]["result"] == {
        "status": "numerical_optimal", "value": 1, "plan_count": 2,
        "minimizing_plan_indices": [0], "worst_values": [1, 4],
        "evaluated_vertices": 4,
    }
    assert by_fixture["all_infeasible"]["result"] == {
        "status": "infeasible", "rejected_plans": [
            {"action_indices": [0], "stage": 1, "violating_successor": [2]},
            {"action_indices": [1], "stage": 1, "violating_successor": [1]},
        ],
    }
    assert by_fixture["empty_catalogue"]["result"] == {"status": "empty_catalogue"}
    assert by_fixture["no_scenarios"]["result"] == {"status": "no_scenarios"}
    assert by_fixture["unsupported"]["result"] == {
        "status": "unsupported", "field": "finite_minimax.capacity",
    }
    assert by_fixture["cancelled"]["result"] == {"status": "stopped", "reason": "cancelled"}
    b08 = by_fixture["b08_rounded"]["result"]
    assert b08["status"] == "numerical_optimal"
    assert b08["plan_count"] == 625
    assert b08["evaluated_vertices"] == 160000
    assert b08["minimizing_plan_indices"] == [17, 33, 129]
    assert abs(b08["value"] - 67.150601101407) < 1e-8


if __name__ == "__main__":
    main()
