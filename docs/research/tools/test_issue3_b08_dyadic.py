"""Behavior checks for the frozen Issue 3 B08 binary64 audit."""

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_issue3_b08_dyadic import audit, check_product_plans, exact_plan_scores


ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "reports/algorithm-results/issue3-finite-catalogue-b4632ce76510aa4f/evidence/accepted-001/accepted.stdout"


def saved_b08():
    return next(json.loads(line) for line in RAW.read_text(encoding="utf-8").splitlines()
                if '"fixture":"b08_rounded"' in line)


class B08DyadicAuditTest(unittest.TestCase):
    def test_small_convex_endpoint_and_plan_record_checks(self):
        fixture = {
            "model": {"A": [[1]], "B": [[1]], "D": [[1]],
                      "initial": [0], "horizon": 1},
            "actions": [[0], [1]],
            "disturbance_vertices_binary64_hex": [[['0x0.0p+0'], ['0x1.0000000000000p+1']]],
            "safe": "universal",
            "objective": {"type": "residual_norm_terminal", "C": [[1]], "target": [1]},
        }
        scores = exact_plan_scores(fixture)
        self.assertEqual([score.squared for score in scores], [1, 4])
        self.assertEqual([score.vertices for score in scores], [2, 2])
        product = {"input_sha256": "literal-input", "status": "numerical_optimal",
                   "plans": [
                       {"status": "feasible", "action_indices": [0],
                        "evaluated_vertices": 2, "worst_value": 1.0},
                       {"status": "feasible", "action_indices": [1],
                        "evaluated_vertices": 2, "worst_value": 2.0},
                   ]}
        check_product_plans(product, "literal-input", scores, 2)
        product["plans"][1]["worst_value"] = 1.0
        with self.assertRaisesRegex(ValueError, "plan 1 objective"):
            check_product_plans(product, "literal-input", scores, 2)
        product["plans"][1]["worst_value"] = 2.0
        product["plans"][1]["status"] = "rejected"
        with self.assertRaisesRegex(ValueError, "plan 1 status/count"):
            check_product_plans(product, "literal-input", scores, 2)

    def test_saved_b08_aggregate_is_checked_against_exact_replay(self):
        result = audit(saved_b08())
        self.assertEqual(result["plans"], 625)
        self.assertEqual(result["terminal_rows"], 160000)
        self.assertEqual(result["product_status"], "numerical_optimal")
        self.assertEqual(result["minimum_squared_exact"],
                         "231872326938210039429249200991359801692751261309588097080034965421/51422017416287688817342786954917203280710495801049370729644032")
        self.assertEqual(result["exact_minimizer_indices"], [17, 33, 129])
        self.assertEqual(result["product_near_indices"], [17, 33, 129])
        self.assertLess(abs(result["product_value"] - result["exact_norm_lower"]), 1e-9)

    def test_wrong_product_value_is_rejected(self):
        row = saved_b08()
        row["result"]["value"] = 0.0
        with self.assertRaisesRegex(ValueError, "saved result hash"):
            audit(row)


if __name__ == "__main__":
    unittest.main()
