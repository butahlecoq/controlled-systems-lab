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
            for name in ("trajectory.png","controls.png","phase.png"): (attempt/name).write_bytes(name.encode())
            audit=root/"audit.json"; audit.write_text(json.dumps({"source_commit":"source","tasks":{"task":{"audit_status":"pass","task_sha256":"hash","completed_holds":1,"expected_holds":1,"applied_original_objective":objective}}}))
            build=root/"build.json"; build.write_text(json.dumps({"source_commit":"source","artifacts":{"source_capsule":{"sha256":"capsule"},"native_policy":{"sha256":"native"},"physical_bridge":{"sha256":"physical"}}}))
            sdk=root/"sdk.json"; sdk.write_text(json.dumps({"sdk_source_commit":"source","files":[]}))
            auditor=root/"auditor.py"; auditor.write_text("# original audit source\n")
            dest=package(attempt,output,"case",audit,build,sdk,auditor,"producer")
            manifest=json.loads((dest/"receipt.json").read_text())
            with zipfile.ZipFile(dest/"raw.zip") as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()),set(manifest["archive_members"]))
                self.assertEqual(archive.read("raw.bin"),b"\x00raw\xff")
                self.assertEqual(hashlib.sha256(archive.read("raw.bin")).hexdigest(),manifest["archive_members"]["raw.bin"]["sha256"])
            self.assertEqual((dest/"trajectory.png").read_bytes(),(attempt/"trajectory.png").read_bytes())
            value=json.loads((attempt/"attempt.json").read_text());value["overall_status"]="incomplete";write("attempt.json",value)
            with self.assertRaisesRegex(ValueError,"complete"):
                package(attempt,output,"incomplete",audit,build,sdk,auditor,"producer")
            self.assertFalse((output/"incomplete").exists())
            value["overall_status"]="complete";write("attempt.json",value)
            (attempt/"link").symlink_to(attempt/"raw.bin")
            with self.assertRaisesRegex(ValueError,"symlinks"):
                package(attempt,output,"symlink",audit,build,sdk,auditor,"producer")
            self.assertFalse((output/"symlink").exists())


if __name__ == "__main__": unittest.main()
