"""Check timing input validation for saved geometry companions."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))

import geometry_opt_companions  # noqa: E402


class GeometryOptimizationTimingTests(unittest.TestCase):
    def test_rejects_nonfinite_and_non_numeric_durations(self):
        for field in ("min", "median", "max"):
            for invalid in (float("inf"), float("-inf"), float("nan"), True, "12"):
                with (
                    self.subTest(field=field, value=invalid),
                    self.assertRaisesRegex(ValueError, "timing row needs finite"),
                ):
                    values = {"min": 10, "median": 12, "max": 15, field: invalid}
                    record = {"summary": {"fixture": {"phases": {"total_ns": values}}}}
                    geometry_opt_companions.timing_rows("geo02", record)

    def test_retains_exact_finite_values_in_the_timing_receipt(self):
        values = {"min": 0, "median": 12.5, "max": 15}
        record = {"summary": {"fixture": {"phases": {"total_ns": values}}}}
        [row] = geometry_opt_companions.timing_rows("geo02", record)
        self.assertEqual(row, {"label": "fixture", "series": "total trial", **values})
        self.assertIs(type(row["min"]), int)
        self.assertIs(type(row["median"]), float)
