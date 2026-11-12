"""Independent acceptance checks for a source-bound affine history."""
from __future__ import annotations

import numpy as np

from task_models import objective


def validate(task, stage, observed, predictor_stages, relation, primal, solver_cost,
             *, absolute_tolerance=1e-7, relative_tolerance=1e-8):
    n = len(task["model"]["states"])
    m = len(task["model"]["controls"])
    horizon = task["episode"]["intervals"] - stage
    z = np.asarray(primal, dtype=float)
    observed = np.asarray(observed, dtype=float)
    if (horizon <= 0 or len(predictor_stages) != horizon or observed.shape != (n,)
            or z.shape != ((horizon + 1) * n + horizon * m,)
            or not np.isfinite(z).all() or not np.isfinite(observed).all()
            or not np.isfinite(solver_cost)):
        raise ValueError("invalid full-history result")
    states = z[:(horizon + 1) * n].reshape(horizon + 1, n)
    controls = z[(horizon + 1) * n:].reshape(horizon, m)
    checks = {}

    def compare(name, lhs, rhs, inequality=False):
        lhs = np.asarray(lhs, dtype=float)
        rhs = np.asarray(rhs, dtype=float)
        if lhs.shape != rhs.shape or not np.isfinite(lhs).all() or not np.isfinite(rhs).all():
            raise ValueError("invalid " + name + " values")
        residual = lhs - rhs
        if inequality:
            residual = np.maximum(residual, 0)
        else:
            residual = np.abs(residual)
        allowed = absolute_tolerance + relative_tolerance * np.maximum(np.abs(lhs), np.abs(rhs))
        checks[name] = {"max_residual": float(np.max(residual, initial=0)),
                        "passed": bool(np.all(residual <= allowed))}

    compare("initial", states[0], observed)
    expected = []
    for x, u, row in zip(states, controls, predictor_stages):
        expected.append(np.asarray(row["A"]) @ x + np.asarray(row["B"]) @ u + np.asarray(row["c"]))
    compare("dynamics", states[1:], expected)
    for key, bounds, equality in (("inequalities", "upper_bounds", False),
                                   ("equalities", "equality_values", True)):
        rows = relation[key]
        if len(rows) != len(relation[bounds]):
            raise ValueError("history row and bound counts differ")
        if rows:
            matrix = np.asarray(rows, dtype=float)
            if matrix.shape != (len(rows), len(z)):
                raise ValueError("invalid full-history rows")
            compare(key, matrix @ z, relation[bounds], inequality=not equality)
        else:
            checks[key] = {"max_residual": 0.0, "passed": True}
    bounds = np.asarray(task["control_domains"]["continuous"]["bounds"], dtype=float)
    compare("control_upper", controls, np.broadcast_to(bounds[:, 1], controls.shape), inequality=True)
    compare("control_lower", -controls, np.broadcast_to(-bounds[:, 0], controls.shape), inequality=True)
    for i, field in enumerate(task["model"]["states"]):
        if field.get("bounds") is not None:
            lo, hi = field["bounds"]
            compare(f"state_{i}_upper", states[:, i], np.full(horizon + 1, hi), inequality=True)
            compare(f"state_{i}_lower", -states[:, i], np.full(horizon + 1, -lo), inequality=True)
    if task["model"]["case_id"] == "ENV717-EARTH-ORBIT-CONTINUOUS-01":
        checks["positive_radius"] = {"passed": bool(np.all(states[:, 0] > 0)),
                                      "minimum": float(np.min(states[:, 0]))}
    source_cost = objective(task, states, controls, absolute_stage_offset=stage)
    compare("source_cost", [solver_cost], [source_cost["total"]])
    return {"accepted": all(row["passed"] for row in checks.values()), "checks": checks,
            "source_cost": source_cost, "states": states.tolist(), "controls": controls.tolist()}
