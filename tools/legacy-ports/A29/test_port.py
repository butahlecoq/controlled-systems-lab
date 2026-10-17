"""Deterministic A29/A30 behavior and independent exact quality tests."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import oracle
import port


HERE = Path(__file__).resolve().parent
SQUARE = json.loads((HERE / "fixtures" / "square.json").read_text(encoding="utf-8"))["points"]
CORNERS = [[0, 0], [2, 0], [2, 2], [0, 2]]


class A29PortTests(unittest.TestCase):
    def test_a30_active_tableau_inside_outside_basis_and_pivots(self):
        matrix = np.array(CORNERS, dtype=float).T
        inside = port.modified_sm(matrix, np.array([1, 1], dtype=float))
        outside = port.modified_sm(matrix, np.array([3, 1], dtype=float))
        self.assertFalse(inside.outside)
        self.assertTrue(outside.outside)
        self.assertTrue(port.modified_sm(matrix, np.array([-1, 1], dtype=float)).outside)
        self.assertEqual(inside.pivots, 3)
        self.assertEqual(outside.pivots, 2)
        self.assertEqual(len(inside.basis), 4)

    def test_ordering_uses_abs_of_signed_max_not_max_of_abs(self):
        points = np.array([[-1, -1], [-1, 0.2], [1, -1], [1, 1], [0, 0]], dtype=float)
        matrix, scores = port.preprocess(points)
        index = next(i for i, point in enumerate(matrix.T.tolist()) if point == [-1, 0.2])
        self.assertAlmostEqual(scores[index], 0.1)
        midpoint = 0.5 * (points.max(axis=0) + points.min(axis=0))
        widths = points.max(axis=0) - points.min(axis=0)
        a33_score = max(abs((points[1] - midpoint) / widths))
        self.assertGreater(a33_score, scores[index])

    def test_candidate_filter_then_simultaneous_final_reduction(self):
        calls = []
        original = port.modified_sm

        def counted(support, candidate):
            calls.append(support.shape[1])
            return original(support, candidate)

        with patch.object(port, "modified_sm", side_effect=counted):
            result = port.run(SQUARE)
        self.assertEqual(result["algorithm_status"], "completed")
        self.assertFalse(result["grouping_executed"])
        self.assertEqual(result["stage2_scanned"], 7)
        self.assertEqual(result["final_scanned"], 6)
        self.assertEqual(calls[-result["final_scanned"]:],
                         [result["final_scanned"] - 1] * result["final_scanned"])
        self.assertEqual(result["helper_calls"], result["stage2_scanned"] + result["final_scanned"])
        self.assertEqual(result["itrt"], result["stage2_pivots"] + result["final_pivots"])
        self.assertEqual(result["itrt"], 36)
        self.assertGreater(result["final_pivots"], 0)
        self.assertEqual(set(map(tuple, result["output"])), set(map(tuple, CORNERS)))
        self.assertEqual(oracle.check(SQUARE, result["output"])["status"], "verified")

    def test_duplicates_boundary_and_rank_deficiency(self):
        for points in (SQUARE + [[0, 0], [1, 1]],
                       [[0, 0], [1, 1], [2, 2], [0.5, 0.5]]):
            result = port.run(points)
            self.assertEqual(result["algorithm_status"], "completed")
            self.assertEqual(oracle.check(points, result["output"])["status"], "verified")
        for order in (SQUARE, list(reversed(SQUARE)), SQUARE[3:] + SQUARE[:3]):
            result = port.run(order)
            self.assertEqual(result["algorithm_status"], "completed")
            self.assertEqual(set(map(tuple, result["output"])), set(map(tuple, CORNERS)))

    def test_source_undefined_shapes_are_retained_as_outcomes(self):
        flat = port.run([[0, 1], [1, 1], [2, 1]])
        self.assertEqual(flat["algorithm_status"], "inconclusive")
        self.assertEqual(flat["stage"], "A29 sorting")
        self.assertIn("zero-range", flat["reason"])
        duplicate_only = port.run([[1, 1], [1, 1]])
        self.assertEqual(duplicate_only["algorithm_status"], "failed")
        self.assertEqual(duplicate_only["stage"], "A29 preprocessing")

    def test_independent_exact_oracle_finds_omitted_true_corner(self):
        missing = oracle.check(SQUARE, [[0, 0], [2, 0], [2, 2], [1, 1]])
        self.assertEqual(missing["status"], "incorrect")
        self.assertEqual(missing["counterexample_index"], 3)
        self.assertEqual(oracle.check(SQUARE, SQUARE)["status"], "verified")
        self.assertEqual(oracle.check([[0, 0, 0]], [[0, 0, 0]])["status"], "inconclusive")

    def test_cli_serializes_success_and_failure_without_losing_quality_status(self):
        completed = subprocess.run(
            [sys.executable, str(HERE / "port.py"), str(HERE / "fixtures" / "square.json")],
            capture_output=True, text=True, check=True)
        result = json.loads(completed.stdout)
        self.assertEqual(result["algorithm_status"], "completed")
        self.assertEqual(result["quality"]["status"], "verified")
        self.assertEqual(result["source_sha256"], port.SOURCE_SHA256)
        self.assertEqual(result["quality"]["input_digest"], oracle.manifest_digest(SQUARE))
        with tempfile.TemporaryDirectory() as directory:
            malformed = Path(directory) / "malformed.json"
            malformed.write_text("{broken", encoding="utf-8")
            failed = subprocess.run([sys.executable, str(HERE / "port.py"), str(malformed)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(failed.returncode, 2)
            failure = json.loads(failed.stdout)
            self.assertEqual(failure["algorithm_status"], "failed")
            self.assertEqual(failure["quality"]["status"], "inconclusive")


if __name__ == "__main__":
    unittest.main()
