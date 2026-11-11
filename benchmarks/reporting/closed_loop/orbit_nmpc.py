"""Task-aware direct-shooting NMPC for the continuous Earth-orbit task."""
from __future__ import annotations

import time

import casadi as ca
import numpy as np


def solve(task: dict, observed: np.ndarray, stage: int, previous_prediction=None) -> dict:
    """Solve the shrinking full-state orbit NLP with the source norm objective."""
    started = time.monotonic()
    n = task["episode"]["intervals"]
    h = n - stage
    dt = task["episode"]["dt"]
    scales = np.asarray([v["scale"] for v in task["model"]["states"]])
    p = {name: row["value"] for name, row in task["model"]["parameters"].items()}
    target = task["objective"]["target"]
    opti = ca.Opti()
    u = opti.variable(2, h)
    x = opti.variable(4, h + 1)  # scaled physical coordinates
    terminal_norm = opti.variable()
    running_norm = opti.variable(h)
    opti.subject_to(x[:, 0] == ca.DM(observed / scales))
    bounds = task["control_domains"]["continuous"]["bounds"]
    for k in range(h):
        opti.subject_to(opti.bounded(bounds[0][0], u[0, k], bounds[0][1]))
        opti.subject_to(opti.bounded(bounds[1][0], u[1, k], bounds[1][1]))

        def f(z):
            r, v, theta, omega = [z[i] * scales[i] for i in range(4)]
            mu = p["G"] * p["M_earth"]
            return ca.vertcat(v, r * omega**2 - mu / r**2 + u[0, k] / (1000 * p["m_vehicle"]),
                              omega, -2 * omega * v / r + u[1, k] / (1000 * p["m_vehicle"] * r)) / ca.DM(scales)

        z = x[:, k]
        k1 = f(z); k2 = f(z + dt * k1 / 2); k3 = f(z + dt * k2 / 2); k4 = f(z + dt * k3)
        opti.subject_to(x[:, k + 1] == z + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6)
        opti.subject_to(x[0, k + 1] >= 1e-12)  # numerical representation of the source r>0 domain
        if stage + k <= 18:
            opti.subject_to(running_norm[k] >= 0)
            opti.subject_to(running_norm[k] ** 2 >= u[0, k] ** 2 + u[1, k] ** 2)
        else:
            opti.subject_to(running_norm[k] == 0)
    final_r = x[0, h] * scales[0]
    final_omega = x[3, h] * scales[3]
    dr = target["radius_km"] - final_r
    dw = 100000 * (target["angular_rate_rad_s"] - final_omega)
    opti.subject_to(terminal_norm >= 0)
    opti.subject_to(terminal_norm**2 >= dr**2 + dw**2)
    opti.minimize(terminal_norm + 0.1 * ca.sum1(running_norm))
    if previous_prediction is None:
        opti.set_initial(u, 0)
        opti.set_initial(x, np.tile(observed / scales, (h + 1, 1)).T)
    else:
        previous_controls = np.asarray(previous_prediction["predicted_controls"])
        shifted = previous_controls[1:]
        if shifted.shape != (h, 2):
            shifted = np.vstack([shifted, np.zeros((h - len(shifted), 2))])
        opti.set_initial(u, shifted.T)
        shifted_states = np.asarray(previous_prediction["predicted_mesh_physical"])[1:]
        if shifted_states.shape == (h + 1, 4):
            opti.set_initial(x, (shifted_states / scales).T)
        else:
            opti.set_initial(x, np.tile(observed / scales, (h + 1, 1)).T)
    initial_dr = target["radius_km"] - observed[0]
    initial_dw = 100000 * (target["angular_rate_rad_s"] - observed[3])
    opti.set_initial(terminal_norm, float(np.hypot(initial_dr, initial_dw)))
    opti.set_initial(running_norm, 0)
    opti.solver("ipopt", {"expand": True, "print_time": False}, {"max_iter": 3000, "tol": 1e-9,
        "acceptable_tol": 1e-8, "bound_relax_factor": 0.0, "print_level": 0})
    try:
        solution = opti.solve()
        controls = np.asarray(solution.value(u), dtype=float).reshape((2, h), order="F").T
        states = np.asarray(solution.value(x)).T * scales
        objective = float(solution.value(opti.f))
        status = str(opti.stats().get("return_status", "unknown"))
        success = bool(opti.stats().get("success", False) and np.isfinite(controls).all() and np.isfinite(states).all())
    except Exception as error:
        return {"accepted": False, "success": False, "status": "solver-error", "error": str(error),
                "solve_seconds": time.monotonic() - started, "solver_profile": "casadi-ipopt/direct-shooting-rk4-1-step/epigraph-exact-euclidean/1"}
    direct = np.hypot(target["radius_km"] - states[-1, 0],
                      100000 * (target["angular_rate_rad_s"] - states[-1, 3]))
    direct += 0.1 * sum(np.hypot(*controls[k]) for k in range(h) if stage + k <= 18)
    return {"accepted": success and abs(direct - objective) <= 1e-6 * max(1.0, abs(direct)),
            "success": success, "status": status, "objective": objective, "objective_recomputed": float(direct),
            "objective_reconstruction_difference": float(abs(direct - objective)),
            "solve_seconds": time.monotonic() - started, "predicted_controls": controls.tolist(),
            "predicted_mesh_physical": states.tolist(), "solver_iterations": opti.stats().get("iter_count"),
            "warm_start_policy": "shift-prior-primal-drop-first-stage-no-terminal-repeat;zero-duals",
            "assurance": "local NLP diagnostics only; direct RK4 transcription; exact source norms represented by epigraphs; no global nonlinear certificate",
            "solver_profile": "casadi-ipopt/direct-shooting-rk4-1-step/epigraph-exact-euclidean/1"}
