"""Exact audit of two published B04 model variants against the published row.

Standard-library rational arithmetic on public transcriptions only: the
historical manifest (the printed L11 model and the reported row) and the
reviewed saved-witness evidence record (the A39/A01/A40 variant). No private
source is read or executed, no solver is run, and no published value is
replaced.

The audit asks one question: which of the two model variants can contain the
published terminal point inside the printed rounding? The terminal map of
this model has rank two, so the reachable terminal set lies in an affine
plane; both variants are tested against the two control-invariant
functionals of their own plane.

The model structure that the plane argument needs is read from the manifest
and asserted, not assumed: the transition matrix, the horizon, the stage
length and the printed control-interval status.
"""

import argparse
import json
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "benchmarks/scenarios/b04-historical.json"
SAVED = ROOT / "docs/research/evidence/b04-saved-witnesses.json"

EXPECTED_A = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
EXPECTED_STOCK_COUPLING = Fraction(-25, 4)  # N[1,0] = N[3,2] = -6.25 per stage
NOMINAL_OXIDIZER_FLOW = Fraction(1200)
NOMINAL_FUEL_FLOW = Fraction(450)


def rational(value):
    return Fraction(str(value))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fraction_text(value):
    return f"{value.numerator}/{value.denominator}"


def decimal_places(text):
    text = str(text)
    return len(text.split(".")[1]) if "." in text else 0


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


def model_structure(manifest):
    """Read and assert the transition structure the plane argument needs."""
    problem = manifest["problem"]
    matrix = problem["dynamics"]["A"]
    require(len(matrix) == 4 and all(len(row) == 4 for row in matrix), "unexpected A shape")
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            if i == j:
                require(rational(value) == 1, "diagonal of A is not one")
            elif (i, j) in ((1, 0), (3, 2)):
                require(rational(value) == EXPECTED_STOCK_COUPLING, "unexpected stock coupling")
            else:
                require(rational(value) == 0, "unexpected non-zero entry in A")
    horizon = int(problem["horizon"])
    step_seconds = rational(problem["step_seconds"])
    total_seconds = horizon * step_seconds
    require(step_seconds * horizon == total_seconds, "inconsistent stage length")
    return {
        "A": matrix,
        "horizon": horizon,
        "step_seconds": fraction_text(step_seconds),
        "total_seconds": fraction_text(total_seconds),
        "stock_coupling": fraction_text(EXPECTED_STOCK_COUPLING),
    }


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
    stock, fuel flow, fuel working stock). The stock rows of the transition
    matrix are the proportional rows (-25/4)*(B1, 0, 0, B3) of N*B, so a
    weight pair that annihilates the control direction also annihilates the
    stock direction and defines a control-invariant functional.
    """
    b1, b3 = variant["B"][0], variant["B"][2]
    require(b1 > 0 and b3 < 0, "unexpected control sign pattern")
    require(variant["B"][1] == 0 and variant["B"][3] == 0, "expected a scalar input on the flow rows")
    ratio = (-b3) / b1
    return ratio.numerator, ratio.denominator


def plane_values(variant, structure):
    """Return the two control-invariant terminal-plane functionals."""
    x1, x2, x3, x4 = variant["x0"]
    w1, w3 = plane_weights(variant)
    total_seconds = rational(structure["total_seconds"])
    flow_plane = w1 * x1 + w3 * x3
    stock_plane = w1 * (x2 - total_seconds * x1) + w3 * (x4 - total_seconds * x3)
    return (w1, w3), flow_plane, stock_plane


def published_point(manifest):
    return tuple(rational(value) for value in manifest["reported"]["terminal_state"])


def rounding_radii(manifest):
    """Derive the rounding radii from the printed decimals of the published row."""
    printed = [str(value) for value in manifest["reported"]["terminal_state"]]
    flow_radius = max(Fraction(1, 10 ** decimal_places(value)) for value in (printed[0], printed[2])) / 2
    stock_radius = max(Fraction(1, 10 ** decimal_places(value)) for value in (printed[1], printed[3])) / 2
    return {"flow_radius": flow_radius, "stock_radius": stock_radius,
            "printed_decimals": [decimal_places(value) for value in printed]}


def plane_residuals(variant, point, structure, radii):
    """Residuals of the published point against the variant's terminal plane."""
    (w1, w3), flow_plane, stock_plane = plane_values(variant, structure)
    flow_residual = w1 * point[0] + w3 * point[2] - flow_plane
    stock_residual = w1 * point[1] + w3 * point[3] - stock_plane
    flow_radius = (abs(w1) + abs(w3)) * radii["flow_radius"]
    stock_radius = (abs(w1) + abs(w3)) * radii["stock_radius"]
    total_seconds = rational(structure["total_seconds"])
    # How far an initial-flow error would have to be to move the verdict. A
    # positive margin is the error the verdict tolerates; a negative margin
    # is the error that would overturn it.
    flow_sensitivity = abs(total_seconds * w1)
    stock_sensitivity = abs(total_seconds * w3)
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
        "stock_verdict_margin_per_initial_fuel_flow_error": fraction_text(
            (stock_radius - abs(stock_residual)) / stock_sensitivity
        ),
        "flow_verdict_margin_per_initial_fuel_flow_error": fraction_text(
            (flow_radius - abs(flow_residual)) / flow_sensitivity
        ),
        "stock_plane_sensitivity_to_initial_flows": {
            "x1": fraction_text(total_seconds * w1),
            "x3": fraction_text(total_seconds * w3),
        },
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
    c1 = rational(printed["coefficients"]["c1"])
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


