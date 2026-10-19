"""Literal public checks of the source-bound four-state retention translation."""

import tempfile
import unittest
from pathlib import Path

import numpy as np

from docs.research.tools.check_l05_dim4_candidate import source_hash
from docs.research.tools.check_l05_dim4_retention import candidate_stages, convsm_mod


class Dim4RetentionTests(unittest.TestCase):
    def test_ordered_square_discards_interior_point(self) -> None:
        cloud = np.array([[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0], [0.0, 0.0]])
        retained, pivots = convsm_mod(cloud)
        self.assertEqual(retained.tolist(), cloud[:4].tolist())
        self.assertEqual(pivots, 11)

    def test_source_ordered_four_state_stage_counts(self) -> None:
        stages = list(candidate_stages())
        self.assertEqual([len(stage[2]) for stage in stages], [4, 16, 52, 128, 260, 464, 756])
        self.assertEqual([stage[1] for stage in stages], [4, 16, 64, 208, 512, 1040, 1856])

    def test_rejects_unregistered_filter_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "ConvSM_mod.m"
            fake.write_bytes(b"unregistered filter")
            with self.assertRaisesRegex(ValueError, "private source SHA-256 mismatch"):
                source_hash(fake, "0" * 64)


if __name__ == "__main__":
    unittest.main()
