"""Prepare a supplied start and check C++ Strategy A/B history results."""

import json

import numpy as np
from history_geometry import parse, verify
from history_validation import validate

PLAIN = "csl.nlp.casadi-ipopt.history-cost"
SCALED = "csl.nlp.casadi-ipopt.scaled-history-cost"
MUMPS = "csl.nlp.casadi-ipopt.mumps-history-cost"


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


def feasible_membership_factors(memberships, history, relation, state_coordinates):
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
            coefficients = _feasibility_lp(matrix.shape[1], normalized, rhs, (-1, 1))
        witnesses.append(coefficients.tolist())
    if not verify(entries, z, witnesses, tolerance=1e-8)["accepted"]:
        raise ValueError(
            "Supplied history has no checked membership witness from fixed-history recovery."
        )
    return witnesses


def prepare_start(task, request, relation, memberships, history):
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
        history = _feasibility_lp(
            len(history), eq or None, eq_values or None, bounds, neq or None, upper_bounds or None
        )
        if not valid(history):
            raise ValueError("Phase-one result did not satisfy the original history.")
        phase = "scipy-highs-zero-objective-phase-one"
    return (
        history.tolist(),
        feasible_membership_factors(memberships, history, relation, dimension),
        phase,
    )


def actuation_error(control, bounds):
    return max(
        max(lo - value, value - hi, 0.0) for value, (lo, hi) in zip(control, bounds, strict=True)
    )


def provider_profiles(task, control_bounds):
    if task["model"]["case_id"] != "ENV717-EARTH-ORBIT-CONTINUOUS-01":
        return [(PLAIN, None), (MUMPS, None)]
    scaling = {
        "state": [field["scale"] for field in task["model"]["states"]],
        "control": [max(abs(lo), abs(hi)) or 1.0 for lo, hi in control_bounds],
    }
    return [(SCALED, scaling), (MUMPS, scaling), (MUMPS, None), (PLAIN, None)]


def solve_strategy(
    task, request, exported, memberships, strategy, start, factors, exchange, checkpoint
):
    """Retry explicit providers for one observation and accept the first applicable checked plan."""
    attempts = []
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
        attempt["outcome"] = response.get("status")
        receipt = response.get("solver_receipt", {})
        if all(
            response.get(key) == request[key]
            for key in ("task_id", "task_sha256", "action_profile_id")
        ):
            if receipt.get("provider"):
                attempt["actual_provider"] = receipt["provider"]
            if response.get("status") == "solved":
                if (
                    response.get("policy_id") != request["controller_id"]
                    or receipt.get("provider") != provider
                    or receipt.get("strategy") != strategy
                    or not receipt.get("supplied_readback")
                    or any(
                        response.get(key) != exported[key]
                        for key in ("history_relation", "history_objective", "geometry")
                    )
                ):
                    raise ValueError(
                        "Native strategy result does not match its exported history and requested route."
                    )
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
