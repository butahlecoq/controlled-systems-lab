"""Full-state membership constraints for an exported affine history."""
from __future__ import annotations

import casadi as ca
import numpy as np


def _array(value, shape, name):
    result = np.asarray(value, dtype=float)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError("invalid geometry " + name)
    return result


def parse(entries, dimension):
    """Validate portable memberships; indices refer to canonical history state coordinates."""
    result = []
    for entry in entries:
        kind = entry["kind"]
        indices = entry["indices"]
        if (not indices or any(not isinstance(i, int) or isinstance(i, bool) or i < 0 or i >= dimension
                               for i in indices) or len(set(indices)) != len(indices)):
            raise ValueError("invalid geometry coordinate indices")
        count = len(indices)
        if kind == "h":
            inequalities = entry["inequalities"]
            equalities = entry["equalities"]
            result.append((kind, indices,
                _array(inequalities, (len(inequalities), count), "inequalities") if inequalities else np.empty((0, count)),
                _array(entry["upper_bounds"], (len(inequalities),), "upper bounds"),
                _array(equalities, (len(equalities), count), "equalities") if equalities else np.empty((0, count)),
                _array(entry["equality_values"], (len(equalities),), "equality values")))
        elif kind in {"zonotope", "ellipsoid"}:
            center = _array(entry["center"], (count,), "center")
            columns = entry["factor_count"]
            if not isinstance(columns, int) or isinstance(columns, bool) or columns < 0:
                raise ValueError("invalid geometry factor count")
            matrix = _array(entry["factor"], (count, columns), "factor matrix")
            result.append((kind, indices, center, matrix))
        else:
            raise ValueError("unknown geometry membership kind")
    return result


def constrain(opti, z, entries, initial):
    """Add each membership without modifying the original cost."""
    factors = []
    for entry in entries:
        kind, indices, *data = entry
        x = ca.vertcat(*(z[i] for i in indices))
        if kind == "h":
            A, b, E, e = data
            if len(A):
                opti.subject_to(ca.DM(A) @ x <= ca.DM(b))
            if len(E):
                opti.subject_to(ca.DM(E) @ x == ca.DM(e))
            factors.append(None)
        else:
            center, matrix = data
            columns = matrix.shape[1]
            if columns:
                factor = opti.variable(columns)
                opti.subject_to(x == ca.DM(center) + ca.DM(matrix) @ factor)
                if kind == "zonotope":
                    opti.subject_to(opti.bounded(-1, factor, 1))
                else:
                    opti.subject_to(ca.sumsqr(factor) <= 1)
                opti.set_initial(factor, 0)
                factors.append(factor)
            else:
                opti.subject_to(x == ca.DM(center))
                factors.append(None)
    return factors


def verify(entries, primal, factors, *, tolerance=1e-7):
    """Independently check the actual H rows and factor witnesses returned by the solver."""
    z = np.asarray(primal, dtype=float)
    if len(entries) != len(factors) or z.ndim != 1 or not np.isfinite(z).all():
        raise ValueError("invalid geometry witness")
    checks = []
    for entry, witness in zip(entries, factors):
        kind, indices, *data = entry
        x = z[indices]
        if kind == "h":
            A, b, E, e = data
            residual = max(float(np.max(A @ x - b, initial=0)),
                           float(np.max(np.abs(E @ x - e), initial=0)))
        else:
            center, matrix = data
            factor = _array(witness, (matrix.shape[1],), "factor witness")
            reconstruction = float(np.max(np.abs(x - center - matrix @ factor), initial=0))
            bound = (float(np.max(np.abs(factor), initial=0)) - 1 if kind == "zonotope"
                     else float(np.linalg.norm(factor)) - 1)
            residual = max(0.0, reconstruction, bound)
        checks.append({"kind": kind, "max_residual": residual, "passed": residual <= tolerance})
    return {"accepted": all(c["passed"] for c in checks), "checks": checks}
