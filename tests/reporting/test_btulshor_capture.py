"""Focused contract tests for BTULSHOR capture helpers and offline verification."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts/reports/btulshor/capture.py"
spec = importlib.util.spec_from_file_location("btulshor_capture", SOURCE)
capture = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(capture)


class CaptureHelpers(unittest.TestCase):
    def test_display_boundary_is_separate_and_classes_cover_duplicates_edges_interior(self):
        points = [[0, 0], [2, 0], [2, 2], [0, 2], [1, 1], [1, 0], [0, 0]]
        raw_order = [4, 2, 0, 3, 1]
        before = list(raw_order)
        boundary, classes = capture.exact_geometry(points)
        self.assertEqual(boundary, [0, 1, 2, 3])
        self.assertEqual(classes, ["vertex", "vertex", "vertex", "vertex", "interior", "edge", "duplicate"])
        self.assertEqual(raw_order, before)

    def test_aggregation_preserves_per_run_status_timing_and_unsupported(self):
        points = [[0, 0], [1, 0], [0, 1]]
        docs = []
        for i in range(5):
            providers = [
                {"method_id": capture.METHODS[0], "status": "completed", "elapsed_ns": i + 10,
                 "retained_indices": [0, 1, 2], "retained_points": points},
                {"method_id": capture.METHODS[1], "status": "unsupported_dimension"},
            ]
            if i % 2: providers.reverse()
            docs.append({"schema": capture.COMPARISON_SCHEMA, "fixture_id": "tiny", "dimension": 2,
                         "input_points": points, "input_count": 3, "providers": providers})
        annotated = [capture._annotate(doc, lambda p, ids: {"status": "verified", "hull_equal": True}) for doc in docs]
        by_method = {mid: [next(p for p in doc["providers"] if p["method_id"] == mid) for doc in annotated]
                     for mid in (capture.METHODS[0], capture.METHODS[1])}
        self.assertEqual([p["elapsed_ns"] if "elapsed_ns" in p else None for p in by_method[capture.METHODS[0]]],
                         [10, 11, 12, 13, 14])
        self.assertEqual([p["status"] for p in by_method[capture.METHODS[1]]], ["unsupported_dimension"] * 5)
        self.assertTrue(all(p["exact_check"]["status"] == "inconclusive" for p in by_method[capture.METHODS[1]]))

    def test_stale_provenance_and_retained_points_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "source_commit"):
            capture._read_provenance({"schema": capture.COMPARISON_SCHEMA, "provenance": {
                "source_commit": "old", "compiler_id": "GNU", "compiler_version": "1", "build_config": "Release"}},
                "new")
        mismatch = {"fixture_id": "tiny", "dimension": 2, "input_count": 3,
            "input_points": [[0, 0], [1, 0], [0, 1]], "providers": [{"method_id": "x",
            "retained_indices": [0], "retained_points": [[7, 7]]}]}
        with self.assertRaisesRegex(ValueError, "disagree"):
            capture._annotate(mismatch, lambda *_: {})

    def test_offline_verifier_detects_tampering_outside_checkout(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "renamed-folder"
            (bundle / "raw").mkdir(parents=True)
            raw = {"schema": capture.SUMMARY_SCHEMA, "comparison_files": {}}
            (bundle / "raw/summary.json").write_bytes(capture.canonical(raw))
            payload = {"raw/summary.json": hashlib.sha256((bundle / "raw/summary.json").read_bytes()).hexdigest()}
            manifest = {"schema": "csl.btulshor-source-faithful-bundle/1", "report_id": "test-id",
                        "capture_source_commit": "a" * 40,
                        "source_sha256": capture.SOURCE_SHA256, "files": payload}
            mb = capture.canonical(manifest)
            (bundle / "manifest.json").write_bytes(mb)
            sums = {**payload, "manifest.json": hashlib.sha256(mb).hexdigest()}
            (bundle / "SHA256SUMS").write_text("".join(f"{sums[k]}  {k}\n" for k in sorted(sums)))
            capture.verify_bundle(bundle)
            (bundle / "raw/summary.json").write_text("tampered")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                capture.verify_bundle(bundle)

    def test_capture_refuses_existing_output_before_attempting_driver(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "exists"
            output.mkdir()
            with self.assertRaises(FileExistsError):
                capture.capture(Path("/does/not/exist"), output)

    def test_synthetic_capture_passes_native_validator_and_publication_adapter(self):
        sys.path.insert(0, str(ROOT / "scripts/reports"))
        import stage_btulshor
        import btulshor_registered_reports

        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary) / "repo"
            for name in capture.REPO_SOURCES:
                target = work / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            (work / "scripts/reports/figure_style.py").parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "scripts/reports/figure_style.py", work / "scripts/reports/figure_style.py")
            checker_copy = work / "docs/research/tools/check_btulshor_hulls.py"
            checker_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "docs/research/tools/check_btulshor_hulls.py", checker_copy)
            capture_copy = work / "scripts/reports/btulshor/capture.py"
            copied_spec = importlib.util.spec_from_file_location("btulshor_capture_integration", capture_copy)
            copied = importlib.util.module_from_spec(copied_spec)
            assert copied_spec and copied_spec.loader
            copied_spec.loader.exec_module(copied)
            copied.git_identity = lambda _root: ("a" * 40, False)

            def fake_invoke(_driver, input_path, stdout_path, stderr_path):
                request = json.loads(input_path.read_text())
                fixture_id = request["fixture_id"]
                points = request.get("points")
                if points is None:
                    points = {"simplex-3d": [[0,0,0],[1,0,0],[0,1,0],[0,0,1],[.1,.1,.1]],
                              "simplex-4d": [[0,0,0,0],[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1],[.1,.1,.1,.1]]}.get(
                                  fixture_id, [[0,0],[2,0],[2,2],[0,2],[1,1]])
                dimension = len(points[0])
                order = list(copied.METHODS)
                if request["reverse_order"]: order.reverse()
                providers = []
                for index, method in enumerate(order):
                    provider = {"method_id": method,
                        "status": "unsupported_dimension" if method == copied.METHODS[1] and dimension != 2 else "completed"}
                    if provider["status"] == "completed":
                        provider.update(elapsed_ns=100 + index,
                            interval="synthetic test process only; not measurement evidence",
                            retained_indices=list(range(len(points))), retained_points=points,
                            input_count=len(points), retained_count=len(points))
                    providers.append(provider)
                doc = {"schema": copied.COMPARISON_SCHEMA, "fixture_id": fixture_id,
                    "dimension": dimension, "input_count": len(points), "input_points": points,
                    "providers": providers, "provider_order": order,
                    "provenance": {"source_commit": "a" * 40, "compiler_id": "synthetic",
                        "compiler_version": "test-only", "build_config": "Release",
                        "driver_id": "test-only"}}
                stdout_path.write_bytes(copied.canonical(doc))
                stderr_path.write_bytes(b"")
                return doc, {"elapsed_ns": 1, "rss_status": "unavailable"}

            copied._invoke = fake_invoke
            driver = Path(temporary) / "fake-driver"
            driver.write_text("#!/bin/sh\nexit 0\n")
            driver.chmod(0o755)
            parent = Path(temporary) / "bundles"
            parent.mkdir()
            bundle = parent / stage_btulshor.REPORT_ID
            copied.capture(driver, Path(os.path.relpath(bundle)),
                render_python=Path(sys.executable))
            copied.verify_bundle(bundle)
            checked = subprocess.run([sys.executable, str(bundle / "offline_check.py")],
                cwd=temporary, check=True, capture_output=True, text=True)
            self.assertIn("verified", checked.stdout)
            admitted = stage_btulshor.validate(bundle)
            self.assertEqual(admitted["manifest"]["capture_source_commit"], "a" * 40)
            publication = btulshor_registered_reports.adapt(bundle)
            self.assertEqual(publication.source_report_id, stage_btulshor.REPORT_ID)
            self.assertIn("raw/runs/square/square-r1.json", admitted["files"])
            self.assertIn("input/square-r1.json", admitted["files"])
            summary = json.loads(admitted["files"]["raw/summary.json"])
            self.assertEqual(summary["execution_policy"]["warmup"], "none; first call retained")
            self.assertIn(b"uncontrolled OS and hardware caches", admitted["files"]["index.html"])


if __name__ == "__main__":
    unittest.main()
