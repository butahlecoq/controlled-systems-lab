"""Local full-history solver for an exported sum of residual norms."""
from __future__ import annotations

import casadi as ca
import numpy as np


def solve(relation: dict, objective: dict, *, initial, positive_indices=()) -> dict:
    """Solve the complete H relation with separate exact norm epigraphs.

    Positive coordinates are parameterized as exp(s), with no artificial
    lower bound. The caller must independently check the returned history.
    """
    initial = np.asarray(initial, dtype=float)
    if initial.ndim != 1 or not np.isfinite(initial).all():
        raise ValueError("initial history must be a finite vector")
    dimension = len(initial)
    positive = set(positive_indices)
    if any(index < 0 or index >= dimension or initial[index] <= 0 for index in positive):
        raise ValueError("positive-coordinate initial values must be positive")
    opti = ca.Opti()
    raw = opti.variable(dimension)
    z = ca.vertcat(*(ca.exp(raw[i]) if i in positive else raw[i] for i in range(dimension)))
    start = initial.copy()
    for index in positive:
        start[index] = np.log(start[index])
    opti.set_initial(raw, start)
    for matrix_key, bound_key, equality in (("inequalities", "upper_bounds", False),
                                            ("equalities", "equality_values", True)):
        rows = relation[matrix_key]
        bounds = relation[bound_key]
        if len(rows) != len(bounds):
            raise ValueError("history row and bound counts differ")
        if rows:
            matrix = np.asarray(rows, dtype=float)
            bound = np.asarray(bounds, dtype=float)
            if matrix.shape != (len(rows), dimension) or not np.isfinite(matrix).all() or not np.isfinite(bound).all():
                raise ValueError("invalid history relation")
            expression = ca.DM(matrix) @ z
            opti.subject_to(expression == ca.DM(bound) if equality else expression <= ca.DM(bound))
    quadratic = objective["quadratic"]
    q = np.asarray(quadratic["Q"], dtype=float)
    linear = np.asarray(quadratic["linear"], dtype=float)
    offset = float(quadratic["offset"])
    if q.shape != (dimension, dimension) or linear.shape != (dimension,) or not np.isfinite(q).all() or not np.isfinite(linear).all() or not np.isfinite(offset):
        raise ValueError("invalid history quadratic")
    cost = 0.5 * ca.mtimes([z.T, ca.DM(q), z]) + ca.dot(ca.DM(linear), z) + offset
    epigraph_initial = []
    for norm in objective["residual_norms"]:
        matrix = np.asarray(norm["map"], dtype=float)
        target = np.asarray(norm["target"], dtype=float)
        weights = np.asarray(norm["weights"], dtype=float)
        coefficient = float(norm["coefficient"])
        if matrix.shape != (len(target), dimension) or weights.shape != target.shape or not np.isfinite(matrix).all() or not np.isfinite(target).all() or not np.isfinite(weights).all() or np.any(weights < 0) or not np.isfinite(coefficient) or coefficient < 0:
            raise ValueError("invalid history residual norm")
        residual = ca.DM(np.sqrt(weights)) * (ca.DM(matrix) @ z - ca.DM(target))
        epigraph = opti.variable()
        opti.subject_to(epigraph >= 0)
        opti.subject_to(ca.sumsqr(residual) <= epigraph ** 2)
        epigraph_start = float(np.linalg.norm(np.sqrt(weights) * (matrix @ initial - target))) + 0.01
        opti.set_initial(epigraph, epigraph_start)
        epigraph_initial.append(epigraph_start)
        cost += coefficient * epigraph
    opti.minimize(cost)
    initial_duals = np.zeros(int(opti.g.numel()))
    opti.set_initial(opti.lam_g, initial_duals)
    warm_start = {"initial_primal": initial.tolist(), "raw_initial": start.tolist(),
                  "epigraph_initial": epigraph_initial, "initial_duals": initial_duals.tolist(),
                  "dual_policy": "zero-every-solve", "provider_initialization": "opti.set_initial",
                  "provider_initial_primal": np.asarray(opti.debug.value(z, opti.initial()), dtype=float).reshape(-1).tolist(),
                  "provider_initial_duals": np.asarray(opti.debug.value(opti.lam_g, opti.initial()), dtype=float).reshape(-1).tolist(),
                  "initialization_status": "submitted-and-read-back"}
    opti.solver("ipopt", {"print_time": False}, {"print_level": 0, "max_iter": 3000,
        "warm_start_init_point": "yes", "tol": 1e-9, "acceptable_tol": 1e-8, "bound_relax_factor": 0.0})
    try:
        solution = opti.solve()
        primal = np.asarray(solution.value(z), dtype=float).reshape(-1)
        stats = opti.stats()
        objective_value = float(solution.value(cost))
        if not np.isfinite(primal).all() or not np.isfinite(objective_value):
            return {"warm_start": warm_start, "success": False, "status": "nonfinite-solution",
                    "solver": "casadi-ipopt/full-history-separate-norm-epigraphs/1",
                    "provider": "casadi-ipopt", "version": f"casadi {ca.__version__}; IPOPT version unavailable"}
        return {"warm_start": warm_start, "success": bool(stats.get("success")),
                "status": str(stats.get("return_status", "unknown")), "primal": primal.tolist(),
                "objective": objective_value, "iterations": stats.get("iter_count"),
                "solver": "casadi-ipopt/full-history-separate-norm-epigraphs/1",
                "provider": "casadi-ipopt", "version": f"casadi {ca.__version__}; IPOPT version unavailable",
                "assurance": "local numerical NLP solution; no global optimality certificate"}
    except Exception as error:
        return {"warm_start": warm_start, "success": False, "status": "solver-error", "error": str(error),
                "solver": "casadi-ipopt/full-history-separate-norm-epigraphs/1",
                "provider": "casadi-ipopt", "version": f"casadi {ca.__version__}; IPOPT version unavailable"}
