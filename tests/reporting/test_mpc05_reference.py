"""Verify the saved MPC-05 exact reference checks the entire Bellman table."""

import json
import unittest
from pathlib import Path

from scripts.reports.mpc05.reference import verify_result

SAVED = (
    Path(__file__).resolve().parents[2]
    / "reports/algorithm-results/mpc05-causal-tree-pilot-v2/result.json"
)


class Mpc05ReferenceTests(unittest.TestCase):
    def test_rejects_missing_bellman_stage(self) -> None:
        record = json.loads(SAVED.read_bytes())
        record["two_points"]["bellman_cost_to_go"].pop()
        with self.assertRaisesRegex(ValueError, "Bellman cost-to-go table stage count"):
            verify_result(record)
