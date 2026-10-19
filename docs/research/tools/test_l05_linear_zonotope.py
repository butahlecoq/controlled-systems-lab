"""Public checks for the independent planar zonotope construction."""

import tempfile
import unittest
from pathlib import Path

from docs.research.tools.check_l05_linear_zonotope import (
    audit,
    vertex_set_distance,
    zonotope_vertices,
)


class LinearZonotopeTests(unittest.TestCase):
    def test_independent_generators_form_the_expected_rectangle(self) -> None:
        vertices = zonotope_vertices((0.0, 0.0), [(1.0, 0.0), (0.0, 2.0)])
        self.assertEqual(vertices, [(-1.0, -2.0), (1.0, -2.0), (1.0, 2.0), (-1.0, 2.0)])
        self.assertEqual(vertex_set_distance(vertices, list(reversed(vertices))), 0.0)

    def test_rejects_an_unregistered_candidate_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "Volterra.m"
            fake.write_text("unregistered source", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "candidate source SHA-256 mismatch"):
                audit(fake, fake)


if __name__ == "__main__":
    unittest.main()
