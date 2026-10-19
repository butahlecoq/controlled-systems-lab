"""Public literal checks for the commented four-state reduction hypothesis."""

import tempfile
import unittest
from pathlib import Path

from scipy.spatial import ConvexHull

from docs.research.tools.check_l05_dim4_approx import stagewise_linear
from docs.research.tools.check_l05_dim4_candidate import source_hash


class Dim4ApproxTests(unittest.TestCase):
    def test_commented_threshold_does_not_reproduce_printed_modified_row(self) -> None:
        stages = list(stagewise_linear(0.001))
        self.assertEqual([len(stage[3]) for stage in stages], [4, 16, 52, 75, 116, 130, 148])
        self.assertAlmostEqual(ConvexHull(stages[-1][3]).volume, 34421.17014411157, delta=1e-7)
        self.assertNotEqual(len(stages[-1][3]), 153)

    def test_tied_distance_rank_order_changes_result(self) -> None:
        terminal = list(stagewise_linear(0.001, sort_kind="quicksort"))[-1][3]
        self.assertEqual(len(terminal), 150)
        self.assertAlmostEqual(ConvexHull(terminal).volume, 34582.74177, delta=1e-5)

    def test_rejects_unregistered_approximation_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "Approx_mod.m"
            fake.write_bytes(b"not the archived source")
            with self.assertRaisesRegex(ValueError, "private source SHA-256 mismatch"):
                source_hash(fake, "0" * 64)


if __name__ == "__main__":
    unittest.main()
