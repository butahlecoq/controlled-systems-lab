"""Cross-check B04's printed nonlinear flow law against its displayed linear data.

This is exact arithmetic on published decimals, not a recovered historical run.
"""

import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HISTORICAL = ROOT / "benchmarks/scenarios/b04-historical.json"
SAVED = ROOT / "docs/research/evidence/b04-saved-witnesses.json"


def rational(value):
    return Fraction(str(value))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def flow_and_slope(parameters, delta):
    """Return fuel/oxidizer flows and their d/d(delta) at an exact delta."""
    p = {key: rational(value) for key, value in parameters.items()}
    numerator = p["P"] + p["c2"] * delta**2 + p["c3"] * delta
    denominator = p["I"] + p["c4"] * delta**2 + p["c5"] * delta
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


def audit():
    historical = json.loads(HISTORICAL.read_text(encoding="utf-8"), parse_float=Decimal)
    saved = json.loads(SAVED.read_text(encoding="utf-8"), parse_float=Decimal)
    printed = historical["reported"]["nonlinear_parameters"]
    kernel = saved["nonlinear_kernel"]["parameters"]
    common = {
        "P": printed["P"],
        "I": printed["I"],
        "K": printed["K"],
        "c1": printed["coefficients"]["c1"],
        "delta_initial": printed["initial_mixture_ratio_perturbation"],
        "c2": printed["coefficients"]["c2"],
        "c3": printed["coefficients"]["c3"],
        "c4": printed["coefficients"]["c4"],
        "c5": printed["coefficients"]["c5"],
    }
    for key in ("P", "I", "K", "c1", "c4", "c5"):
        require(rational(common[key]) == rational(kernel[key]), f"source mismatch: {key}")
    require(rational(common["delta_initial"]) == rational(kernel["dK"]), "source mismatch: dK")
    require(rational(kernel["c2"]) == 4 * rational(common["c2"]), "source mismatch: c2 factor")
    require(rational(kernel["c3"]) == 4 * rational(common["c3"]), "source mismatch: c3 factor")

    printed_law = {key: common[key] for key in ("P", "I", "K", "c1", "c2", "c3", "c4", "c5")}
    delta_initial = rational(common["delta_initial"])
    printed_initial, _ = flow_and_slope(printed_law, delta_initial)
    kernel_initial, _ = flow_and_slope(kernel, delta_initial)
    _, printed_derivative = flow_and_slope(printed_law, Fraction(0))
    _, kernel_derivative = flow_and_slope(kernel, Fraction(0))
    printed_slope = tuple(rational(common["c1"]) * x for x in printed_derivative)
    kernel_slope = tuple(rational(kernel["c1"]) * x for x in kernel_derivative)
    displayed_initial = tuple(rational(historical["problem"]["initial_state"][i]) for i in (0, 2))
    displayed_b = tuple(rational(historical["problem"]["dynamics"]["B"][i][0]) for i in (0, 2))
    saved_initial = tuple(rational(saved["model_derivation"]["x0"][i]) for i in (0, 2))
    a01_b = tuple(rational(saved["model_derivation"]["B_exact_expressions"][i]) for i in (0, 2))

    return {
        "printed_nonlinear_initial": [str(x) for x in printed_initial],
        "displayed_linear_initial": [str(x) for x in displayed_initial],
        "printed_nonlinear_initial_matches_displayed": printed_initial == displayed_initial,
        "kernel_nonlinear_initial": [str(x) for x in kernel_initial],
        "saved_initial": [str(x) for x in saved_initial],
        "kernel_initial_minus_saved": [str(a - b) for a, b in zip(kernel_initial, saved_initial)],
        "printed_nonlinear_reference_input_slope": [str(x) for x in printed_slope],
        "displayed_linear_B_flow_rows": [str(x) for x in displayed_b],
        "printed_slope_matches_displayed_B": printed_slope == displayed_b,
        "kernel_nonlinear_reference_input_slope": [str(x) for x in kernel_slope],
        "A01_B_flow_rows": [str(x) for x in a01_b],
        "kernel_slope_matches_A01_B": kernel_slope == a01_b,
        "scope": "Printed rational equations and archived source cross-check; not a canonical B04 generator or constrained optimum",
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
