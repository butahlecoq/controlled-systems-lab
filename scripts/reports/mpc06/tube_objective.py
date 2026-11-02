"""Exact finite-horizon cost evaluation for the fixed MPC-06 tube policy."""
from __future__ import annotations

from fractions import Fraction as Q
from itertools import product
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCENARIO_PATH = ROOT / "benchmarks/scenarios/mpc06-tube-objective-v1.json"
BASE_SCENARIO_PATH = ROOT / "benchmarks/scenarios/mpc06-nilpotent-tube-v1.json"
BASE_RESULT_PATH = ROOT / "reports/algorithm-results/mpc06-nilpotent-tube-pilot-v1/result.json"
OUTPUT = ROOT / "reports/algorithm-results/mpc06-tube-objective-v1"


def rational(value: str) -> Q:
    return Q(value)


def encode(value: Q) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dot(left: tuple[Q, ...], right: tuple[Q, ...]) -> Q:
    return sum((a * b for a, b in zip(left, right)), Q(0))


def quadratic(vector: tuple[Q, ...]) -> Q:
    return dot(vector, vector)


def simulate(scenario: dict, disturbances: tuple[Q, ...]) -> dict:
    """Replay one full-state feedback history using exact rational arithmetic."""
    A = tuple(tuple(map(rational, row)) for row in scenario["dynamics"]["A"])
    B = tuple(rational(row[0]) for row in scenario["dynamics"]["B"])
    E = tuple(rational(row[0]) for row in scenario["dynamics"]["E"])
    K = tuple(map(rational, scenario["feedback"]["K"][0]))
    state = tuple(map(rational, scenario["initial"]["actual_state"]))
    nominal = tuple(map(rational, scenario["initial"]["nominal_state"]))
    nominal_controls = tuple(map(rational, scenario["nominal_plan"]["controls"]))
    state_bound = tuple(tuple(map(rational, row)) for row in scenario["constraints"]["state_box"])
    input_bound = tuple(map(rational, scenario["constraints"]["input_interval"]))

    states = [state]
    nominal_states = [nominal]
    controls: list[Q] = []
    stage_costs: list[dict] = []
    for stage, disturbance in enumerate(disturbances):
        error = tuple(x - z for x, z in zip(state, nominal))
        control = nominal_controls[stage] + dot(K, error)
        stage_cost = quadratic(state) + control * control
        controls.append(control)
        stage_costs.append({"state": encode(quadratic(state)), "input": encode(control * control),
                            "total": encode(stage_cost)})

        next_state = tuple(sum((A[i][j] * state[j] for j in range(2)), Q(0)) +
                           B[i] * control + E[i] * disturbance for i in range(2))
        next_nominal = tuple(sum((A[i][j] * nominal[j] for j in range(2)), Q(0)) +
                             B[i] * nominal_controls[stage] for i in range(2))
        if any(not (state_bound[i][0] <= next_state[i] <= state_bound[i][1]) for i in range(2)):
            raise ValueError("disturbance vertex violates a state constraint")
        if not input_bound[0] <= control <= input_bound[1]:
            raise ValueError("disturbance vertex violates an input constraint")
        state, nominal = next_state, next_nominal
        states.append(state)
        nominal_states.append(nominal)

    terminal_cost = quadratic(state)
    nominal_cost = sum((quadratic(nominal_states[stage]) + nominal_controls[stage] ** 2
                        for stage in range(len(nominal_controls))), Q(0))
    nominal_cost += quadratic(nominal_states[-1])
    actual_cost = sum((Q(item["total"]) for item in stage_costs), Q(0)) + terminal_cost
    return {
        "disturbances": [encode(value) for value in disturbances],
        "states": [[encode(value) for value in state] for state in states],
        "nominal_states": [[encode(value) for value in state] for state in nominal_states],
        "controls": [encode(value) for value in controls],
        "stage_costs": stage_costs,
        "terminal_cost": encode(terminal_cost),
        "actual_cost": encode(actual_cost),
        "nominal_surrogate_cost": encode(nominal_cost),
    }


