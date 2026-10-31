#!/usr/bin/env python3
"""Check saved HORIZON-01 attempts against literal scalar-integrator facts."""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path


STRATEGIES = {"csl.synthesis.reach-back", "csl.synthesis.strategy-b"}
EXPECTED_HORIZONS = {2, 4, 8}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rational(value: object) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("H rows and bounds must be finite JSON numbers")
    return Fraction.from_float(float(value)) if isinstance(value, float) else Fraction(value)


def canonical(row: list[object], equality: bool) -> tuple[Fraction, ...]:
    values = tuple(rational(value) for value in row)
    if not any(values):
        raise ValueError("zero H row is not a required literal")
    first = next(value for value in values if value)
    scale = abs(first)
    normalized = tuple(value / scale for value in values)
    if equality and next(value for value in normalized if value) < 0:
        normalized = tuple(-value for value in normalized)
    return normalized


def required_rows(horizon: int, labels: list[str]) -> tuple[set[tuple[Fraction, ...]], set[tuple[Fraction, ...]]]:
    dimension = 2 * horizon + 1
    if len(labels) not in (0, dimension) or (labels and len(set(labels)) != dimension):
        raise ValueError(f"expected zero or {dimension} unique joint-history labels")
    equalities: set[tuple[Fraction, ...]] = set()
    inequalities: set[tuple[Fraction, ...]] = set()

    def row(terms: dict[int, int], rhs: int) -> list[int]:
        result = [0] * (dimension + 1)
        for index, coefficient in terms.items():
            result[index] = coefficient
        result[-1] = rhs
        return result

    state_width = horizon + 1
    equalities.add(canonical(row({0: 1}, 0), True))
    for step in range(horizon):
        control_index = state_width + step
        equalities.add(canonical(row({step + 1: 1, step: -1, control_index: -1}, 0), True))
        lower = row({control_index: -1}, 0)  # -u <= 0
        upper = row({control_index: 1}, 1)   #  u <= 1
        inequalities.add(canonical(lower, False))
        inequalities.add(canonical(upper, False))
    return equalities, inequalities


