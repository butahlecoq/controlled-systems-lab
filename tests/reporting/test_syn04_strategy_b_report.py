from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import hashlib
import unittest

ROOT=Path(__file__).resolve().parents[2]
TOOL=ROOT/"reports/algorithm-results/tooling/syn04/report.py"
spec=importlib.util.spec_from_file_location("csl_test_syn04_strategy_b_report",TOOL)
report=importlib.util.module_from_spec(spec);sys.modules[spec.name]=report;spec.loader.exec_module(report)
sys.path.insert(0,str(ROOT/"scripts/reports"))
import report_data
import syn04_strategy_b_registered_reports as publication
site_spec=importlib.util.spec_from_file_location("csl_test_syn04_report_site",ROOT/"scripts/reports/site.py")
report_site=importlib.util.module_from_spec(site_spec);sys.modules[site_spec.name]=report_site;site_spec.loader.exec_module(report_site)

def valid_record():
    times=[100,110,90,120,105,95,115]
    base={"schema":report.EVENT_SCHEMA,"status":"passed","termination":"completed","outcome":"optimal","result_disposition":"complete_optimal_family","registry_verified":True,"assurance":"numerical","canonical_relation_checked":True,"completeness_verifier":"csl.verifier.ts01-analytic","completeness_verifier_version":"1","consumed_result_marker":1,"lp_provider":"csl.lp.highs@1.0.0+highs.1.11.0","convex_provider":"csl.convex.highs@1.0.0+highs.1.11.0","trajectory_objective":0,"trajectory_max_residual":0,"absolute_tolerance":1e-8,"relative_tolerance":1e-8,"residual_verifier":"csl.trajectory.original","error":""}
    events=[{**base,"repetition":0,"warmup":True,"elapsed_ns":80}]
    events += [{**base,"repetition":i,"warmup":False,"elapsed_ns":value} for i,value in enumerate(times,1)]
    relation={"coordinates":["x0","x1","x2","u0","u1"],"inequalities":[[0,0,0,1,0],[0,0,0,-1,0],[0,0,0,0,1],[0,0,0,0,-1]],"inequality_rhs":[1,0,1,0],"equalities":[[1,0,0,0,0],[0,1,0,-1,0],[0,0,1,0,0],[0,0,0,1,1]],"equality_rhs":[0,0,1,1],"parametric_form":"(0,s,1,s,1-s), 0<=s<=1","objective_minimum":0}
    return {"schema":report.SCHEMA,"report_id":report.REPORT_ID,"source_commit":report.SOURCE_COMMIT,
      "algorithm":{"strategy_id":"csl.synthesis.strategy-b","strategy_version":"1","profile_id":"ts01_exact_integrator","lp_provider":"csl.lp.highs@1.0.0+highs.1.11.0","convex_provider":"csl.convex.highs@1.0.0+highs.1.11.0"},
      "scenario":{"value":{"profile":"ts01_exact_integrator"},"sha256":report.digest({"profile":"ts01_exact_integrator"})},"canonical_relation":relation,"evidence_limits":["inconclusive"],"measurement":{"scope":"exact canonical H-relation checked inside end-to-end interval","events":events,"timing_ns":{"observations":times,"median":105,"min":90,"max":120,"range":30},"counts":{"warmup":1,"measured":7,"passed":7,"failed":0,"all_outputs_consumed_and_validated":True},"result_observation":{"termination":"completed","outcome":"optimal","disposition":"complete_optimal_family","registry_verified":True,"assurance":"numerical","objective_lower":0,"objective_upper":0,"canonical_relation_checked_each_trial":True},"trajectory_checks":{"original_objectives":[0]*8,"maximum_residuals":[0]*8,"tolerances":{"absolute":1e-8,"relative":1e-8},"verifiers":["csl.trajectory.original"]},"performance_conclusion":"inconclusive","limiter":{"reason":"No sampled call-stack source attribution is available."}}}

class StrategyBReportContractTests(unittest.TestCase):
    def test_accepts_only_complete_validated_trials_with_recomputed_summary(self):
        self.assertEqual(report.validate(valid_record()),[])

    def test_rejects_candidate_downgrade_even_when_timing_is_present(self):
        record=valid_record();record["measurement"]["events"][1]["result_disposition"]="candidate_relaxation"
        self.assertIn("event_invalid",report.validate(record))

    def test_rejects_unverified_or_unchecked_complete_family(self):
        record=valid_record();record["measurement"]["events"][1]["registry_verified"]=False
        self.assertIn("event_invalid",report.validate(record))
        record=valid_record();record["measurement"]["events"][1]["canonical_relation_checked"]=False
        self.assertIn("event_invalid",report.validate(record))

    def test_rejects_changed_median(self):
        record=valid_record();record["measurement"]["timing_ns"]["median"]+=1
        self.assertIn("timing_summary",report.validate(record))

    def test_source_bundle_identity_has_repository_fallback_links(self):
        tree,archive,label=report_data.artifact_links(report.REPORT_ID)
        self.assertIn(report.REPORT_ID,tree);self.assertIn(report.REPORT_ID+".zip",archive)
        self.assertEqual(label,"current main")

    def test_measured_bundle_passes_registered_adapter_and_projection(self):
        bundle=ROOT/"reports/algorithm-results"/report.REPORT_ID
        item=publication.adapt(bundle)
        self.assertEqual(item.kind,"syn04-strategy-b-ts01")
        self.assertEqual(item.source_commit,report.SOURCE_COMMIT)
        page=publication.render_page(bundle,item)
        self.assertIn("complete_optimal_family",page)
        self.assertIn("Performance conclusion: inconclusive",page)

    def test_schema_three_site_stages_and_hashes_the_offline_zip(self):
        catalog=ROOT/"reports/algorithm-results/catalog.json"
        public_id=publication.adapt(ROOT/"reports/algorithm-results"/report.REPORT_ID).report_id
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/"site"
            report_site.stage(catalog,output,check=True)
            staged=output/(public_id+".zip")
            committed=ROOT/"reports/algorithm-results"/(public_id+".zip")
            self.assertTrue(staged.is_file())
            self.assertEqual(hashlib.sha256(staged.read_bytes()).digest(),hashlib.sha256(committed.read_bytes()).digest())

if __name__=="__main__": unittest.main()
