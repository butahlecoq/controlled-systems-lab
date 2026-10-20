from fractions import Fraction
from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parent

def f(value):
    return Fraction(str(value))

def dot(left, right):
    return sum((a * b for a, b in zip(left, right)), Fraction(0))

def matvec(matrix, vector):
    return [dot(row, vector) for row in matrix]

def matmul(left, right):
    return [[dot(row, [right[i][j] for i in range(len(right))]) for j in range(len(right[0]))] for row in left]

def transpose(matrix):
    return [list(column) for column in zip(*matrix)]

def solve2(matrix, rhs):
    a, b = matrix[0]
    c, d = matrix[1]
    determinant = a * d - b * c
    if determinant == 0:
        raise ValueError("Terminal-plane Gram matrix is singular")
    return [(rhs[0] * d - b * rhs[1]) / determinant,
            (a * rhs[1] - rhs[0] * c) / determinant]

def parse_case():
    case = json.loads((ROOT / "canonical-case.json").read_text(encoding="utf-8-sig"))
    if case["case_id"] != "b04-reference-v1" or case["source_scenario_id"] != "B04-historical":
        raise ValueError("Reference scenario identity mismatch")
    if case["horizon"] != 16 or case["state_dimension"] != 4 or case["control_dimension"] != 1:
        raise ValueError("Reference case dimensions mismatch")
    if case["owner_authorized_control_interval"]["date"] != "2026-10-19":
        raise ValueError("Owner authorization date mismatch")
    if case["owner_authorized_control_interval"]["lower"] != "-1" or case["owner_authorized_control_interval"]["upper"] != "1":
        raise ValueError("Owner-authorized control interval mismatch")
    if case["explicit_exclusions"] != [
        "No additional stock constraints are added because the source does not specify their numerical values.",
        "No fixed first action is added; the owner-authorized variant uses the continuous control interval on all sixteen stages.",
        "This case makes no reproduction claim for the published terminal state, objective, runtime, or historical optimizer.",
    ]:
        raise ValueError("Variant exclusions changed")
    return case

def case_matrices(case):
    n, horizon = case["state_dimension"], case["horizon"]
    raw_a = case["dynamics"]["A_row_major"]
    A = [[f(raw_a[i*n+j]) for j in range(n)] for i in range(n)]
    B = [f(value) for value in case["dynamics"]["B"]]
    affine = [f(value) for value in case["dynamics"]["affine"]]
    x0 = [f(value) for value in case["initial_state"]]
    Wraw, rows = case["terminal_objective"]["W_row_major"], case["terminal_objective"]["matrix_rows"]
    W = [[f(Wraw[i*n+j]) for j in range(n)] for i in range(rows)]
    target = [f(value) for value in case["terminal_objective"]["target"]]
    return A, B, affine, x0, W, target

