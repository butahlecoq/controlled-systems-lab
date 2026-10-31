#!/usr/bin/env python3
"""Exact fixture and emitted-relation checks for CONSTRAINT-01."""
from __future__ import annotations
import argparse, hashlib, json, math
from fractions import Fraction
from pathlib import Path

CASES = {f"r{rows}": rows for rows in (2, 4, 8)}
STRATEGIES = {"csl.synthesis.reach-back", "csl.synthesis.strategy-b"}
BASE = {
    "schema": "csl.scenario/1", "horizon": 2,
    "model": {"kind": "linear_discrete", "A": [[1]], "B": [[1]]},
    "initial_state": [0],
    "controls": {"kind": "box", "lower": [0], "upper": [1]},
    "objective": {"kind": "linear", "coefficients": [1]},
    "metadata": {"state_labels": ["x1"], "control_labels": ["u1"],
                 "state_units": ["dimensionless"], "control_units": ["dimensionless"]}}

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def q(value: object) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("H coefficients and bounds must be finite JSON numbers")
    return Fraction.from_float(value) if isinstance(value, float) else Fraction(value)

def canon(row: list[object], equality: bool = False) -> tuple[Fraction, ...]:
    values = tuple(q(value) for value in row)
    if not any(values):
        raise ValueError("zero H row")
    scale = abs(next(value for value in values if value))
    values = tuple(value / scale for value in values)
    if equality and next(value for value in values if value) < 0:
        values = tuple(-value for value in values)
    return values

def hrow(width: int, terms: dict[int, int], rhs: int = 0) -> list[int]:
    row = [0] * (width + 1)
    for index, value in terms.items():
        row[index] = value
    row[-1] = rhs
    return row

def authored_rows(count: int) -> tuple[list[list[int | float]], list[int | float]]:
    rows: list[list[int | float]] = [[1], [-1]]
    bounds: list[int | float] = [2, 2]
    if count >= 4:
        rows.extend([[2], [-2]])
        bounds.extend([5, 5])
    if count >= 8:
        rows.extend([[0.5], [-0.5], [3], [-3]])
        bounds.extend([1.5, 1.5, 9, 9])
    return rows, bounds

def expected_fixture(count: int) -> dict[str, object]:
    h, bounds = authored_rows(count)
    stage_set = {"kind": "polyhedron_h", "H": h, "h": bounds,
                 "E": {"rows": 0, "cols": 1, "values": []}, "e": []}
    return {**BASE, "id": f"review05-constraint01-n1-t2-r{count}",
            "states": {"kind": "stages", "values": [stage_set, stage_set, stage_set]}}

def expected_relation_rows() -> tuple[int, set[tuple[Fraction, ...]], set[tuple[Fraction, ...]]]:
    # Joint order is x[0], x[1], x[2], u[0], u[1].
    width = 5
    equalities = {
        canon(hrow(width, {0: 1}), True),
        canon(hrow(width, {1: 1, 0: -1, 3: -1}), True),
        canon(hrow(width, {2: 1, 1: -1, 4: -1}), True),
        canon(hrow(width, {2: 1}), True),  # attained objective x[2] = 0
    }
    inequalities = set()
    for index in (3, 4):
        inequalities.add(canon(hrow(width, {index: -1})))
        inequalities.add(canon(hrow(width, {index: 1}, 1)))
    for index in (0, 1, 2):
        inequalities.add(canon(hrow(width, {index: 1}, 2)))
        inequalities.add(canon(hrow(width, {index: -1}, 2)))
    return width, equalities, inequalities