def input_slope_table(manifest, saved, variants):
    """Compare the law's reference input slope with each variant's input matrix.

    The comparison is conditional in the same sense as the parameter
    cross-check: it identifies the scalar u of equation (1.1) with the
    incremental control of the linear recurrence and differentiates at the
    law's reference d = 0. The article does not print a generating
    control-unit map for its numerical run.
    """
    printed = manifest["reported"]["nonlinear_parameters"]
    c1 = rational(printed["coefficients"]["c1"])
    delta_initial = rational(printed["initial_mixture_ratio_perturbation"])
    laws = {
        "printed-c2-c3": law_parameters(manifest, saved, False),
        "scaled-c2-c3": law_parameters(manifest, saved, True),
    }
    table = {}
    for law_name, parameters in laws.items():
        _, derivative = flow_and_slope(parameters, Fraction(0))
        slope = tuple(c1 * value for value in derivative)
        _, operating_slope = flow_and_slope(parameters, delta_initial)
        operating = tuple(c1 * value for value in operating_slope)
        table[law_name] = {
            "reference_input_slope_at_d_zero": [fraction_text(value) for value in slope],
            "input_slope_at_d_initial": [fraction_text(value) for value in operating],
            "matches_input_matrix_per_variant": {
                variant["id"]: (slope[0] == variant["B"][0] and slope[1] == variant["B"][2])
                for variant in variants
            },
        }
    return table


def mixture_sensitivity(variant):
    """Exact d(oxidizer flow / fuel flow)/du at the nominal flows."""
    b1, b3 = variant["B"][0], variant["B"][2]
    return (b1 * NOMINAL_FUEL_FLOW - NOMINAL_OXIDIZER_FLOW * b3) / NOMINAL_FUEL_FLOW ** 2


