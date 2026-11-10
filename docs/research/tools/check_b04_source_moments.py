#!/usr/bin/env python3
"""Build and verify the exact-rational B04 source-candidate certificate."""

from __future__ import annotations

import argparse
from decimal import Decimal, localcontext
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUTS = ROOT / "docs/research/evidence/b04-source-moment-inputs.json"
DEFAULT_CERTIFICATE = ROOT / "docs/research/evidence/b04-source-moment-certificate.json"
REACHABLE_SHA256 = "1f03dac9f0339dd7b518c9e0f0bae51047b766b1d9342e770b78d1563036e405"
PROGRAM_SHA256 = "43fa64b7539d2418512700fdbe83385a741f1615eee114b99cbde400d01dac78"
ARCHIVE_SHA256 = "d13b82f848002137cfab4682f1d6f69b9411b360f4078dec27fa0f54566c8453"
N = 16
H = F(25, 4)
BO = F(2208, 110)
BF = F(-1152, 110)
R = F(8, 3)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _q(value: F) -> str:
    return str(value)


def _dot(a: list[F], b: list[F]) -> F:
    return sum((x * y for x, y in zip(a, b)), F(0))


def _stock_inner(a: list[F], b: list[F]) -> F:
    """Polar form for x^2+y^2+(x-y)^2 in coordinates (x,y)."""
    return 2 * a[0] * b[0] + 2 * a[1] * b[1] - a[0] * b[1] - a[1] * b[0]


def _load(path: Path) -> dict:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load inputs {path}: {exc}") from exc
    if not isinstance(result, dict):
        raise ValueError("inputs must be a JSON object")
    return result


def load_inputs(path: Path = DEFAULT_INPUTS) -> dict:
    return _load(path)


def _validate_inputs(inputs: dict) -> None:
    """Reject semantic/profile edits instead of changing the certified case."""
    expected = {
        "schema": "b04.source-candidate.exact-global-inputs/1",
        "source": {
            "ReachableSets.m": {"collection": "dissertation-working-collection", "sha256": REACHABLE_SHA256, "bytes": 8941},
            "program.m": {"collection": "dissertation-working-collection", "sha256": PROGRAM_SHA256, "bytes": 3815},
            "archive_collection_sha256": ARCHIVE_SHA256,
            "archive_scope": "The archive hash and 45/45 registered-source identity matches attest the separately supplied original collection; they do not bind these changed dissertation-working-collection files to that ZIP or establish chronology.",
            "registered_source_count": 45,
            "identity_matches": 45,
            "attribution": "Recovered dissertation article-folder source candidate; exact historical generator revision and canonical attribution remain unknown",
        },
        "assumptions": {
            "arithmetic": "Source decimal inputs and coefficients are interpreted as exact rational numbers; this certifies a mathematical candidate model, not original floating-point execution.",
            "dynamics": "For k=0..15: q_o[k+1]=q_o[k]+(2208/110)u[k]; m_o[k+1]=m_o[k]-(25/4)q_o[k]; q_f[k+1]=q_f[k]-(1152/110)u[k]; m_f[k+1]=m_f[k]-(25/4)q_f[k].",
            "constraints": "Every one of 17 states has q_o in [1176,1224] and q_f in [432,468]; each of 16 shared controls is in [-1,1]. No stock-state constraints are included.",
            "criterion": "sqrt((1200-q_o[16])^2+m_o[16]^2+(64/9)(450-q_f[16])^2+(64/9)m_f[16]^2+(m_o[16]-(8/3)m_f[16])^2).",
            "initialization_identity": "The source-commented decimal initialization and active rounded initialization are separate candidate cases. The commented values are not attributed as the historical active run.",
            "rounding_band": "For a printed objective 30.899 rounded to 3 decimals, the exact predicate is 30.8985^2 <= minimum_squared < 30.8995^2; decimal square-root display is not an interval certificate.",
            "provenance_limit": "No claim is made about original floating solver optimality, original U values or row mapping, historical generator identity, publication-author intent, physical scaling authority, or nonlinear dynamics enclosure.",
        },
        "model": {
            "horizon": 16,
            "state_order": ["q_o", "m_o", "q_f", "m_f"],
            "state_units": ["kg/s", "kg", "kg/s", "kg"],
            "time_unit": "s",
            "step": "25/4", "B": ["2208/110", "0", "-1152/110", "0"],
            "control_bounds": ["-1", "1"],
            "flow_bounds": {"oxidizer": ["1176", "1224"], "fuel": ["432", "468"]},
            "stock_bounds": None,
            "objective_weights": ["1", "1", "64/9", "64/9", "1"],
            "objective_residuals": ["1200-q_o", "m_o", "450-q_f", "m_f", "m_o-(8/3)m_f"],
            "case_ids": {
                "commented_initial": "B04-SOURCE-COMMENTED-X0-V1",
                "active_rounded_initial": "B04-SOURCE-ACTIVE-X0-V1",
            },
            "initializations": {
                "commented_initial": ["1220.28265395983", "119500", "440.005764648976", "45300"],
                "active_rounded_initial": ["1220.283", "119500", "440.007", "45300"],
            },
        },
    }
    if inputs != expected:
        raise ValueError("input semantics/profile differ from the frozen B04 candidate specification")


