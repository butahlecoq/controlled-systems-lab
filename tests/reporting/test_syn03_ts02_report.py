from __future__ import annotations
import importlib.util, json, unittest, sys, zipfile, re, tempfile, csv
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

    def test_saved_events_do_not_claim_unperformed_trajectory_residual_check(self):
        spec=importlib.util.spec_from_file_location("syn03_ts02_report",REPORT_PATH)
        report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)
        bundle=ROOT/"reports/algorithm-results"/report.REPORT_ID
        record=json.loads((bundle/"records.json").read_text(encoding="utf-8"))
        forbidden={"representative_coordinates","trajectory_objective","trajectory_max_residual","absolute_tolerance","relative_tolerance","residual_verifier"}
        injected=json.loads(json.dumps(record));injected["measurement"]["events"][0]["trajectory_max_residual"]=0
        self.assertIn("event_invalid",report.validate(injected))
        self.assertTrue(all(not forbidden.intersection(event) for event in record["measurement"]["events"]))
        self.assertFalse(forbidden.intersection(record["environment"]))
        raw=[json.loads(line) for line in (bundle/"measurement-events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(raw,record["measurement"]["events"])
        profile=[json.loads(line) for line in (bundle/"separate-profile-events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(all(not forbidden.intersection(event) for event in profile))

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
        forbidden=(b"representative_coordinates",b"trajectory_objective",b"trajectory_max_residual",b"absolute_tolerance",b"relative_tolerance",b"residual_verifier",b"syn03-strategy-a-independent-original-check/1")
        self.assertFalse(any(token in page.lower().encode() for token in forbidden))
        with (bundle/"trials.csv").open(encoding="utf-8",newline="") as stream:
            rows=list(csv.DictReader(stream))
        self.assertTrue(rows)
        self.assertFalse(set(key.encode() for key in rows[0]) & set(forbidden))
        sys.path.insert(0,str(ROOT/"scripts/reports"))
        site_spec=importlib.util.spec_from_file_location("csl_syn03_ts02_test_site",ROOT/"scripts/reports/site.py")
        site=importlib.util.module_from_spec(site_spec);site_spec.loader.exec_module(site)
        with tempfile.TemporaryDirectory() as temporary:
            staged=site.stage(ROOT/"reports/algorithm-results/catalog.json",Path(temporary)/"site",check=True)
            published=staged/item.report_id
            envelope=json.loads((published/"report-envelope.json").read_text(encoding="utf-8"))
            self.assertEqual(envelope["payload"]["measurement"]["events"],record["measurement"]["events"])
            text_files=[p for p in published.rglob("*") if p.is_file()]
            self.assertTrue(any(p.name=="trials.csv" for p in text_files))
            for path in text_files:
                content=path.read_bytes().lower()
                self.assertFalse(any(token in content for token in forbidden),path.name)
            zip_path=staged/(item.report_id+".zip")
            with zipfile.ZipFile(zip_path) as archive:
                self.assertIn("index.html",archive.namelist())
                for name in archive.namelist():
                    content=archive.read(name).lower()
                    self.assertFalse(any(token in content for token in forbidden),name)
                    self.assertIsNone(re.search(rb"[A-Za-z]:[\\/](?!/)",content),name)

if __name__=="__main__": unittest.main()
