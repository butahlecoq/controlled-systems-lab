"""Independent exact-dyadic checker for the B04-C optimal-fiber record."""
from __future__ import annotations

from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys

HORIZON = 16
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RECORD = ROOT / "docs/research/evidence/b04-c-exact-dyadic-v1/record.json"


def dyadic(text: str) -> F:
    return F.from_float(float(F(text)))


def parse(value: str) -> F:
    return F(value)


def multiply(row, vector):
    return sum((a * b for a, b in zip(row, vector)), F(0))


def expected_model():
    initial = tuple(dyadic(x) for x in ("1220.28265395983", "119500", "440.005764648976", "45300"))
    a = tuple(tuple(F(1) if i == j else F(-25, 4) if (i, j) in ((1, 0), (3, 2)) else F(0)
                     for j in range(4)) for i in range(4))
    b = (dyadic("2208/110"), F(0), dyadic("-1152/110"), F(0))
    cross, weight = dyadic("8/3"), dyadic("64/9")
    feature = ((F(-1), F(0), F(0), F(0)), (F(0), F(1), F(0), F(0)),
               (F(0), F(0), F(-1), F(0)), (F(0), F(0), F(0), F(1)),
               (F(0), F(1), F(0), -cross))
    feature_offset = (F(1200), F(0), F(450), F(0), F(0))
    weights = (F(1), F(1), weight, weight, F(1))
    return initial, a, b, feature, feature_offset, weights


def affine(a, b, initial):
    offsets = [initial]
    matrices = [tuple(tuple(F(0) for _ in range(HORIZON)) for _ in range(4))]
    for stage in range(HORIZON):
        c = tuple(multiply(row, offsets[-1]) for row in a)
        m = tuple(tuple(multiply(a[state], tuple(matrices[-1][j][k] for j in range(4)))
                        + (b[state] if k == stage else F(0))
                        for k in range(HORIZON)) for state in range(4))
        offsets.append(c)
        matrices.append(m)
    return tuple(zip(offsets, matrices))


def replay(a, b, initial, controls):
    if len(controls) != HORIZON:
        raise ValueError("wrong control count")
    states = [initial]
    for control in controls:
        states.append(tuple(multiply(a[i], states[-1]) + b[i] * control for i in range(4)))
    return tuple(states)


def expected_rows(model, maps):
    _, _, _, _, _, _ = model
    rows = []
    for stage in range(HORIZON):
        unit = tuple(F(i == stage) for i in range(HORIZON))
        rows.extend(((f"control/{stage}/upper", unit, F(1)),
                     (f"control/{stage}/lower", tuple(-x for x in unit), F(1))))
    for stage, (offset, matrix) in enumerate(maps):
        for coordinate, low, high in ((0, F(1176), F(1224)), (2, F(432), F(468))):
            row = tuple(matrix[coordinate])
            rows.extend(((f"phase/{stage}/{coordinate}/upper", row, high - offset[coordinate]),
                         (f"phase/{stage}/{coordinate}/lower", tuple(-x for x in row), offset[coordinate] - low)))
    return tuple(rows)


def exact_rank_two(columns):
    first, second = columns[0], columns[1]
    pivot = next(((r, s) for r in range(5) for s in range(r + 1, 5)
                  if first[r] * second[s] - first[s] * second[r]), None)
    if pivot is None:
        raise ValueError("the declared terminal residual map is not rank two")
    r, s = pivot
    determinant = first[r] * second[s] - first[s] * second[r]
    for column in columns[2:]:
        alpha = (column[r] * second[s] - column[s] * second[r]) / determinant
        beta = (first[r] * column[s] - first[s] * column[r]) / determinant
        if any(column[i] != alpha * first[i] + beta * second[i] for i in range(5)):
            raise ValueError("terminal residual map has rank greater than two")
    return pivot


