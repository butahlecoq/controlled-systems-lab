"""Saved-record oracle and report-rendering tests for SYN-02."""
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import collect
import render_saved
import publication_map

def event(name, *, outcome="optimal", relation=True, value=0.0, equalities=None, rhs=None):
    spec=collect.SCENARIOS[name]
    return {"schema":"csl.syn02-terminal-trial/1","scenario":name,"status":"passed",
            "outcome":outcome,"termination":spec["termination"],"expected_termination":spec["termination"],"expected_provider":spec["provider"],"relation":relation,
            "optimization_present":True,"optimum_present":True,"provider":spec["provider"],
            "relation_support":"unestablished","optimum_support":"unestablished","raw_diagnostics":"solver state retained" if outcome=="undetermined" else "",
            "solver_observations":({"native.primal_infeasibility":0,"native.dual_infeasibility":0} if spec["provider"]=="csl.lp.highs" else {"check.rows.violation":0,"check.variables.violation":0,"check.stationarity.violation":0}),
            "primal_value":value,"diagnostic":"degeneracy evidence retained" if outcome=="undetermined" else "",
            "inequalities":[[1,0],[-1,0],[0,1],[0,-1]],"upper_bounds":[1,0,1,0],
            "equalities":equalities or [[1,0]],"equality_values":rhs or [0.0]}

