import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import b04_historical_report as report


class B04HistoricalReportTests(unittest.TestCase):
    def setUp(self):
        self.manifest = ROOT / "benchmarks/scenarios/b04-historical.json"
        self.consistency = ROOT / "docs/research/b04-consistency.json"
        self.register = ROOT / "docs/research/archive-selected-sources.json"
        self.audit = json.loads(self.consistency.read_text())
        self.value = report.build(self.manifest, self.consistency, self.register)

    def test_keeps_historical_report_calculation_and_reproduction_separate(self):
        self.assertEqual(self.value["schema"], "csl.b04-historical-report/1")
        self.assertEqual(self.value["track"], "historical-only")
        self.assertEqual(self.value["scenario_id"], "B04-historical")
        rows = self.value["reported_table"]["rows"]
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[-1]["reported_objective"]["value"], "30.899")
        self.assertEqual(rows[-1]["printed_coordinate_evaluation"]["objective_norm"],
                         self.audit["displayed_table_evaluations"][-1]["objective_at_printed_coordinates"])
        self.assertNotEqual(rows[-1]["reported_objective"]["value"],
                            rows[-1]["printed_coordinate_evaluation"]["objective_norm"])
        self.assertEqual(self.value["runtime"]["historical_reported_seconds"], "0.4")
        self.assertEqual(self.value["runtime"]["current_measurement"]["status"], "unavailable")
        self.assertEqual(self.value["reproduction"]["status"], "unavailable")
        self.assertEqual(self.value["restoration"]["stock_invariant"]["gap_exact"], "1716499/1000")
        self.assertIn("not the historical constrained optimum",
                      self.value["restoration"]["unrestricted_terminal_plane_minimum"]["scope"])
        hypothesis = self.value["restoration"]["excluded_control_interval_hypothesis"]
        self.assertEqual(hypothesis["status"], "adaptive_demonstration_only_not_confirmed_B04_data")
        self.assertEqual(hypothesis["owner_control_interval_recollection"]["status"], "provisional_owner_recollection")

    def test_preserves_decimal_lexemes_precision_and_source_hashes(self):
        rows = self.value["reported_table"]["rows"]
        regulator = rows[1]
        self.assertEqual(regulator["terminal_state"][0]["value"], "1190.4")
        self.assertEqual(regulator["terminal_state"][0]["fractional_digits"], 1)
        self.assertEqual(regulator["terminal_state"][0]["radius_exact"], "1/20")
        witness_two = rows[3]
        self.assertEqual(witness_two["terminal_state"][1]["value"], "0.50887")
        self.assertEqual(witness_two["terminal_state"][1]["fractional_digits"], 5)
        self.assertEqual(witness_two["terminal_state"][1]["radius_exact"], "1/200000")
        sources = {item["id"]: item for item in self.value["source_citations"]}
        manifest = json.loads(self.manifest.read_text())
        self.assertEqual(sources["A11"]["sha256"], "45d6d82e0447a3a1b988753b618097c20f9be56c30d2c2022789b8893a4f9de1")
        self.assertEqual(sources["A12"]["page"], 20)
        self.assertEqual(sources["A14"]["sha256"], manifest["sources"][0]["sha256"])
        for key in ("manifest_sha256", "consistency_audit_sha256", "archive_register_sha256"):
            self.assertEqual(len(self.value[key]), 64)
            self.assertTrue(all(char in "0123456789abcdef" for char in self.value[key]))

    def test_rejects_audit_from_different_manifest_or_changed_printed_row(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            manifest = tmp / "manifest.json"
            consistency = tmp / "consistency.json"
            register = tmp / "register.json"
            shutil.copyfile(self.manifest, manifest)
            shutil.copyfile(self.consistency, consistency)
            shutil.copyfile(self.register, register)
            text = manifest.read_text()
            manifest.write_text(text.replace('"id": "B04-historical"', '"id": "B04-other"', 1))
            with self.assertRaisesRegex(ValueError, "non-executable, incomplete B04 historical gate"):
                report.build(manifest, consistency, register)

            shutil.copyfile(self.manifest, manifest)
            manifest.write_text(manifest.read_text().replace("0.50887", "0.50888", 1))
            with self.assertRaisesRegex(ValueError, "manifest and unresolved status"):
                report.build(manifest, consistency, register)

    def test_rejects_corrupt_source_registration_and_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            register = json.loads(self.register.read_text())
            next(item for item in register["selected_sources"] if item["id"] == "A11")["sha256"] = "bad"
            register_path = tmp / "register.json"
            register_path.write_text(json.dumps(register))
            with self.assertRaisesRegex(ValueError, "invalid SHA-256"):
                report.build(self.manifest, self.consistency, register_path)

            duplicate_path = tmp / "duplicate.json"
            duplicate_path.write_text('{"schema_version":1,"schema_version":1}')
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                report._load(duplicate_path)

    def test_export_is_deterministic_and_has_an_accessible_static_table(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            report.write_report(self.value, output)
            json_bytes = (output / "b04-historical-comparison.json").read_bytes()
            html_bytes = (output / "b04-historical-comparison.html").read_bytes()
            report.write_report(report.build(self.manifest, self.consistency, self.register), output)
            self.assertEqual((output / "b04-historical-comparison.json").read_bytes(), json_bytes)
            self.assertEqual((output / "b04-historical-comparison.html").read_bytes(), html_bytes)
            page = html_bytes.decode()
            self.assertIn("Historical-only record", page)
            self.assertIn("Computed at printed coordinates", page)
            self.assertIn("Current measurement: unavailable", page)
            self.assertIn("not a constrained optimum", page)
            self.assertIn("provisional", page)
            markdown = (output / "b04-historical-comparison.md").read_text()
            self.assertIn("| Policy | Printed terminal state", markdown)
            self.assertIn("Historical-only record", markdown)
            self.assertIn("Current measured runtime: unavailable", markdown)

    def test_checked_in_report_matches_the_reproducible_generator(self):
        expected = ROOT / "docs/research"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report.write_report(self.value, output)
            for name in ("b04-historical-comparison.json", "b04-historical-comparison.html",
                         "b04-historical-comparison.md"):
                self.assertEqual((output / name).read_bytes(), (expected / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
