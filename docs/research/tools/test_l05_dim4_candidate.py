"""Public geometry and source-gate checks for the private four-state audit."""

import tempfile
import unittest
from pathlib import Path

import numpy as np

from docs.research.tools.check_l05_dim4_candidate import generator_volume, source_hash


class Dim4CandidateTests(unittest.TestCase):
    def test_four_independent_generators_form_a_volume_16_box(self) -> None:
        generators = [np.eye(4)[:, index] for index in range(4)]
        volume, minimum_minor, minor_count = generator_volume(generators)
        self.assertEqual((volume, minimum_minor, minor_count), (16.0, 1.0, 1))

    def test_rejects_unregistered_private_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "Dim4.m"
            fake.write_bytes(b"unregistered source")
            with self.assertRaisesRegex(ValueError, "private source SHA-256 mismatch"):
                source_hash(fake, "0" * 64)


if __name__ == "__main__":
    unittest.main()