def exact_reference_optimum(case):
    A, B, affine, x0, W, target = case_matrices(case)
    n, horizon = case["state_dimension"], case["horizon"]
    identity = [[Fraction(int(i == j)) for j in range(n)] for i in range(n)]
    N = [[A[i][j] - identity[i][j] for j in range(n)] for i in range(n)]
    if matmul(N, N) != [[Fraction(0) for _ in range(n)] for _ in range(n)]:
        raise ValueError("Frozen affine model no longer has the audited nilpotent form")
    if any(affine):
        raise ValueError("This checker expects the frozen zero-affine model")
    base = x0[:]
    for _ in range(horizon):
        base = matvec(A, base)
    NB = matvec(N, B)
    WB, WNB = matvec(W, B), matvec(W, NB)
    y = [left - right for left, right in zip(matvec(W, base), target)]
    gram = [[dot(WB, WB), dot(WB, WNB)], [dot(WNB, WB), dot(WNB, WNB)]]
    s, m = solve2(gram, [-dot(WB, y), -dot(WNB, y)])
    terminal = [base[i] + B[i] * s + NB[i] * m for i in range(n)]
    residual = [value - reference for value, reference in zip(matvec(W, terminal), target)]
    squared_norm = dot(residual, residual)

    # An exact feasible history realizes the unrestricted terminal-plane minimizer.
    middle = (m + 1) / 14
    controls = [Fraction(-1), middle + 1] + [Fraction(0)] * 13 + [s - middle]
    if len(controls) != horizon:
        raise ValueError("Constructed history has the wrong horizon")
    expected_s = sum(controls, Fraction(0))
    expected_m = sum((Fraction(horizon - 1 - k) * controls[k] for k in range(horizon)), Fraction(0))
    if (expected_s, expected_m) != (s, m):
        raise ValueError("Constructed history does not realize the optimal terminal moments")

    lower_u, upper_u = f(case["control_bounds_each_stage"]["lower"]), f(case["control_bounds_each_stage"]["upper"])
    states = [x0]
    for u in controls:
        if not lower_u <= u <= upper_u:
            raise ValueError("Exact optimal history violates a control bound")
        states.append([sum((A[i][j] * states[-1][j] for j in range(n)), Fraction(0)) + B[i] * u + affine[i] for i in range(n)])
    stage_start, stage_end = case["state_bound_stages"]
    for stage in range(stage_start, stage_end + 1):
        for bound in case["state_bounds_each_stage"]:
            value = states[stage][bound["coordinate"]]
            if not f(bound["lower"]) <= value <= f(bound["upper"]):
                raise ValueError(f"Exact optimal history violates stage {stage} state bound")
    if states[-1] != terminal:
        raise ValueError("Exact feasible trajectory does not reach the terminal-plane minimizer")
    return {
        "terminal_base_exact": [str(value) for value in base],
        "terminal_plane_basis_exact": [[str(value) for value in B], [str(value) for value in NB]],
        "sum_controls_exact": str(s),
        "weighted_sum_controls_exact": str(m),
        "exact_optimal_terminal_state": [str(value) for value in terminal],
        "exact_optimal_controls_one_solution": [str(value) for value in controls],
        "exact_optimal_states_one_solution": [[str(value) for value in state] for state in states],
        "exact_squared_norm_optimum_fraction": str(squared_norm),
        "exact_squared_norm_optimum_decimal": format(float(squared_norm), ".17g"),
        "exact_norm_optimum_decimal": format(math.sqrt(float(squared_norm)), ".17g"),
        "global_optimality_argument": "The exact minimizer over the entire affine terminal plane is attained by the exact control history above, which satisfies every declared control and stagewise flow bound. It is therefore also a global optimum of this constrained reference variant.",
    }

def read_key_values(name):
    raw = {}
    for line in (ROOT / name).read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            raw[key] = value
    return raw

def verify_solver(case, optimum, raw):
    A, B, affine, x0, W, target = case_matrices(case)
    horizon, n = case["horizon"], case["state_dimension"]
    values = {key: Fraction.from_float(float(value)) for key, value in raw.items() if key not in ("case", "solver")}
    states = [[values[f"x{k}_{i}"] for i in range(n)] for k in range(horizon + 1)]
    controls = [values[f"u{k}"] for k in range(horizon)]
    residuals = {}
    for i in range(n):
        residuals[f"initial_{i}"] = states[0][i] - x0[i]
    for k in range(horizon):
        for i in range(n):
            prediction = sum((A[i][j] * states[k][j] for j in range(n)), Fraction(0)) + B[i] * controls[k] + affine[i]
            residuals[f"dynamics_{k}_{i}"] = states[k+1][i] - prediction
        lo, hi = f(case["control_bounds_each_stage"]["lower"]), f(case["control_bounds_each_stage"]["upper"])
        residuals[f"control_lower_{k}"] = max(lo - controls[k], Fraction(0))
        residuals[f"control_upper_{k}"] = max(controls[k] - hi, Fraction(0))
    for k in range(case["state_bound_stages"][0], case["state_bound_stages"][1] + 1):
        for bound in case["state_bounds_each_stage"]:
            value = states[k][bound["coordinate"]]
            residuals[f"state_lower_{k}_{bound['coordinate']}"] = max(f(bound["lower"]) - value, Fraction(0))
            residuals[f"state_upper_{k}_{bound['coordinate']}"] = max(value - f(bound["upper"]), Fraction(0))
    terminal_residual = [a - b for a, b in zip(matvec(W, states[-1]), target)]
    squared_norm = dot(terminal_residual, terminal_residual)
    exact_sq_gap = squared_norm - f(optimum["exact_squared_norm_optimum_fraction"])
    max_violation = max([abs(value) for key, value in residuals.items() if key.startswith(("initial_", "dynamics_"))] + [value for key, value in residuals.items() if key.startswith(("control_", "state_"))])
    residual_keys = ("res_stationarity", "res_dynamics", "res_inequality", "res_complementarity")
    return {
        "acados_status": int(raw["status"]),
        "witness_controls_exact_binary_rational": [str(value) for value in controls],
        "witness_terminal_state_exact_binary_rational": [str(value) for value in states[-1]],
        "exact_constraint_residuals": {key: str(value) for key, value in residuals.items()},
        "largest_exact_constraint_violation_fraction": str(max_violation),
        "largest_exact_constraint_violation_decimal": format(float(max_violation), ".17g"),
        "witness_squared_norm_exact": str(squared_norm),
        "witness_squared_norm_decimal": format(float(squared_norm), ".17g"),
        "witness_norm_decimal": format(math.sqrt(float(squared_norm)), ".17g"),
        "exact_squared_objective_gap_fraction": str(exact_sq_gap),
        "exact_squared_objective_gap_decimal": format(float(exact_sq_gap), ".17g"),
        "norm_gap_decimal": format(math.sqrt(float(squared_norm)) - math.sqrt(float(f(optimum["exact_squared_norm_optimum_fraction"]))), ".17g"),
        "acados_residuals": {key: raw[key] for key in residual_keys},
        "acados_variable_objective": raw["variable_objective"],
        "canonical_squared_objective_offset": raw["squared_objective_offset"],
    }

