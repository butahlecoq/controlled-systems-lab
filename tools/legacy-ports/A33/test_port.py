"""Bounded deterministic A33 behavior and independent quality oracle tests."""

import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import numpy as np

import oracle
import port


HERE = Path(__file__).resolve().parent
SQUARE = json.loads((HERE / "fixtures" / "square.json").read_text(encoding="utf-8"))["points"]
CORNERS = [[0, 0], [2, 0], [2, 2], [0, 2]]


class A33PortTests(unittest.TestCase):
    def test_both_active_helpers_keep_their_distinct_tableau_outcomes(self):
        matrix = np.array(CORNERS + [[1, 1]], dtype=float).T
        reduced = port.simplex_hull_mod(matrix, 4)
        self.assertFalse(reduced.outside)
        self.assertEqual(reduced.pivots, 3)
        self.assertEqual(set(map(tuple, reduced.points.T.tolist())), set(map(tuple, CORNERS)))
        inside = port.modified_sm(matrix[:, :4], np.array([1, 1], dtype=float))
        outside = port.modified_sm(matrix[:, :4], np.array([3, 1], dtype=float))
        self.assertFalse(inside.outside)
        self.assertTrue(outside.outside)
        self.assertEqual(inside.pivots, 3)
        self.assertEqual(outside.pivots, 2)
        self.assertEqual(len(inside.basis), 4)

    def test_square_has_exact_hull_with_boundary_and_interior_points(self):
        result = port.run(SQUARE)
        self.assertEqual(result["algorithm_status"], "completed")
        self.assertEqual(result["itrt"], 0)
        self.assertGreater(result["observed_helper_pivots"], 0)
        self.assertGreater(result["helper_calls"]["A16"], result["stage2_scanned"])
        self.assertEqual(set(map(tuple, result["output"])), set(map(tuple, CORNERS)))
        self.assertEqual(oracle.check(SQUARE, result["output"])["status"], "verified")
        self.assertFalse(result["grouping_triggered"])

    def test_tenth_redundant_triggers_grouping_including_tenth_point(self):
        points = CORNERS + [[i / 16, j / 16]
                            for i in range(4, 13, 2) for j in range(4, 13, 2)]
        result = port.run(points)
        self.assertEqual(result["algorithm_status"], "completed")
        self.assertTrue(result["grouping_triggered"])
        self.assertEqual(result["stage2_scanned"], 12)  # 2 corners, then 10 redundant
        self.assertEqual(result["stage3_scanned"], 16)  # includes the tenth again
        self.assertEqual(result["group_fixed_count"], 4)  # floor(size(C,2)*1)
        self.assertGreater(result["helper_calls"]["constrained_Modified_SM"], 0)
        self.assertEqual(oracle.check(points, result["output"])["status"], "verified")

    def test_grouping_retains_late_outside_point_and_accumulates_nearby(self):
        points = ([[-1, 0], [1, 0], [0, -1], [0, 1]]
                  + [[x, 0.75] for x in (0.61, 0.66, 0.70)]
                  + [[k / 64, 0] for k in range(49, 64)])
        original = port.modified_sm
        nearby_sizes = {}

        def observe_group(group, candidate):
            key = tuple(candidate.tolist())
            if key in {(0.61, 0.75), (0.66, 0.75), (0.70, 0.75)}:
                nearby_sizes[key] = group.shape[1] - 4  # fixed Ck has four points
            return original(group, candidate)

        with mock.patch.object(port, "modified_sm", side_effect=observe_group):
            result = port.run(points)
        self.assertEqual(result["algorithm_status"], "completed")
        self.assertTrue(result["grouping_triggered"])
        self.assertEqual(result["group_nearby_appends"], 3)
        self.assertEqual(nearby_sizes, {
            (0.61, 0.75): 0,
            (0.66, 0.75): 1,
            (0.70, 0.75): 3,
        })
        self.assertIn([0.7, 0.75], result["output"])
        self.assertEqual(oracle.check(points, result["output"])["status"], "verified")

    def test_tenth_redundant_at_last_column_is_checked_again_in_group(self):
        interior = [[i / 16, j / 16]
                    for i in range(4, 13, 2) for j in range(4, 13, 2)][:10]
        points = CORNERS + interior
        result = port.run(points)
        self.assertEqual(result["algorithm_status"], "completed")
        self.assertTrue(result["grouping_triggered"])
        self.assertEqual(result["stage2_scanned"], 12)
        self.assertEqual(result["stage3_scanned"], 1)
        self.assertEqual(oracle.check(points, result["output"])["status"], "verified")

    def test_signed_max_abs_metric_differs_from_a29_abs_max(self):
        points = np.array([[-1, -1], [-1, 0.2], [1, -1], [1, 1], [0, 0]], dtype=float)
        matrix, widths, scores = port.preprocess(points)
        index = next(i for i, point in enumerate(matrix.T.tolist()) if point == [-1, 0.2])
        self.assertEqual(scores[index], 0.5)
        midpoint = 0.5 * (points.max(axis=0) + points.min(axis=0))
        a29_score = abs(max((points[1] - midpoint) / widths))
        self.assertLess(a29_score, scores[index])

    def test_duplicates_and_rank_deficient_inputs_have_explicit_outcomes(self):
        with_duplicates = SQUARE + [[0, 0], [1, 1]]
        result = port.run(with_duplicates)
        self.assertEqual(result["algorithm_status"], "completed")
        self.assertEqual(oracle.check(with_duplicates, result["output"])["status"], "verified")
        flat = port.run([[0, 1], [1, 1], [2, 1]])
        self.assertEqual(flat["algorithm_status"], "inconclusive")
        self.assertEqual(flat["stage"], "A33 sorting")
        self.assertIn("zero-range", flat["reason"])
        one_unique = port.run([[1, 1], [1, 1]])
        self.assertEqual(one_unique["algorithm_status"], "failed")
        self.assertEqual(one_unique["stage"], "A33 preprocessing")
        # Non-axis-flat rank-deficient points still exercise the source tableau.
        line = [[0, 0], [1, 1], [2, 2], [0.5, 0.5]]
        line_result = port.run(line)
        self.assertEqual(line_result["algorithm_status"], "completed")
        self.assertEqual(oracle.check(line, line_result["output"])["status"], "verified")

    def test_oracle_rejects_omitted_corner_and_accepts_redundant_retention(self):
        missing = oracle.check(SQUARE, [[0, 0], [2, 0], [2, 2], [1, 1]])
        self.assertEqual(missing["status"], "incorrect")
        self.assertEqual(missing["counterexample_index"], 3)
        self.assertEqual(oracle.check(SQUARE, SQUARE)["status"], "verified")
        self.assertEqual(oracle.check([[0, 0, 0]], [[0, 0, 0]])["status"], "inconclusive")

    def test_cli_retains_status_and_quality_in_one_json_record(self):
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
            self.assertEqual(failure["stage"], "fixture")
            self.assertEqual(failure["quality"]["status"], "inconclusive")


if __name__ == "__main__":
    unittest.main()
