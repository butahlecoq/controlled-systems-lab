"""Audit displayed B04 data using exact rational arithmetic, without solving its missing constraints."""
import json
import hashlib
import math
from decimal import Decimal, localcontext
from fractions import Fraction as F
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCENARIO = ROOT / "benchmarks/scenarios/b04-historical.json"
scenario_bytes = SCENARIO.read_bytes()
case = json.loads(scenario_bytes, parse_float=Decimal)
problem = case["problem"]

def vector(values):
    return [F(str(v)) for v in values]

def mv(matrix, v):
    return [sum(a * b for a, b in zip(row, v)) for row in matrix]

def dot(a, b):
    return sum(x * y for x, y in zip(a, b))

def subtract(a, b):
    return [x - y for x, y in zip(a, b)]

A = [vector(row) for row in problem["dynamics"]["A"]]
B = vector([row[0] for row in problem["dynamics"]["B"]])
W = [vector(row) for row in problem["objective"]["residual_matrix"]]
r = vector(problem["objective"]["residual_target"])
x0 = vector(problem["initial_state"])
T = problem["horizon"]
base = x0[:]
for _ in range(T):
    base = mv(A, base)
NB = subtract(mv(A, B), B)
assert mv(A, NB) == NB  # N^2 B = 0 for A = I + N.
columns = []
for k in range(T):
    col = B[:]
    for _ in range(T - 1 - k):
        col = mv(A, col)
    assert col == [b + (T - 1 - k) * nb for b, nb in zip(B, NB)]
    columns.append(col)
# B and NB are independent: their nonzero positions are disjoint.
assert B[0] != 0 and NB[1] != 0 and B[1] == 0 and NB[0] == 0
# Every terminal state is base + B*s + NB*m, where s=sum(u_k), m=sum((15-k)*u_k).
y = subtract(mv(W, base), r)
v1, v2 = mv(W, B), mv(W, NB)
h11, h12, h22 = dot(v1, v1), dot(v1, v2), dot(v2, v2)
g1, g2 = dot(v1, y), dot(v2, y)
det = h11 * h22 - h12 * h12
assert h11 > 0 and det > 0  # Strictly convex squared residual on the terminal plane.
s = (-g1 * h22 + g2 * h12) / det
m = (-g2 * h11 + g1 * h12) / det
opt = [b + s * c + m * d for b, c, d in zip(base, B, NB)]
residual = subtract(mv(W, opt), r)
assert dot(v1, residual) == 0 and dot(v2, residual) == 0
lower_bound_squared = dot(residual, residual)
reported_x = vector(case["reported"]["terminal_state"])
reported_residual = subtract(mv(W, reported_x), r)
reported_cost_squared = dot(reported_residual, reported_residual)
# Left null vectors of the terminal-control map yield exact invariants.
flow_invariant = vector([12, 0, 17, 0])
stock_invariant = vector([0, 12, 0, 17])
for row in [flow_invariant, stock_invariant]:
    assert dot(row, B) == 0 and dot(row, NB) == 0
stock_gap = dot(stock_invariant, reported_x) - dot(stock_invariant, base)
# Independently rounded displayed stock coordinates (3 decimals) permit at most this change.
stock_rounding_radius = F(12 + 17, 2000)
assert abs(stock_gap) > stock_rounding_radius
assert lower_bound_squared > F(case["reported"]["objective"]) ** 2

def decimal_token(value):
    return str(value)

def displayed_rounding_radius(value):
    exponent = Decimal(decimal_token(value)).as_tuple().exponent
    return F(1, 2) * (F(10) ** exponent)

def square_root_decimal(value):
    with localcontext() as context:
        context.prec = 40
        return format((Decimal(value.numerator) / Decimal(value.denominator)).sqrt(), ".35g")

displayed_rows = [case["reported"]["nominal_reference"], *case["reported"]["nonlinear_table_rows"], {
    "policy": "linear_any_of_witnesses_1_to_3",
    "terminal_state": case["reported"]["terminal_state"],
    "objective": case["reported"]["objective"],
}]
displayed_evaluations = []
for row in displayed_rows:
    state_tokens = [decimal_token(value) for value in row["terminal_state"]]
    point = vector(state_tokens)
    residual_at_point = subtract(mv(W, point), r)
    objective_squared = dot(residual_at_point, residual_at_point)
    coordinate_radii = [displayed_rounding_radius(token) for token in state_tokens]
    residual_radii = [sum(abs(coefficient) * radius for coefficient, radius in zip(weight_row, coordinate_radii))
                      for weight_row in W]
    objective_rounding_bound_squared = dot(residual_radii, residual_radii)
    reported_objective = F(decimal_token(row["objective"]))
    displayed_evaluations.append({
        "policy": row["policy"],
        "terminal_state_printed": state_tokens,
        "reported_objective_printed": decimal_token(row["objective"]),
        "reported_objective_rounding_radius_exact": str(displayed_rounding_radius(row["objective"])),
        "objective_squared_at_printed_coordinates_exact": str(objective_squared),
        "objective_at_printed_coordinates": square_root_decimal(objective_squared),
        "coordinate_rounding_radii_exact": [str(radius) for radius in coordinate_radii],
        "objective_rounding_effect_bound_squared_exact": str(objective_rounding_bound_squared),
        "objective_rounding_effect_bound": square_root_decimal(objective_rounding_bound_squared),
        "interpretation": "display-coordinate evaluation and rounding bound; not a reproduced run result",
    })
result = {
    "date": "2026-10-11",
    "scenario": case["id"],
    "source_manifest_sha256": hashlib.sha256(scenario_bytes).hexdigest(),
    "status": "displayed_data_inconsistent_with_reported_optimizer",
    "arithmetic": "Exact Fraction arithmetic on displayed coefficients; square roots use Decimal presentation only",
    "terminal_control_map_rank": 2,
    "terminal_base_exact": [str(v) for v in base],
    "terminal_plane_basis_exact": [[str(v) for v in col] for col in [B, NB]],
    "reported_point_recomputed_objective": math.sqrt(float(reported_cost_squared)),
    "displayed_table_evaluations": displayed_evaluations,
    "stock_invariant": {
        "left_vector": [0, 12, 0, 17],
        "required_exact": str(dot(stock_invariant, base)),
        "reported_point_exact": str(dot(stock_invariant, reported_x)),
        "gap_exact": str(stock_gap),
        "reported_point_rounding_radius_exact": str(stock_rounding_radius),
    },
    "unrestricted_terminal_plane_minimum": {
        "terminal_state_exact": [str(v) for v in opt],
        "terminal_state_float": [float(v) for v in opt],
        "sum_controls_exact": str(s),
        "weighted_sum_controls_exact": str(m),
        "objective_squared_exact": str(lower_bound_squared),
        "objective_float": math.sqrt(float(lower_bound_squared)),
        "scope": "Global lower bound for any constraints on the displayed linear model; not the historical constrained optimum",
    },
    "historical_reproduction_complete": False,
    "limits": [
        "No numerical U_t recovered and no constrained optimal family or historical witness computed.",
        "The displayed coefficients are treated as exact rational data; original unrounded coefficients are unknown.",
        "Terminal-point rounding alone cannot repair the stock invariant; possible model/coefficient/transcription changes remain unresolved.",
        "No nonlinear simulation, runtime reproduction or full validated floating-point solver certificate.",
    ],
}
(ROOT / "docs/research/b04-consistency.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
