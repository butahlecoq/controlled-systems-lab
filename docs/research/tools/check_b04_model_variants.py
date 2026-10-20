"""Exact audit of two published B04 model variants against the published row.

Standard-library rational arithmetic on public transcriptions only: the
historical manifest (the printed L11 model and the reported row) and the
reviewed saved-witness evidence record (the A39/A01/A40 variant). No private
source is read or executed, no solver is run, and no published value is
replaced.

The audit asks one question: which of the two model variants can contain the
published terminal point inside the printed rounding? The terminal map of
this model has rank two, so the reachable terminal set is a plane; both
variants are tested against the two control-invariant functionals of their
own plane.
"""

import argparse
import json
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "benchmarks/scenarios/b04-historical.json"
SAVED = ROOT / "docs/research/evidence/b04-saved-witnesses.json"

TRANSITIONS = 16
STAGE_SECONDS = Fraction(100)  # 16 transitions of 25/4 s
NOMINAL_OXIDIZER_FLOW = Fraction(1200)
NOMINAL_FUEL_FLOW = Fraction(450)
FLOW_RADIUS = Fraction(1, 20)  # published flows carry one decimal
STOCK_RADIUS = Fraction(1, 2000)  # published stocks carry three decimals


def rational(value):
    return Fraction(str(value))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fraction_text(value):
    return f"{value.numerator}/{value.denominator}"


def decimal_text(value, digits=12):
    return f"{float(value):.{digits}g}"


def compatibility_summary(variants, point):
    """Name the variants whose terminal plane contains the published point."""
    compatible, incompatible = [], []
    for variant in variants:
        residuals = plane_residuals(variant, point)
        (compatible if residuals["compatible"] else incompatible).append(variant["id"])
    return {
        "published_row_compatible_variants": compatible,
        "published_row_incompatible_variants": incompatible,
    }


def flow_and_slope(parameters, delta):
    """Return (oxidizer, fuel) flows and their d/d(delta) at an exact delta."""
    p = {key: rational(value) for key, value in parameters.items()}
    numerator = p["P"] + p["c2"] * delta ** 2 + p["c3"] * delta
    denominator = p["I"] + p["c4"] * delta ** 2 + p["c5"] * delta
    ratio = 1 + p["K"] + delta
    numerator_prime = 2 * p["c2"] * delta + p["c3"]
    denominator_prime = 2 * p["c4"] * delta + p["c5"]
    fuel = numerator / (denominator * ratio)
    fuel_prime = (
        numerator_prime * denominator * ratio
        - numerator * (denominator_prime * ratio + denominator)
    ) / (denominator * ratio) ** 2
    oxidizer = (p["K"] + delta) * fuel
    oxidizer_prime = fuel + (p["K"] + delta) * fuel_prime
    return (oxidizer, fuel), (oxidizer_prime, fuel_prime)


def printed_variant(manifest):
    problem = manifest["problem"]
    return {
        "id": "printed-l11",
        "source": "L11 printed equations (1.4)-(1.6) and Table 1, as transcribed in the historical manifest",
        "x0": tuple(rational(value) for value in problem["initial_state"]),
        "B": tuple(rational(row[0]) for row in problem["dynamics"]["B"]),
    }


def saved_variant(saved):
    derivation = saved["model_derivation"]
    return {
        "id": "saved-a39-a01-a40",
        "source": "A39 saved state, A01 driver input matrix, A40 nonlinear kernel, curated in the saved-witness record",
        "x0": tuple(rational(value) for value in derivation["x0"]),
        "B": tuple(rational(value) for value in derivation["B_exact_expressions"]),
    }


def plane_weights(variant):
    """Return coprime integer weights (w1, w3) with w1*B1 + w3*B3 = 0.

    A and B act on the four coordinates (oxidizer flow, oxidizer working
    stock, fuel flow, fuel working stock). The stock rows integrate the
    previous flows, so a weight pair that annihilates the control direction
    also annihilates the stock direction and defines a control-invariant
    functional of the terminal state.
    """
    b1, b3 = variant["B"][0], variant["B"][2]
    require(b1 > 0 and b3 < 0, "unexpected control sign pattern")
    require(variant["B"][1] == 0 and variant["B"][3] == 0, "expected a scalar input on the flow rows")
    ratio = (-b3) / b1
    return ratio.numerator, ratio.denominator


def plane_values(variant):
    """Return the two control-invariant terminal-plane functionals."""
    x1, x2, x3, x4 = variant["x0"]
    w1, w3 = plane_weights(variant)
    flow_plane = w1 * x1 + w3 * x3
    stock_plane = w1 * (x2 - STAGE_SECONDS * x1) + w3 * (x4 - STAGE_SECONDS * x3)
    return (w1, w3), flow_plane, stock_plane


