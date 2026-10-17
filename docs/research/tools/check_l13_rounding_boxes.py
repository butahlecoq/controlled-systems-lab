"""Exact nearest-decimal rounding-box audit of L13 Table 2 criteria.

The A09 synchronization expression is a candidate, not an identified source
of the published rows. This script does not run either nonlinear model.
"""

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from docs.research.tools.check_l13_displayed_criteria import ROWS, TARGET, squared_criteria


RESEARCH = Path(__file__).resolve().parents[1]
WITNESS_X2 = {
    "simplified/open_loop": "47.663343",
    "simplified/adaptive": "20.284693",
    "original/open_loop": "22.630245",
    "original/adaptive": "20.284611",
}


def rational(value):
    return f"{value.numerator}/{value.denominator}"


def half_unit(text):
    """Half a unit in the last decimal place as printed, including integers."""
    decimals = len(text.split(".", 1)[1]) if "." in text else 0
    return Fraction(1, 2 * 10 ** decimals)


def euclidean_squared_box(coordinates, target):
    """Exact extrema of squared Euclidean distance over coordinate boxes."""
    if len(coordinates) != len(target):
        raise ValueError("coordinate and target dimensions differ")
    lower = upper = Fraction(0)
    for printed, goal in zip(coordinates, target):
        distance = abs(Fraction(printed) - Fraction(goal))
        radius = half_unit(printed)
        lower += max(Fraction(0), distance - radius) ** 2
        upper += (distance + radius) ** 2
    return lower, upper


def registered_identity(source_id):
    if source_id == "L13":
        records = json.loads((RESEARCH / "inventory.json").read_text(encoding="utf-8"))
    elif source_id == "A09":
        records = json.loads((RESEARCH / "archive-selected-sources.json").read_text(
            encoding="utf-8"))["selected_sources"]
    else:
        raise ValueError("only L13 and A09 are source-registered for this audit")
    return next(entry for entry in records if entry["id"] == source_id)


def verify_source_bytes(source_id, raw):
    identity = registered_identity(source_id)
    if len(raw) != identity["bytes"] or hashlib.sha256(raw).hexdigest() != identity["sha256"]:
        label = "L13 PDF" if source_id == "L13" else "A09 source"
        raise ValueError(f"{label} bytes/hash differ from registered original")


def audit():
    result = {
        "scope": "L13 Table 2 printed coordinate and criterion rounding boxes only",
        "rounding_convention": "nearest decimal, half a last-place unit; ties immaterial here",
        "source_sha256": {source_id: registered_identity(source_id)["sha256"]
                          for source_id in ("L13", "A09")},
        "rows": {},
    }
    for label, coordinates, reported in ROWS:
        center = tuple(map(Fraction, coordinates))
        cost = Fraction(reported)
        cost_half = half_unit(reported)
        cost_lower = (cost - cost_half) ** 2
        cost_upper = (cost + cost_half) ** 2
        euclidean_lower, euclidean_upper = euclidean_squared_box(coordinates, TARGET)
        witness_x2 = WITNESS_X2[label]
        witness = (coordinates[0], witness_x2, coordinates[2], coordinates[3])
        _, candidate_squared = squared_criteria(witness)
        witness_in_coordinate_box = all(
            abs(Fraction(value) - nominal) < half_unit(printed)
            for value, nominal, printed in zip(witness, center, coordinates))
        witness_in_cost_box = cost_lower < candidate_squared < cost_upper
        result["rows"][label] = {
            "printed_coordinates": list(coordinates),
            "reported_criterion": reported,
            "euclidean_squared_box": [rational(euclidean_lower), rational(euclidean_upper)],
            "reported_squared_box": [rational(cost_lower), rational(cost_upper)],
            "euclidean_cost_box_disjoint": (
                euclidean_lower > cost_upper or euclidean_upper < cost_lower),
            "candidate_witness_x2": witness_x2,
            "candidate_witness_squared": rational(candidate_squared),
            "candidate_witness_in_boxes": witness_in_coordinate_box and witness_in_cost_box,
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--l13-pdf", type=Path, help="optional registered private L13 PDF")
    parser.add_argument("--a09-source", type=Path, help="optional registered private A09 MATLAB file")
    args = parser.parse_args()
    if bool(args.l13_pdf) != bool(args.a09_source):
        parser.error("supply both private source paths or neither")
    if args.l13_pdf:
        for source_id, path in (("L13", args.l13_pdf), ("A09", args.a09_source)):
            try:
                verify_source_bytes(source_id, path.read_bytes())
            except OSError as error:
                parser.error(f"cannot read registered {source_id} original: {error.strerror}")
    observed = audit()
    observed["private_sources_verified"] = bool(args.l13_pdf)
    print(json.dumps(observed, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
