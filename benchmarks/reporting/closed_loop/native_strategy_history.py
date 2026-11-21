"""Prepare a supplied start and check C++ Strategy A/B history results."""

import json

import numpy as np
from history_geometry import parse, verify
from history_policy import provider_profiles
from history_validation import validate


def _feasibility_lp(
    size, equalities, equality_values, bounds, inequalities=None, upper_bounds=None
):
    from scipy.optimize import linprog

    outcome = linprog(
        np.zeros(size),
        A_eq=equalities,
        b_eq=equality_values,
        A_ub=inequalities,
        b_ub=upper_bounds,
        bounds=bounds,
        method="highs",
    )
    if not outcome.success:
        raise ValueError(f"Native history start feasibility search failed: {outcome.message}")
    return outcome.x


def feasible_membership_factors(
    memberships, history, relation, state_coordinates, *, lp_calls=None
):
    """Recover latent coefficients for a fixed history without optimizing source cost."""
    z = np.asarray(history, dtype=float)
    entries = parse(memberships, state_coordinates, relation=relation, history_dimension=len(z))
    witnesses = []
    for kind, indices, *data in entries:
        if kind in {"h", "lifted-h"}:
            witnesses.append([])
            continue
        center, matrix = data
        residual = z[indices] - center
        scale = np.max(np.abs(matrix), axis=1, initial=0)
        scale[scale == 0] = 1
        normalized, rhs = matrix / scale[:, None], residual / scale
        coefficients = np.linalg.lstsq(normalized, rhs, rcond=None)[0]
        if kind == "zonotope" and np.max(np.abs(coefficients), initial=0) > 1:
            if lp_calls is not None:
                lp_calls.append("history.start-membership-feasibility")
            coefficients = _feasibility_lp(matrix.shape[1], normalized, rhs, (-1, 1))
        witnesses.append(coefficients.tolist())
    if not verify(entries, z, witnesses, tolerance=1e-8)["accepted"]:
        raise ValueError(
            "Supplied history has no checked membership witness from fixed-history recovery."
        )
    return witnesses


def prepare_start(task, request, relation, memberships, history, *, lp_calls):
    orbit = task["model"]["case_id"] == "ENV717-EARTH-ORBIT-CONTINUOUS-01"
    n = len(request["observed_physical_state"])
    dimension = n * (len(request["predictor_stages"]) + 1)
    radii = list(range(0, dimension, n)) if orbit else []
    eq, neq = relation["equalities"], relation["inequalities"]
    eq_values, upper_bounds = relation["equality_values"], relation["upper_bounds"]

    def valid(rows):
        return (
            np.isfinite(rows).all()
            and (not radii or np.all(rows[radii] > 0))
            and (not eq or np.max(np.abs(np.asarray(eq) @ rows - eq_values), initial=0) <= 1e-8)
            and (not neq or np.max(np.asarray(neq) @ rows - upper_bounds, initial=0) <= 1e-8)
        )

    phase = None
    if not valid(history):
        bounds = [(None, None)] * len(history)
        for index in radii:
            bounds[index] = (1e-9, None)
        lp_calls.append("history.start-feasibility")
        history = _feasibility_lp(
            len(history), eq or None, eq_values or None, bounds, neq or None, upper_bounds or None
        )
        if not valid(history):
            raise ValueError("Phase-one result did not satisfy the original history.")
        phase = "scipy-highs-zero-objective-phase-one"
    return (
        history.tolist(),
        feasible_membership_factors(memberships, history, relation, dimension, lp_calls=lp_calls),
        phase,
    )


def actuation_error(control, bounds):
    return max(
        max(lo - value, value - hi, 0.0) for value, (lo, hi) in zip(control, bounds, strict=True)
    )


def _axis_witness_residual(member, chosen, coefficients, family):
    dimension = len(chosen)
    lower, upper = np.full(dimension, -np.inf), np.full(dimension, np.inf)
    for rows, rhs, equal in (
        ("inequalities", "upper_bounds", False),
        ("equalities", "equality_values", True),
    ):
        for row, value in zip(member[rows], member[rhs], strict=True):
            (index,) = np.flatnonzero(row)
            multiplier = row[index]
            bound = value / multiplier
            if equal or multiplier < 0:
                lower[index] = max(lower[index], bound)
            if equal or multiplier > 0:
                upper[index] = min(upper[index], bound)
    if not np.isfinite(lower).all() or not np.isfinite(upper).all() or np.any(lower > upper):
        raise ValueError("Native axis membership has invalid physical bounds.")
    factor = np.asarray(coefficients, dtype=float)
    if factor.shape != chosen.shape or not np.isfinite(factor).all():
        raise ValueError("Native axis membership witness has invalid shape or values.")
    if family == "box":
        center = lower * 0.5 + upper * 0.5
        radius = np.maximum(center - lower, upper - center)
        lifted = center + radius * factor
        bounds_error = np.max(np.abs(factor) - 1, initial=0.0)
    else:
        frame = np.asarray(member["parallelotope_frame"], dtype=float)
        if not np.array_equal(frame, np.eye(dimension)):
            raise ValueError("Native parallelotope membership uses an unsupported frame.")
        lifted = frame @ factor
        bounds_error = max(np.max(lower - factor, initial=0.0), np.max(factor - upper, initial=0.0))
    return float(max(np.max(np.abs(chosen - lifted), initial=0.0), bounds_error))


