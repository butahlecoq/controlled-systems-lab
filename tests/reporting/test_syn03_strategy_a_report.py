from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import hashlib
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts/reports"))
import report_data

TOOL=ROOT/"reports/algorithm-results/tooling/syn03/strategy_a_report.py"
spec=importlib.util.spec_from_file_location("csl_test_syn03_strategy_a_report",TOOL)
report=importlib.util.module_from_spec(spec);sys.modules[spec.name]=report;spec.loader.exec_module(report)
COLLECT_TOOL=ROOT/"reports/algorithm-results/tooling/syn03/strategy_a_collect.py"
sys.path.insert(0,str(COLLECT_TOOL.parent));sys.modules.pop("report",None)
collect_spec=importlib.util.spec_from_file_location("csl_test_syn03_strategy_a_collect",COLLECT_TOOL)
collect=importlib.util.module_from_spec(collect_spec);sys.modules[collect_spec.name]=collect;collect_spec.loader.exec_module(collect)
sys.modules.pop("report",None);sys.path.remove(str(COLLECT_TOOL.parent))
ADAPTER_TOOL=ROOT/"scripts/reports/syn03_strategy_a_registered_reports.py"
adapter_spec=importlib.util.spec_from_file_location("csl_test_syn03_strategy_a_publisher",ADAPTER_TOOL)
adapter=importlib.util.module_from_spec(adapter_spec);sys.modules[adapter_spec.name]=adapter;adapter_spec.loader.exec_module(adapter)

def scenario_fixture():
    return {"profile":"ts01_exact_integrator","time_domain":"discrete","times":[0,1,2],"initial_state":[0],"dynamics":[{"A":[[1]],"B":[[1]],"offset":[0]},{"A":[[1]],"B":[[1]],"offset":[0]}],"controls":[{"lower":[0],"upper":[1]},{"lower":[0],"upper":[1]}],"state_constraints":"universal at all stages","external_channels":0,"information":"nominal_open_loop","terminal_objective":{"Q":[[2]],"linear":[-2],"offset":1},"effective_request":{"target":"exact_optimal_relation","representation":"csl.polyhedron.h","assurance":"numerical","materialization_limit":None}}

ASSUMPTIONS=report.EXPECTED_ASSUMPTIONS
EVIDENCE_LIMITS=report.EXPECTED_EVIDENCE_LIMITS

def valid_record():
    times=[100,110,90,120,105,95,115]
    providers=["csl.conversion.qhull@1.0.0+qhull.8.0.2","csl.convex.highs@1.0.0+highs.1.11.0","csl.geometry.affine-sum@1.0.0","csl.geometry.polyhedral-projection@1.0.0","csl.hull.lp-membership@1.0.0","csl.lp.highs@1.0.0+highs.1.11.0"]
    base={"schema":report.EVENT_SCHEMA,"status":"passed","termination":"completed","outcome":"optimal","result_disposition":"complete_optimal_family","registry_verified":True,"assurance":"numerical","canonical_relation_checked":True,"completeness_verifier":"csl.verifier.ts01-analytic","completeness_verifier_version":"1","consumed_result_marker":1,"lp_provider":"csl.lp.highs@1.0.0+highs.1.11.0","convex_provider":"csl.convex.highs@1.0.0+highs.1.11.0","providers":providers,"lineage":report.EXPECTED_LINEAGE,"representative_coordinates":[0,0.25,1,0.25,0.75],"trajectory_objective":0,"trajectory_max_residual":0,"absolute_tolerance":1e-8,"relative_tolerance":1e-8,"residual_verifier":"syn03-strategy-a-independent-original-check/1","error":""}
    events=[{**base,"repetition":0,"warmup":True,"elapsed_ns":80}]
    events += [{**base,"repetition":i,"warmup":False,"elapsed_ns":value} for i,value in enumerate(times,1)]
    relation={"coordinates":["x0","x1","x2","u0","u1"],"inequalities":[[0,0,0,1,0],[0,0,0,-1,0],[0,0,0,0,1],[0,0,0,0,-1]],"inequality_rhs":[1,0,1,0],"equalities":[[1,0,0,0,0],[0,1,0,-1,0],[0,0,1,0,0],[0,0,0,1,1]],"equality_rhs":[0,0,1,1],"parametric_form":"(0,s,1,s,1-s), 0<=s<=1","objective_minimum":0}
    return {"schema":report.SCHEMA,"report_id":report.REPORT_ID,"source_commit":report.SOURCE_COMMIT,"harness_commit":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "algorithm":{"strategy_id":"csl.synthesis.reach-back","strategy_version":"1","profile_id":"ts01_exact_integrator","lp_provider":"csl.lp.highs@1.0.0+highs.1.11.0","convex_provider":"csl.convex.highs@1.0.0+highs.1.11.0","registered_providers":providers},
      "scenario":{"value":scenario_fixture(),"sha256":report.digest(scenario_fixture())},"assumptions":ASSUMPTIONS,"canonical_relation":relation,"evidence_limits":EVIDENCE_LIMITS,"measurement":{"scope":report.EXPECTED_SCOPE,"events":events,"timing_ns":{"observations":times,"median":105,"min":90,"max":120,"range":30},"counts":{"warmup":1,"measured":7,"passed":7,"failed":0,"all_outputs_consumed_and_validated":True},"result_observation":{"termination":"completed","outcome":"optimal","disposition":"complete_optimal_family","registry_verified":True,"assurance":"numerical","objective_lower":0,"objective_upper":0,"canonical_relation_checked_each_trial":True},"trajectory_checks":{"representative_coordinates":[[0,0.25,1,0.25,0.75]]*8,"original_objectives":[0]*8,"maximum_residuals":[0]*8,"equations_checked":["x0=0","x1=x0+u0","x2=x1+u1","0<=u0<=1","0<=u1<=1","J(x2)=(x2-1)^2=0"],"tolerances":{"absolute":1e-8,"relative":1e-8},"verifiers":["syn03-strategy-a-independent-original-check/1"]},"phase_counters":report.EXPECTED_PHASE_COUNTERS,"performance_conclusion":"inconclusive","limiter":report.EXPECTED_LIMITER}}