def published_point(manifest):
    return tuple(rational(value) for value in manifest["reported"]["terminal_state"])


def plane_residuals(variant, point):
    """Residuals of the published point against the variant's terminal plane."""
    (w1, w3), flow_plane, stock_plane = plane_values(variant)
    flow_residual = w1 * point[0] + w3 * point[2] - flow_plane
    stock_residual = w1 * point[1] + w3 * point[3] - stock_plane
    flow_radius = (abs(w1) + abs(w3)) * FLOW_RADIUS
    stock_radius = (abs(w1) + abs(w3)) * STOCK_RADIUS
    return {
        "weights": [w1, w3],
        "flow_plane_required": fraction_text(flow_plane),
        "stock_plane_required": fraction_text(stock_plane),
        "flow_residual": fraction_text(flow_residual),
        "stock_residual": fraction_text(stock_residual),
        "flow_rounding_radius": fraction_text(flow_radius),
        "stock_rounding_radius": fraction_text(stock_radius),
        "flow_compatible": abs(flow_residual) <= flow_radius,
        "stock_compatible": abs(stock_residual) <= stock_radius,
        "compatible": abs(flow_residual) <= flow_radius and abs(stock_residual) <= stock_radius,
    }


def squared_criterion(manifest, point):
    """Exact squared value of the printed terminal criterion at a state."""
    objective = manifest["problem"]["objective"]
    require(objective["kind"] == "affine_residual_euclidean_norm", "unexpected objective kind")
    matrix = objective["residual_matrix"]
    target = tuple(rational(value) for value in objective["residual_target"])
    total = Fraction(0)
    for row, reference in zip(matrix, target):
        residual = Fraction(0)
        for coefficient, coordinate in zip(row, point):
            residual += rational(coefficient) * coordinate
        total += (residual - reference) ** 2
    return total


def criterion_rounding_verdict(manifest, point):
    """Check the printed objective against the published row's own rounding.

    The published objective carries three decimals, so the printed value may
    stand for any value in [reported - 0.0005, reported + 0.0005].
    """
    reported = rational(manifest["reported"]["objective"])
    lower = reported - Fraction(1, 2000)
    upper = reported + Fraction(1, 2000)
    squared = squared_criterion(manifest, point)
    return {
        "reported_objective": fraction_text(reported),
        "criterion_squared_at_published_point": fraction_text(squared),
        "rounding_interval": [fraction_text(lower), fraction_text(upper)],
        "squared_interval": [fraction_text(lower ** 2), fraction_text(upper ** 2)],
        "reported_objective_inside_rounding": lower ** 2 <= squared <= upper ** 2,
    }


def law_parameters(manifest, saved, use_kernel_coefficients):
    """Return the nonlinear law parameters, printed or with the kernel's scaled c2, c3."""
    printed = manifest["reported"]["nonlinear_parameters"]
    kernel = saved["nonlinear_kernel"]["parameters"]
    require(rational(kernel["c2"]) == 4 * rational(printed["coefficients"]["c2"]), "c2 scale changed")
    require(rational(kernel["c3"]) == 4 * rational(printed["coefficients"]["c3"]), "c3 scale changed")
    return {
        "P": printed["P"],
        "I": printed["I"],
        "K": printed["K"],
        "c1": printed["coefficients"]["c1"],
        "c2": kernel["c2"] if use_kernel_coefficients else printed["coefficients"]["c2"],
        "c3": kernel["c3"] if use_kernel_coefficients else printed["coefficients"]["c3"],
        "c4": printed["coefficients"]["c4"],
        "c5": printed["coefficients"]["c5"],
    }


def law_versus_state_table(manifest, saved, variants):
    """Compare the nonlinear law at d = dK with both transcribed initial states."""
    printed = manifest["reported"]["nonlinear_parameters"]
    delta_initial = rational(printed["initial_mixture_ratio_perturbation"])
    laws = {
        "printed-c2-c3": law_parameters(manifest, saved, False),
        "scaled-c2-c3": law_parameters(manifest, saved, True),
    }
    table = {}
    for law_name, parameters in laws.items():
        (oxidizer, fuel), _ = flow_and_slope(parameters, delta_initial)
        row = {}
        for variant in variants:
            row[variant["id"]] = {
                "state_oxidizer_flow": fraction_text(variant["x0"][0]),
                "state_fuel_flow": fraction_text(variant["x0"][2]),
                "law_oxidizer_flow": fraction_text(oxidizer),
                "law_fuel_flow": fraction_text(fuel),
                "oxidizer_flow_difference": fraction_text(variant["x0"][0] - oxidizer),
                "fuel_flow_difference": fraction_text(variant["x0"][2] - fuel),
                "matches_state_exactly": variant["x0"][0] == oxidizer and variant["x0"][2] == fuel,
                "matches_state_within_1e-6": (
                    abs(variant["x0"][0] - oxidizer) <= Fraction(1, 10 ** 6)
                    and abs(variant["x0"][2] - fuel) <= Fraction(1, 10 ** 6)
                ),
            }
        table[law_name] = row
    return table


