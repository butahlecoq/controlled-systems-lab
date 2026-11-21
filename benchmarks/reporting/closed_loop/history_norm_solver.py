"""Local full-history solver for an exported sum of residual norms."""

from __future__ import annotations

import casadi as ca
import numpy as np


def solve(
    relation: dict,
    objective: dict,
    *,
    initial,
    positive_indices=(),
    geometry_memberships=(),
    tighten_epigraph=False,
    physical_scales=None,
) -> dict:
    """Solve the complete H relation with separate exact norm epigraphs.

    Positive coordinates are parameterized as exp(s), with no artificial
    lower bound. Optional physical scales condition the NLP coordinates and
    equations. The caller must independently check the returned physical history.
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
    scales = None if physical_scales is None else np.asarray(physical_scales, dtype=float)
    if scales is None:
        z = ca.vertcat(*(ca.exp(raw[i]) if i in positive else raw[i] for i in range(dimension)))
        start = initial.copy()
        for index in positive:
            start[index] = np.log(start[index])
    else:
        if (
            scales.shape != initial.shape
            or not dimension
            or not np.isfinite(scales).all()
            or np.any(scales <= 0)
        ):
            raise ValueError(
                "physical scales must be finite and positive for each history coordinate"
            )
        ratios: dict[int, float] = {i: scales[i] / initial[i] for i in positive}
        if any(not np.isfinite(value) or value <= 0 for value in ratios.values()):
            raise ValueError("positive coordinate scale cannot be represented")
        start = np.zeros_like(initial)
        z = ca.vertcat(
            *(
                initial[i] * ca.exp(raw[i] * ratios[i])
                if i in positive
                else initial[i] + scales[i] * raw[i]
                for i in range(dimension)
            )
        )
    opti.set_initial(raw, start)
    fixed = {}
    for matrix_key, bound_key, equality in (
        ("inequalities", "upper_bounds", False),
        ("equalities", "equality_values", True),
    ):
        rows = relation[matrix_key]
        bounds = relation[bound_key]
        if len(rows) != len(bounds):
            raise ValueError("history row and bound counts differ")
        if rows:
            matrix = np.asarray(rows, dtype=float)
            bound = np.asarray(bounds, dtype=float)
            if (
                matrix.shape != (len(rows), dimension)
                or not np.isfinite(matrix).all()
                or not np.isfinite(bound).all()
            ):
                raise ValueError("invalid history relation")
            expression = ca.DM(matrix) @ z
            if scales is None:
                opti.subject_to(
                    expression == ca.DM(bound) if equality else expression <= ca.DM(bound)
                )
            else:
                row_scale = np.maximum(1e-12, np.max(np.abs(matrix * scales), axis=1))
                if not np.isfinite(row_scale).all():
                    raise ValueError("scaled history row overflow")
                residual = (expression - ca.DM(bound)) / ca.DM(row_scale)
                opti.subject_to(residual == 0 if equality else residual <= 0)
            if equality and geometry_memberships:
                for i in np.flatnonzero(np.count_nonzero(matrix, axis=1) == 1):
                    coordinate = int(np.flatnonzero(matrix[i])[0])
                    coefficient = matrix[i, coordinate]
                    if abs(coefficient) == 1:
                        fixed[coordinate] = float(bound[i] * coefficient)
    from history_geometry import constrain, fixed_axis_witnesses, parse, verify

    geometry = parse(geometry_memberships, dimension, relation=relation)
    fixed_witnesses = fixed_axis_witnesses(geometry, fixed, include_zonotopes=scales is not None)
    active = [index for index in range(len(geometry)) if index not in fixed_witnesses]
    factor_variables = constrain(
        opti, z, [geometry[index] for index in active], initial, physical_scales=scales
    )
    quadratic = objective["quadratic"]
    q = np.asarray(quadratic["Q"], dtype=float)
    linear = np.asarray(quadratic["linear"], dtype=float)
    offset = float(quadratic["offset"])
    if (
        q.shape != (dimension, dimension)
        or linear.shape != (dimension,)
        or not np.isfinite(q).all()
        or not np.isfinite(linear).all()
        or not np.isfinite(offset)
    ):
        raise ValueError("invalid history quadratic")
    cost = 0.5 * ca.mtimes([z.T, ca.DM(q), z]) + ca.dot(ca.DM(linear), z) + offset
    epigraph_initial = []
    for norm in objective["residual_norms"]:
        matrix = np.asarray(norm["map"], dtype=float)
        target = np.asarray(norm["target"], dtype=float)
        weights = np.asarray(norm["weights"], dtype=float)
        coefficient = float(norm["coefficient"])
        if (
            matrix.shape != (len(target), dimension)
            or weights.shape != target.shape
            or not np.isfinite(matrix).all()
            or not np.isfinite(target).all()
            or not np.isfinite(weights).all()
            or np.any(weights < 0)
            or not np.isfinite(coefficient)
            or coefficient < 0
        ):
            raise ValueError("invalid history residual norm")
        residual = ca.DM(np.sqrt(weights)) * (ca.DM(matrix) @ z - ca.DM(target))
        epigraph = opti.variable()
        opti.subject_to(epigraph >= 0)
        opti.subject_to(ca.sumsqr(residual) <= epigraph**2)
        epigraph_start = (
            float(np.linalg.norm(np.sqrt(weights) * (matrix @ initial - target))) + 0.01
        )
        opti.set_initial(epigraph, epigraph_start)
        epigraph_initial.append(epigraph_start)
        cost += coefficient * epigraph
    opti.minimize(cost)
    initial_duals = np.zeros(int(opti.g.numel()))
    opti.set_initial(opti.lam_g, initial_duals)
    warm_start = {
        "initial_primal": initial.tolist(),
        "raw_initial": start.tolist(),
        "epigraph_initial": epigraph_initial,
        "initial_duals": initial_duals.tolist(),
        "dual_policy": "zero-every-solve",
        "provider_initialization": "opti.set_initial",
        "provider_initial_primal": np.asarray(opti.debug.value(z, opti.initial()), dtype=float)
        .reshape(-1)
        .tolist(),
        "provider_initial_duals": np.asarray(
            opti.debug.value(opti.lam_g, opti.initial()), dtype=float
        )
        .reshape(-1)
        .tolist(),
        "initialization_status": "submitted-and-read-back",
    }
    if fixed_witnesses:
        warm_start["fixed_geometry_witnesses"] = list(fixed_witnesses)
    options = {
        "warm_start_init_point": "yes",
        "print_level": 0,
        "max_iter": 3000,
        "tol": 1e-9,
        "acceptable_tol": 1e-8,
        "bound_relax_factor": 0.0,
    }
    profile = "standard" if scales is None else "physical-scaling"
    if scales is not None:
        warm_start["physical_scales"] = scales.tolist()
        options["nlp_scaling_method"] = "none"
    if tighten_epigraph:
        profile = "tight-epigraph" if scales is None else "physical-scaling-tight-epigraph"
        options.update(
            {
                "max_iter": 6000,
                "tol": 1e-12,
                "acceptable_tol": 1e-11,
                "constr_viol_tol": 1e-12,
                "compl_inf_tol": 1e-12,
            }
        )
    opti.solver("ipopt", {"print_time": False}, options)

    # CasADi initializes this at import time, and its binding stubs omit it.
    provider_version = ca.__version__  # ty: ignore[missing-attribute]
    try:
        solution = opti.solve()
        primal = np.asarray(solution.value(z), dtype=float).reshape(-1)
        stats = opti.stats()
        objective_value = float(solution.value(cost))
        if not np.isfinite(primal).all() or not np.isfinite(objective_value):
            return {
                "warm_start": warm_start,
                "success": False,
                "status": "nonfinite-solution",
                "numerical_profile": profile,
                "solver": "casadi-ipopt/full-history-separate-norm-epigraphs/1",
                "provider": "casadi-ipopt",
                "version": f"casadi {provider_version}; IPOPT version unavailable",
            }
        witnesses = dict(fixed_witnesses)
        for index, variable in zip(active, factor_variables, strict=True):
            witnesses[index] = (
                []
                if variable is None
                else np.asarray(solution.value(variable), dtype=float).reshape(-1).tolist()
            )
        factor_values = [witnesses[index] for index in range(len(geometry))]
        geometry_check = verify(geometry, primal, factor_values)
        return {
            "warm_start": warm_start,
            "success": bool(stats.get("success")) and geometry_check["accepted"],
            "geometry_factors": factor_values,
            "geometry_validation": geometry_check,
            "numerical_profile": profile,
            "status": str(stats.get("return_status", "unknown")),
            "primal": primal.tolist(),
            "objective": objective_value,
            "iterations": stats.get("iter_count"),
            "solver": "casadi-ipopt/full-history-separate-norm-epigraphs/1",
            "provider": "casadi-ipopt",
            "version": f"casadi {provider_version}; IPOPT version unavailable",
            "assurance": "local numerical NLP solution; no global optimality certificate",
        }
    except Exception as error:
        return {
            "warm_start": warm_start,
            "success": False,
            "status": "solver-error",
            "error": str(error),
            "numerical_profile": profile,
            "solver": "casadi-ipopt/full-history-separate-norm-epigraphs/1",
            "provider": "casadi-ipopt",
            "version": f"casadi {provider_version}; IPOPT version unavailable",
        }