def verify_native_geometry_receipt(geometry, primal, receipt):
    """Check the native source bindings and axis-family witnesses from the actual receipt."""
    family = geometry["family"]
    expected_bindings = []
    members = []
    for stage in geometry["stages"]:
        for member in stage["memberships"]:
            role, selected = member["role"], member["set_id"]
            reference = selected
            if member["kind"] != "lifted-h":
                reference = stage[role + "_h"]["set_id"]
            expected_bindings.append(
                dict(
                    stage=stage["stage"],
                    role=role,
                    selected=selected,
                    reference=reference,
                    relation=member["relation"],
                )
            )
            members.append(member)
    if receipt.get("geometry_bindings") != expected_bindings:
        raise ValueError("Native membership source binding differs from the exported geometry.")
    z = np.asarray(primal, dtype=float)
    if z.ndim != 1 or not np.isfinite(z).all():
        raise ValueError("Native history witness is not a finite vector.")
    residual = 0.0
    for member, factor in zip(members, receipt["geometry_factors"], strict=True):
        if family in {"box", "parallelotope"}:
            residual = max(
                residual, _axis_witness_residual(member, z[member["indices"]], factor, family)
            )
        elif member["kind"] in {"h", "lifted-h"} and factor != []:
            raise ValueError("Native H memberships expect an empty latent witness.")
    return {"passed": residual <= 1e-7, "max_residual": residual, "bindings_checked": len(members)}


def solve_strategy(
    task, request, exported, memberships, strategy, start, factors, exchange, checkpoint
):
    """Retry explicit providers for one observation and accept the first applicable checked plan."""
    attempts = []
    strategy_module = {"A": "csl.synthesis.reach-back", "B": "csl.synthesis.strategy-b"}[strategy]
    for provider, scaling in provider_profiles(task, request["control_bounds"]):
        native_request = dict(
            request,
            native_history_strategy=strategy,
            native_history_optimizer=provider,
            initial_primal=start,
            initial_geometry_factors=factors,
        )
        if scaling is not None:
            native_request["native_history_scaling"] = scaling
        raw = json.dumps(native_request, separators=(",", ":"), allow_nan=False) + "\n"
        attempt = {"requested_provider": provider, "state": "prepared", "request_raw": raw}
        attempts.append(attempt)
        checkpoint(attempts)
        response_raw = exchange(raw)
        attempt.update(state="returned", response_raw=response_raw)
        checkpoint(attempts)
        response = json.loads(response_raw)
        status = response.get("status")
        attempt["outcome"] = status
        receipt = response.get("solver_receipt", {})
        if all(
            response.get(key) == request[key]
            for key in ("task_id", "task_sha256", "action_profile_id")
        ):
            if not isinstance(receipt, dict) or (
                (receipt or status == "solved")
                and (
                    response.get("policy_id") != request["controller_id"]
                    or receipt.get("provider") != provider
                    or receipt.get("strategy") != strategy
                    or receipt.get("strategy_module") != strategy_module
                    or receipt.get("program_id") != request["request_id"]
                    or receipt.get("supplied_readback") is not True
                )
            ):
                raise ValueError("Native strategy receipt does not match its requested route.")
            if receipt:
                attempt["actual_provider"] = receipt["provider"]
                attempt["actual_version"] = receipt.get("version")
                attempt["actual_strategy_module"] = receipt["strategy_module"]
            if status == "solved":
                if any(
                    response.get(key) != exported[key]
                    for key in ("history_relation", "history_objective", "geometry")
                ):
                    raise ValueError("Native strategy result does not match its exported history.")
                checks = validate(
                    task,
                    request["absolute_update_index"],
                    request["observed_physical_state"],
                    request["predictor_stages"],
                    exported["history_relation"],
                    response["primal"],
                    receipt["objective"],
                    geometry_memberships=memberships,
                    geometry_factors=receipt["geometry_factors"],
                )
                native_geometry = verify_native_geometry_receipt(
                    exported["geometry"], response["primal"], receipt
                )
                checks["checks"]["native_geometry_receipt"] = native_geometry
                checks["accepted"] = checks["accepted"] and native_geometry["passed"]
                attempt["independent_accepted"] = checks["accepted"]
                if checks["accepted"]:
                    difference = actuation_error(checks["controls"][0], request["control_bounds"])
                    if difference == 0:
                        attempt["outcome"] = "accepted"
                        checkpoint(attempts)
                        return response, checks, attempts
                    attempt.update(
                        outcome="actuation-refused", maximum_actuation_violation=difference
                    )
        else:
            raise ValueError(
                "Native strategy response belongs to a different task or action profile."
            )
        checkpoint(attempts)
    return None, None, attempts