def check_attempt(attempt: dict[str, object], expected_hash: str) -> tuple[str, list[str]]:
    reasons: list[str] = []
    horizon = attempt.get("horizon")
    result = attempt.get("result")
    if attempt.get("process_status") != "completed" or not isinstance(result, dict):
        return "unavailable", [f"process status: {attempt.get('process_status')}"]
    try:
        if result.get("schema") != "csl.review05.horizon-attempt/1":
            raise ValueError("wrong attempt schema")
        if result.get("fixture") != "HORIZON-01-scalar-integrator" or horizon not in EXPECTED_HORIZONS:
            raise ValueError("fixture or horizon mismatch")
        if result.get("horizon") != horizon or result.get("scenario_sha256") != expected_hash:
            raise ValueError("result horizon or fixture hash mismatch")
        if result.get("strategy") != attempt.get("strategy") or result.get("strategy") not in STRATEGIES:
            raise ValueError("strategy identity mismatch")
        observed_threads = result.get("observed_backend_threads", "missing")
        if observed_threads == "missing" or (observed_threads is not None and
                (not isinstance(observed_threads, int) or isinstance(observed_threads, bool) or observed_threads < 1)):
            raise ValueError("observed backend thread count must be a positive integer or explicit null")
        if result.get("target") != "candidate_relaxation" or result.get("assurance") != "numerical":
            raise ValueError("unexpected claim scope")
        if result.get("termination") != "completed":
            raise ValueError(f"solver termination {result.get('termination')}")
        coordinates = result.get("candidate_coordinates")
        if coordinates != {"state_dimension": 1, "control_dimension": 1, "external_dimension": 0,
                           "horizon": horizon}:
            raise ValueError("candidate coordinate dimensions mismatch")
        relation = result.get("candidate_relation")
        if relation is None:
            return "inconclusive", ["strategy completed without a recordable candidate H-relation"]
        if not isinstance(relation, dict) or relation.get("dimension") != 2 * horizon + 1:
            raise ValueError("candidate H-relation has wrong dimension")
        if result.get("objective_lower") not in (None, 0) or result.get("objective_upper") != 0:
            raise ValueError("available objective bounds do not match analytic optimum 0")
        labels = relation.get("labels")
        if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
            raise ValueError("joint-history labels are unavailable")
        eq_expected, ineq_expected = required_rows(horizon, labels)
        inequalities = relation.get("inequalities")
        upper_bounds = relation.get("upper_bounds")
        equalities = relation.get("equalities")
        equality_values = relation.get("equality_values")
        if not all(isinstance(value, list) for value in (inequalities, upper_bounds, equalities, equality_values)):
            raise ValueError("H-relation matrices or bounds are malformed")
        if len(inequalities) != len(upper_bounds) or len(equalities) != len(equality_values):
            raise ValueError("H-relation matrix and bound lengths differ")
        if any(not isinstance(row, list) or len(row) != relation["dimension"]
               for row in inequalities + equalities):
            raise ValueError("H-relation row width does not match its dimension")
        observed_eq = {canonical(list(row) + [rhs], True) for row, rhs in zip(equalities, equality_values)}
        observed_ineq = {canonical(list(row) + [rhs], False) for row, rhs in zip(inequalities, upper_bounds)}
        if not eq_expected <= observed_eq:
            raise ValueError("required initial-state/dynamics equalities are missing")
        if not ineq_expected <= observed_ineq:
            raise ValueError("required 0<=u<=1 inequalities are missing")
        zero = [0] * relation["dimension"]
        for row, rhs in zip(inequalities, upper_bounds):
            if sum(rational(a) * b for a, b in zip(row, zero)) > rational(rhs):
                raise ValueError("analytic zero history violates a candidate inequality")
        for row, rhs in zip(equalities, equality_values):
            if sum(rational(a) * b for a, b in zip(row, zero)) != rational(rhs):
                raise ValueError("analytic zero history violates a candidate equality")
        incumbents = result.get("incumbents")
        if not isinstance(incumbents, list) or not any(
            item.get("states") == [[0]] * (horizon + 1)
            and item.get("controls") == [[0]] * horizon
            and item.get("original_objective") == 0
            for item in incumbents if isinstance(item, dict)
        ):
            raise ValueError("analytic zero-history incumbent is absent")
        reasons.append("literal analytic optimum and required H rows verified; no family completeness claim")
        return "verified", reasons
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError) as error:
        return "incorrect", [str(error)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    args = parser.parse_args()
    bundle = args.bundle.resolve(strict=True)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    attempts = [json.loads(line) for line in (bundle / "attempts.jsonl").read_text(encoding="utf-8").splitlines() if line]
    checks = []
    if manifest.get("schema") != "csl.review05.horizon-manifest/1":
        parser.error("unsupported manifest schema")
    expected_hashes = manifest.get("scenario_sha256", {})
    for horizon, name in ((2, "horizon01-t02.json"), (4, "horizon01-t04.json"), (8, "horizon01-t08.json")):
        copied = bundle / "inputs" / name
        if not copied.is_file() or sha256(copied) != expected_hashes.get(str(horizon)):
            parser.error(f"copied fixture/hash mismatch for horizon {horizon}")
    expected_schedule = {
        (horizon, repetition, position)
        for horizon in EXPECTED_HORIZONS for repetition in range(7) for position in (0, 1)
    }
    observed_schedule = {(row.get("horizon"), row.get("repetition"), row.get("order_position")) for row in attempts}
    if len(attempts) != 42 or observed_schedule != expected_schedule or len({row.get("attempt_id") for row in attempts}) != 42:
        parser.error("attempts do not contain the complete 42-process schedule")
    strategy_order = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")
    for row in attempts:
        horizon, repetition, position = row["horizon"], row["repetition"], row["order_position"]
        first = horizon % 2 if repetition == 0 else (repetition + horizon // 2) % 2
        if row.get("strategy") != strategy_order[(first + position) % 2]:
            parser.error("attempt order does not match the alternating schedule")
    for attempt in attempts:
        horizon = attempt.get("horizon")
        expected_hash = manifest.get("scenario_sha256", {}).get(str(horizon), "")
        status, reasons = check_attempt(attempt, expected_hash)
        for field in ("stdout", "stderr"):
            path = bundle / str(attempt.get(f"{field}_path", ""))
            if not path.is_file() or sha256(path) != attempt.get(f"{field}_sha256"):
                status, reasons = "incorrect", [f"{field} artifact missing or hash mismatch"]
                break
        checks.append({"attempt_id": attempt.get("attempt_id"), "horizon": horizon,
                       "strategy": attempt.get("strategy"), "warmup": attempt.get("warmup"),
                       "status": status, "reasons": reasons})
    check_path = bundle / "checks.jsonl"
    with check_path.open("w", encoding="utf-8") as stream:
        for check in checks:
            stream.write(json.dumps(check, separators=(",", ":")) + "\n")
    counts: dict[str, int] = {}
    for check in checks:
        counts[check["status"]] = counts.get(check["status"], 0) + 1
    print(json.dumps({"attempts": len(checks), "statuses": counts, "checks": str(check_path)}, indent=2))
    return 0 if checks and counts.get("incorrect", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
