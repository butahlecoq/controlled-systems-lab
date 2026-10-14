from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
TOOL=ROOT/"reports/algorithm-results/tooling/syn04/report.py"
spec=importlib.util.spec_from_file_location("csl_test_syn04_strategy_b_report",TOOL)
report=importlib.util.module_from_spec(spec);sys.modules[spec.name]=report;spec.loader.exec_module(report)
sys.path.insert(0,str(ROOT/"scripts/reports"))
import report_data

def valid_record():
    times=[100,110,90,120,105,95,115]
    base={"schema":report.EVENT_SCHEMA,"status":"passed","result_disposition":"complete_optimal_family","consumed_result_marker":1,"lp_provider":"csl.lp.highs@1.0.0+highs.1.11.0","convex_provider":"csl.convex.highs@1.0.0+highs.1.11.0","error":""}
    events=[{**base,"repetition":0,"warmup":True,"elapsed_ns":80}]
    events += [{**base,"repetition":i,"warmup":False,"elapsed_ns":value} for i,value in enumerate(times,1)]
    relation={"coordinates":["x0","x1","x2","u0","u1"],"inequalities":[[0,0,0,1,0],[0,0,0,-1,0],[0,0,0,0,1],[0,0,0,0,-1]],"inequality_rhs":[1,0,1,0],"equalities":[[1,0,0,0,0],[0,1,0,-1,0],[0,0,1,0,0],[0,0,0,1,1]],"equality_rhs":[0,0,1,1],"parametric_form":"(0,s,1,s,1-s), 0<=s<=1","objective_minimum":0}
    return {"schema":report.SCHEMA,"report_id":report.REPORT_ID,"source_commit":report.SOURCE_COMMIT,
      "algorithm":{"strategy_id":"csl.synthesis.strategy-b","strategy_version":"1","profile_id":"ts01_exact_integrator","lp_provider":"csl.lp.highs@1.0.0+highs.1.11.0","convex_provider":"csl.convex.highs@1.0.0+highs.1.11.0"},
      "scenario":{"value":{"profile":"ts01_exact_integrator"},"sha256":report.digest({"profile":"ts01_exact_integrator"})},"canonical_relation":relation,"evidence_limits":["inconclusive"],"measurement":{"scope":"exact canonical H-relation checked inside end-to-end interval","events":events,"timing_ns":{"observations":times,"median":105,"min":90,"max":120,"range":30},"counts":{"warmup":1,"measured":7,"passed":7,"failed":0,"all_outputs_consumed_and_validated":True},"result_observation":{"termination":"completed","outcome":"optimal","disposition":"complete_optimal_family","registry_verified":True,"assurance":"numerical","objective_lower":0,"objective_upper":0,"canonical_relation_checked_each_trial":True},"performance_conclusion":"inconclusive","limiter":{"reason":"No sampled call-stack source attribution is available."}}}

class StrategyBReportContractTests(unittest.TestCase):
    def test_accepts_only_complete_validated_trials_with_recomputed_summary(self):
        self.assertEqual(report.validate(valid_record()),[])

    def test_rejects_candidate_downgrade_even_when_timing_is_present(self):
        record=valid_record();record["measurement"]["events"][1]["result_disposition"]="candidate_relaxation"
        self.assertIn("event_invalid",report.validate(record))

    def test_rejects_changed_median(self):
        record=valid_record();record["measurement"]["timing_ns"]["median"]+=1
        self.assertIn("timing_summary",report.validate(record))

    def test_source_bundle_identity_has_repository_fallback_links(self):
        tree,archive,label=report_data.artifact_links(report.REPORT_ID)
        self.assertIn(report.REPORT_ID,tree);self.assertIn(report.REPORT_ID+".zip",archive)
        self.assertEqual(label,"current main")

if __name__=="__main__": unittest.main()