class StrategyAReportContractTests(unittest.TestCase):
    def test_report_identity_is_syn03_strategy_a(self):
        self.assertEqual(report.SCHEMA,"csl.syn03-strategy-a-ts01-report/1")
        self.assertTrue(report.REPORT_ID.startswith("syn03-strategy-a-ts01-"))
        self.assertTrue(report.EVENT_SCHEMA.startswith("csl.syn03-strategy-a-ts01-"))
        self.assertEqual(adapter.KIND,"syn03-strategy-a-ts01")
        identity={"schema":"csl.registered-publication-identity/1","source_report_id":report.REPORT_ID,"source_files":{"records.json":"a"*64},"publisher_sha256":"b"*64}
        report_id=adapter.public_report_id(identity)
        self.assertEqual(report_id,adapter.public_report_id(identity))
        self.assertTrue(report_id.startswith("syn03-strategy-a-ts01-"))
        self.assertNotIn("syn04-strategy-a",report_id)
        catalogue_row={"report_id":report_id,"report_kind":adapter.KIND,"source_report_id":report.REPORT_ID}
        self.assertEqual(catalogue_row["report_kind"],"syn03-strategy-a-ts01")
        self.assertNotIn("syn04-strategy-a",json.dumps(catalogue_row))

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
        record=valid_record();record["measurement"]["events"][1]["lineage"]=[]
        self.assertIn("event_invalid",report.validate(record))
        record=valid_record();record["measurement"]["events"][1]["providers"]=["csl.fake@9"]
        self.assertIn("event_invalid",report.validate(record))

    def test_rejects_changed_median(self):
        record=valid_record();record["measurement"]["timing_ns"]["median"]+=1
        self.assertIn("timing_summary",report.validate(record))

    def test_rejects_rehashed_mutated_t_s01_scenario(self):
        record=valid_record()
        record["scenario"]["value"]["dynamics"][0]["A"]=[[2]]
        record["scenario"]["value"]["controls"][0]["upper"]=None
        record["scenario"]["sha256"]=report.digest(record["scenario"]["value"])
        self.assertIn("scenario_contract",report.validate(record))
        with self.assertRaises(ValueError): report.render_html(record)

    def test_rejects_free_form_assumptions_and_evidence_claims(self):
        record=valid_record();record["assumptions"]= ["The result is globally validated for all systems."]
        self.assertIn("assumptions",report.validate(record))
        with self.assertRaises(ValueError): report.render_html(record)
        record=valid_record();record["evidence_limits"]= ["Global exact validation is proven."]
        self.assertIn("evidence_limits",report.validate(record))
        with self.assertRaises(ValueError): report.render_html(record)

    def test_nonzero_measurement_process_retains_emitted_failure_jsonl(self):
        failed_event={"schema":report.EVENT_SCHEMA,"repetition":1,"warmup":False,"status":"failed","elapsed_ns":42,"error":"deliberate fixture failure"}
        process=subprocess.run([sys.executable,"-c",f"import json,sys; print(json.dumps({failed_event!r},separators=(',',':'))); print('driver failed',file=sys.stderr); sys.exit(1)"],capture_output=True,check=False)
        self.assertEqual(process.returncode,1)
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/"failed-collection"
            events,error=collect.persist_measurement_process(output,process)
            self.assertIsNotNone(error)
            self.assertEqual(events,[failed_event])
            self.assertEqual((output/"events.jsonl").read_bytes(),process.stdout)
            self.assertEqual((output/"process-stderr.txt").read_bytes(),process.stderr)
            metadata=json.loads((output/"failed-run.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["process_return_code"],1)
            self.assertEqual(metadata["failed_event_count"],1)

    def test_html_describes_the_strategy_a_scope(self):
        self.assertIn("Strategy A on the T-S01 profile", report.render_html(valid_record()))

    def test_source_report_identity_has_repository_fallback_links(self):
        tree,archive,label=report_data.artifact_links(report.REPORT_ID)
        self.assertIn(report.REPORT_ID,tree);self.assertIn(report.REPORT_ID+".zip",archive)
        self.assertEqual(label,"current main")

if __name__=="__main__": unittest.main()
