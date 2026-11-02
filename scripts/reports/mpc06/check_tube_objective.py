#!/usr/bin/env python3
"""Independent exact checker for the MPC-06 finite-horizon cost extension."""
from __future__ import annotations

from fractions import Fraction as Q
from itertools import product
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_tube import check_record as check_base_tube

SCENARIO = ROOT / "benchmarks/scenarios/mpc06-tube-objective-v1.json"
BASE_SCENARIO = ROOT / "benchmarks/scenarios/mpc06-nilpotent-tube-v1.json"
BASE_RESULT = ROOT / "reports/algorithm-results/mpc06-nilpotent-tube-pilot-v1/result.json"
RESULT = ROOT / "reports/algorithm-results/mpc06-tube-objective-v1/result.json"
BASE_SCENARIO_COPY = ROOT / "reports/algorithm-results/mpc06-tube-objective-v1/base-scenario.json"
BASE_RESULT_COPY = ROOT / "reports/algorithm-results/mpc06-tube-objective-v1/base-result.json"
OUTPUT = ROOT / "reports/algorithm-results/mpc06-tube-objective-v1/verification.json"


def q(value: str) -> Q:
    return Q(value)


def text(value: Q) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_vertex(scenario: dict, disturbance: tuple[Q, ...]) -> tuple[Q, Q, list[list[Q]], list[Q]]:
    """Derive dynamics and costs afresh; do not import the report builder."""
    a = [[q(v) for v in row] for row in scenario["dynamics"]["A"]]
    b = [q(row[0]) for row in scenario["dynamics"]["B"]]
    e = [q(row[0]) for row in scenario["dynamics"]["E"]]
    k = [q(v) for v in scenario["feedback"]["K"][0]]
    z = [q(v) for v in scenario["initial"]["nominal_state"]]
    x = [q(v) for v in scenario["initial"]["actual_state"]]
    nominal_controls = [q(v) for v in scenario["nominal_plan"]["controls"]]
    low, high = map(q, scenario["constraints"]["state_box"][0])
    velocity_low, velocity_high = map(q, scenario["constraints"]["state_box"][1])
    input_low, input_high = map(q, scenario["constraints"]["input_interval"])
    states = [x[:]]
    inputs: list[Q] = []
    actual_cost = Q(0)
    nominal_cost = Q(0)
    for t, w in enumerate(disturbance):
        error = [x[i] - z[i] for i in range(2)]
        u = nominal_controls[t] + sum((k[i] * error[i] for i in range(2)), Q(0))
        actual_cost += x[0] ** 2 + x[1] ** 2 + u ** 2
        nominal_cost += z[0] ** 2 + z[1] ** 2 + nominal_controls[t] ** 2
        inputs.append(u)
        next_x = [sum((a[i][j] * x[j] for j in range(2)), Q(0)) + b[i] * u + e[i] * w
                   for i in range(2)]
        next_z = [sum((a[i][j] * z[j] for j in range(2)), Q(0)) + b[i] * nominal_controls[t]
                   for i in range(2)]
        if not (low <= next_x[0] <= high and velocity_low <= next_x[1] <= velocity_high):
            raise AssertionError("a disturbance vertex violates the state box")
        if not input_low <= u <= input_high:
            raise AssertionError("a disturbance vertex violates the input interval")
        x, z = next_x, next_z
        states.append(x[:])
    actual_cost += x[0] ** 2 + x[1] ** 2
    nominal_cost += z[0] ** 2 + z[1] ** 2
    return actual_cost, nominal_cost, states, inputs


