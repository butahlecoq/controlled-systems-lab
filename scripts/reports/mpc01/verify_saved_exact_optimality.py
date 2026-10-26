#!/usr/bin/env python3
"""Reconstruct saved MPC control candidates with exact rational arithmetic."""

import argparse
from collections import Counter
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from pathlib import Path


def q(value: object) -> Fraction:
    return Fraction(str(value))


def vector(values: list[object]) -> list[Fraction]:
    return [q(value) for value in values]


def matrix(values: list[list[object]]) -> list[list[Fraction]]:
    return [vector(row) for row in values]


@dataclass
class Case:
    case_id: str
    initial: list[Fraction]
    a: list[list[Fraction]]
    b: list[list[Fraction]]
    affine: list[Fraction]
    control_lower: list[Fraction]
    control_upper: list[Fraction]
    state_bounds: dict[int, dict[int, tuple[Fraction, Fraction]]]
    objective_kind: str
    q_matrix: list[list[Fraction]] | None
    linear: list[Fraction] | None
    offset: Fraction | None
    w_matrix: list[list[Fraction]] | None
    target: list[Fraction] | None
    optimal_lower_bound: Fraction
    bound_kind: str


def scalar_case(case_id: str, dynamics_a: Fraction, objective_q: Fraction,
                objective_linear: Fraction, objective_offset: Fraction,
                lower_bound: Fraction) -> Case:
    return Case(
        case_id=case_id,
        initial=[Fraction(0)],
        a=[[dynamics_a]],
        b=[[Fraction(1)]],
        affine=[Fraction(0)],
        control_lower=[Fraction(0)],
        control_upper=[Fraction(1)],
        state_bounds={},
        objective_kind="quadratic",
        q_matrix=[[objective_q]],
        linear=[objective_linear],
        offset=objective_offset,
        w_matrix=None,
        target=None,
        optimal_lower_bound=lower_bound,
        bound_kind="original_objective",
    )


def load_double_integrator(path: Path) -> Case:
    document = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    model = document["model"]
    objective = document["objective"]
    states = {}
    for stage, value in enumerate(document["states"]["values"]):
        if value["kind"] == "singleton":
            point = vector(value["point"])
            states[stage] = {i: (item, item) for i, item in enumerate(point)}
        elif value["kind"] == "box":
            lower, upper = vector(value["lower"]), vector(value["upper"])
            states[stage] = {i: (lower[i], upper[i]) for i in range(len(lower))}
    return Case(
        case_id="double-integrator-421-v1",
        initial=vector(document["initial_state"]),
        a=matrix(model["A"]),
        b=matrix(model["B"]),
        affine=[Fraction(0) for _ in document["initial_state"]],
        control_lower=vector(document["controls"]["lower"]),
        control_upper=vector(document["controls"]["upper"]),
        state_bounds=states,
        objective_kind="quadratic",
        q_matrix=matrix(objective["Q"]),
        linear=vector(objective["linear"]),
        offset=q(objective["offset"]),
        w_matrix=None,
        target=None,
        optimal_lower_bound=Fraction(0),
        bound_kind="original_objective",
    )


def load_b04(case_path: Path, reference_path: Path) -> Case:
    document = json.loads(case_path.read_text(encoding="utf-8"))
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    dynamics = document["dynamics"]
    dimensions = document["state_dimension"]
    a_flat = vector(dynamics["A_row_major"])
    a = [a_flat[i * dimensions:(i + 1) * dimensions] for i in range(dimensions)]
    b_flat = vector(dynamics["B"])
    b = [[value] for value in b_flat]
    objective = document["terminal_objective"]
    rows, cols = objective["matrix_rows"], objective["matrix_cols"]
    w_flat = vector(objective["W_row_major"])
    w = [w_flat[i * cols:(i + 1) * cols] for i in range(rows)]
    bounds = {}
    for stage in document["state_bound_stages"]:
        stage_bounds = {}
        for item in document["state_bounds_each_stage"]:
            stage_bounds[item["coordinate"]] = (q(item["lower"]), q(item["upper"]))
        bounds[stage] = stage_bounds
    return Case(
        case_id="b04-reference-v1",
        initial=vector(document["initial_state"]),
        a=a,
        b=b,
        affine=vector(dynamics["affine"]),
        control_lower=[q(document["control_bounds_each_stage"]["lower"])],
        control_upper=[q(document["control_bounds_each_stage"]["upper"])],
        state_bounds=bounds,
        objective_kind="residual_norm_squared",
        q_matrix=None,
        linear=None,
        offset=None,
        w_matrix=w,
        target=vector(objective["target"]),
        optimal_lower_bound=q(reference["exact_squared_norm_optimum_fraction"]),
        bound_kind="squared_original_norm",
    )


def fraction_json(value: Fraction) -> dict[str, str]:
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_objective(case: Case, terminal: list[Fraction]) -> Fraction:
    if case.objective_kind == "quadratic":
        assert case.q_matrix is not None and case.linear is not None and case.offset is not None
        quadratic = sum(terminal[i] * case.q_matrix[i][j] * terminal[j]
                        for i in range(len(terminal)) for j in range(len(terminal))) / 2
        return quadratic + sum(case.linear[i] * terminal[i] for i in range(len(terminal))) + case.offset
    assert case.w_matrix is not None and case.target is not None
    residual = [sum(case.w_matrix[i][j] * terminal[j] for j in range(len(terminal))) - case.target[i]
                for i in range(len(case.target))]
    return sum(value * value for value in residual)