def check(record_path: Path) -> dict:
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("schema") != "csl.b04-c-exact-dyadic-fiber/1" or record.get("scenario_id") != "B04-c-exact-dyadic-20261102":
        raise ValueError("wrong profile or scenario identity")
    initial, a, b, feature, feature_offset, weights = expected_model()
    expected_input = record["input"]
    if [parse(x) for x in expected_input["initial"]] != list(initial):
        raise ValueError("profile initial point differs from the registered dyadic inputs")
    if [[parse(x) for x in row] for row in expected_input["A"]] != [list(row) for row in a]:
        raise ValueError("profile transition differs from the registered model")
    if [parse(x) for x in expected_input["B"]] != list(b):
        raise ValueError("profile input vector differs from the registered dyadic inputs")
    if expected_input["criterion_dyadics"] != {"8/3": str(dyadic("8/3")), "64/9": str(dyadic("64/9"))}:
        raise ValueError("criterion coefficient bits differ from the registered profile")
    expected_bits = {
        "initial": [float(F(value)).hex() for value in (
            "1220.28265395983", "119500", "440.005764648976", "45300")],
        "B": [float(F(value)).hex() for value in ("2208/110", "0", "-1152/110", "0")],
        "objective_8_over_3": float(F("8/3")).hex(),
        "objective_64_over_9": float(F("64/9")).hex(),
    }
    if expected_input["binary64_source_bits"] != expected_bits:
        raise ValueError("binary64 source bit patterns differ")
    if (expected_input["horizon"] != HORIZON or expected_input["control_bounds"] != ["-1", "1"]
            or expected_input["step_duration_seconds"] != "25/4"):
        raise ValueError("control catalog or horizon changed")
    if expected_input["phase_bounds"] != {"stages": [0, 16], "x1": [1176, 1224], "x3": [432, 468]}:
        raise ValueError("phase bounds differ from issue #531")
    if "exact dyadic" not in expected_input["input_semantics"]:
        raise ValueError("represented-dyadic input semantics are missing")
    if expected_input["criterion"] != "(1200-x1)^2 + x2^2 + (64/9)*(450-x3)^2 + (64/9)*x4^2 + (x2-(8/3)*x4)^2":
        raise ValueError("criterion expression differs from issue #531")
    if "corrected-track issue scenario" not in expected_input["input_authority"]:
        raise ValueError("the scenario must retain its corrected-track source boundary")
    canonical = json.dumps(expected_input, sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(canonical).hexdigest() != record["input_canonical_sha256"]:
        raise ValueError("canonical input digest differs")
    band_spec = ["|J* - 30.899| <= 0.0005", "J* < 30.8985", "J* > 30.8995"]
    if record["optimality"]["pre_registered_bands_unchanged"] != band_spec:
        raise ValueError("acceptance bands changed")

    maps = affine(a, b, initial)
    rows = expected_rows((initial, a, b, feature, feature_offset, weights), maps)
    saved_rows = record["optimal_family"]["control_polytope_rows"]
    decoded_rows = tuple((row["name"], tuple(parse(x) for x in row["coefficients"]), parse(row["upper"]))
                         for row in saved_rows)
    if decoded_rows != rows:
        raise ValueError("saved control H-polytope differs from the independently reconstructed constraints")

    controls = tuple(parse(x) for x in record["optimality"]["control_witness"])
    states = replay(a, b, initial, controls)
    if any(multiply(row, controls) >= bound for _, row, bound in rows):
        raise ValueError("optimality witness is not exactly feasible")
    terminal = states[-1]
    if [[parse(value) for value in state] for state in record["optimality"]["replay_states"]] != [list(state) for state in states]:
        raise ValueError("saved optimal witness replay differs")
    if [parse(x) for x in record["optimality"]["terminal_state"]] != list(terminal):
        raise ValueError("terminal witness differs from exact replay")

    # Reconstruct the objective as a weighted sum of exact affine features.
    features = tuple(multiply(row, terminal) + shift for row, shift in zip(feature, feature_offset))
    squared = sum((w * z * z for w, z in zip(weights, features)), F(0))
    if parse(record["optimality"]["squared_objective"]) != squared:
        raise ValueError("exact objective value differs")
    if [parse(x) for x in record["optimality"]["feature_residuals"]] != list(features):
        raise ValueError("saved exact objective residuals differ")
    minimum_slack = min(bound - multiply(row, controls) for _, row, bound in rows)
    if parse(record["optimality"]["minimum_hard_constraint_slack"]) != minimum_slack or minimum_slack <= 0:
        raise ValueError("minimum exact hard-constraint slack differs")
    terminal_map = maps[-1][1]
    feature_map = tuple(tuple(sum((feature[i][s] * terminal_map[s][u] for s in range(4)), F(0))
                              for u in range(HORIZON)) for i in range(5))
    rank_pivot = exact_rank_two(tuple(tuple(feature_map[row][column] for row in range(5))
                                      for column in range(HORIZON)))
    if record["optimality"]["terminal_map_rank"] != 2:
        raise ValueError("terminal-map rank declaration differs")

    gradient = tuple(sum((weights[i] * feature_map[i][control] * features[i]
                          for i in range(5)), F(0)) for control in range(HORIZON))
    kkt = record["optimality"]["kkt"]
    if any(gradient) or [parse(x) for x in kkt["gradient_of_half_squared_objective"]] != list(gradient):
        raise ValueError("exact stationarity failed")
    multipliers = [parse(x) for x in kkt["inequality_multipliers"]]
    if len(multipliers) != len(rows) or any(value < 0 for value in multipliers):
        raise ValueError("KKT inequality multipliers are invalid")
    active_rows = [name for name, row, bound in rows if multiply(row, controls) == bound]
    if any(multipliers) or kkt["active_inequality_rows"] != active_rows or active_rows:
        raise ValueError("the claimed strict-interior zero-multiplier certificate is inconsistent")
    if record["optimality"]["band_verdict"] != band(squared):
        raise ValueError("exact objective band verdict differs")
    if record["optimality"]["other_bands"] != [
            "J* < 30.8985: not applicable", "J* > 30.8995: not applicable"]:
        raise ValueError("nonapplicable acceptance-band verdicts are missing")

    # Validate the published-point reachability witness independently.
    reach = record["reachability"]
    reach_controls = tuple(parse(x) for x in reach["controls"])
    reach_states = replay(a, b, initial, reach_controls)
    point = tuple(F(x) for x in ("12007/10", "-22929/1000", "2251/5", "-7709/1000"))
    radii = tuple(F(x) for x in ("1/20", "1/2000", "1/20", "1/2000"))
    reachable = all(abs(value - center) <= radius for value, center, radius
                    in zip(reach_states[-1], point, radii))
    if not reachable or any(multiply(row, reach_controls) > bound for _, row, bound in rows):
        raise ValueError("published terminal rounding-box reachability witness failed")
    if (reach["within_coordinate_rounding_box"] is not True
            or reach["phase_and_control_constraints_exactly_feasible"] is not True
            or [parse(x) for x in reach["terminal_replay"]] != list(reach_states[-1])):
        raise ValueError("saved reachability summary differs from the exact replay")
    flow = F(12) * point[0] + F(23) * point[2] - F("3095440554305551/125000000000")
    stock = F(12) * point[1] + F(23) * point[3] + F("565554305551/1250000000")
    if reach["plane_residuals"] != {"flow": str(flow), "stock": str(stock)}:
        raise ValueError("published plane-functional residuals differ")

    # The relation is exactly the feasible control polytope intersected with
    # x_16 = x*. Its affine lift is rebuilt here instead of trusted from JSON.
    equalities = record["optimal_family"]["terminal_equalities"]
    if len(equalities) != 4:
        raise ValueError("terminal fiber equality count differs")
    for i, equality in enumerate(equalities):
        if (equality["coordinate"] != i
                or tuple(parse(x) for x in equality["coefficients"]) != tuple(maps[-1][1][i])
                or parse(equality["value"]) != terminal[i] - maps[-1][0][i]):
            raise ValueError("terminal fiber equalities differ from exact reconstruction")
    lift = record["optimal_family"]["affine_lift"]
    if len(lift) != HORIZON + 1:
        raise ValueError("affine lift does not cover all 17 states")
    for stage, (offset, matrix) in enumerate(maps):
        item = lift[stage]
        if item["stage"] != stage or [parse(x) for x in item["offset"]] != list(offset):
            raise ValueError("affine state lift offset differs")
        if [[parse(x) for x in row] for row in item["control_coefficients"]] != [list(row) for row in matrix]:
            raise ValueError("affine state lift matrix differs")

    context = record["published_context"]
    expected_nonlinear_rows = [
        {"model": "frozen-coefficient regulator", "terminal": ["1190.4", "101.7", "455.12", "-72.817"], "reported_objective": "368.45"},
        {"model": "nonlinear, optimal linear witness 1", "terminal": ["1200.5", "-2.695", "449.72", "10.556"], "reported_objective": "41.855"},
        {"model": "nonlinear, optimal linear witness 2", "terminal": ["1200.5", "0.50887", "449.72", "17.561"], "reported_objective": "65.874"},
        {"model": "nonlinear, optimal linear witness 3", "terminal": ["1200.5", "-6.366", "449.72", "-1.475"], "reported_objective": "7.922"},
    ]
    expected_sources = [
        {"id": "A01", "file": "ReachableSets.m", "sha256": "e7010e0a830595029b9876b1511558514cec8398d2ffa290313a566ba6997558"},
        {"id": "A39", "file": "1st.fig", "sha256": "1120e70dbf3a300d1f8c9ee19d1082632c3adbb24f5ac445802954b164181f38"},
        {"id": "A40", "file": "program.m", "sha256": "581a91dbb1041973f9559a6cac07657279a5e3f40091f04606216be0f97bac46"},
    ]
    if context["source_artifacts"] != expected_sources:
        raise ValueError("saved-family source identities differ")
    if context["linear_reported_objective"] != "30.899" or context["nonlinear_rows"] != expected_nonlinear_rows:
        raise ValueError("immutable published context is incomplete")
    if ("not a reproduction claim" not in context["claim"]
            or "open unit-convention question" not in context["a40_fourfold_coefficient_scaling"]):
        raise ValueError("record must not claim reproduction")
    family = record["optimal_family"]
    if (family["representation"] != "bounded 16-control H-polytope with an exact affine lift to the 84 state/control coordinates"
            or family["joint_coordinate_order"] != "x0,x1,...,x16,u0,u1,...,u15 (state vectors are coordinate-major within each stage)"
            or len(family["control_polytope_rows"]) != 100):
        raise ValueError("optimal-family representation or coordinate schema differs")
    if family["induced_terminal_set"] != {"kind": "singleton", "point": [str(x) for x in terminal]}:
        raise ValueError("induced terminal set is not the certified singleton")
    if (family["bounded"] is not True or family["query_contract"] != [
            "exact control-vector membership in the terminal fiber",
            "exact full state/control history membership",
            "exact 84-coordinate history reconstruction from a control vector",
            "terminal-state projection (singleton)",
            "other geometric projections are unsupported unless separately computed with exact arithmetic"]):
        raise ValueError("optimal-fiber query contract differs")
    if "every optimal history" not in family["coverage_argument"]:
        raise ValueError("the complete-family coverage argument is missing")

    return {"schema": "csl.b04-c-exact-dyadic-fiber-check/1",
            "scenario_id": record["scenario_id"],
            "model_inputs": "exact dyadic replay passed",
            "control_rows": len(rows),
            "terminal_residual_rank": 2,
            "terminal_residual_rank_pivot_rows": list(rank_pivot),
            "exact_kkt_stationarity": "passed",
            "exact_kkt_feasibility": "passed",
            "global_optimality": "proved for the represented-dyadic convex profile",
            "exact_squared_objective": str(squared),
            "acceptance_band": band(squared),
            "published_rounding_box_reachability": "passed",
            "optimal_control_family": "exact 16D H-polytope terminal fiber with independently reconstructed 84D affine lift",
            "terminal_set": "singleton"}


def band(squared: F) -> str:
    lower, upper = F("30.8985") ** 2, F("30.8995") ** 2
    if lower <= squared <= upper:
        return "within pre-registered confirmation band"
    return "below pre-registered lower band" if squared < lower else "above pre-registered upper band"


if __name__ == "__main__":
    result = check(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RECORD)
    print(json.dumps(result, sort_keys=True))
