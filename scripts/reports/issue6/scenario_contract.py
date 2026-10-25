"""Dimension and meaning checks for the owner-confirmed B06 executable scenario."""
from fractions import Fraction
import json
from pathlib import Path

SCENARIO_ID = "b06-owner-confirmed-disturbance-v1"


def scalar(value, path):
    if type(value) not in (int, float, str):
        raise ValueError(f"{path} must be a finite numeric scalar")
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f"{path} must be a finite numeric scalar") from error
    return result


def vector(values, size, path):
    if not isinstance(values, list) or len(values) != size:
        raise ValueError(f"{path} must contain exactly {size} values")
    return [scalar(value, f"{path}[{index}]") for index, value in enumerate(values)]


def validate(document):
    if not isinstance(document, dict) or document.get("schema_version") != 1 or document.get("id") != SCENARIO_ID:
        raise ValueError("expected owner-confirmed B06 scenario schema and identity")
    model = document.get("model")
    if not isinstance(model, dict) or model.get("time_domain") != "discrete":
        raise ValueError("model must declare a discrete transition system")
    n, m, d, horizon = (model.get(key) for key in
                        ("state_dimension", "control_dimension", "disturbance_dimension", "horizon"))
    if any(type(value) is not int or value <= 0 for value in (n, m, d, horizon)):
        raise ValueError("model dimensions and horizon must be positive integers")
    if len(model.get("A_row_major", [])) != n*n:
        raise ValueError(f"model.A_row_major must contain state_dimension squared ({n*n}) entries")
    if len(model.get("B", [])) != n*m:
        raise ValueError(f"model.B must contain state_dimension times control_dimension ({n*m}) entries")
    if len(model.get("D_row_major", [])) != n*d:
        raise ValueError(f"model.D_row_major must contain state_dimension times disturbance_dimension ({n*d}) entries")
    a = vector(model["A_row_major"], n*n, "model.A_row_major")
    b = vector(model["B"], n*m, "model.B")
    disturbance = vector(model["D_row_major"], n*d, "model.D_row_major")
    initial = vector(model.get("initial_state"), n, "model.initial_state")
    offset = vector(model.get("offset"), n, "model.offset")
    controls = model.get("control_catalogue_rows")
    if not isinstance(controls, list) or not controls:
        raise ValueError("model.control_catalogue_rows must be a nonempty ordered catalogue")
    control_rows = [vector(row, m, f"model.control_catalogue_rows[{i}]")
                    for i, row in enumerate(controls)]
    legacy_controls = model.get("control_catalogue_ordered")
    if m == 1 and [row[0] for row in control_rows] != vector(
            legacy_controls, len(control_rows), "model.control_catalogue_ordered"):
        raise ValueError("structured and legacy control catalogues disagree")
    disturbance_box = model.get("disturbance_box_per_stage")
    if not isinstance(disturbance_box, dict) or disturbance_box.get("kind") != "box" or disturbance_box.get("independent_choices_across_stages") is not True:
        raise ValueError("model.disturbance_box_per_stage must declare an independently chosen box")
    lower = vector(disturbance_box.get("lower"), d, "model.disturbance_box_per_stage.lower")
    upper = vector(disturbance_box.get("upper"), d, "model.disturbance_box_per_stage.upper")
    if any(lo >= hi for lo, hi in zip(lower, upper)):
        raise ValueError("disturbance box lower bounds must be below upper bounds")
    if model.get("state_constraints") != "none; this is the unconstrained B06/L09 formulation":
        raise ValueError("this B06 reference supports the declared unconstrained formulation")
    objective = document.get("objective", {}).get("quadratic_terminal")
    if not isinstance(objective, dict) or objective.get("convention") != "one_half_x_transpose_Q_x_plus_linear_transpose_x_plus_constant":
        raise ValueError("objective.quadratic_terminal must use the declared quadratic convention")
    q = vector(objective.get("Q_row_major"), n*n, "objective.quadratic_terminal.Q_row_major")
    linear = vector(objective.get("linear"), n, "objective.quadratic_terminal.linear")
    constant = scalar(objective.get("constant"), "objective.quadratic_terminal.constant")
    return {"dimensions": (n, m, d), "horizon": horizon, "A": a, "B": b, "D": disturbance,
            "offset": offset, "initial": initial, "controls": control_rows,
            "disturbance_lower": lower, "disturbance_upper": upper,
            "Q": q, "linear": linear, "constant": constant}


def load(path):
    return validate(json.loads(Path(path).read_text(encoding="utf-8")))