def check() -> dict:
    scenario_bytes = SCENARIO.read_bytes()
    scenario = json.loads(scenario_bytes)
    base_scenario_bytes = BASE_SCENARIO.read_bytes()
    base_scenario = json.loads(base_scenario_bytes)
    base_result_bytes = BASE_RESULT.read_bytes()
    assert BASE_SCENARIO_COPY.read_bytes() == base_scenario_bytes
    assert BASE_RESULT_COPY.read_bytes() == base_result_bytes
    base_result = json.loads(base_result_bytes)
    result_bytes = RESULT.read_bytes()
    result = json.loads(result_bytes)

    assert scenario["schema"] == "csl.mpc06-tube-objective-input/1"
    assert scenario["base_scenario_id"] == base_scenario["scenario_id"] == base_result["case_id"]
    assert base_result["schema"] == "csl.mpc06-nilpotent-tube-pilot/1"
    check_base_tube(base_result)
    assert base_result["rpi_inclusion_exactly_verified"] and base_result["initial_tube_membership"]
    assert result["schema"] == "csl.mpc06-tube-objective-result/1"
    assert result["case_id"] == scenario["scenario_id"]
    assert result["source_commit"] == base_result["source_commit"]
    assert result["source_identity"] == {
        "driver_sha256": base_result["driver_sha256"],
        "base_scenario_sha256": sha(base_scenario_bytes),
        "base_result_sha256": sha(base_result_bytes),
        "objective_scenario_sha256": sha(scenario_bytes),
    }
    assert result["policy_semantics"]["is_minimax_optimum"] is False
    assert result["policy_semantics"]["optimized_variables"] == []

    bounds = tuple(map(q, scenario["dynamics"]["disturbance_bounds"]))
    horizon = scenario["nominal_plan"]["horizon_steps"]
    expected_rows = []
    for w in product(bounds, repeat=horizon):
        actual, nominal, states, inputs = run_vertex(scenario, w)
        expected_rows.append((actual, nominal, [text(v) for v in w], states, inputs))
    expected_max = max(row[0] for row in expected_rows)
    expected_nominal = expected_rows[0][1]
    assert all(row[1] == expected_nominal for row in expected_rows)
    assert len(expected_rows) == 2 ** horizon == result["coverage"]["expected_vertices"]
    assert result["coverage"]["disturbance_vertices_checked"] == len(expected_rows)
    assert result["coverage"]["all_vertex_paths_satisfy_state_and_input_constraints"] is True
    objective = result["objective"]
    assert q(objective["nominal_surrogate_cost"]) == expected_nominal == 0
    assert q(objective["worst_case_actual_cost"]) == expected_max == Q(3, 8)
    assert q(objective["cost_gap"]) == expected_max - expected_nominal

    recorded_rows = result["vertex_paths"]
    assert len(recorded_rows) == len(expected_rows)
    for recorded, expected in zip(recorded_rows, expected_rows):
        assert [q(v) for v in recorded["disturbances"]] == [q(v) for v in expected[2]]
        assert q(recorded["actual_cost"]) == expected[0]
        assert q(recorded["nominal_surrogate_cost"]) == expected[1]
        assert [[q(v) for v in state] for state in recorded["states"]] == expected[3]
        assert [q(v) for v in recorded["controls"]] == expected[4]

    witnesses = [row for row in expected_rows if row[0] == expected_max]
    assert objective["worst_case_witness_count"] == len(witnesses) == 2
    assert [[q(v) for v in row] for row in objective["worst_case_witnesses"]] == [
        [q(v) for v in witness[2]] for witness in witnesses]
    assert "convex quadratic" in objective["continuous_box_maximum_argument"]
    return {
        "schema": "csl.mpc06-tube-objective-check/1",
        "status": "verified",
        "checker": "independent exact Fraction recurrence and vertex enumeration",
        "checked": {
            "base_rpi_and_feasibility_evidence": "verified in the independently checked base record",
            "disturbance_vertex_count": len(expected_rows),
            "all_vertex_safety_constraints": "passed",
            "nominal_surrogate_cost": text(expected_nominal),
            "exact_continuous_box_worst_cost": text(expected_max),
            "worst_witness_count": len(witnesses),
            "objective_record_sha256": sha(result_bytes),
            "scenario_sha256": sha(scenario_bytes),
        },
        "proof_scope": "For this fixed zero nominal plan, fixed K, horizon, and rational box, the cost is convex quadratic in the complete disturbance vector; exact vertex enumeration establishes its maximum over the continuous box. This does not optimize the plan or gain.",
    }


if __name__ == "__main__":
    verification = check()
    OUTPUT.write_text(json.dumps(verification, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(verification, sort_keys=True))
