"""Literal geometry checks for the private FIG audit's exact operations."""

import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from docs.research.tools.check_l05_saved_figures import area, convex_hull, saved_patches, violations


def point(x: int, y: int) -> tuple[Fraction, Fraction]:
    return Fraction(x), Fraction(y)


class SavedFigureGeometryTests(unittest.TestCase):
    def test_exact_area_and_polygon_inclusion(self) -> None:
        square = convex_hull([
            point(1, 1), point(0, 0), point(1, 0), point(0, 1),
            point(0, 0), (Fraction(1, 2), Fraction(1, 2)),
        ])
        triangle = convex_hull([point(0, 0), point(1, 0), point(0, 1)])
        self.assertEqual(area(square), Fraction(1))
        self.assertEqual(area(triangle), Fraction(1, 2))
        self.assertEqual(violations(triangle, square), 0)
        self.assertEqual(violations(square, triangle), 1)

    def test_rejects_collinear_polygon_and_wrong_source_hash(self) -> None:
        with self.assertRaisesRegex(ValueError, "collinear"):
            convex_hull([point(0, 0), point(1, 0), point(2, 0)])
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "4.fig"
            fake.write_bytes(b"not the registered private source")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                saved_patches(fake, {"0" * 64})


if __name__ == "__main__":
    unittest.main()