def mixture_band(manifest, variants, structure):
    """Reconcile the throttle authority, the phase box and the printed c1.

    Two conventions are reported because the archive uses both: the law's
    accumulated action (a single scalar per run) and a per-step control in
    the unit interval (which the saved variant's inferred actions use).
    """
    printed = manifest["reported"]["nonlinear_parameters"]
    coefficients = printed["coefficients"]
    k = rational(printed["K"])
    delta_initial = rational(printed["initial_mixture_ratio_perturbation"])
    c1 = rational(coefficients["c1"])
    constraints = manifest["problem"]["state_constraints"]
    require(constraints["h"] == [1224, -1176, 468, -432], "unexpected phase box")
    upper_face = Fraction(1224, 432)
    lower_face = Fraction(1176, 468)
    horizon = structure["horizon"]
    return {
        "nominal_mixture_ratio": fraction_text(k),
        "nominal_ratio_identity_1200_over_450": k == NOMINAL_OXIDIZER_FLOW / NOMINAL_FUEL_FLOW,
        "initial_mixture_perturbation": fraction_text(delta_initial),
        "initial_perturbation_relative_to_K": fraction_text(delta_initial / k),
        "throttle_sensitivity_c1": fraction_text(c1),
        "reachable_mixture_band_accumulated_action_in_unit_interval": [
            fraction_text(delta_initial - c1), fraction_text(delta_initial + c1)
        ],
        "reachable_mixture_band_per_step_control_in_unit_interval": [
            fraction_text(delta_initial - horizon * c1), fraction_text(delta_initial + horizon * c1)
        ],
        "phase_box_upper_mixture_face": fraction_text(upper_face),
        "phase_box_upper_face_excess_over_K": fraction_text(upper_face - k),
        "phase_box_lower_mixture_face": fraction_text(lower_face),
        "phase_box_lower_face_excess_over_K": fraction_text(lower_face - k),
        "mixture_sensitivity_per_variant": {
            variant["id"]: fraction_text(mixture_sensitivity(variant)) for variant in variants
        },
        "mixture_sensitivity_matches_c1_per_variant": {
            variant["id"]: mixture_sensitivity(variant) == c1 for variant in variants
        },
    }


def linear_flow_box(manifest, variants, structure):
    """Exact phase-box analysis of the linear model, with the tied flows.

    In the linear model the two flows are tied by the input matrix, so the
    reachable flow pair is a line segment. The box is intersected with the
    segment and the mixture ratio is reported at the segment ends.
    """
    constraints = manifest["problem"]["state_constraints"]
    box_x1 = (Fraction(1176), Fraction(1224))
    box_x3 = (Fraction(432), Fraction(468))
    horizon = structure["horizon"]
    report = {}
    for variant in variants:
        b1, b3 = variant["B"][0], variant["B"][2]
        x1_0, _, x3_0, _ = variant["x0"]
        ratio = b3 / b1  # x3 - x3(0) = (B3/B1) * (x1 - x1(0))
        def x3_at(x1):
            return x3_0 + ratio * (x1 - x1_0)
        ends = {}
        for x1 in box_x1:
            ends[fraction_text(x1)] = {
                "x3": fraction_text(x3_at(x1)),
                "mixture_ratio": fraction_text(x1 / x3_at(x1)),
            }
        control_x1 = (x1_0 - horizon * abs(b1), x1_0 + horizon * abs(b1))
        control_x3 = (x3_0 - horizon * abs(b3), x3_0 + horizon * abs(b3))
        tie_x3 = [x3_at(box_x1[0]), x3_at(box_x1[1])]
        x3_inside = all(box_x3[0] <= value <= box_x3[1] for value in tie_x3)
        report[variant["id"]] = {
            "flow_tie": f"x3 = x3(0) + ({fraction_text(ratio)})*(x1 - x1(0))",
            "box_x1": [fraction_text(box_x1[0]), fraction_text(box_x1[1])],
            "box_x3": [fraction_text(box_x3[0]), fraction_text(box_x3[1])],
            "terminal_x1_range_from_unit_step_controls": [
                fraction_text(control_x1[0]), fraction_text(control_x1[1])
            ],
            "terminal_x3_range_from_unit_step_controls": [
                fraction_text(control_x3[0]), fraction_text(control_x3[1])
            ],
            "x1_control_range_exceeds_box": control_x1[0] < box_x1[0] or control_x1[1] > box_x1[1],
            "x3_control_range_exceeds_box": control_x3[0] < box_x3[0] or control_x3[1] > box_x3[1],
            "x3_inside_box_along_tie_line": x3_inside,
            "binding_flow_box_faces": ["x1"] if x3_inside else ["x1", "x3"],
            "tie_line_at_box_x1_ends": ends,
        }
    return report


