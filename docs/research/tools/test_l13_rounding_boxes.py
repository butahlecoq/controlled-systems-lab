"""Literal behavior checks for L13 Table 2 nearest-decimal boxes."""

from fractions import Fraction
import unittest

from docs.research.tools.check_l13_rounding_boxes import (
    audit, euclidean_squared_box, verify_source_bytes,
)


class L13RoundingBoxesTests(unittest.TestCase):
    def test_euclidean_bounds_allow_a_target_inside_a_coordinate_box(self):
        self.assertEqual(euclidean_squared_box(("0", "2"), (0, 0)),
                         (Fraction(9, 4), Fraction(13, 2)))

    def test_all_four_reported_costs_exclude_printed_euclidean_criterion(self):
        rows = audit()["rows"]
        self.assertEqual([rows[name]["euclidean_cost_box_disjoint"] for name in (
            "simplified/open_loop", "simplified/adaptive",
            "original/open_loop", "original/adaptive")], [True] * 4)
        self.assertEqual(rows["original/adaptive"]["euclidean_squared_box"],
                         ["85973/200", "17413/40"])

    def test_each_a09_candidate_witness_rounds_to_both_printed_fields(self):
        rows = audit()["rows"]
        self.assertEqual({name: (row["candidate_witness_x2"],
                                 row["candidate_witness_squared"],
                                 row["candidate_witness_in_boxes"])
                          for name, row in rows.items()}, {
            "simplified/open_loop":
                ("47.663343", "6703662052435649/500000000000", True),
            "simplified/adaptive":
                ("20.284693", "256692473854249/500000000000", True),
            "original/open_loop":
                ("22.630245", "12796741050401/20000000000", True),
            "original/adaptive":
                ("20.284611", "256669819671321/500000000000", True),
        })

    def test_source_gate_rejects_wrong_bytes(self):
        with self.assertRaisesRegex(ValueError, "L13 PDF bytes/hash"):
            verify_source_bytes("L13", b"not the original")
        with self.assertRaisesRegex(ValueError, "A09 source bytes/hash"):
            verify_source_bytes("A09", b"not the original")


if __name__ == "__main__":
    unittest.main()
