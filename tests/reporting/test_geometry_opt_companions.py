"""Check timing input validation for saved geometry companions."""

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))

import geometry_opt_companions  # noqa: E402


class GeometryOptimizationTimingTests(unittest.TestCase):
    def test_svg_accessibility_serialization_restores_process_namespaces(self):
        namespace_map = vars(ET)["_namespace_map"]
        before = namespace_map.copy()
        svg = (
            b'<svg xmlns="http://www.w3.org/2000/svg" '
            b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            b'<metadata rdf:resource="urn:csl:saved-timing"/></svg>'
        )
        rendered = geometry_opt_companions._svg_with_accessibility(svg, "Saved", "Timing")
        root = ET.fromstring(rendered)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertIn(b'<svg xmlns="http://www.w3.org/2000/svg"', rendered)
        self.assertEqual(namespace_map, before)

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

    def test_rejects_invalid_samples_before_computing_statistics(self):
        for invalid in (float("nan"), float("inf"), True, "12"):
            samples = [1, 2, 3, 4, invalid]
            records = {
                "geo05": {
                    "catalog": {"scenarios": ["fixture"]},
                    "trials": [
                        {
                            "scenario": "fixture",
                            "status": "passed",
                            "durations_ns": {"end_to_end_ns": value},
                        }
                        for value in samples
                    ],
                },
                "opt12": {
                    "trials": [
                        {
                            "scenario": "fixture",
                            "status": "verified",
                            "mode": "cold",
                            "wall_ns": value,
                        }
                        for value in samples
                    ],
                },
            }
            for slug, record in records.items():
                with (
                    self.subTest(report=slug, value=invalid),
                    self.assertRaisesRegex(ValueError, "timing row needs finite"),
                ):
                    geometry_opt_companions.timing_rows(slug, record)

    def test_keeps_existing_sample_admission_rules(self):
        geo05 = {
            "catalog": {"scenarios": ["fixture"]},
            "trials": [
                {"scenario": "fixture", "status": status, "durations_ns": {"end_to_end_ns": value}}
                for status, value in (("passed", 8), ("passed", None), ("failed", float("nan")))
            ],
        }
        opt12 = {
            "trials": [
                {"scenario": "fixture", "status": status, "mode": "cold", "wall_ns": value}
                for status, value in (("verified", 8), ("failed", float("nan")))
            ],
        }
        for slug, record in (("geo05", geo05), ("opt12", opt12)):
            with self.subTest(report=slug):
                [row] = geometry_opt_companions.timing_rows(slug, record)
                self.assertEqual((row["min"], row["median"], row["max"]), (8, 8, 8))
