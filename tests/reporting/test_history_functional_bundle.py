"""Functional-history evidence is archived exactly and only after completion."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))


class HistoryBundleTest(unittest.TestCase):
    def test_source_edit_disclosure_belongs_only_to_the_recorded_historical_attempt(self):
        from package_feedback_history import postcheck_source_timing
        historical_source = "a800b95b9be6a874c0bab188d1cf3394fbb836b1"
        historical_attempt = "syn-nl-fuel-01-20261112T113606Z-6e1a2885"
        self.assertIn("were edited", postcheck_source_timing(historical_source, historical_attempt))
        self.assertIsNone(postcheck_source_timing(historical_source, "another-fuel-attempt"))
        self.assertIsNone(postcheck_source_timing(
            "a4889d4727cf5ba0bc2dbf64c8c39b7792a18ae5", historical_attempt))

    def test_archive_preserves_every_original_byte_and_refuses_incomplete_attempt(self):
        from package_history_functional import package
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); attempt=root/"attempt"; attempt.mkdir(); output=root/"output"; output.mkdir()
            def write(name,value): (attempt/name).write_text(json.dumps(value))
            objective={"terminal":1,"running":2,"total":3}
            write("attempt.json", {"attempt_id":"attempt", "task_id":"task", "task_sha256":"hash", "source_sha256":"src",
                "action_profile_id":"continuous", "objective_id":"cost", "controller_id":"controller",
                "original_intervals":1,"completed_holds":1,"status":"complete", "overall_status":"complete",
                "algorithm_status":"complete", "postcheck_status":"complete", "render_status":"complete",
                "physical_objective":objective, "independent_replay":{"common":{"status":"complete"},"tight":{"status":"complete"}},
                "preparation_receipt":{"adapter_receipt":{"executable_sha256":"native"}}})
            write("run-manifest.json", {"source_commit":"source", "task_sha256":"hash", "capability_manifest_sha256":"manifest", "bridge_sha256":"physical", "graph_id":"graph", "graph_fingerprint":"fingerprint"})
            write("resolved-graph.json", {"graph_id":"graph", "graph_fingerprint":"fingerprint", "task_id":"task", "controller":{"id":"controller"}, "action_profile_id":"continuous", "objective_id":"cost"})
            (attempt/"raw.bin").write_bytes(b"\x00raw\xff")
            (attempt/"stage-000.json").write_bytes(b"stage")
            for name in ("trajectory.png","controls.png","phase.png"): (attempt/name).write_bytes(name.encode())
            audit=root/"audit.json"; audit.write_text(json.dumps({"source_commit":"source","tasks":{"task":{"audit_status":"pass","task_sha256":"hash","completed_holds":1,"expected_holds":1,"provider_ids":["casadi-ipopt"],"applied_original_objective":objective}}}))
            build=root/"build.json"; build.write_text(json.dumps({"source_commit":"source","artifacts":{"source_capsule":{"sha256":"capsule"},"native_policy":{"sha256":"native"},"physical_bridge":{"sha256":"physical"}}}))
            sdk=root/"sdk.json"; sdk.write_text(json.dumps({"sdk_source_commit":"source","files":[]}))
            auditor=root/"auditor.py"; auditor.write_text("# original audit source\n")
            rendered=root/"rendered";rendered.mkdir()
            for name in ("trajectory.png","controls.png","phase.png"): (rendered/name).write_bytes(("corrected-"+name).encode())
            (rendered/"render-receipt.json").write_text(json.dumps({"producer_commit":"producer", "attempt_sha256":hashlib.sha256((attempt/"attempt.json").read_bytes()).hexdigest(), "task_sha256":"hash", "controller_id":"controller", "actual_provider":"casadi-ipopt", "stage_sources":[{"path":"stage-000.json","sha256":hashlib.sha256(b"stage").hexdigest()}], "plots":{name:hashlib.sha256((rendered/name).read_bytes()).hexdigest() for name in ("trajectory.png","controls.png","phase.png")}, "correction":"corrected label", "renderer_source_sha256":hashlib.sha256((ROOT/"benchmarks/reporting/closed_loop/run_closed_loop.py").read_bytes()).hexdigest(), "generator_source_sha256":hashlib.sha256((ROOT/"scripts/reports/render_history_functional.py").read_bytes()).hexdigest()}))
            dest=package(attempt,output,"case",audit,build,sdk,auditor,"producer",rendered)
            manifest=json.loads((dest/"receipt.json").read_text())
            with zipfile.ZipFile(dest/"raw.zip") as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()),set(manifest["archive_members"]))
                self.assertEqual(archive.read("raw.bin"),b"\x00raw\xff")
                self.assertEqual(hashlib.sha256(archive.read("raw.bin")).hexdigest(),manifest["archive_members"]["raw.bin"]["sha256"])
            self.assertEqual((dest/"trajectory.png").read_bytes(),(rendered/"trajectory.png").read_bytes())
            with zipfile.ZipFile(dest/"raw.zip") as archive:
                self.assertEqual(archive.read("trajectory.png"),(attempt/"trajectory.png").read_bytes())
            value=json.loads((attempt/"attempt.json").read_text());value["overall_status"]="incomplete";write("attempt.json",value)
            with self.assertRaisesRegex(ValueError,"complete"):
                package(attempt,output,"incomplete",audit,build,sdk,auditor,"producer",rendered)
            self.assertFalse((output/"incomplete").exists())
            value["overall_status"]="complete";write("attempt.json",value)
            (attempt/"link").symlink_to(attempt/"raw.bin")
            with self.assertRaisesRegex(ValueError,"symlinks"):
                package(attempt,output,"symlink",audit,build,sdk,auditor,"producer",rendered)
            self.assertFalse((output/"symlink").exists())


if __name__ == "__main__": unittest.main()