def initial_mixture_ratios(manifest, variants):
    """The mixture ratio of each transcribed initial state."""
    printed = manifest["reported"]["nonlinear_parameters"]
    k = rational(printed["K"])
    delta_initial = rational(printed["initial_mixture_ratio_perturbation"])
    target = k + delta_initial
    return {
        variant["id"]: {
            "ratio": fraction_text(variant["x0"][0] / variant["x0"][2]),
            "target_K_plus_dK": fraction_text(target),
            "difference": fraction_text(variant["x0"][0] / variant["x0"][2] - target),
        }
        for variant in variants
    }


def source_identities(manifest, saved):
    """Public source identities of the two transcriptions, without private paths."""
    entries = []
    for entry in manifest["sources"]:
        entries.append({
            "id": entry["id"],
            "sha256": entry.get("sha256"),
            "role": entry.get("role", "printed article behind the transcribed model"),
            "pdf_pages": entry.get("pdf_pages"),
        })
    for entry in saved["sources"]:
        entries.append({
            "id": entry["id"],
            "sha256": entry.get("sha256"),
            "role": entry.get("role"),
            "bytes": entry.get("bytes"),
        })
    return entries


def compatibility_summary(variants, point, structure, radii):
    """Name the variants whose terminal plane contains the published point."""
    compatible, incompatible = [], []
    for variant in variants:
        residuals = plane_residuals(variant, point, structure, radii)
        (compatible if residuals["compatible"] else incompatible).append(variant["id"])
    return {
        "published_row_compatible_variants": compatible,
        "published_row_incompatible_variants": incompatible,
    }


def audit():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    saved = json.loads(SAVED.read_text(encoding="utf-8"))
    structure = model_structure(manifest)
    variants = [printed_variant(manifest), saved_variant(saved)]
    point = published_point(manifest)
    require(len(point) == 4, "unexpected published terminal point")
    radii = rounding_radii(manifest)
    return {
        "scope": (
            "Exact rational comparison of two published B04 transcriptions against the published row; "
            "no optimizer, no private source, no nonlinear simulation and no historical run"
        ),
        "scenario_id": manifest["id"],
        "model_structure": structure,
        "published_terminal_state": [fraction_text(value) for value in point],
        "published_rounding": {
            "printed_decimals": radii["printed_decimals"],
            "flow_radius": fraction_text(radii["flow_radius"]),
            "stock_radius": fraction_text(radii["stock_radius"]),
        },
        "variants": {
            variant["id"]: {
                "source": variant["source"],
                "initial_state": [fraction_text(value) for value in variant["x0"]],
                "B": [fraction_text(value) for value in variant["B"]],
                "initial_mixture_ratio": initial_mixture_ratios(manifest, variants)[variant["id"]],
                "plane": plane_residuals(variant, point, structure, radii),
            }
            for variant in variants
        },
        "criterion": criterion_rounding_verdict(manifest, point),
        "compatibility": compatibility_summary(variants, point, structure, radii),
        "law_versus_initial_state": law_versus_state_table(manifest, saved, variants),
        "law_input_slope": input_slope_table(manifest, saved, variants),
        "mixture": mixture_band(manifest, variants, structure),
        "linear_phase_box": linear_flow_box(manifest, variants, structure),
        "sources": source_identities(manifest, saved),
        "limitations": [
            "No optimizer was run: the audit tests membership of a terminal plane, not optimality.",
            "No private original was read or executed; only public transcriptions were used.",
            "Generator identity is not established for either variant.",
            "The canonical U rows, the first-action convention and the stagewise control domain stay open.",
            "The unit control interval is a provisional owner recollection and is not imported into the historical manifest.",
            "The execution gate of the historical manifest is unchanged.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write the derived record as JSON")
    parser.add_argument("--verify-record", type=Path, help="compare the derived record with a stored JSON")
    arguments = parser.parse_args()
    record = audit()
    if arguments.output is not None:
        with arguments.output.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, indent=2) + "\n")
    if arguments.verify_record is not None:
        stored = json.loads(arguments.verify_record.read_text(encoding="utf-8"))
        if stored != record:
            raise SystemExit("stored record differs from the recomputed record")
        print("stored record matches the recomputed record")
    if arguments.output is None and arguments.verify_record is None:
        print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
