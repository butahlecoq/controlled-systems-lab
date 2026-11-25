#!/usr/bin/env python3
"""Independently check full-state dynamics, constraints and objectives in a saved 1012 capture."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import pathlib
from datetime import datetime, timezone


ROOT = pathlib.Path(__file__).resolve().parents[2]


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def matrix(rows: int, columns: int) -> list[list[float]]:
    return [[0.0 for _ in range(columns)] for _ in range(rows)]


def read_model_data(path: pathlib.Path) -> dict[str, dict[str, object]]:
    models: dict[str, dict[str, object]] = {}
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            ident, kind = row["model"], row["kind"]
            data = models.setdefault(ident, {})
            r, c, value = int(row["row"]), int(row["column"]), float(row["value"])
            if kind in {"A", "B", "G"}:
                rows = max(r + 1, len(data.get(kind, [])))
                cols = max(c + 1, max((len(line) for line in data.get(kind, [])), default=0))
                previous = data.get(kind)
                if previous is not None:
                    rows = max(rows, len(previous))
                    cols = max(cols, max((len(line) for line in previous), default=0))
                result = matrix(rows, cols)
                if previous is not None:
                    for i, line in enumerate(previous):
                        result[i][: len(line)] = line
                result[r][c] = value
                data[kind] = result
            else:
                vector = data.setdefault(kind, [])
                while len(vector) <= r:
                    vector.append(0.0)
                vector[r] = value
    return models


def close(a: float, b: float, atol: float = 2e-6) -> bool:
    return abs(a - b) <= atol * max(1.0, abs(a), abs(b))


def mat_vec(a: list[list[float]], x: list[float]) -> list[float]:
    return [sum(value * x[j] for j, value in enumerate(row)) for row in a]


def add(*vectors: list[float]) -> list[float]:
    return [sum(vector[i] for vector in vectors) for i in range(len(vectors[0]))]


def as_record(path: pathlib.Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


EXPECTED_IDS = {f"catalogue-2026/model-{i}/1" for i in range(1, 36)}
EXPECTED_REFUSALS = {f"catalogue-2026/model-{i}/1" for i in (23, 27, 28)}
REFUSAL_TEXT = "nonzero coefficient at or below native removal threshold 1e-12"


def validate_partition(outcomes: list[dict[str, object]]) -> None:
    ids = [str(item.get("model", "")) for item in outcomes]
    if len(ids) != len(set(ids)) or set(ids) != EXPECTED_IDS:
        raise ValueError("capture must contain each of the 35 exact catalogue identities once")
    for item in outcomes:
        expected = "failed" if item["model"] in EXPECTED_REFUSALS else "completed"
        if item.get("status") != expected:
            raise ValueError(f"{item['model']}: expected verified status {expected}, got {item.get('status')}")


def validate_attempt(case_dir: pathlib.Path, outcome: dict[str, object]) -> None:
    attempt = as_record(case_dir / "attempt.json")
    if attempt.get("status") != outcome.get("status"):
        raise ValueError(f"{outcome['model']}: attempt and manifest statuses disagree")
    for stream in ("stdout", "stderr"):
        actual = sha256(case_dir / f"{stream}.log")
        if attempt.get(f"{stream}_sha256") != actual:
            raise ValueError(f"{outcome['model']}: {stream} digest does not match attempt record")
    expected_code = 1 if outcome["model"] in EXPECTED_REFUSALS else 0
    if attempt.get("returncode") != expected_code:
        raise ValueError(f"{outcome['model']}: unexpected native return code")
    if outcome["model"] in EXPECTED_REFUSALS:
        diagnostic = (case_dir / "stderr.log").read_text(encoding="utf-8")
        if REFUSAL_TEXT not in diagnostic:
            raise ValueError(f"{outcome['model']}: expected native coefficient-threshold refusal is absent")


def mutation_guard(outcomes: list[dict[str, object]]) -> None:
    """Prove that identity/status mutations are refused before checking saved values."""
    mutations = []
    unknown = [dict(row) for row in outcomes] + [{"model": "catalogue-2026/model-36/1", "status": "completed"}]
    mutations.append(unknown)
    timeout = [dict(row) for row in outcomes]
    timeout[0]["status"] = "timed_out"
    mutations.append(timeout)
    missing = [dict(row) for row in outcomes if row["model"] != "catalogue-2026/model-1/1"]
    mutations.append(missing)
    duplicate = [dict(row) for row in outcomes] + [dict(outcomes[0])]
    mutations.append(duplicate)
    for changed in mutations:
        try:
            validate_partition(changed)
        except (KeyError, ValueError):
            continue
        raise ValueError("mutation guard accepted an altered capture outcome partition")


def values_for(rows: list[dict[str, str]], kind: str, replan: int, stage: int,
               coordinate_count: int) -> list[float]:
    found: dict[int, float] = {}
    for row in rows:
        if row["kind"] == kind and int(row["replan"]) == replan and int(row["stage"]) == stage:
            coordinate, value = int(row["coordinate"]), float(row["value"])
            if coordinate in found and not close(found[coordinate], value, 1e-12):
                raise ValueError(f"Conflicting repeated {kind} coordinate")
            found[coordinate] = value
    if len(found) != coordinate_count or set(found) != set(range(coordinate_count)):
        raise ValueError(f"Incomplete {kind} record at replan={replan}, stage={stage}")
    return [found[i] for i in range(coordinate_count)]


def scalar_for(rows: list[dict[str, str]], kind: str, replan: int) -> float:
    matches = [float(row["value"]) for row in rows
               if row["kind"] == kind and int(row["replan"]) == replan]
    if len(matches) != 1:
        raise ValueError(f"Expected one {kind} value in replan {replan}, found {len(matches)}")
    return matches[0]


def source_cost(states: list[list[float]], controls: list[list[float]]) -> float:
    result = 0.0
    for k, state in enumerate(states):
        for i, value in enumerate(state):
            weight = 10.0 if i in (2, 3, 4, 5) else 5.0 if i in (9, 10, 11) else 0.0
            target = 1.0 if i == 2 else 0.0
            result += weight * (value - target) ** 2
        if k < len(controls):
            result += 0.1 * sum(value * value for value in controls[k])
    return result


def check_source21(rows: list[dict[str, str]], data: dict[str, object]) -> dict[str, object]:
    nx, nu, horizon, replans = len(data["x0"]), len(data["B"][0]), 10, 15
    a, b = data["A"], data["B"]
    previous_observed = list(data["x0"])
    transition_checks = 0
    max_dynamics_residual = 0.0
    max_objective_residual = 0.0
    trajectory: list[tuple[int, list[float]]] = []
    objectives: list[float] = []
    realized_costs: list[float] = []
    for replan in range(replans):
        observed = values_for(rows, "observed_state", replan, 0, nx)
        trajectory.append((replan, observed))
        if any(not close(x, y) for x, y in zip(observed, previous_observed)):
            raise ValueError(f"source21 observed state did not carry into replan {replan}")
        states = [values_for(rows, "predicted_state", replan, k, nx) for k in range(horizon + 1)]
        controls = [values_for(rows, "predicted_control", replan, k, nu) for k in range(horizon)]
        if any(not close(x, y) for x, y in zip(states[0], observed)):
            raise ValueError(f"source21 initial binding failed at replan {replan}")
        for k in range(horizon):
            expected = add(mat_vec(a, states[k]), mat_vec(b, controls[k]))
            residual = max(abs(x - y) for x, y in zip(expected, states[k + 1]))
            max_dynamics_residual = max(max_dynamics_residual, residual)
            transition_checks += 1
            if any(not close(x, y, 2e-6) for x, y in zip(expected, states[k + 1])):
                raise ValueError(f"source21 dynamics failed at replan={replan}, stage={k}")
            angle_bound = math.pi / 6.0
            if any(x < -angle_bound - 1e-6 or x > angle_bound + 1e-6 for x in (states[k][0], states[k][1])):
                raise ValueError(f"source21 attitude bound failed at replan={replan}, stage={k}")
            if states[k][5] < -1.000001 or any(u < -0.9916 - 1e-6 or u > 2.4084 + 1e-6 for u in controls[k]):
                raise ValueError(f"source21 state/input bound failed at replan={replan}, stage={k}")
        if (any(x < -math.pi / 6.0 - 1e-6 or x > math.pi / 6.0 + 1e-6 for x in states[horizon][:2])
                or states[horizon][5] < -1.000001):
            raise ValueError("source21 terminal state bound failed")
        literal = source_cost(states, controls)
        compiled = scalar_for(rows, "program_plan_cost", replan)
        saved_independent = scalar_for(rows, "independent_plan_cost", replan)
        max_objective_residual = max(max_objective_residual, abs(literal - compiled), abs(literal - saved_independent))
        if not close(literal, compiled, 1e-6) or not close(literal, saved_independent, 1e-6):
            raise ValueError(f"source21 objective mismatch at replan={replan}")
        objectives.append(literal)
        applied = values_for(rows, "applied_control", replan, 0, nu)
        if any(not close(applied[i], controls[0][i]) for i in range(nu)):
            raise ValueError("source21 applied first control differs from plan")
        state_cost = 0.0
        for i, value in enumerate(observed):
            weight = 10.0 if i in (2, 3, 4, 5) else 5.0 if i in (9, 10, 11) else 0.0
            target = 1.0 if i == 2 else 0.0
            state_cost += weight * (value - target) ** 2
        realized = state_cost + 0.1 * sum(value * value for value in applied)
        if not close(realized, scalar_for(rows, "realized_running_cost", replan), 1e-6):
            raise ValueError(f"source21 realized stage cost mismatch at replan={replan}")
        realized_costs.append(realized)
        expected_next = add(mat_vec(a, observed), mat_vec(b, applied))
        next_observed = values_for(rows, "observed_next_state", replan, 1, nx)
        if any(not close(x, y) for x, y in zip(expected_next, next_observed)):
            raise ValueError(f"source21 plant step mismatch at replan={replan}")
        previous_observed = next_observed
    trajectory.append((replans, previous_observed))
    return {"status": "passed", "replans": replans, "full_state_dynamics_transitions": transition_checks,
            "max_abs_dynamics_residual": max_dynamics_residual, "max_abs_objective_residual": max_objective_residual,
            "first_plan_objective": objectives[0], "last_plan_objective": objectives[-1],
            "total_realized_running_cost": sum(realized_costs),
            "trajectory": trajectory}


def check_authored(rows: list[dict[str, str]], data: dict[str, object]) -> dict[str, object]:
    nx, nu, horizon, replans = len(data["x0"]), len(data["B"][0]), 3, 3
    a, b = data["A"], data["B"]
    affine = list(data.get("a", [0.0] * nx))
    external = list(data.get("nominal_w", []))
    if data.get("G") and external:
        affine = add(affine, mat_vec(data["G"], external))
    weights = [1.0 / max(1.0, abs(x)) ** 2 for x in data["x0"]]
    previous_observed = list(data["x0"])
    transitions = 0
    max_dynamics_residual = max_objective_residual = 0.0
    trajectory: list[tuple[int, list[float]]] = []
    objectives: list[float] = []
    realized_costs: list[float] = []
    for replan in range(replans):
        observed = values_for(rows, "observed_state", replan, 0, nx)
        if any(not close(x, y) for x, y in zip(observed, previous_observed)):
            raise ValueError(f"authored observed state did not carry into replan {replan}")
        states = [values_for(rows, "predicted_state", replan, k, nx) for k in range(horizon + 1)]
        controls = [values_for(rows, "predicted_control", replan, k, nu) for k in range(horizon)]
        if replan == 0:
            trajectory.append((0, observed))
        if any(not close(x, y) for x, y in zip(states[0], observed)):
            raise ValueError(f"authored initial binding failed at replan {replan}")
        for k in range(horizon):
            expected = add(mat_vec(a, states[k]), mat_vec(b, controls[k]), affine)
            residual = max(abs(x - y) for x, y in zip(expected, states[k + 1]))
            max_dynamics_residual = max(max_dynamics_residual, residual)
            transitions += 1
            if any(not close(x, y) for x, y in zip(expected, states[k + 1])):
                raise ValueError(f"authored dynamics failed at replan={replan}, stage={k}")
            if any(u < -1.000001 or u > 1.000001 for u in controls[k]):
                raise ValueError(f"authored actuator bounds failed at replan={replan}, stage={k}")
        literal = 0.0
        for k, state in enumerate(states[:-1]):
            literal += sum(weights[i] * state[i] ** 2 for i in range(nx))
            literal += 0.02 * sum(value * value for value in controls[k])
        literal += 5.0 * sum(weights[i] * states[-1][i] ** 2 for i in range(nx))
        compiled = scalar_for(rows, "compiled_plan_cost", replan)
        saved_independent = scalar_for(rows, "independent_plan_cost", replan)
        max_objective_residual = max(max_objective_residual, abs(literal - compiled), abs(literal - saved_independent))
        if not close(literal, compiled, 1e-6) or not close(literal, saved_independent, 1e-6):
            raise ValueError(f"authored objective mismatch at replan={replan}")
        objectives.append(literal)
        applied = values_for(rows, "applied_control", replan, 0, nu)
        if any(not close(applied[i], controls[0][i]) for i in range(nu)):
            raise ValueError("authored applied first control differs from plan")
        observed_cost = sum(weights[i] * observed[i] ** 2 for i in range(nx)) + 0.02 * sum(x * x for x in applied)
        saved_running = scalar_for(rows, "realized_running_cost", replan)
        if not close(observed_cost, saved_running, 1e-6):
            raise ValueError("authored realized running cost mismatch")
        realized_costs.append(observed_cost)
        expected_next = add(mat_vec(a, observed), mat_vec(b, applied), affine)
        next_observed = values_for(rows, "observed_next_state", replan, 1, nx)
        if any(not close(x, y) for x, y in zip(expected_next, next_observed)):
            raise ValueError(f"authored plant step mismatch at replan={replan}")
        previous_observed = next_observed
        trajectory.append((replan + 1, next_observed))
    return {"status": "passed", "replans": replans, "full_state_dynamics_transitions": transitions,
            "max_abs_dynamics_residual": max_dynamics_residual, "max_abs_objective_residual": max_objective_residual,
            "first_plan_objective": objectives[0], "last_plan_objective": objectives[-1],
            "total_realized_running_cost": sum(realized_costs),
            "trajectory": trajectory}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=pathlib.Path)
    parser.add_argument("--retry", type=pathlib.Path)
    args = parser.parse_args()
    capture = args.capture.resolve()
    manifest = as_record(capture / "manifest.json")
    models_file = capture / "catalogue-data/native-output/models.csv"
    data = read_model_data(models_file)
    validate_partition(manifest["outcomes"])
    mutation_guard(manifest["outcomes"])
    outcomes = {item["model"]: item for item in manifest["outcomes"]}
    output_parent = capture.parent
    analysis_name = "independent-checks-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    analysis = output_parent / analysis_name
    suffix = 0
    while analysis.exists():
        suffix += 1
        analysis = output_parent / f"{analysis_name}-{suffix:02d}"
    analysis.mkdir()
    checks: dict[str, object] = {}
    trajectory_rows: list[dict[str, object]] = []
    for number in range(1, 36):
        ident = f"catalogue-2026/model-{number}/1"
        status = outcomes[ident]["status"]
        case_dir = capture / f"model-{number:02d}"
        validate_attempt(case_dir, outcomes[ident])
        if status != "completed":
            error = (case_dir / "stderr.log").read_text(encoding="utf-8")
            small = [(abs(float(value)), kind) for kind in ("A", "B", "G")
                     for row in data[ident].get(kind, []) for value in row
                     if value != 0.0 and abs(float(value)) <= 1e-12]
            if not small:
                raise ValueError(f"{ident}: refusal has no nonzero catalogue matrix coefficient at or below 1e-12")
            checks[ident] = {"status": "failure_preserved", "attempt_status": status,
                             "stderr": error.strip(),
                             "smallest_nonzero_catalogue_matrix_coefficient": min(small)[0],
                             "coefficient_scope": "source catalogue A/B/G entry; solver diagnostic independently identifies its native matrix threshold"}
            continue
        try:
            if number == 21:
                trace_path = case_dir / "source21-output/plans.csv"
                with trace_path.open(newline="", encoding="utf-8") as stream:
                    rows = list(csv.DictReader(stream))
                result = check_source21(rows, data[ident])
            else:
                trace_path = case_dir / "tracking-output/trace.csv"
                with trace_path.open(newline="", encoding="utf-8") as stream:
                    rows = list(csv.DictReader(stream))
                result = check_authored(rows, data[ident])
            for stage, state in result.pop("trajectory"):
                trajectory_rows.append({"model": ident, "profile": "source21-literal" if number == 21 else "authored-zero-target-v1",
                                        "executed_step": stage,
                                        "coordinates": json.dumps(state, separators=(",", ":"))})
            checks[ident] = result
        except Exception as error:  # preserve each check outcome and continue through all cases
            checks[ident] = {"status": "checker_error", "message": str(error)}

    with (analysis / "full_state_trajectory_checked.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["model", "profile", "executed_step", "coordinates"])
        writer.writeheader()
        writer.writerows(trajectory_rows)
    with (analysis / "independent_results.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["model", "status", "profile", "state_dimension", "control_dimension", "replans",
                  "first_plan_objective", "last_plan_objective", "total_realized_running_cost",
                  "max_abs_dynamics_residual", "max_abs_objective_residual", "failure"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for ident, result in checks.items():
            model_number = int(ident.split("/")[1].split("-")[1])
            row = {"model": ident, "status": result["status"],
                   "profile": "source21 literal" if model_number == 21 else "authored nominal tracking",
                   "state_dimension": len(data[ident]["x0"]),
                   "control_dimension": len(data[ident]["B"][0]),
                   "failure": result.get("stderr", result.get("message", ""))}
            row.update({key: result.get(key, "") for key in fields[5:]})
            writer.writerow(row)
    summary = {
        "schema": "csl.1012-native-model-tracking-independent-checks/1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "capture": str(capture),
        "capture_manifest_sha256": sha256(capture / "manifest.json"),
        "checker_source_sha256": sha256(pathlib.Path(__file__).resolve()),
        "model_data_sha256": sha256(models_file),
        "checks": checks,
        "verified_reported_partition": "exactly 32 completed and exactly models 23, 27, 28 failed with native coefficient-threshold refusal; attempt status and stdout/stderr hashes validated",
        "mutation_guard": "rejected unknown identity, timeout substitution, missing identity, and duplicate identity",
        "counts": {
            "independent_check_passed": sum(item.get("status") == "passed" for item in checks.values()),
            "native_outcomes_failure_preserved": sum(item.get("status") == "failure_preserved" for item in checks.values()),
            "checker_errors": sum(item.get("status") == "checker_error" for item in checks.values()),
            "full_state_dynamics_transitions_checked": sum(item.get("full_state_dynamics_transitions", 0) for item in checks.values()),
        },
    }
    if args.retry:
        retry = args.retry.resolve()
        retry_manifest = as_record(retry / "manifest.json")
        summary["capability_retries"] = {
            "capture": str(retry),
            "capture_manifest_sha256": sha256(retry / "manifest.json"),
            "outcomes": [
                {"model": row["model"], "status": row["status"],
                 "diagnostic": (retry / f"model-{int(row['model'].split('/')[1].split('-')[1]):02d}" / "stderr.log").read_text(encoding="utf-8").strip()}
                for row in retry_manifest["outcomes"]
            ],
        }
    (analysis / "checks.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"analysis": str(analysis), "counts": summary["counts"]}, sort_keys=True))
    return int(summary["counts"]["checker_errors"] != 0 or summary["counts"]["independent_check_passed"] != 32
               or summary["counts"]["native_outcomes_failure_preserved"] != 3)


if __name__ == "__main__":
    raise SystemExit(main())