def mixture_sensitivity(variant):
    """Exact d(oxidizer flow / fuel flow)/du at the nominal flows."""
    b1, b3 = variant["B"][0], variant["B"][2]
    return (b1 * NOMINAL_FUEL_FLOW - NOMINAL_OXIDIZER_FLOW * b3) / NOMINAL_FUEL_FLOW ** 2


def mixture_band(manifest, saved, variants):
    """Reconcile the throttle authority, the phase box and the printed c1."""
    printed = manifest["reported"]["nonlinear_parameters"]
    coefficients = printed["coefficients"]
    k = rational(printed["K"])
    delta_initial = rational(printed["initial_mixture_ratio_perturbation"])
    c1 = rational(coefficients["c1"])
    constraints = manifest["problem"]["state_constraints"]
    require(constraints["h"] == [1224, -1176, 468, -432], "unexpected phase box")
    upper_face = Fraction(1224, 432)
    lower_face = Fraction(1176, 468)
    band = (delta_initial - c1, delta_initial + c1)
    return {
        "nominal_mixture_ratio": fraction_text(k),
        "nominal_ratio_identity_1200_over_450": k == NOMINAL_OXIDIZER_FLOW / NOMINAL_FUEL_FLOW,
        "initial_mixture_perturbation": fraction_text(delta_initial),
        "initial_perturbation_relative_to_K": fraction_text(delta_initial / k),
        "throttle_sensitivity_c1": fraction_text(c1),
        "reachable_mixture_band_for_u_in_unit_interval": [fraction_text(band[0]), fraction_text(band[1])],
        "phase_box_upper_mixture_face": fraction_text(upper_face),
        "phase_box_upper_face_excess_over_K": fraction_text(upper_face - k),
        "phase_box_lower_mixture_face": fraction_text(lower_face),
        "phase_box_lower_face_excess_over_K": fraction_text(lower_face - k),
        "phase_box_binds_above_reachable_band": upper_face - k < band[1],
        "mixture_sensitivity_per_variant": {
            variant["id"]: fraction_text(mixture_sensitivity(variant)) for variant in variants
        },
        "mixture_sensitivity_matches_c1_per_variant": {
            variant["id"]: mixture_sensitivity(variant) == c1 for variant in variants
        },
    }


def audit():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    saved = json.loads(SAVED.read_text(encoding="utf-8"))
    variants = [printed_variant(manifest), saved_variant(saved)]
    point = published_point(manifest)
    require(len(point) == 4, "unexpected published terminal point")
    return {
        "scenario_id": manifest["id"],
        "published_terminal_state": [fraction_text(value) for value in point],
        "variants": {
            variant["id"]: {
                "source": variant["source"],
                "initial_state": [fraction_text(value) for value in variant["x0"]],
                "B": [fraction_text(value) for value in variant["B"]],
                "plane": plane_residuals(variant, point),
            }
            for variant in variants
        },
        "criterion": criterion_rounding_verdict(manifest, point),
        "compatibility": compatibility_summary(variants, point),
        "law_versus_initial_state": law_versus_state_table(manifest, saved, variants),
        "mixture": mixture_band(manifest, saved, variants),
        "scope": (
            "Exact rational comparison of two published B04 transcriptions against the published row; "
            "no optimizer, no private source, no nonlinear simulation and no historical run"
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write the derived record as JSON")
    parser.add_argument("--verify-record", type=Path, help="compare the derived record with a stored JSON")
    arguments = parser.parse_args()
    record = audit()
    if arguments.output is not None:
        arguments.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if arguments.verify_record is not None:
        stored = json.loads(arguments.verify_record.read_text(encoding="utf-8"))
        if stored != record:
            raise SystemExit("stored record differs from the recomputed record")
        print("stored record matches the recomputed record")
    if arguments.output is None and arguments.verify_record is None:
        print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
