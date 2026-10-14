from __future__ import annotations
import importlib.util, json, unittest, sys, zipfile, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
REPORT_PATH=ROOT/"reports/algorithm-results/tooling/syn03_ts02/report.py"

class StrategyATs02ReportTests(unittest.TestCase):
    def test_exact_profile_and_all_required_trial_checks(self):
        spec=importlib.util.spec_from_file_location("syn03_ts02_report",REPORT_PATH)
        report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)
        record=json.loads((ROOT/"reports/algorithm-results"/report.REPORT_ID/"records.json").read_text(encoding="utf-8"))
        self.assertEqual(report.validate(record),[])
        self.assertEqual(record["canonical_relation"]["objective_minimum"],3)
        self.assertEqual({(event["objective_lower"],event["objective_upper"]) for event in record["measurement"]["events"]},{(3,3)})
        for event in record["measurement"]["events"]:
            self.assertTrue(event["four_box_corners_checked"])
            self.assertTrue(event["distinct_histories_same_terminal_checked"])

    def test_standalone_html_identifies_analytical_path_and_scope(self):
        spec=importlib.util.spec_from_file_location("syn03_ts02_report",REPORT_PATH)
        report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)
        record=json.loads((ROOT/"reports/algorithm-results"/report.REPORT_ID/"records.json").read_text(encoding="utf-8"))
        page=report.render_html(record)
        self.assertIn("Strategy A",page)
        self.assertIn("registered highs lp provider",page.lower())
        self.assertIn("history relation analytically",page.lower())
        self.assertIn("speedup claim",page.lower())

    def test_event_identity_and_schema_three_offline_publication(self):
        spec=importlib.util.spec_from_file_location("syn03_ts02_report",REPORT_PATH)
        report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)
        bundle=ROOT/"reports/algorithm-results"/report.REPORT_ID
        record=json.loads((bundle/"records.json").read_text(encoding="utf-8"))
        mutated=json.loads(json.dumps(record));mutated["measurement"]["events"][2]["four_box_corners_checked"]=False
        self.assertIn("event_invalid",report.validate(mutated))
        sys.path.insert(0,str(ROOT/"scripts/reports"))
        import syn03_strategy_a_ts02_registered_reports as publisher
        item=publisher.adapt(bundle)
        self.assertEqual(item.kind,"syn03-strategy-a-ts02")
        page=publisher.render_page(bundle,item)
        self.assertIn("objective bounds [3,3]",page)
        with zipfile.ZipFile(ROOT/"reports/algorithm-results"/(item.report_id+".zip")) as archive:
            self.assertIn("index.html",archive.namelist())
            for name in archive.namelist():
                self.assertIsNone(re.search(rb"[A-Za-z]:[\\/](?!/)",archive.read(name)),name)

if __name__=="__main__": unittest.main()
