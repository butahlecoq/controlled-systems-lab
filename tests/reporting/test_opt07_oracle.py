"""Literal, solver-independent checks for the OPT-07 standalone harness."""
import json
import importlib
import math
import sys
import tempfile
from types import ModuleType
import unittest
from pathlib import Path

_package_name = "csl_opt07_report_tooling"
_tooling = Path(__file__).resolve().parents[2] / "reports/algorithm-results/tooling/opt07"
if _package_name not in sys.modules:
    package = ModuleType(_package_name)
    package.__path__ = [str(_tooling)]
    sys.modules[_package_name] = package
validate_call = importlib.import_module(_package_name + ".oracle").validate_call
validate_stream = importlib.import_module(_package_name + ".validate").validate_stream


def valid_late_row():
    return {
        "kind": "call", "purpose": "smoke", "case_id": "late-outside",
        "problem": "opt07-late-outside",
        "round": 0, "warmup": True, "ordinal": 0,
        "points": [[0.0], [0.5], [0.25], [1.0]],
        "status": "complete", "retained": [0, 3],
        "removed": [
            {"point": 2, "program": "hull-membership-2", "program_problem": "opt07-late-outside",
             "terms": [[0, 0.75], [3, 0.25]]},
            {"point": 1, "program": "hull-membership-1", "program_problem": "opt07-late-outside",
             "terms": [[0, 0.5], [3, 0.5]]},
        ],
        "order": [0, 3, 2, 1], "ordered_candidates": 4,
        "zero_width_coordinates": 0, "identity_fallback": False,
        "lp_calls": 4, "attempts": [[0, "infeasible"], [3, "infeasible"],
                                    [2, "feasible"], [1, "feasible"]],
        "support": [1.0, 0.0], "verified": True,
    }


class OracleTests(unittest.TestCase):
    def test_literal_valid_deletion(self):
        validate_call(valid_late_row())

    def test_rounded_weight_is_not_exact(self):
        row = valid_late_row()
        row["removed"][0]["terms"][1][1] = math.nextafter(0.25, 1.0)
        with self.assertRaises(ValueError):
            validate_call(row)

    def test_duplicate_retained_id_is_rejected(self):
        row = valid_late_row()
        row["retained"] = [0, 0, 3]
        with self.assertRaises(ValueError):
            validate_call(row)

    def test_forged_order_is_rejected(self):
        row = valid_late_row()
        row["order"] = [0, 3, 1, 2]
        with self.assertRaises(ValueError):
            validate_call(row)

    def test_missing_certificate_is_rejected(self):
        row = valid_late_row()
        row["removed"].pop()
        with self.assertRaises(ValueError):
            validate_call(row)

    def test_smoke_stream_requires_all_three_cases_and_batches(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "smoke.jsonl"
            # A valid late-outside call alone still cannot be a complete smoke.
            row = valid_late_row()
            batch = {"kind": "batch", "purpose": "smoke", "case_id": "late-outside",
                     "round": 0, "warmup": True, "calls": 1,
                     "verified_calls": 1, "elapsed_ns": 12}
            path.write_text(json.dumps(row) + "\n" + json.dumps(batch) + "\n",
                            encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing or extra"):
                validate_stream(path, "smoke")

    def test_batch_cannot_claim_unverified_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "smoke.jsonl"
            row = valid_late_row()
            batch = {"kind": "batch", "purpose": "smoke", "case_id": "late-outside",
                     "round": 0, "warmup": True, "calls": 1,
                     "verified_calls": 0, "elapsed_ns": 12}
            path.write_text(json.dumps(row) + "\n" + json.dumps(batch) + "\n",
                            encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid batch count"):
                validate_stream(path, "smoke")


if __name__ == "__main__":
    unittest.main()