def _family_constraints(lower: F, upper: F) -> dict:
    """Return H u <= b, with 32 box and 32 prefix-flow inequalities."""
    rows: list[dict] = []
    for j in range(N):
        row = [F(0)] * N
        row[j] = 1
        rows.append({"kind": "control_upper", "stage": j, "coefficients": list(map(_q, row)), "rhs": "1"})
        row = [F(0)] * N
        row[j] = -1
        rows.append({"kind": "control_lower", "stage": j, "coefficients": list(map(_q, row)), "rhs": "1"})
    for k in range(1, N + 1):
        row = [F(int(j < k)) for j in range(N)]
        rows.append({"kind": "prefix_upper", "stage": k, "coefficients": list(map(_q, row)), "rhs": _q(upper)})
        rows.append({"kind": "prefix_lower", "stage": k, "coefficients": list(map(_q, (-v for v in row))), "rhs": _q(-lower)})
    rank_minor = [[F(1), F(1)], [F(N - 1), F(0)]]
    determinant = rank_minor[0][0] * rank_minor[1][1] - rank_minor[0][1] * rank_minor[1][0]
    assert determinant == -15
    return {
        "convention": "H u <= b",
        "rows": rows,
        "row_count": len(rows),
        "control_dimension": N,
        "equalities": {
            "matrix": [["1"] * N, [str(N - 1 - j) for j in range(N)]],
            "rhs_names": ["sum_control", "weighted_control_sum"],
            "rank": 2,
            "rank_witness": {
                "columns": [0, 15],
                "minor": [["1", "1"], ["15", "0"]],
                "determinant": _q(determinant),
            },
        },
    }


def _state_lift(initial: list[F]) -> dict:
    """Affine state history x_k = offset_k + L_k u for stages 0..16."""
    lift = []
    for k in range(N + 1):
        offsets = [initial[0], initial[1] - H * k * initial[0], initial[2], initial[3] - H * k * initial[2]]
        matrix = [[F(0) for _ in range(N)] for _ in range(4)]
        for j in range(k):
            matrix[0][j] = BO
            matrix[2][j] = BF
        for j in range(max(0, k - 1)):
            weight = -H * (k - 1 - j)
            matrix[1][j] = weight * BO
            matrix[3][j] = weight * BF
        lift.append({"stage": k, "offset": list(map(_q, offsets)), "control_matrix": [list(map(_q, row)) for row in matrix]})
    return {"state_order": ["q_o", "m_o", "q_f", "m_f"], "stages": lift}


