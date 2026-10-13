"""Saved-record oracle and report-rendering tests for SYN-02."""
import json
import tempfile
import unittest
from pathlib import Path
import collect
import render_saved

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
        timing={key:{"median_ns":1000,"min_ns":900,"max_ns":1200} for key in ("prepare_ns","solve_ns","oracle_ns","total_ns")}
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
        timing={key:{"median_ns":1000,"min_ns":900,"max_ns":1200} for key in ("prepare_ns","solve_ns","oracle_ns","total_ns")}
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

if __name__=="__main__": unittest.main()
