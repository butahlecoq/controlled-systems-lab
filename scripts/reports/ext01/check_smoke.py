"""Check the public EXT-01 report driver's saved-data surface, not its internals."""
import json
import subprocess
import sys


def main() -> None:
    completed = subprocess.run([sys.argv[1], "--smoke"], capture_output=True, text=True, check=True)
    assert not completed.stderr, completed.stderr
    rows = [json.loads(line) for line in completed.stdout.splitlines()]
    assert len(rows) == 4
    by_fixture = {row["fixture"]: row for row in rows}
    assert set(by_fixture) == {
        "l19", "integrator_feasible", "integrator_violation", "b08_rounded"
    }
    for row in rows:
        assert row["schema"] == "csl.ext01-raw-trial/1"
        assert row["checked_calls"] == row["batch"] == 1
        assert row["elapsed_ns"] > 0

    l19 = by_fixture["l19"]["result"]
    assert l19["status"] == "numerical_value"
    assert l19["worst_value"] == 1
    assert l19["maximizer"] == [0]
    assert l19["evaluated_vertices"] == 3
    assert l19["sampled_points"] == [0, 1, 2]
    assert l19["observed_objective_values"] == [1, 0, 1]
    assert l19["stationary_midpoint_value"] == l19["observed_objective_values"][1]

    feasible = by_fixture["integrator_feasible"]["result"]
    assert feasible["status"] == "numerical_reachable"
    assert feasible["terminal_candidates"] == 4
    assert feasible["terminal_worst_value"] == 4
    violation = by_fixture["integrator_violation"]["result"]
    assert violation == {"status": "robust_violation", "stage": 1,
                         "violating_successor": [-1]}
    b08 = by_fixture["b08_rounded"]["result"]
    assert b08["status"] == "numerical_reference"
    assert b08["plan_count"] == 625
    assert b08["disturbance_histories"] == 160000
    assert b08["ties_at_1e-8"] == 3
    assert abs(b08["minimum_worst_value"] - 67.150601101407) < 1e-8


if __name__ == "__main__":
    main()
