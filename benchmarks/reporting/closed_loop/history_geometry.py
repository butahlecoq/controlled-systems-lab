"""Full-state membership constraints for an exported affine history."""

from __future__ import annotations

from fractions import Fraction

import casadi as ca
import numpy as np


def _array(value, shape, name):
    result = np.asarray(value, dtype=float)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError("invalid geometry " + name)
    return result


def _lifted_rows(relation, dimension):
    result = []
    for rows_key, values_key in (
        ("inequalities", "upper_bounds"),
        ("equalities", "equality_values"),
    ):
        rows = relation[rows_key]
        matrix = (
            _array(rows, (len(rows), dimension), rows_key) if rows else np.empty((0, dimension))
        )
        values = _array(relation[values_key], (len(rows),), values_key)
        result.append((rows_key, matrix, values))
    return result


def _lifted_slices(selection, rows):
    if selection == {"kind": "full"}:
        return [(matrix, rhs, key == "equalities") for key, matrix, rhs in rows]
    if not isinstance(selection, dict) or selection.get("kind") != "prefix":
        raise ValueError("invalid lifted history row selection")
    result = []
    for key, matrix, rhs in rows:
        ranges = selection.get(key)
        if not isinstance(ranges, list):
            raise ValueError("invalid lifted history row ranges")
        last_end = 0
        for interval in ranges:
            if (
                not isinstance(interval, list)
                or len(interval) != 2
                or any(type(i) is not int for i in interval)
            ):
                raise ValueError("invalid lifted history row range")
            lo, hi = interval
            if not last_end <= lo < hi <= len(matrix):
                raise ValueError("invalid lifted history row range bounds")
            result.append((matrix[lo:hi], rhs[lo:hi], key == "equalities"))
            last_end = hi
    return result


def parse(entries, dimension, *, relation=None, history_dimension=None):
    """Validate portable memberships; indices refer to canonical history state coordinates."""
    result = []
    reuse_rows = None
    for entry in entries:
        kind = entry["kind"]
        indices = entry["indices"]
        if (
            not indices
            or any(
                not isinstance(i, int) or isinstance(i, bool) or i < 0 or i >= dimension
                for i in indices
            )
            or len(set(indices)) != len(indices)
        ):
            raise ValueError("invalid geometry coordinate indices")
        count = len(indices)
        if kind == "lifted-h":
            if (
                not relation
                or relation.get("representation") != "polytope-h"
                or not relation.get("set_id")
                or relation["set_id"] != entry.get("history_set_id")
            ):
                raise ValueError("lifted projection must refer to the mandatory original H history")
            if reuse_rows is None:
                reuse_rows = _lifted_rows(relation, history_dimension or dimension)
            result.append((kind, indices, _lifted_slices(entry.get("row_selection"), reuse_rows)))
        elif kind == "h":
            inequalities = entry["inequalities"]
            equalities = entry["equalities"]
            result.append(
                (
                    kind,
                    indices,
                    _array(inequalities, (len(inequalities), count), "inequalities")
                    if inequalities
                    else np.empty((0, count)),
                    _array(entry["upper_bounds"], (len(inequalities),), "upper bounds"),
                    _array(equalities, (len(equalities), count), "equalities")
                    if equalities
                    else np.empty((0, count)),
                    _array(entry["equality_values"], (len(equalities),), "equality values"),
                )
            )
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


def fixed_axis_witnesses(entries, fixed, *, include_zonotopes=False):
    """Prove which supported axis factor sets contain a fixed original H block."""
    witnesses = {}
    for position, (kind, indices, *data) in enumerate(entries):
        if kind != "ellipsoid" and not (include_zonotopes and kind == "zonotope"):
            continue
        if any(index not in fixed for index in indices):
            continue
        center, factor = data
        if factor.shape != (len(indices), len(indices)) or np.any(
            factor != np.diag(np.diag(factor))
        ):
            continue

        values = []
        for column, index in enumerate(indices):
            residual = Fraction(fixed[index]) - Fraction(float(center[column]))
            scale = Fraction(float(factor[column, column]))
            if scale == 0 and residual != 0:
                break
            values.append(residual / scale if scale else Fraction(0))
        if len(values) != len(indices):
            continue
        admissible = (
            all(abs(value) <= 1 for value in values)
            if kind == "zonotope"
            else sum(value * value for value in values) <= 1
        )
        if admissible:
            witnesses[position] = list(map(float, values))
    return witnesses


def constrain(opti, z, entries, initial, *, physical_scales=None):
    """Add each membership without modifying the original cost."""
    factors = []
    for entry in entries:
        kind, indices, *data = entry
        if kind == "lifted-h":
            # The original full H constraints already include every selected row.
            factors.append(None)
            continue
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
                if physical_scales is None:
                    opti.subject_to(x == ca.DM(center) + ca.DM(matrix) @ factor)
                else:
                    residual = x - ca.DM(center) - ca.DM(matrix) @ factor
                    opti.subject_to(residual / ca.DM(physical_scales[indices]) == 0)
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
    for entry, witness in zip(entries, factors, strict=True):
        kind, indices, *data = entry
        x = z[indices]
        if kind == "lifted-h":
            _array(witness, (0,), "lifted witness")
            residual = 0.0
            for matrix, rhs, equality in data[0]:
                delta = matrix @ z - rhs
                if not np.isfinite(delta).all():
                    raise ValueError("nonfinite lifted membership residual")
                if equality:
                    delta = np.abs(delta)
                residual = max(residual, float(np.max(delta, initial=0)))
        elif kind == "h":
            A, b, E, e = data
            residual = max(
                float(np.max(A @ x - b, initial=0)), float(np.max(np.abs(E @ x - e), initial=0))
            )
        else:
            center, matrix = data
            factor = _array(witness, (matrix.shape[1],), "factor witness")
            reconstruction = float(np.max(np.abs(x - center - matrix @ factor), initial=0))
            bound = (
                float(np.max(np.abs(factor), initial=0)) - 1
                if kind == "zonotope"
                else float(np.linalg.norm(factor)) - 1
            )
            residual = max(0.0, reconstruction, bound)
        checks.append({"kind": kind, "max_residual": residual, "passed": residual <= tolerance})
    return {"accepted": all(c["passed"] for c in checks), "checks": checks}
