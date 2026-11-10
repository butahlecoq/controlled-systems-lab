import importlib.util
from fractions import Fraction
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "docs/research/tools/check_btulshor_hulls.py"
SPEC = importlib.util.spec_from_file_location("check_btulshor_hulls", SCRIPT)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def assert_certificates(test, points, certificates):
    """Check the public certificate identities without using checker internals."""
    for target_index, terms in certificates.items():
        target = [Fraction.from_float(float(x)) for x in points[int(target_index)]]
        weights = [(term["index"], Fraction(term["weight"])) for term in terms]
        test.assertTrue(weights)
        test.assertTrue(all(weight >= 0 for _, weight in weights))
        test.assertEqual(sum((w for _, w in weights), Fraction(0)), Fraction(1))
        rebuilt = [sum((w * Fraction.from_float(float(points[i][axis])) for i, w in weights), Fraction(0))
                   for axis in range(len(target))]
        test.assertEqual(rebuilt, target)


class ExactBtulshorHullTests(unittest.TestCase):
    def check(self, points, retained, **kwargs):
        return checker.check_hull(points, retained, **kwargs)

    def test_one_dimensional_extremes_and_interior(self):
        points = [[-2.0], [0.5], [3.0]]
        result = self.check(points, [2, 0])
        self.assertEqual(result["status"], "verified")
        self.assertTrue(result["hull_equal"])
        assert_certificates(self, points, result["certificates"])

    def test_square_missing_corner_is_rejected(self):
        points = [[0, 0], [1, 0], [1, 1], [0, 1]]
        result = self.check(points, [0, 1, 2])
        self.assertEqual((result["status"], result["hull_equal"]), ("rejected", False))

    def test_tiny_outside_square_points_are_exactly_rejected(self):
        square = [[0, 0], [1, 0], [1, 1], [0, 1]]
        for extra in ([0.5, 1.00000001], [1e-8, -1e-8]):
            points = square + [extra]
            result = self.check(points, [3, 0, 1, 2])
            self.assertEqual((result["status"], result["hull_equal"]), ("rejected", False))

    def test_simplex_interiors_in_three_and_four_dimensions(self):
        for d in (3, 4):
            simplex = [[0.0] * d] + [[float(axis == k) for axis in range(d)] for k in range(d)]
            points = simplex + [[1.0 / (d + 1)] * d]
            result = self.check(points, list(range(d + 1)))
            self.assertEqual(result["status"], "verified")
            assert_certificates(self, points, result["certificates"])

    def test_lower_dimensional_collinear_cloud(self):
        points = [[0, 0, 0], [1, 2, 3], [2, 4, 6], [0.5, 1, 1.5]]
        result = self.check(points, [0, 2])
        self.assertEqual(result["status"], "verified")
        assert_certificates(self, points, result["certificates"])

    def test_duplicate_coordinates_keep_distinct_original_indices(self):
        points = [[0, 0], [0, 0], [1, 0], [0, 1]]
        result = self.check(points, [0, 1, 2, 3])
        self.assertEqual(result["status"], "verified")
        self.assertIn(0, result["extra_indices"])
        self.assertIn(1, result["extra_indices"])
        self.assertFalse(result["irredundancy"])
        self.assertIn("1", result["redundancy_certificates"])
        assert_certificates(self, points, result["certificates"])
        assert_certificates(self, points, result["redundancy_certificates"])

    def test_hull_equality_does_not_claim_redundancy_is_irredundant(self):
        points = [[0], [1], [0.5]]
        result = self.check(points, [0, 1, 2])
        self.assertTrue(result["hull_equal"])
        self.assertEqual(result["extra_indices"], [2])
        self.assertFalse(result["irredundancy"])

    def test_empty_cloud_is_well_defined(self):
        result = self.check([], [])
        self.assertEqual((result["status"], result["hull_equal"]), ("verified", True))

    def test_invalid_inputs_are_inconclusive(self):
        cases = [([[0], [1, 2]], [0]), ([[float("nan")]], [0]), ([[float("inf")]], [0]),
                 ([[0]], [1]), ([[0]], [0, 0]), ([[0]], [True]), ([[0]], [0.0]),
                 ([[0]] * 13, [0]), ([[0, 0, 0, 0, 0]], [0]), ([[10 ** 400]], [0])]
        for points, retained in cases:
            with self.subTest(points=points, retained=retained):
                self.assertEqual(self.check(points, retained)["status"], "inconclusive")

    def test_zero_budget_never_claims_missing_corner(self):
        result = self.check([[0], [1]], [0], max_basis_tests=0)
        self.assertEqual((result["status"], result["hull_equal"]), ("inconclusive", None))
        self.assertEqual(result["basis_tests"], 0)

    def test_exhausted_redundancy_budget_preserves_verified_hull(self):
        result = self.check([[0], [1]], [0, 1], max_basis_tests=3)
        self.assertEqual((result["status"], result["hull_equal"]), ("verified", True))
        self.assertIsNone(result["irredundancy"])


if __name__ == "__main__":
    unittest.main()
