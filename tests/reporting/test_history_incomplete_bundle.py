"""Timed-out history attempts retain their raw request and outcome."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts/reports"))

class IncompleteBundleTest(unittest.TestCase):
    def test_timeout_preserves_request_and_never_claims_solver_outcome(self):
        from package_history_incomplete import package
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);attempt=root/"attempt";attempt.mkdir();output=root/"output";output.mkdir()
            request=json.dumps({"absolute_update_index":1,"original_horizon":2,"predictor_stages":[{}],"task_sha256":"hash","action_profile_id":"continuous", "controller_id":"controller", "observed_physical_state":[1]}).encode()+b"\n"
            (attempt/"request.jsonl").write_bytes(request)
            capture={"update_index":1,"bridge_request_sent":True,"response_parse_status":"not_received","response":None,"request_sha256":hashlib.sha256(request).hexdigest(),"request":{"path":"request.jsonl","sha256":hashlib.sha256(request).hexdigest()}}
            (attempt/"capture.json").write_text(json.dumps(capture))
            capture_sha=hashlib.sha256((attempt/"capture.json").read_bytes()).hexdigest()
            (attempt/"stage-001.json").write_text(json.dumps({"update_index":1,"status":"started","native_query_capture":{"path":"capture.json","sha256":capture_sha}}))
            episode={"attempt_id":"attempt","task_id":"task/continuous", "task_sha256":"hash", "source_sha256":"src", "action_profile_id":"continuous", "objective_id":"cost", "controller_id":"controller", "original_intervals":2, "completed_holds":1, "status":"incomplete", "algorithm_status":"incomplete", "postcheck_status":"not_run", "render_status":"not_run", "overall_status":"incomplete", "physical_objective":None, "controls":[[1]], "physical_states":[[0],[1]], "supervisor":{"status":"timed_out", "requested_wall_seconds":1800}, "preparation_receipt":{"adapter_receipt":{"executable_sha256":"native"}}}
            (attempt/"attempt.json").write_text(json.dumps(episode))
            (attempt/"run-manifest.json").write_text(json.dumps({"source_commit":"source", "task_sha256":"hash", "capability_manifest_sha256":"manifest", "bridge_sha256":"physical", "graph_id":"graph", "graph_fingerprint":"fingerprint"}))
            (attempt/"resolved-graph.json").write_text(json.dumps({"task_id":"task/continuous", "controller":{"id":"controller"}, "graph_id":"graph", "graph_fingerprint":"fingerprint", "action_profile_id":"continuous", "objective_id":"cost"}))
            audit=root/"audit.json";audit.write_text(json.dumps({"source_commit":"source","tasks":{"task":{"audit_status":"incomplete-or-failed","errors":[],"task_sha256":"hash","completed_holds":1,"expected_holds":2,"provider_ids":["csl.convex.highs"]}}}))
            build=root/"build.json";build.write_text(json.dumps({"source_commit":"source","artifacts":{"source_capsule":{"sha256":"capsule"},"native_policy":{"sha256":"native"},"physical_bridge":{"sha256":"physical"}}}))
            sdk=root/"sdk.json";sdk.write_text(json.dumps({"sdk_source_commit":"source","files":[]}))
            auditor=root/"auditor.py";auditor.write_text("# source\n")
            dest=package(attempt,output,"timeout",audit,build,sdk,auditor,"producer")
            receipt=json.loads((dest/"receipt.json").read_text())
            self.assertEqual(receipt["supervisor_status"],"timed_out")
            self.assertEqual(receipt["solver_outcome"],"not returned")
            with zipfile.ZipFile(dest/"raw.zip") as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(archive.read("request.jsonl"),request)
            episode["status"]="complete";(attempt/"attempt.json").write_text(json.dumps(episode))
            with self.assertRaisesRegex(ValueError,"incomplete"):
                package(attempt,output,"wrong",audit,build,sdk,auditor,"producer")

if __name__ == "__main__": unittest.main()
