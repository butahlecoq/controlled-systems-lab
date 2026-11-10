#!/usr/bin/env python3
"""Exact all-stage moment sets for the B04 source candidate."""

from __future__ import annotations

import argparse
from fractions import Fraction as Q
from functools import reduce
from math import gcd, lcm
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
HELPER_DIR = ROOT / "benchmarks/reporting/mpc08_explicit"
if str(HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(HELPER_DIR))
import exact_regions as E  # noqa: E402
from explicit_double_integrator import intersect  # noqa: E402

TOOLS_DIR = ROOT / "docs/research/tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
import check_b04_source_moments as C  # noqa: E402


DEFAULT_OUTPUT = ROOT / "docs/research/evidence/b04-source-moment-stage-sets.json"
CERTIFICATE_PATH = ROOT / "docs/research/evidence/b04-source-moment-certificate.json"
HELPER_PATHS = (
    "benchmarks/reporting/mpc08_explicit/exact_regions.py",
    "benchmarks/reporting/mpc08_explicit/explicit_double_integrator.py",
    "scripts/reports/figure_style.py",
)
N = 16
H = Q(25, 4)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _encoded(value):
    if isinstance(value, Q):
        return str(value)
    if isinstance(value, dict):
        return {key: _encoded(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encoded(item) for item in value]
    return value


def _normalized(rows):
    result = set()
    for row in rows:
        a, b, c = map(Q, row)
        if not a and not b:
            if c < 0:
                raise ValueError("inconsistent constant halfspace")
            continue
        scale = lcm(a.denominator, b.denominator, c.denominator)
        values = [int(item * scale) for item in (a, b, c)]
        divisor = reduce(gcd, (abs(item) for item in values))
        result.add(tuple(Q(item // divisor) for item in values))
    return sorted(result)


def _rows_for(poly):
    if not poly:
        raise ValueError("cannot derive bounded H-representation for empty set")
    if len(poly) == 1:
        x, y = poly[0]
        return [(Q(1), Q(0), x), (Q(-1), Q(0), -x),
                (Q(0), Q(1), y), (Q(0), Q(-1), -y)]
    if len(poly) == 2:
        p, q = poly
        dx, dy = q[0] - p[0], q[1] - p[1]
        a, b = -dy, dx
        c = a * p[0] + b * p[1]
        return [(a, b, c), (-a, -b, -c),
                (dx, dy, dx * q[0] + dy * q[1]),
                (-dx, -dy, -dx * p[0] - dy * p[1])]
    return [(q[1] - p[1], p[0] - q[0],
             (q[1] - p[1]) * p[0] + (p[0] - q[0]) * p[1])
            for p, q in zip(poly, poly[1:] + poly[:1])]


def _eliminate(joint, strip):
    positive = [row for row in joint if row[2] > 0]
    negative = [row for row in joint if row[2] < 0]
    rows = [(a, b, c) for a, b, u, c in joint if not u]
    rows.extend((a / u - d / v, b / u - e / v, c / u - f / v)
                for a, b, u, c in positive for d, e, v, f in negative)
    return _normalized(rows + strip)


def _canonical_h(rows):
    rows = _normalized(rows)
    if not E.is_bounded(rows):
        raise ValueError("stage set is unbounded")
    points = E.vertices(rows)
    if not points:
        raise ValueError("unexpected empty stage set")
    if not all(a * x + b * y <= c for x, y in points for a, b, c in rows):
        raise ValueError("vertex extraction returned an infeasible point")
    return _normalized(_rows_for(points)), points


def _h_step(rows, strip, *, backward=False):
    if backward:
        joint = [(a + b, b, a, c) for a, b, c in rows]
    else:
        joint = [(a - b, b, b - a, c) for a, b, c in rows]
    joint.extend([(Q(0), Q(0), Q(1), Q(1)),
                  (Q(0), Q(0), Q(-1), Q(1))])
    return _canonical_h(_eliminate(joint, strip))


def _v_step(poly, strip, *, backward=False):
    if backward:
        points = [(s + u, m - s - u) for s, m in poly for u in (Q(-1), Q(1))]
    else:
        points = [(s + u, m + s) for s, m in poly for u in (Q(-1), Q(1))]
    return E.hull(intersect(E.hull(points), strip))


def _physical(k, point, initial, bo, bf):
    s, m = point
    qo, mo, qf, mf = initial
    return [qo + bo * s, mo - k * H * qo - H * bo * m,
            qf + bf * s, mf - k * H * qf - H * bf * m]


def _holds(point, rows):
    return all(a * point[0] + b * point[1] <= c for a, b, c in rows)


def _verify_public_certificate(certificate: dict) -> dict:
    inputs = C.load_inputs()
    C.verify_certificate(certificate, inputs)
    saved = json.loads(C.DEFAULT_CERTIFICATE.read_text(encoding="utf-8"))
    if certificate != saved:
        raise ValueError("certificate argument differs from the saved public certificate")
    return certificate["commented_initial"]


def build_stage_sets(certificate: dict) -> dict:
    """Build and internally cross-check all 17 exact forward/backward sets."""
    case = _verify_public_certificate(certificate)
    initial = list(map(Q, case["initial"]))
    endpoint = (Q(case["sum_control"]), Q(case["weighted_control_sum"]))
    lower, upper = map(Q, case["prefix_bounds"])
    strip = [(Q(1), Q(0), upper), (Q(-1), Q(0), -lower)]
    bo, bf = C.BO, C.BF

    forward = [[(Q(0), Q(0))]]
    forward_h = [_normalized(_rows_for(forward[0]))]
    for k in range(1, N + 1):
        v_poly = _v_step(forward[-1], strip)
        h_rows, h_poly = _h_step(forward_h[-1], strip)
        if v_poly != h_poly:
            raise ValueError(f"forward V/H mismatch at stage {k}")
        forward.append(v_poly)
        forward_h.append(h_rows)

    backward = [None] * (N + 1)
    backward_h = [None] * (N + 1)
    backward[N] = [endpoint]
    backward_h[N] = _normalized(_rows_for(backward[N]))
    for k in reversed(range(N)):
        v_poly = _v_step(backward[k + 1], strip, backward=True)
        h_rows, h_poly = _h_step(backward_h[k + 1], strip, backward=True)
        if v_poly != h_poly:
            raise ValueError(f"backward V/H mismatch at stage {k}")
        backward[k], backward_h[k] = v_poly, h_rows

    controls = list(map(Q, case["interior_witness_controls"]))
    states = [[Q(item) for item in state] for state in case["interior_witness_states"]]
    if len(controls) != N or len(states) != N + 1:
        raise ValueError("certificate witness has unexpected horizon")
    moment = (Q(0), Q(0))
    stages = []
    for k in range(N + 1):
        corridor = E.hull(intersect(forward[k], _rows_for(backward[k])))
        h_corridor, h_vertices = _canonical_h(forward_h[k] + backward_h[k])
        if corridor != h_vertices:
            raise ValueError(f"corridor V/H mismatch at stage {k}")
        if not _holds(moment, h_corridor):
            raise ValueError(f"optimal witness moment leaves corridor at stage {k}")
        physical_witness = _physical(k, moment, initial, bo, bf)
        if physical_witness != states[k]:
            raise ValueError(f"physical witness identity mismatch at stage {k}")
        stages.append({
            "stage": k,
            "time_seconds": k * H,
            "moment_sets": {"forward": forward[k], "backward": backward[k], "corridor": corridor},
            "physical_sets": {
                name: [_physical(k, point, initial, bo, bf) for point in poly]
                for name, poly in (("forward", forward[k]), ("backward", backward[k]), ("corridor", corridor))
            },
            "moment_witness": moment,
            "physical_witness": physical_witness,
            "vertex_counts": [len(forward[k]), len(backward[k]), len(corridor)],
            "corridor_area": E.area(corridor),
        })
        if k < N:
            moment = (moment[0] + controls[k], moment[1] + moment[0])

    if stages[0]["moment_sets"]["corridor"] != [(Q(0), Q(0))]:
        raise ValueError("initial corridor is not the initial singleton")
    if stages[-1]["moment_sets"]["corridor"] != [endpoint]:
        raise ValueError("terminal corridor is not the unique endpoint singleton")
    if any(len(stages[k]["moment_sets"]["corridor"]) < 3 or stages[k]["corridor_area"] <= 0
           for k in range(2, 15)):
        raise ValueError("expected interior corridor polygon is degenerate")

    for primitive in (
        [(Q(1), Q(2))],
        [(Q(-1), Q(0)), (Q(1), Q(0))],
        [(Q(-1), Q(-1)), (Q(1), Q(-1)), (Q(1), Q(1)), (Q(-1), Q(1))],
    ):
        if _canonical_h(_rows_for(primitive))[1] != primitive:
            raise ValueError("point/segment/polygon boundary handling failed")

    checker_path = ROOT / "docs/research/tools/check_b04_source_moments.py"
    helpers = [{"path": path, "sha256": _hash(ROOT / path)} for path in HELPER_PATHS]
    return _encoded({
        "schema": "b04.source-candidate.exact-stage-sets/1",
        "source_model_sha256": certificate["source_sha256"],
        "certificate_sha256": _hash(CERTIFICATE_PATH),
        "provenance": {
            "helpers": helpers,
            "producer_sha256": _hash(Path(__file__)),
            "checker_sha256": _hash(checker_path),
        },
        "scope": "Exact nominal source candidate with commented decimal initial condition; no historical run attribution",
        "semantics": {
            "forward": "States reached from the fixed initial point after k steps under all prefix flow and input bounds",
            "backward": "States in the stage-specific affine plane that can reach the unique optimal endpoint under remaining flow/input bounds",
            "corridor": "Forward/backward intersection, the exact stage-state projection of the complete optimal family; histories remain coupled",
            "trajectory": "One constructed exact optimal witness, not a recovered historical optimizer sequence",
            "independence": "V affine/Minkowski/clip recursion cross-checked against H Fourier-Motzkin/pair-intersection route; both share rational hull canonicalization; V forward/backward/intersection operations reuse clipping",
            "time": "Separate sets at all 17 times; no hull or union presented as a single-time reachable set",
        },
        "stages": stages,
    })


def verify_stage_sets(stored: dict, certificate: dict) -> None:
    expected = build_stage_sets(certificate)
    if stored != expected:
        raise ValueError("stored exact stage sets do not match recomputation")


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--write", type=Path, help="write a new stage artifact; refuses to overwrite")
    args = parser.parse_args()
    try:
        certificate = json.loads(CERTIFICATE_PATH.read_text(encoding="utf-8"))
        if args.write:
            if args.write.exists():
                raise ValueError(f"refusing to overwrite existing output: {args.write}")
            record = build_stage_sets(certificate)
            args.write.parent.mkdir(parents=True, exist_ok=True)
            args.write.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"wrote exact stage sets: {args.write}")
        else:
            stored = json.loads(args.input.read_text(encoding="utf-8"))
            verify_stage_sets(stored, certificate)
            print(f"verified exact stage sets: {args.input}")
        print(f"stages={N + 1} certificate_sha256={_hash(CERTIFICATE_PATH)}")
        return 0
    except (ValueError, OSError, AssertionError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