def verify_highs(optimum, raw):
    if raw["termination"] != "completed" or raw["outcome"] != "optimal":
        raise SystemExit("Project HiGHS adapter did not report an optimal terminal-plane problem")
    if int(read_key_values("highs-exit.txt")["exit_code"]) != 0:
        raise SystemExit("Project HiGHS executable did not return success")
    exact_sq = f(optimum["exact_squared_norm_optimum_fraction"])
    highs_value = Fraction.from_float(float(raw["certified_squared_value"]))
    highs_norm = math.sqrt(2.0 * float(raw["certified_squared_value"]))
    exact_norm = math.sqrt(float(exact_sq))
    norm_gap = highs_norm - exact_norm
    if abs(norm_gap) > 1e-5:
        raise SystemExit("HiGHS converted norm does not match exact terminal-plane optimum")
    moments = [Fraction.from_float(float(raw[key])) for key in ("x0", "x1")]
    exact_moments = [f(optimum["sum_controls_exact"]), f(optimum["weighted_sum_controls_exact"])]
    return {
        "termination": raw["termination"], "outcome": raw["outcome"],
        "certified_squared_value_half_norm_squared": raw["certified_squared_value"],
        "converted_norm_sqrt_two_times_value": format(highs_norm, ".17g"),
        "exact_norm_optimum": format(exact_norm, ".17g"),
        "norm_gap": format(norm_gap, ".17g"),
        "exact_squared_value_gap": str(highs_value - exact_sq),
        "terminal_moments": [raw["x0"], raw["x1"]],
        "terminal_moment_errors_exact_binary_rational": [str(moments[i] - exact_moments[i]) for i in range(2)],
        "raw_diagnostics": raw.get("raw_diagnostics", ""),
    }

def main():
    case = parse_case()
    optimum = exact_reference_optimum(case)
    (ROOT / "exact-optimal-reference.json").write_text(json.dumps(optimum, indent=2) + "\n", encoding="utf-8")
    highs_report = None
    if (ROOT / "highs-output.log").exists():
        highs_report = verify_highs(optimum, read_key_values("highs-output.log"))
    if not (ROOT / "solver-output.log").exists():
        report = {"case_id": case["case_id"], "exact_global_optimum": optimum, "highs_check": highs_report}
        (ROOT / "highs-check-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return
    if highs_report is None:
        raise SystemExit("HiGHS output is required before the acados witness run")
    raw = read_key_values("solver-output.log")
    verification = verify_solver(case, optimum, raw)
    status_code = verification["acados_status"]
    verification["acados_status_name"] = {0: "ACADOS_SUCCESS", 1: "ACADOS_NAN_DETECTED", 2: "ACADOS_MAXITER", 3: "ACADOS_MINSTEP", 4: "ACADOS_QP_FAILURE"}.get(status_code, f"ACADOS_STATUS_{status_code}")
    executable_exit = int(read_key_values("solver-exit.txt")["exit_code"])
    verification["acados_executable_exit_code"] = executable_exit
    norm_gap = float(verification["witness_norm_decimal"]) - float(highs_report["converted_norm_sqrt_two_times_value"])
    verification["highs_check"] = highs_report
    verification["highs_norm_minus_acados_witness_norm"] = format(norm_gap, ".17g")
    if abs(norm_gap) > 1e-5:
        raise SystemExit("HiGHS converted norm does not match independently checked acados witness norm")
    report = {"case_id": case["case_id"], "exact_global_optimum": optimum, "acados_witness_check": verification}
    (ROOT / "exact-check-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if verification["acados_status"] != 0 or executable_exit != 0:
        raise SystemExit("Evidence recorded, but acados acceptance failed: solver status or executable exit was nonzero")

if __name__ == "__main__":
    main()