def analyze() -> dict:
    scenario_bytes = SCENARIO_PATH.read_bytes()
    scenario = json.loads(scenario_bytes)
    base_scenario_bytes = BASE_SCENARIO_PATH.read_bytes()
    base_scenario = json.loads(base_scenario_bytes)
    base_result_bytes = BASE_RESULT_PATH.read_bytes()
    base_result = json.loads(base_result_bytes)
    if base_result["case_id"] != scenario["base_scenario_id"] or base_scenario["scenario_id"] != scenario["base_scenario_id"]:
        raise ValueError("base MPC-06 feasibility case identity differs")

    bounds = tuple(map(rational, scenario["dynamics"]["disturbance_bounds"]))
    horizon = int(scenario["nominal_plan"]["horizon_steps"])
    rows = [simulate(scenario, disturbances)
            for disturbances in product(bounds, repeat=horizon)]
    worst = max(Q(row["actual_cost"]) for row in rows)
    witnesses = [row for row in rows if Q(row["actual_cost"]) == worst]
    nominal_surrogate = Q(rows[0]["nominal_surrogate_cost"])
    if any(Q(row["nominal_surrogate_cost"]) != nominal_surrogate for row in rows):
        raise ValueError("nominal surrogate must not depend on disturbances")
    return {
        "schema": "csl.mpc06-tube-objective-result/1",
        "case_id": scenario["scenario_id"],
        "base_case_id": scenario["base_scenario_id"],
        "source_commit": base_result["source_commit"],
        "source_identity": {
            "driver_sha256": base_result["driver_sha256"],
            "base_scenario_sha256": digest(base_scenario_bytes),
            "base_result_sha256": digest(base_result_bytes),
            "objective_scenario_sha256": digest(scenario_bytes),
        },
        "policy_semantics": {
            "quantifier": "one fixed nominal sequence; at each stage the controller observes x_t and applies u_t=v_t+K(x_t-z_t); all stagewise disturbance sequences are then covered",
            "is_minimax_optimum": False,
            "optimized_variables": [],
        },
        "objective": {
            "formula": "sum(t=0..T-1, x_t^T I x_t + u_t^2) + x_T^T I x_T",
            "nominal_surrogate_formula": "same sum evaluated on z_t and v_t",
            "nominal_surrogate_cost": encode(nominal_surrogate),
            "worst_case_actual_cost": encode(worst),
            "worst_case_witness_count": len(witnesses),
            "worst_case_witnesses": [row["disturbances"] for row in witnesses],
            "cost_gap": encode(worst - nominal_surrogate),
            "continuous_box_maximum_argument": "The cost is a convex quadratic in the complete disturbance vector because it is a sum of squared affine state and input coordinates. A convex function on a compact box attains a maximum at some vertex; exact enumeration of all 2^T vertices therefore gives the exact maximum over the continuous disturbance box.",
        },
        "vertex_paths": rows,
        "coverage": {
            "disturbance_vertices_checked": len(rows),
            "expected_vertices": 2 ** horizon,
            "all_vertex_paths_satisfy_state_and_input_constraints": True,
            "stagewise_disturbance_box": [encode(value) for value in bounds],
        },
        "measurement": {"performed": False, "reason": "exact rational enumeration, not a timing experiment"},
        "limitations": [
            "one fixed zero nominal plan and one fixed ancillary gain; neither was optimized",
            "the exact worst-case cost is a policy-specific finite-horizon value, not a fixed-plan minimax value or a globally optimal causal value",
            "no terminal invariance or asymptotic stability claim is made",
            "approximation comparisons remain gated by issues 99 and 100",
            "the feedback policy assumes exact full-state observation before each input",
        ],
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "scenario.json").write_bytes(SCENARIO_PATH.read_bytes())
    result = analyze()
    (OUTPUT / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"case_id": result["case_id"],
                      "nominal_surrogate_cost": result["objective"]["nominal_surrogate_cost"],
                      "worst_case_actual_cost": result["objective"]["worst_case_actual_cost"],
                      "vertices": result["coverage"]["disturbance_vertices_checked"]}, sort_keys=True))


if __name__ == "__main__":
    main()
