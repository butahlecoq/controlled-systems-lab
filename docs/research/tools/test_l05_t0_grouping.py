"""Public regression checks for the L05 T0 grouping evidence."""

import json
import unittest
from fractions import Fraction
from pathlib import Path

from docs.research.tools.check_l05_linear_zonotope import FIGURE_SHA256, SOURCE_SHA256
from docs.research.tools.check_l05_t0_grouping import grouping_summary


ROOT = Path(__file__).resolve().parents[3]
RECORD = ROOT / "docs/research/evidence/l05-t0-grouping.json"


class T0GroupingTests(unittest.TestCase):
    def test_printed_groupings_have_exact_ratio_twenty_five_over_eighteen(self) -> None:
        product = Fraction(9, 10) * Fraction(4, 5)
        self.assertEqual(product, Fraction(18, 25))
        self.assertEqual(1 / product, Fraction(25, 18))
        summary = grouping_summary()
        self.assertEqual(summary["candidate"]["simplified"], "pi/(18*sqrt(2))")
        self.assertEqual(summary["alternative"]["simplified"], "pi*sqrt(2)/50")
        self.assertEqual(summary["candidate_over_alternative"], "25/18")

    def test_saved_record_matches_public_formula_and_scope(self) -> None:
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        self.assertEqual(record["grouping_formula_audit"], grouping_summary())
        self.assertEqual(record["candidate_source_sha256"], SOURCE_SHA256)
        self.assertEqual(record["figure_sha256"], FIGURE_SHA256)
        self.assertEqual(record["stages"], 60)
        self.assertEqual(record["candidate_matching_stages"], 60)
        self.assertEqual(record["alternative_matching_stages"], 0)
        self.assertEqual(len(record["per_stage"]), 60)
        self.assertTrue(any("Table 1 driver" in limit for limit in record["limits"]))


if __name__ == "__main__":
    unittest.main()