class SavedOracleTests(unittest.TestCase):
    def test_linear_face_checks_literal_included_and_excluded_points(self):
        row=event("linear-face",value=7)
        self.assertEqual([],collect.validate_trial(row))

    def test_full_box_relation_retains_every_box_corner_and_interior(self):
        row=event("constant-linear",value=3,equalities=[])
        # A zero row denotes the constant-objective level and does not cut down the box.
        row["equalities"]=[[0,0]];row["equality_values"]=[0]
        self.assertEqual([],collect.validate_trial(row))

    def test_shifted_degenerate_outcome_is_kept_without_relation(self):
        row=event("shifted-residual-degenerate",outcome="undetermined",relation=False,value=None,equalities=[],rhs=[])
        row["solver_observations"].update({"phase.qp.model_status":7,"optimality.withheld":"original-space checks unavailable or failing","check.stationarity.violation":1})
        self.assertEqual([],collect.validate_trial(row))

    def test_wrong_literal_value_or_relation_is_rejected(self):
        row=event("rectangular-residual",value=0)
        row["equality_values"]=[1]
        self.assertIn("literal_relation_sample",collect.validate_trial(row))

    def test_report_html_is_standalone_and_names_evidence_limits(self):
        timing={key:{"median_ns":1000,"min_ns":900,"max_ns":1200} for key in ("prepare_ns","solve_ns","oracle_ns","execute_ns")}
        summary=[{"scenario":name,"matched_expected":7,"completed":0 if spec["termination"]!="completed" else 7,"requested":7,"failed":0,"non_success":7 if spec["termination"]!="completed" else 0,
                  "expected_outcome":spec["outcome"],"expected_termination":spec["termination"],"observed_outcomes":{spec["outcome"]:7},"observed_terminations":{spec["termination"]:7},"observed_providers":{spec["provider"]:7},"relation_count":0 if spec["outcome"]=="undetermined" else 7,"objective_bounds":{"lower_available":0,"upper_available":0},"primal_objective_value":{"min":0.5,"max":0.5,"count":7},"residual_observations":{"check.rows.violation":{"max":0.0,"count":7}},"timings":timing}
                 for name,spec in collect.SCENARIOS.items()]
        payload={"report_id":"syn02-test","harness_commit":"0"*40,
                 "provenance":{"compiler":"test compiler"},
                 "environment":{"os":"test OS","processor":"test CPU"},
                 "summary":summary,"profile_summary":"Limiter unknown"}
        page=collect.render_html(payload)
        self.assertIn("<svg",page)
        self.assertIn("Unestablished",page)
        self.assertIn("no competitor",page.lower())
        self.assertNotIn("<script src=",page)

    def test_saved_renderer_uses_records_without_solver(self):
        timing={key:{"median_ns":1000,"min_ns":900,"max_ns":1200} for key in ("prepare_ns","solve_ns","oracle_ns","execute_ns")}
        summary=[{"scenario":name,"matched_expected":7,"completed":0 if spec["termination"]!="completed" else 7,"requested":7,"failed":0,"non_success":7 if spec["termination"]!="completed" else 0,
                  "expected_outcome":spec["outcome"],"expected_termination":spec["termination"],"observed_outcomes":{spec["outcome"]:7},"observed_terminations":{spec["termination"]:7},"observed_providers":{spec["provider"]:7},"relation_count":0 if spec["outcome"]=="undetermined" else 7,"objective_bounds":{"lower_available":0,"upper_available":0},"primal_objective_value":{"min":0.5,"max":0.5,"count":7},"residual_observations":{"check.rows.violation":{"max":0.0,"count":7}},"timings":timing}
                 for name,spec in collect.SCENARIOS.items()]
        payload={"schema":"csl.syn02-terminal-report/1","report_id":"saved-record-test","harness_commit":"0"*40,
                 "provenance":{"compiler":"test compiler"},"environment":{"os":"test OS","processor":"test CPU"},
                 "summary":summary,"profile_summary":"Limiter unknown"}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);records=root/"records.json";out=root/"rendered"
            records.write_text(json.dumps(payload),encoding="utf-8")
            render_saved.render(records,out)
            self.assertIn("SYN-02",(out/"index.html").read_text(encoding="utf-8"))
            self.assertIn("<svg",(out/"latency.svg").read_text(encoding="utf-8"))

    def test_native_record_has_explicit_shared_publication_mapping(self):
        record={"schema":"csl.syn02-terminal-report/1","report_id":"syn02-example","source_commit":"c"*40,
                "measurement":{"scope":"terminal optimizer"},"evidence_limits":["binary64 only"]}
        mapping=publication_map.project(record)
        self.assertEqual("csl.algorithm-report-catalog/3",mapping["publication_contract"]["catalogue_schema"])
        self.assertEqual("csl.algorithm-report-envelope/1",mapping["publication_contract"]["envelope_schema"])
        self.assertEqual("syn02-example",mapping["source_report_id"])
        self.assertEqual(64,len(mapping["native_payload_sha256"]))
        self.assertEqual({"schema","report_id","report_kind","payload_schema","payload_sha256","source_commit","measured_scope","evidence_limits","payload","source_report_id"},set(mapping["envelope_fields"]))
        self.assertEqual("scripts/reports/syn02_registered_reports.py",mapping["publisher_registration"]["adapter_module"])
        self.assertFalse(mapping["publisher_registration"]["publishable_now"])

    def test_profile_summary_reports_incomplete_final_status(self):
        profile={"status":"process_counter_sampling_incomplete","incomplete_reason":"missing events"}
        summary=collect.profile_summary_for(profile)
        self.assertIn("incomplete",summary)
        self.assertIn("missing events",summary)
        self.assertIn("unknown",summary)

    def test_profile_summary_reports_completed_counter_run(self):
        summary=collect.profile_summary_for({"status":"process_counter_sampling_completed"})
        self.assertIn("completed",summary)
        self.assertIn("no call-stack attribution",summary)
        self.assertIn("unknown",summary)

    def test_failed_collection_persists_stage_and_partial_streams(self):
        class Args: pass
        with tempfile.TemporaryDirectory() as directory:
            args=Args();args.out_root=Path(directory);args.harness_commit="d"*40;args.command=["fake-driver"]
            state={"stage":"measurement","measurement_trials_started":True,"driver_stdout":b'{"partial":true}\n',"build_log":b"release build log"}
            error=TimeoutError("driver exceeded timeout")
            path=collect.persist_failure(args,state,error)
            details=json.loads((path/"failure.json").read_text(encoding="utf-8"))
            self.assertEqual("measurement",details["stage"])
            self.assertTrue(details["measurement_trials_started"])
            self.assertFalse(details["accepted_measurement"])
            self.assertEqual(b'{"partial":true}\n',(path/"driver-stdout.jsonl").read_bytes())
            self.assertEqual(b"release build log",(path/"build-log.txt").read_bytes())
            self.assertIn("driver-stdout.jsonl",details["evidence_files"])

    def test_collector_preflight_failure_creates_nonpublishable_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            argv=["collect.py","--cmake",str(root/"cmake.exe"),"--build-dir",str(root/"build"),
                  "--out-root",str(root/"results"),"--harness-commit","e"*40,"--repetitions","1"]
            with patch.object(sys,"argv",argv), self.assertRaises(ValueError):
                collect.main()
            attempts=list((root/"results"/"collection-failures").iterdir())
            self.assertEqual(1,len(attempts))
            details=json.loads((attempts[0]/"failure.json").read_text(encoding="utf-8"))
            self.assertEqual("csl.syn02-collection-failure/1",details["schema"])
            self.assertEqual("preflight",details["stage"])
            self.assertFalse(details["measurement_trials_started"])
            self.assertFalse(details["accepted_measurement"])
            self.assertFalse((root/"results"/details["attempt_id"]/"records.json").exists())

if __name__=="__main__": unittest.main()