def verify_attempt(attempt: dict[str, object], expected_hash: str) -> tuple[str, list[str]]:
    try:
        result = attempt["result"]
        if attempt.get("process_status") != "completed" or not isinstance(result, dict):
            return "unavailable", ["process did not complete with parseable JSON"]
        receipt = attempt.get("resource_receipt")
        if not isinstance(receipt, dict) or receipt.get("receipt_source") != "POSIX wait4(RUSAGE_CHILDREN) for this isolated child":
            raise ValueError("missing per-process wait4 resource receipt")
        for field in ("user_cpu_seconds", "system_cpu_seconds", "child_cpu_seconds", "peak_rss_kib"):
            if (not isinstance(receipt.get(field), (int, float)) or
                    not math.isfinite(receipt[field]) or receipt[field] < 0):
                raise ValueError(f"invalid resource receipt field: {field}")
        if not math.isclose(receipt["child_cpu_seconds"],
                            receipt["user_cpu_seconds"] + receipt["system_cpu_seconds"],
                            rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("resource receipt CPU total is inconsistent")
        if receipt.get("timed_out") is not False:
            raise ValueError("completed attempt has timed-out resource receipt")
        count = CASES[str(attempt["case"])]
        if attempt.get("state_rows_per_stage") != count or attempt.get("authored_state_rows_total") != 3 * count:
            raise ValueError("attempt row count differs from the fixed fixture case")
        if result.get("schema") != "csl.review05.dimension-attempt/1" or result.get("fixture") != "CONSTRAINT-01-redundant-state-H-rows":
            raise ValueError("wrong driver result schema or fixture")
        if result.get("scenario_sha256") != expected_hash or result.get("horizon") != 2:
            raise ValueError("scenario identity or horizon mismatch")
        if result.get("strategy") != attempt.get("strategy") or result.get("strategy") not in STRATEGIES:
            raise ValueError("strategy identity mismatch")
        if result.get("target") != "candidate_relaxation" or result.get("assurance") != "numerical":
            raise ValueError("unexpected request target or assurance")
        if result.get("termination") != "completed":
            return "inconclusive", [f"strategy termination: {result.get('termination')}"]
        coords = result.get("candidate_coordinates")
        if coords != {"state_dimension": 1, "control_dimension": 1, "external_dimension": 0, "horizon": 2}:
            raise ValueError("candidate coordinate dimensions mismatch")
        relation = result.get("candidate_relation")
        if not isinstance(relation, dict):
            return "inconclusive", ["strategy returned no recordable candidate H-relation"]
        width, expected_eq, expected_le = expected_relation_rows()
        if relation.get("dimension") != width:
            raise ValueError("candidate relation has wrong joint dimension")
        ineq, ub = relation.get("inequalities"), relation.get("upper_bounds")
        eq, ev = relation.get("equalities"), relation.get("equality_values")
        if not all(isinstance(value, list) for value in (ineq, ub, eq, ev)):
            raise ValueError("malformed H representation")
        if len(ineq) != len(ub) or len(eq) != len(ev):
            raise ValueError("H row and bound counts differ")
        if any(not isinstance(row, list) or len(row) != width for row in ineq + eq):
            raise ValueError("H row width mismatch")
        seen_eq = {canon(row + [bound], True) for row, bound in zip(eq, ev)}
        seen_le = {canon(row + [bound]) for row, bound in zip(ineq, ub)}
        if not expected_eq <= seen_eq:
            raise ValueError("initial, dynamics, or attained objective equality missing")
        if not expected_le <= seen_le:
            raise ValueError("control or common state-box rows missing")
        zero = [0] * width
        if any(sum(q(a) * b for a, b in zip(row, zero)) > q(bound) for row, bound in zip(ineq, ub)):
            raise ValueError("zero history violates an emitted inequality")
        if any(sum(q(a) * b for a, b in zip(row, zero)) != q(bound) for row, bound in zip(eq, ev)):
            raise ValueError("zero history violates an emitted equality")
        for field in ("objective_lower", "objective_upper"):
            bound = result.get(field)
            if bound is not None and q(bound) != 0:
                raise ValueError(f"reported {field} differs from the exact zero optimum")
        incumbents = result.get("incumbents")
        if not isinstance(incumbents, list):
            raise ValueError("malformed incumbent list")
        if any(not isinstance(item, dict) or item.get("states") != [[0], [0], [0]] or
               item.get("controls") != [[0], [0]] or item.get("original_objective") != 0
               for item in incumbents):
            raise ValueError("incumbent contradicts the exact zero history")
        return "verified", ["exact fixture oracle checks initial/dynamics/control/state rows, attained zero objective, and zero-history feasibility"]
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError) as error:
        return "incorrect", [str(error)]

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    args = parser.parse_args()
    bundle = args.bundle.resolve(strict=True)
    manifest = json.loads((bundle / "manifest.json").read_text())
    if manifest.get("schema") != "csl.review05.constraint-manifest/1":
        parser.error("wrong manifest schema")
    attempts = [json.loads(line) for line in (bundle / "attempts.jsonl").read_text().splitlines() if line]
    expected_keys = {(key, rep, pos) for key in CASES for rep in range(7) for pos in (0, 1)}
    observed = {(row.get("case"), row.get("repetition"), row.get("order_position")) for row in attempts}
    if len(attempts) != 42 or observed != expected_keys or len({row.get("attempt_id") for row in attempts}) != 42:
        parser.error("incomplete 42-attempt schedule")
    expected_order = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")
    for row in attempts:
        count = CASES.get(row.get("case"))
        if count is None:
            parser.error("unknown case in attempts")
        if row.get("warmup") is not (row.get("repetition") == 0):
            parser.error("warmup flag must be true exactly for repetition zero")
        first = (row["repetition"] + count // 2) % 2
        if row.get("strategy") != expected_order[(first + row["order_position"]) % 2]:
            parser.error("strategy order violates alternating schedule")
    checks = []
    for key, count in CASES.items():
        path = bundle / "inputs" / f"constraint01-n1-t2-r{count}.json"
        if not path.is_file() or sha(path) != manifest["cases"][key]["scenario_sha256"]:
            parser.error(f"fixture hash mismatch: {key}")
        fixture = json.loads(path.read_text())
        if fixture != expected_fixture(count):
            parser.error(f"fixture differs from the independent authored-data oracle: {key}")
        rows, bounds = authored_rows(count)
        if len(rows) != count or len(bounds) != count or any(
            q(coefficient[0]) * 2 > q(bound) if coefficient[0] > 0 else -q(coefficient[0]) * 2 > q(bound)
            for coefficient, bound in zip(rows[2:], bounds[2:])
        ):
            parser.error(f"added H rows are not redundant over the common [-2,2] state set: {key}")
    for row in attempts:
        expected_hash = manifest["cases"][row["case"]]["scenario_sha256"]
        status, reasons = verify_attempt(row, expected_hash)
        for field in ("stdout", "stderr"):
            path = bundle / str(row.get(f"{field}_path", ""))
            if not path.is_file() or sha(path) != row.get(f"{field}_sha256"):
                status, reasons = "incorrect", [f"{field} artifact missing or hash mismatch"]
                break
        checks.append({"attempt_id": row.get("attempt_id"), "case": row.get("case"),
                       "strategy": row.get("strategy"), "warmup": row.get("warmup"),
                       "status": status, "reasons": reasons})
    (bundle / "checks.jsonl").write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in checks))
    counts = {status: sum(row["status"] == status for row in checks)
              for status in ("verified", "inconclusive", "incorrect", "unavailable")}
    print(json.dumps({"attempts": len(checks), "statuses": counts}, indent=2))
    return int(counts["incorrect"] > 0 or counts["verified"] == 0)

if __name__ == "__main__":
    raise SystemExit(main())
