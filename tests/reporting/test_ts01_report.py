from __future__ import annotations
import json
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "reports" / "algorithm-results" / "tooling" / "ts01"
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

def load_tool(name):
    spec = importlib.util.spec_from_file_location("csl_test_ts01_" + name, TOOLS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

report = load_tool("report")
publication_map = load_tool("publication_map")
build_bundle = load_tool("build_bundle")
import ts01_registered_reports


class Ts01SavedReportTests(unittest.TestCase):
    def setUp(self):
        self.bundle = ROOT / "reports" / "algorithm-results" / "syn07-ts01-20261013-28f305387f66"
        self.record = json.loads((self.bundle / "records.json").read_text(encoding="utf-8"))

    def test_exact_membership_matrix_matches_saved_outcomes(self):
        self.assertEqual(report.validate(self.record), [])
        self.assertEqual(sum(row["actual_member"] for row in self.record["membership_examples"]), 4)
        self.assertEqual(sum(not row["actual_member"] for row in self.record["membership_examples"]), 3)

    def test_changed_membership_result_is_rejected(self):
        changed = json.loads(json.dumps(self.record))
        changed["membership_examples"][0]["actual_member"] = False
        self.assertIn("membership_result:s=0", report.validate(changed))

    def test_changed_timing_summary_is_rejected(self):
        for field in ("median", "min", "max", "range"):
            with self.subTest(field=field):
                changed = json.loads(json.dumps(self.record))
                changed["measurement"]["timing_ns"][field] += 1
                self.assertIn("measurement_summary", report.validate(changed))

    def test_scenario_and_input_hashes_are_canonical_and_checked(self):
        scenario = self.record["scenario"]
        self.assertEqual(scenario["sha256"], report.digest(scenario["value"]))
        self.assertEqual(self.record["input"]["sha256"], report.digest(self.record["input"]["value"]))
        changed = json.loads(json.dumps(self.record))
        changed["scenario"]["sha256"] = "0" * 64
        self.assertIn("scenario_hash", report.validate(changed))

    def test_actual_strategy_observations_are_separate_from_analytic_expectations(self):
        expected = self.record["canonical_relation"]["objective_minimum"]
        observed = self.record["measurement"]["strategy_observation"]
        self.assertEqual(expected, 0)
        self.assertEqual(observed["termination"], "completed")
        self.assertEqual(observed["outcome"], "optimal")
        self.assertEqual(observed["objective_lower"], 0)
        self.assertEqual(observed["objective_upper"], 0)
        self.assertEqual(observed["residuals"], {"available": False, "reason": "StrategyPort result exposes no residual fields"})
        changed = json.loads(json.dumps(self.record))
        changed["measurement"]["strategy_observation"]["objective_upper"] = 1
        self.assertIn("strategy_objective_observation", report.validate(changed))

    def test_html_is_projected_from_saved_record(self):
        page = report.render_html(self.record)
        self.assertIn("(0,s,1,s,1−s)", page)
        self.assertIn("Exact binary64 membership examples", page)
        self.assertIn(self.record["source_commit"], page)
        self.assertIn("Observed StrategyPort result", page)
        self.assertIn(self.record["scenario"]["sha256"], page)

    def test_publication_map_describes_exploratory_measurements(self):
        projection = publication_map.project(self.record)
        scope = projection["publication_contract"]["measured_scope"]
        self.assertIn("exploratory timings available", scope)
        self.assertIn("inconclusive", scope)
        self.assertNotIn("performance unavailable", scope)

    def test_bundle_builder_requires_measurement_input(self):
        with self.assertRaisesRegex(ValueError, "--measurement-dir is required"):
            build_bundle.build()

    def test_registered_adapter_checks_bundle_and_creates_offline_archive(self):
        publication = ts01_registered_reports.adapt(self.bundle)
        self.assertEqual(publication.source_commit, report.SOURCE_COMMIT)
        self.assertEqual(publication.source_report_id, self.record["report_id"])
        archive = ts01_registered_reports.offline_zip(self.bundle, publication)
        self.assertGreater(len(archive), 1000)


if __name__ == "__main__":
    unittest.main()
