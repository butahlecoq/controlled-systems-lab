"""One exploratory, candidate-only solve for the saved B04-c linear model.

This intentionally does not claim complete-family coverage or certified
optimality. Inputs are copied from issue #531 and the A39/A01/A40 record.
"""
from __future__ import annotations

from fractions import Fraction as F
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time

import numpy as np
import scipy
from scipy.optimize import Bounds, LinearConstraint, linprog, minimize


def rat(value: str) -> F:
    return F(value)


def main(output: str) -> None:
    n = 16
    initial = [rat(v) for v in (
        "122028265395983/100000000000", "119500",
        "27500360290561/62500000000", "45300")]
    b = [rat(v) for v in ("1104/55", "0", "-576/55", "0")]
    a = [[F(i == j) for j in range(4)] for i in range(4)]
    a[1][0] = rat("-25/4")
    a[3][2] = rat("-25/4")
    base, sens = initial, [[F(0) for _ in range(n)] for _ in range(4)]
    stage_base, stage_sens = [base], [sens]
    for k in range(n):
        base = [sum(a[i][j] * base[j] for j in range(4)) for i in range(4)]
        sens = [[sum(a[i][j] * sens[j][c] for j in range(4)) + (b[i] if c == k else 0)
                 for c in range(n)] for i in range(4)]
        stage_base.append(base)
        stage_sens.append(sens)

    # State phase box applies to x1 and x3 at stages 0 through 16.
    rows, lower, upper = [], [], []
    for state, lo, hi in ((0, F(1176), F(1224)), (2, F(432), F(468))):
        for k in range(17):
            rows.append(stage_sens[k][state])
            lower.append(lo - stage_base[k][state])
            upper.append(hi - stage_base[k][state])
    g = np.array([[float(x) for x in row] for row in rows])
    gl = np.array([float(x) for x in lower])
    gu = np.array([float(x) for x in upper])

    # Phi residual vector, with objective Phi^2 / 2.
    r = np.array([[-1, 0, 0, 0], [0, 1, 0, 0], [0, 0, -8/3, 0],
                  [0, 0, 0, 8/3], [0, 1, 0, -8/3]], dtype=float)
    c = np.array([1200, 0, 1200, 0, 0], dtype=float)
    f0 = np.array([float(x) for x in stage_base[-1]])
    m = np.array([[float(x) for x in row] for row in stage_sens[-1]])
    h = r @ m
    q = r @ f0 + c

    def objective(u):
        z = q + h @ u
        return 0.5 * float(z @ z)

    def gradient(u):
        return h.T @ (q + h @ u)

    started = time.perf_counter_ns()
    opt = minimize(objective, np.zeros(n), jac=gradient, method="SLSQP",
                   bounds=Bounds(-np.ones(n), np.ones(n)),
                   constraints=[LinearConstraint(g, gl, gu)],
                   options={"ftol": 1e-12, "maxiter": 4000, "disp": False})
    elapsed_ns = time.perf_counter_ns() - started

    # Separate LP feasibility check against the published coordinate rounding box.
    target = [rat(v) for v in ("12007/10", "-22929/1000", "2251/5", "-7709/1000")]
    radius = [F(1, 20), F(1, 2000), F(1, 20), F(1, 2000)]
    tm = np.array([[float(x) for x in row] for row in stage_sens[-1]])
    tb = np.array([float(x) for x in stage_base[-1]])
    target_float = np.array([float(x) for x in target])
    rad = np.array([float(x) for x in radius])
    # Maximize a common fraction of the printed rounding box as interior slack.
    aa = np.vstack((np.column_stack((g, np.zeros(len(g)))),
                    np.column_stack((-g, np.zeros(len(g)))),
                    np.column_stack((tm, rad)), np.column_stack((-tm, rad))))
    bb = np.concatenate((gu, -gl, target_float + rad - tb,
                         tb - target_float + rad))
    reach = linprog(np.concatenate((np.zeros(n), [-1.0])), A_ub=aa, b_ub=bb,
                    bounds=[(-1.0, 1.0)] * n + [(0.0, 1.0)], method="highs")

    # Replay the returned binary64 candidate with exact dyadic arithmetic.
    candidate = [F.from_float(float(x)) for x in opt.x]
    states = [initial]
    for k, u in enumerate(candidate):
        states.append([sum(a[i][j] * states[-1][j] for j in range(4)) + b[i] * u
                       for i in range(4)])
    phase_violations = []
    for k, state in enumerate(states):
        for index, lo, hi, label in ((0, F(1176), F(1224), "x1"),
                                     (2, F(432), F(468), "x3")):
            value = state[index]
            if value < lo or value > hi:
                phase_violations.append({"stage": k, "coordinate": label,
                    "violation": str(lo-value if value < lo else value-hi)})
    terminal = states[-1]
    z = [F(1200)-terminal[0], terminal[1], F(8,3)*(F(450)-terminal[2]),
         F(8,3)*terminal[3], terminal[1]-F(8,3)*terminal[3]]
    squared = sum(v*v for v in z)
    objective_value = float(squared) ** 0.5

    reach_exact = None
    if reach.success:
        reach_u = [F.from_float(float(x)) for x in reach.x[:n]]
        reach_states = [initial]
        for u in reach_u:
            reach_states.append([sum(a[i][j] * reach_states[-1][j] for j in range(4)) + b[i]*u
                                 for i in range(4)])
        reach_t = reach_states[-1]
        within_rounding = all(abs(reach_t[i]-target[i]) <= radius[i] for i in range(4))
        exact_phase_violations = []
        for k, state in enumerate(reach_states):
            for index, lo, hi, label in ((0, F(1176), F(1224), "x1"),
                                         (2, F(432), F(468), "x3")):
                if state[index] < lo or state[index] > hi:
                    exact_phase_violations.append({"stage": k, "coordinate": label})
        reach_exact = {"within_published_coordinate_rounding_exactly": within_rounding,
                       "maximized_common_fractional_rounding_slack": float(reach.x[-1]),
                       "phase_box_exactly_feasible": not exact_phase_violations,
                       "terminal_state_exact_dyadic": [str(x) for x in reach_t],
                       "phase_violations": exact_phase_violations,
                       "controls_binary64_hex": [float(x).hex() for x in reach.x[:n]]}

    flow_functional = F(12)*target[0] + F(23)*target[2]
    stock_functional = F(12)*target[1] + F(23)*target[3]
    objective_low = rat("30.8985") ** 2
    objective_high = rat("30.8995") ** 2
    if objective_low <= squared <= objective_high:
        band_verdict = "within pre-registered confirmation band"
    elif squared < objective_low:
        band_verdict = "below pre-registered lower band"
    else:
        band_verdict = "above pre-registered upper band"
    record = {
        "schema": "csl.b04-c-preliminary/1", "scenario_id": "B04-c-preliminary-numerical-20261023",
        "authorization_issue": 531, "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True).strip(),
        "input_authority": "A39/A01/A40 saved-family model as specified in issue #531; not B04-historical",
        "input": {"initial": [str(x) for x in initial], "A": [[str(x) for x in row] for row in a],
            "B": [str(x) for x in b], "horizon": n, "control_bounds": ["-1", "1"],
            "phase_box": {"stages": [0, 16], "x1": [1176, 1224], "x3": [432, 468]},
            "objective": "sqrt((1200-x1)^2+x2^2+(64/9)*(450-x3)^2+(64/9)*x4^2+(x2-(8/3)*x4)^2)"},
        "input_canonical_sha256": hashlib.sha256(json.dumps({"initial": [str(x) for x in initial],
            "A": [[str(x) for x in row] for row in a], "B": [str(x) for x in b],
            "horizon": n, "control_bounds": ["-1", "1"], "phase_box": [[1176, 1224], [432, 468]],
            "objective": "issue531"}, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "solver": {"scipy": scipy.__version__, "numpy": np.__version__, "method": "SLSQP",
                   "start": "zero control vector", "ftol": 1e-12, "maxiter": 4000,
                   "termination_success": bool(opt.success), "status": int(opt.status),
                   "message": str(opt.message), "iterations": int(opt.nit),
                   "elapsed_ns_single_call": elapsed_ns,
                   "linprog_method": "HiGHS", "reachability_status": int(reach.status),
                   "reachability_message": str(reach.message),
                   "reachability_success": bool(reach.success)},
        "candidate": {"objective": objective_value, "exact_squared_objective": str(squared),
            "controls_binary64_hex": [float(x).hex() for x in opt.x],
            "terminal_state_exact_dyadic": [str(x) for x in terminal],
            "terminal_state_float": [float(x) for x in terminal],
            "exact_phase_box_feasible": not phase_violations,
            "phase_box_violations": phase_violations,
            "max_control_abs": max(abs(float(x)) for x in opt.x),
            "stationarity_gradient_inf_norm_unprojected": float(np.linalg.norm(gradient(opt.x), ord=np.inf))},
        "published_point_reachability": reach_exact,
        "published_plane_residuals_exact": {
            "flow_12x1_plus_23x3_minus_3095440554305551_over_125000000000":
                str(flow_functional-rat("3095440554305551/125000000000")),
            "stock_12x2_plus_23x4_plus_565554305551_over_1250000000":
                str(stock_functional+rat("565554305551/1250000000"))},
        "pre_registered_bands_unchanged": [
            "|J* - 30.899| <= 0.0005", "J* < 30.8985", "J* > 30.8995"],
        "candidate_objective_band_location": band_verdict,
        "optimality_band_verdict": "inconclusive: no global optimum certificate",
        "evidence_limits": ["exploratory numerical candidate only",
            "no global optimality certificate", "no complete optimal-family coverage",
            "single solver and single start", "not a historical reproduction"],
    }
    with open(output, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(json.dumps({"status": record["solver"], "candidate": record["candidate"],
                      "published_point_reachability": record["published_point_reachability"]},
                     sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main(sys.argv[1])