def reconstruct(case: Case, controls: list[list[Fraction]]) -> tuple[list[list[Fraction]], Fraction]:
    if len(controls) == 0 or len(case.a) == 0 or len(case.b) == 0:
        raise ValueError("empty trajectory")
    states = [case.initial]
    for stage, control in enumerate(controls):
        if len(control) != len(case.control_lower):
            raise ValueError("control dimension mismatch")
        for i, value in enumerate(control):
            if value < case.control_lower[i] or value > case.control_upper[i]:
                raise ValueError(f"control bound violation at stage {stage}, coordinate {i}")
        current = states[-1]
        following = []
        for i in range(len(case.initial)):
            value = case.affine[i]
            value += sum(case.a[i][j] * current[j] for j in range(len(current)))
            value += sum(case.b[i][j] * control[j] for j in range(len(control)))
            following.append(value)
        states.append(following)
    for stage, bounds in case.state_bounds.items():
        if stage >= len(states):
            raise ValueError(f"state bound stage {stage} is outside the trajectory")
        for coordinate, (lower, upper) in bounds.items():
            if not lower <= states[stage][coordinate] <= upper:
                raise ValueError(f"state bound violation at stage {stage}, coordinate {coordinate}")
    return states, compute_objective(case, states[-1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--double-integrator", type=Path, required=True)
    parser.add_argument("--b04-case", type=Path, required=True)
    parser.add_argument("--b04-reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cases = {
        "ts01-exact-v1": scalar_case("ts01-exact-v1", Fraction(1), Fraction(2), Fraction(-2), Fraction(1), Fraction(0)),
        "ts02-constant-v1": scalar_case("ts02-constant-v1", Fraction(1), Fraction(0), Fraction(0), Fraction(3), Fraction(3)),
        "ts03-singular-v1": scalar_case("ts03-singular-v1", Fraction(0), Fraction(2), Fraction(-2), Fraction(1), Fraction(0)),
        "double-integrator-421-v1": load_double_integrator(args.double_integrator),
        "b04-reference-v1": load_b04(args.b04_case, args.b04_reference),
    }
    rows = [json.loads(line) for line in args.attempts.read_text(encoding="utf-8").splitlines() if line.strip()]
    output_rows = []
    checked = 0
    repetitions: Counter[tuple[str, str, str]] = Counter()
    for row in rows:
        key = (row["case_id"], row["method"], row["start_mode"])
        repetition = repetitions[key]
        repetitions[key] += 1
        if row["mathematical_outcome"] != "optimal":
            continue
        case = cases[row["case_id"]]
        raw_controls = row["trajectory"]["controls"]
        controls = [[Fraction.from_float(float(value)) for value in vector_row] for vector_row in raw_controls]
        states, candidate_value = reconstruct(case, controls)
        lower_bound = case.optimal_lower_bound
        if candidate_value < lower_bound:
            raise ValueError(f"exact objective is below the analytic lower bound for {case.case_id}")
        if case.case_id == "ts03-singular-v1" and (controls[0][0] < 0 or controls[0][0] > 1 or
                                                     (controls[1][0] - 1) ** 2 > Fraction(1, 10_000_000)):
            raise ValueError("T-S03 control is outside the exact optimal face to objective tolerance")
        exact_state_sha = hashlib.sha256(";".join(
            ",".join(f"{value.numerator}/{value.denominator}" for value in state) for state in states
        ).encode("ascii")).hexdigest()
        output_rows.append({
            "schema": "csl.mpc01-exact-candidate-check/1",
            "case_id": case.case_id,
            "method": row["method"],
            "start_mode": row["start_mode"],
            "repetition": repetition,
            "native_status": row["native_status"],
            "feasibility": "verified_exact_rational",
            "objective_quantity": case.bound_kind,
            "candidate_upper_bound": fraction_json(candidate_value),
            "analytic_lower_bound": fraction_json(lower_bound),
            "exact_gap": fraction_json(candidate_value - lower_bound),
            "reconstructed_state_sequence_sha256": exact_state_sha,
        })
        checked += 1
    if checked == 0:
        raise ValueError("no optimal native candidates were checked")
    args.output.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                                  for row in output_rows), encoding="utf-8")
    manifest = {
        "schema": "csl.mpc01-exact-check-manifest/1",
        "checker_source_sha256": sha256(Path(__file__)),
        "attempts_sha256": sha256(args.attempts),
        "comparison_records_sha256": sha256(args.records),
        "double_integrator_input_sha256": sha256(args.double_integrator),
        "b04_case_input_sha256": sha256(args.b04_case),
        "b04_exact_reference_sha256": sha256(args.b04_reference),
        "checks_sha256": sha256(args.output),
        "checked_optimal_candidates": checked,
        "arithmetic": "Python fractions.Fraction; input decimals/rationals parsed exactly, saved binary64 controls recovered as exact dyadic rationals",
    }
    manifest_path = args.output.with_name("exact-check-manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"verified exact feasibility and objective bounds for {checked} saved optimal candidates")


if __name__ == "__main__":
    main()
