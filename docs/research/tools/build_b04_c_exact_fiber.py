"""Construct the exact B04-C KKT witness and 16-control optimal fiber record."""
from __future__ import annotations

from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from b04_c_exact_profile import (
    HORIZON, affine_states, band_verdict, constraints, correct_candidate,
    dyadic, gradient, objective_squared, profile, replay,
)

ROOT = Path(__file__).resolve().parents[3]
SEED = ROOT / "docs/research/evidence/b04-c-preliminary-20261023/attempt-002/record.json"
OUTPUT = ROOT / "docs/research/evidence/b04-c-exact-dyadic-v1/record.json"


def rational(value: F) -> str:
    return f"{value.numerator}/{value.denominator}"


def main() -> None:
    model = profile()
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    candidate = tuple(F.from_float(float.fromhex(value))
                      for value in seed["candidate"]["controls_binary64_hex"])
    controls, corrected_indices = correct_candidate(model, candidate)
    states = replay(model, controls)
    terminal = states[-1]
    squared = objective_squared(model, terminal)
    state_maps = affine_states(model)
    h_rows = constraints(model)

    # Exact feasibility includes all 32 control rows and all 68 phase rows.
    violations = [name for name, row, bound in h_rows if sum(
        (a * u for a, u in zip(row, controls)), F(0)) > bound]
    if violations:
        raise RuntimeError(f"exact KKT witness is infeasible: {violations[:3]}")
    active_rows = [name for name, row, bound in h_rows
                   if sum((a * u for a, u in zip(row, controls)), F(0)) == bound]
    if active_rows:
        raise RuntimeError(f"zero-multiplier KKT certificate requires strict feasibility: {active_rows[:3]}")
    exact_gradient = gradient(model, controls)
    if any(exact_gradient):
        raise RuntimeError("exact rational stationarity correction did not close")
    minimum_slack = min(bound - sum((a * u for a, u in zip(row, controls)), F(0))
                        for _, row, bound in h_rows)
    residual_features = []
    for row, shift in zip(model.feature_matrix, model.feature_offset):
        residual_features.append(sum((a * x for a, x in zip(row, terminal)), F(0)) + shift)

    # Recover the separate archived-point reachability witness. It is checked
    # against coordinate-wise rounding intervals, not plane residuals alone.
    reach_record = seed["published_point_reachability"]
    reach_candidate = [F.from_float(float.fromhex(value))
                       for value in reach_record["controls_binary64_hex"]]
    # The prior witness sat exactly on a state lower bound under its rational
    # coefficient interpretation. A 1e-12 rational perturbation to u7 moves
    # it into the interior under this profile's represented-dyadic inputs.
    reach_candidate[7] += F(1, 10**12)
    reach_controls = tuple(reach_candidate)
    reach_states = replay(model, reach_controls)
    published = tuple(F(value) for value in ("12007/10", "-22929/1000", "2251/5", "-7709/1000"))
    radii = tuple(F(value) for value in ("1/20", "1/2000", "1/20", "1/2000"))
    reach_terminal = reach_states[-1]
    in_rounding_box = all(abs(value - center) <= radius
                          for value, center, radius in zip(reach_terminal, published, radii))
    reach_feasible = all(abs(value) <= 1 for value in reach_controls) and all(
        sum((a * u for a, u in zip(row, reach_controls)), F(0)) <= bound
        for _, row, bound in h_rows)
    if not in_rounding_box or not reach_feasible:
        raise RuntimeError("archived reachability witness failed exact replay under dyadic semantics")

    flow_residual = F(12) * published[0] + F(23) * published[2] - F("3095440554305551/125000000000")
    stock_residual = F(12) * published[1] + F(23) * published[3] + F("565554305551/1250000000")
    state_offset, state_matrix = state_maps[-1]
    fiber_equalities = []
    for coordinate in range(4):
        fiber_equalities.append({
            "coordinate": coordinate,
            "coefficients": [rational(value) for value in state_matrix[coordinate]],
            "value": rational(terminal[coordinate] - state_offset[coordinate]),
        })

    profile_input = {
        "input_authority": "A39/A01/A40 saved-family constants frozen in issue #531; the sixteen-stage profile is the corrected-track issue scenario, not a recovered historical T16 generator",
        "initial": [rational(value) for value in model.initial],
        "A": [[rational(value) for value in row] for row in model.transition],
        "B": [rational(value) for value in model.input_vector],
        "input_semantics": "Each finite source decimal/fraction is first parsed as binary64, then interpreted as that exact dyadic; A entries and acceptance edges that are exact terminating rationals remain exact.",
        "horizon": HORIZON,
        "step_duration_seconds": "25/4",
        "control_bounds": ["-1", "1"],
        "phase_bounds": {"stages": [0, 16], "x1": [1176, 1224], "x3": [432, 468]},
        "criterion": "(1200-x1)^2 + x2^2 + (64/9)*(450-x3)^2 + (64/9)*x4^2 + (x2-(8/3)*x4)^2",
        "criterion_dyadics": {"8/3": rational(dyadic("8/3")), "64/9": rational(dyadic("64/9"))},
        "binary64_source_bits": {
            "initial": [float(F(value)).hex() for value in (
                "1220.28265395983", "119500", "440.005764648976", "45300")],
            "B": [float(F(value)).hex() for value in ("2208/110", "0", "-1152/110", "0")],
            "objective_8_over_3": float(F("8/3")).hex(),
            "objective_64_over_9": float(F("64/9")).hex(),
        },
    }
    canonical = json.dumps(profile_input, sort_keys=True, separators=(",", ":")).encode()
    result = {
        "schema": "csl.b04-c-exact-dyadic-fiber/1",
        "scenario_id": "B04-c-exact-dyadic-20261102",
        "authorization_issue": 531,
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "seed": {"scenario_id": seed["scenario_id"], "record_sha256": hashlib.sha256(SEED.read_bytes()).hexdigest(),
                 "role": "feasible start only; the proof below is exact and does not rely on the seed solver status"},
        "input": profile_input,
        "input_canonical_sha256": hashlib.sha256(canonical).hexdigest(),
        "published_context": {
            "source_artifacts": [
                {"id": "A01", "file": "ReachableSets.m", "sha256": "e7010e0a830595029b9876b1511558514cec8398d2ffa290313a566ba6997558"},
                {"id": "A39", "file": "1st.fig", "sha256": "1120e70dbf3a300d1f8c9ee19d1082632c3adbb24f5ac445802954b164181f38"},
                {"id": "A40", "file": "program.m", "sha256": "581a91dbb1041973f9559a6cac07657279a5e3f40091f04606216be0f97bac46"},
            ],
            "linear_reported_objective": "30.899",
            "nonlinear_rows": [
                {"model": "frozen-coefficient regulator", "terminal": ["1190.4", "101.7", "455.12", "-72.817"], "reported_objective": "368.45"},
                {"model": "nonlinear, optimal linear witness 1", "terminal": ["1200.5", "-2.695", "449.72", "10.556"], "reported_objective": "41.855"},
                {"model": "nonlinear, optimal linear witness 2", "terminal": ["1200.5", "0.50887", "449.72", "17.561"], "reported_objective": "65.874"},
                {"model": "nonlinear, optimal linear witness 3", "terminal": ["1200.5", "-6.366", "449.72", "-1.475"], "reported_objective": "7.922"},
            ],
            "claim": "immutable published context only; this corrected-track result is not a reproduction claim",
            "a40_fourfold_coefficient_scaling": "open unit-convention question; archived family coefficients are used without endorsing a normalization",
        },
        "reachability": {
            "published_terminal": [rational(value) for value in published],
            "rounding_radii": [rational(value) for value in radii],
            "controls": [rational(value) for value in reach_controls],
            "construction": "archived reachability witness with 1e-12 added to u7 to preserve strict phase feasibility under represented-dyadic inputs",
            "terminal_replay": [rational(value) for value in reach_terminal],
            "within_coordinate_rounding_box": in_rounding_box,
            "phase_and_control_constraints_exactly_feasible": reach_feasible,
            "plane_residuals": {"flow": rational(flow_residual), "stock": rational(stock_residual)},
        },
        "optimality": {
            "solver_status": "exact rational two-variable stationarity correction completed; independent exact KKT verification passed",
            "numerical_optimizer": "not invoked for this profile; the archived preliminary candidate is only a feasible starting point",
            "control_witness": [rational(value) for value in controls],
            "corrected_control_indices": list(corrected_indices),
            "replay_states": [[rational(value) for value in state] for state in states],
            "terminal_state": [rational(value) for value in terminal],
            "squared_objective": rational(squared),
            "feature_residuals": [rational(value) for value in residual_features],
            "minimum_hard_constraint_slack": rational(minimum_slack),
            "objective_approximation": format(float(squared) ** 0.5, ".15g"),
            "feasible_control_polytope": "all registered control and phase inequalities are checked exactly",
            "kkt": {"gradient_of_half_squared_objective": [rational(value) for value in exact_gradient],
                    "inequality_multipliers": ["0"] * len(h_rows),
                    "active_inequality_rows": active_rows, "stationarity": "exact", "dual_feasibility": "exact",
                    "complementarity": "exact"},
            "terminal_map_rank": 2,
            "strict_convexity": "positive definite in terminal state: the first four criterion features recover x1..x4 with positive exact weights",
            "global_optimality_argument": "The control polytope is convex; exact feasibility and zero gradient with zero multipliers satisfy convex quadratic KKT, proving the global minimum. Strict convexity in the terminal state makes the optimal terminal state unique.",
            "pre_registered_bands_unchanged": ["|J* - 30.899| <= 0.0005", "J* < 30.8985", "J* > 30.8995"],
            "band_verdict": band_verdict(squared),
            "other_bands": ["J* < 30.8985: not applicable", "J* > 30.8995: not applicable"],
        },
        "optimal_family": {
            "representation": "bounded 16-control H-polytope with an exact affine lift to the 84 state/control coordinates",
            "latent_variables": [f"u{stage}" for stage in range(HORIZON)],
            "joint_coordinate_order": "x0,x1,...,x16,u0,u1,...,u15 (state vectors are coordinate-major within each stage)",
            "control_polytope_rows": [{"name": name, "coefficients": [rational(value) for value in row], "upper": rational(bound)}
                                      for name, row, bound in h_rows],
            "terminal_equalities": fiber_equalities,
            "affine_lift": [{"stage": stage, "offset": [rational(value) for value in offset],
                             "control_coefficients": [[rational(value) for value in row] for row in matrix]}
                            for stage, (offset, matrix) in enumerate(state_maps)],
            "induced_terminal_set": {"kind": "singleton", "point": [rational(value) for value in terminal]},
            "coverage_argument": "Every feasible history in the exact terminal fiber has the certified optimum value. Conversely, strict convexity in terminal state forces every optimal history into this fiber. The H rows and affine lift therefore encode the full joint optimizer relation without materializing an 84-dimensional H matrix.",
            "bounded": True,
            "query_contract": ["exact control-vector membership in the terminal fiber", "exact full state/control history membership", "exact 84-coordinate history reconstruction from a control vector", "terminal-state projection (singleton)", "other geometric projections are unsupported unless separately computed with exact arithmetic"],
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "scenario_id": result["scenario_id"],
                      "objective": result["optimality"]["objective_approximation"],
                      "band": result["optimality"]["band_verdict"],
                      "rows": len(h_rows), "fiber_dimension": HORIZON}, sort_keys=True))


if __name__ == "__main__":
    main()
