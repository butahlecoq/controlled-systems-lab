"""Observable saved-record checks for the GEO-06 report."""
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[2] / "scripts" / "reports" / "geo06_report.py"
SPEC = importlib.util.spec_from_file_location("geo06_report", MODULE)
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


class Geo06ReportTests(unittest.TestCase):
    def rows(self):
        rows = []
        for name in report.ORDER:
            rows.append({"scenario": name, "repetition": 0, "warmup": 1, "calls": 10,
                         "duration_ns": 200, "status": "passed",
                         "observed_vertices": 10 * len(report.CASES[name]["indices"].split(":")),
                         "indices": report.CASES[name]["indices"]})
        for repetition in range(7):
            for name in (report.ORDER if repetition % 2 == 0 else report.ORDER[::-1]):
                rows.append({"scenario": name, "repetition": repetition, "warmup": 0,
                             "calls": 10, "duration_ns": 100 + repetition * 10,
                             "status": "passed", "observed_vertices": 10 * len(report.CASES[name]["indices"].split(":")),
                             "indices": report.CASES[name]["indices"]})
        return rows

    def test_full_matrix_has_literal_median_and_range(self):
        rows = self.rows()
        report.validate_rows(rows, 7, 1, 10)
        self.assertEqual(report.summarize(rows)["square_duplicates"],
                         {"trials": 7, "median_batch_ns": 130, "min_batch_ns": 100, "max_batch_ns": 160})

    def test_failed_oracle_is_rejected_for_publication(self):
        rows = self.rows()
        rows[4]["indices"] = "0:2:3"
        with self.assertRaisesRegex(ValueError, "output or work count"):
            report.validate_rows(rows, 7, 1, 10)

    def test_missing_trial_is_not_summarized(self):
        with self.assertRaisesRegex(ValueError, "missing or extra"):
            report.validate_rows(self.rows()[:-1], 7, 1, 10)


if __name__ == "__main__":
    unittest.main()