def _certify(initial_values: list[str], scenario_id: str) -> dict:
    initial = list(map(F, initial_values))
    qo, mo, qf, mf = initial
    flow_slopes = [BO, R * BF]
    flow_offsets = [qo - 1200, R * (qf - 450)]
    stock_slopes = [-H * BO, -R * H * BF]
    stock_offsets = [mo - N * H * qo, R * (mf - N * H * qf)]
    alpha, beta = _dot(flow_slopes, flow_slopes), _stock_inner(stock_slopes, stock_slopes)
    sum_control = -_dot(flow_slopes, flow_offsets) / alpha
    weighted = -_stock_inner(stock_slopes, stock_offsets) / beta
    lower = max((F(1176) - qo) / BO, (F(468) - qf) / BF)
    upper = min((F(1224) - qo) / BO, (F(432) - qf) / BF)

    first = F(-9, 10)
    middle = (weighted - first) / 14
    controls = [first, middle - first] + [F(0)] * 13 + [sum_control - middle]
    assert len(controls) == N and sum(controls) == sum_control
    assert sum((N - 1 - j) * u for j, u in enumerate(controls)) == weighted
    assert all(-1 < u < 1 for u in controls)

    states = [initial]
    prefixes = []
    total = F(0)
    for u in controls:
        q0, m0, q1, m1 = states[-1]
        states.append([q0 + BO * u, m0 - H * q0, q1 + BF * u, m1 - H * q1])
        total += u
        prefixes.append(total)
    assert all(lower < p < upper for p in prefixes)
    assert all(F(1176) < s[0] < F(1224) and F(432) < s[2] < F(468) for s in states)

    terminal = states[-1]
    residuals = [terminal[0] - 1200, terminal[1], R * (terminal[2] - 450), R * terminal[3], terminal[1] - R * terminal[3]]
    minimum_squared = _dot(residuals, residuals)
    constant = _dot(flow_offsets, flow_offsets) + _stock_inner(stock_offsets, stock_offsets)
    assert minimum_squared == constant - alpha * sum_control**2 - beta * weighted**2
    assert alpha > 0 and beta > 0
    with localcontext() as ctx:
        ctx.prec = 70
        minimum_decimal = str((Decimal(minimum_squared.numerator) / Decimal(minimum_squared.denominator)).sqrt())

    return {
        "scenario_id": scenario_id,
        "initial": list(map(_q, initial)),
        "sum_control": _q(sum_control),
        "weighted_control_sum": _q(weighted),
        "prefix_bounds": [_q(lower), _q(upper)],
        "quadratic_coefficients": [_q(alpha), _q(beta)],
        "quadratic_identity": "J(u)^2 = minimum_squared + alpha*(sum(u)-sum_control)^2 + beta*(weighted_sum(u)-weighted_control_sum)^2; stock quadratic uses [[2,-1],[-1,2]] in (m_o,8/3*m_f)",
        "minimum_squared": _q(minimum_squared),
        "minimum_decimal": minimum_decimal,
        "rounding_band_30_899": {
            "predicate": "30.8985^2 <= minimum_squared < 30.8995^2",
            "lower_holds": minimum_squared >= F("30.8985") ** 2,
            "upper_holds": minimum_squared < F("30.8995") ** 2,
        },
        "terminal": list(map(_q, terminal)),
        "interior_witness_controls": list(map(_q, controls)),
        "interior_witness_states": [list(map(_q, state)) for state in states],
        "all_constraints_exact": True,
        "optimal_family": {
            "control_dimension": N,
            "affine_dimension": 14,
            "equalities": ["sum(u_k)=sum_control", "sum((15-k)*u_k)=weighted_control_sum"],
            "inequalities": ["-1 <= u_k <= 1 for k=0..15", "lower <= sum(u_0..u_(k-1)) <= upper for k=1..16"],
            "H_matrix": _family_constraints(lower, upper),
            "state_histories": "Unique affine recurrence from initial state for each joint control history",
            "affine_state_history_lift": _state_lift(initial),
            "completeness": "Positive quadratic identity proves equality iff both moment equations hold; strict feasible witness proves relative interior and dimension14",
        },
    }


def build_certificate(inputs: dict) -> dict:
    _validate_inputs(inputs)
    profile_hash = hashlib.sha256(_canonical(inputs)).hexdigest()
    return {
        "schema": "b04.source-candidate.exact-global-certificate/1",
        "source_sha256": REACHABLE_SHA256,
        "source_hashes": {"ReachableSets.m": REACHABLE_SHA256, "program.m": PROGRAM_SHA256, "archive_collection": ARCHIVE_SHA256},
        "profile_sha256": profile_hash,
        "scope": "Exact decimal/rational source candidate; no historical run attribution or original floating solver proof",
        "commented_initial": _certify(
            inputs["model"]["initializations"]["commented_initial"],
            inputs["model"]["case_ids"]["commented_initial"],
        ),
        "active_rounded_initial": _certify(
            inputs["model"]["initializations"]["active_rounded_initial"],
            inputs["model"]["case_ids"]["active_rounded_initial"],
        ),
    }


def verify_certificate(stored: dict, inputs: dict) -> None:
    expected = build_certificate(inputs)
    if stored != expected:
        raise ValueError("stored certificate does not match the exact recomputation")


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--write", type=Path, help="write a new certificate file; refuses to overwrite")
    parser.add_argument("--private-source", type=Path, help="optional local source file to SHA-256 check; never executed")
    args = parser.parse_args()
    try:
        inputs = load_inputs(args.inputs)
        certificate = build_certificate(inputs)
        if args.private_source:
            actual = hashlib.sha256(args.private_source.read_bytes()).hexdigest()
            if actual != REACHABLE_SHA256:
                raise ValueError(f"private source hash mismatch: expected {REACHABLE_SHA256}, got {actual}")
        if args.write:
            if args.write.exists():
                raise ValueError(f"refusing to overwrite existing output: {args.write}")
            args.write.parent.mkdir(parents=True, exist_ok=True)
            args.write.write_text(json.dumps(certificate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"wrote certificate: {args.write}")
        else:
            stored = _load(DEFAULT_CERTIFICATE)
            verify_certificate(stored, inputs)
            print("certificate verified")
        print(f"checker_sha256={hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}")
        for name in ("commented_initial", "active_rounded_initial"):
            case = certificate[name]
            print(f"{name}: minimum={case['minimum_decimal']} affine_dimension={case['optimal_family']['affine_dimension']}")
        return 0
    except (ValueError, OSError, AssertionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
