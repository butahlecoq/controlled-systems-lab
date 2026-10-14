from __future__ import annotations
import copy, importlib.util, json, sys, unittest, tempfile, hashlib, shutil, re, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("syn04_ts02_contract", ROOT/"reports/algorithm-results/tooling/syn04_ts02/report.py")
report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)

class Ts02ReportTests(unittest.TestCase):
    def saved(self):
        return json.loads((ROOT/"reports/algorithm-results"/report.REPORT_ID/"records.json").read_text(encoding="utf-8"))
    def test_measured_exact_profile_and_distinct_histories(self):
        record=self.saved()
        self.assertEqual(report.validate(record),[])
        self.assertEqual(record["canonical_relation"]["objective_minimum"],3)
        self.assertEqual(record["canonical_relation"]["equality_rhs"],[0,0,0])
        for event in record["measurement"]["events"]:
            self.assertEqual((event["objective_lower"],event["objective_upper"]),(3,3))
            self.assertTrue(event["distinct_histories_same_terminal_checked"])
    def test_rejects_timing_of_unverified_or_incomplete_work(self):
        for key,value in [("registry_verified",False),("canonical_relation_checked",False),("distinct_histories_same_terminal_checked",False),("objective_upper",4)]:
            record=self.saved();record["measurement"]["events"][1][key]=value
            self.assertIn("event_invalid",report.validate(record))
    def test_rejects_rehashed_wrong_scenario_or_wrong_summary(self):
        record=self.saved();record["scenario"]["value"]["terminal_objective"]["offset"]=4
        record["scenario"]["sha256"]=report.digest(record["scenario"]["value"])
        self.assertIn("scenario_contract",report.validate(record))
        record=self.saved();record["measurement"]["timing_ns"]["median"]+=1
        self.assertIn("timing_summary",report.validate(record))
    def test_adapter_validates_saved_projections_and_schema_three_stage(self):
        sys.path.insert(0,str(ROOT/"scripts/reports"))
        import syn04_ts02_registered_reports as publisher
        bundle=ROOT/"reports/algorithm-results"/report.REPORT_ID
        for path in bundle.rglob("*"):
            if path.is_file():self.assertIsNone(re.search(rb"[A-Za-z]:[\\/](?!/)",path.read_bytes()),path.name)
        self.assertEqual(self.saved()["build"]["sanitization"]["schema"],"csl.report-public-provenance/1")
        item=publisher.adapt(bundle)
        self.assertEqual(item.kind,"syn04-strategy-b-ts02")
        page=publisher.render_page(ROOT/"reports/algorithm-results"/report.REPORT_ID,item)
        self.assertIn("objective bounds [3,3]",page)
        self.assertIn("Performance conclusion: inconclusive",page)

    def test_complete_catalogue_stages_exact_offline_archive(self):
        sys.path.insert(0,str(ROOT/"scripts/reports"))
        import syn04_ts02_registered_reports as publisher
        spec=importlib.util.spec_from_file_location("ts02_site",ROOT/"scripts/reports/site.py")
        site=importlib.util.module_from_spec(spec);spec.loader.exec_module(site)
        item=publisher.adapt(ROOT/"reports/algorithm-results"/report.REPORT_ID)
        with tempfile.TemporaryDirectory() as temporary:
            output=site.stage(ROOT/"reports/algorithm-results/catalog.json",Path(temporary)/"site",check=True)
            self.assertEqual((output/(item.report_id+".zip")).read_bytes(),(ROOT/"reports/algorithm-results"/(item.report_id+".zip")).read_bytes())
            self.assertIn("objective bounds [3,3]",(output/item.report_id/"index.html").read_text(encoding="utf-8"))
            with zipfile.ZipFile(output/(item.report_id+".zip")) as archive:
                for name in archive.namelist():self.assertIsNone(re.search(rb"[A-Za-z]:[\\/](?!/)",archive.read(name)),name)
    def test_rehashed_csv_corruption_still_rejects(self):
        sys.path.insert(0,str(ROOT/"scripts/reports"))
        import syn04_ts02_registered_reports as publisher
        bundle=ROOT/"reports/algorithm-results"/report.REPORT_ID
        with tempfile.TemporaryDirectory() as temporary:
            copy=Path(temporary)/bundle.name;shutil.copytree(bundle,copy)
            csv=copy/"trials.csv";csv.write_bytes(csv.read_bytes().replace(b"74200",b"74201"))
            manifest=json.loads((copy/"manifest.json").read_text(encoding="utf-8"));manifest["files"]["trials.csv"]=hashlib.sha256(csv.read_bytes()).hexdigest()
            (copy/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"CSV differs"):publisher.adapt(copy)

if __name__=="__main__":unittest.main()
