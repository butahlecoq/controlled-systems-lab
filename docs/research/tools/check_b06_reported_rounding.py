"""Exact decimal-center checks for L09's B06 terminal rows."""

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path


SOURCE_ID = "L09"
SOURCE_BYTES = 638778
SOURCE_SHA256 = "bb32b230e600fd0871322768dbf42d181fa7a0a288b97c717659a6448e3b72aa"
ROWS = {
    "linear_table_center": (("29.83", "6.73", "19.87", "5"), "10.11", 2),
    "nonlinear_table_center": (("30", "6.03", "20", "4.47"), "9.049", 3),
    "nonlinear_text_center": (("30", "6.0345", "20", "4.4731"), "9.049", 3),
}


def rational(value):
    return f"{value.numerator}/{value.denominator}"


def squared_criterion(coordinates):
    x1, x2, x3, x4 = coordinates
    return ((30 - x1) ** 2 + x2 ** 2
            + Fraction("2.25") * (20 - x3) ** 2
            + Fraction("2.25") * x4 ** 2
            + (x2 - Fraction("1.5") * x4) ** 2)


def audit():
    result = {
        "source_id": SOURCE_ID,
        "source_sha256": SOURCE_SHA256,
        "source_bytes": SOURCE_BYTES,
        "scope": "Exact B06 criterion at L09 displayed terminal-coordinate centers",
        "criterion": "L09 physical PDF p.11; sqrt((30-x1)^2+x2^2+2.25(20-x3)^2+2.25x4^2+(x2-1.5x4)^2)",
        "coordinates": {
            "linear_table_center": "physical PDF p.16 (printed p.6), Table 2",
            "nonlinear_table_center": "physical PDF p.16 (printed p.6), Table 2",
            "nonlinear_text_center": "physical PDF p.12 prose",
        },
    }
    for name, (coordinate_text, reported_text, digits) in ROWS.items():
        coordinates = tuple(map(Fraction, coordinate_text))
        reported = Fraction(reported_text)
        half_ulp = Fraction(1, 2 * 10 ** digits)
        lower = reported - half_ulp
        upper = reported + half_ulp
        squared = squared_criterion(coordinates)
        result[name] = {
            "terminal_coordinates": list(coordinate_text),
            "reported_criterion": reported_text,
            "criterion_decimal_places": digits,
            "criterion_squared_at_center": rational(squared),
            "reported_criterion_squared_interval": [rational(lower ** 2), rational(upper ** 2)],
            "center_rounds_to_reported_criterion": lower ** 2 <= squared < upper ** 2,
        }
    return result


def verify_source(path):
    raw = path.read_bytes()
    if len(raw) != SOURCE_BYTES or hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("L09 PDF bytes/hash differ from registered source")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-pdf", type=Path, help="optional private L09 original hash check")
    parser.add_argument("--verify-record", type=Path, help="compare with committed exact result")
    args = parser.parse_args()
    if args.source_pdf:
        verify_source(args.source_pdf)
    observed = audit()
    if args.verify_record:
        expected = json.loads(args.verify_record.read_text(encoding="utf-8"))
        if observed != expected:
            raise ValueError("B06 reported-rounding record differs from exact calculation")
        print("B06 reported-cost center audit verified")
    else:
        print(json.dumps(observed, indent=2, ensure_ascii=False))
