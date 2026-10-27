from __future__ import annotations

import builtins
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.reports import stage_projection_data as data
from scripts.reports.stage_projection_figures import render_batch


ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "benchmarks/reporting/stage-projection/bundle-v1"
STYLE = ROOT / "scripts/reports/styles/control-v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StageProjectionEndToEndTests(unittest.TestCase):
    def test_saved_fuel_and_nonfuel_bundles_are_source_bound_and_checksummed(self):
        manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "csl.stage-projection-demo-bundle/1")
        self.assertEqual(manifest["classification"], "illustrative demonstration; not benchmark results")
        listed = {item["path"]: item["sha256"] for item in manifest["artifacts"]}
        sums = {}
        for line in (BUNDLE / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            digest, path = line.split("  ", 1)
            sums[path] = digest
        for relative, digest in listed.items():
            self.assertEqual(sha256(BUNDLE / relative), digest, relative)
            self.assertEqual(sums[relative], digest, relative)

        for stem, expected_problem, expected_route in (
            ("fuel-four-state", "fuel-four-state-box-control-demo", "demo.affine-box-reachability"),
            ("nonfuel-integrator", "planar-integrator-box-control-demo", "demo.affine-box-reachability"),
        ):
            source_path = ROOT / "benchmarks/reporting/stage-projection/examples" / f"{stem}.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            source_digest = sha256(source_path)
            self.assertIn(source_digest, {item["sha256"] for item in manifest["inputs"]})
            document = data.read_stage_projection_batch(
                BUNDLE / f"{stem}.stage-projection-batch.json",
                expected_run_id=source["run_id"],
                expected_problem_id=expected_problem,
                expected_request_id=source["request_id"],
                expected_route_id=expected_route,
                expected_record_schema=source["record_schema"],
                expected_source_sha256=source_digest,
            )
            self.assertEqual(document["stage_axis"]["points"],
                             [float(stage) for stage in range(source["dynamics"]["horizon"] + 1)])
            figures = BUNDLE / f"{stem}-figures"
            receipt = json.loads((figures / "render-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["input_content_sha256"], document["content_sha256"])
            for filename, digest in receipt["files"].items():
                self.assertEqual(sha256(figures / filename), digest, filename)

    def test_offline_render_consumes_saved_geometry_without_launching_execution_or_conversion(self):
        source_path = ROOT / "benchmarks/reporting/stage-projection/examples/fuel-four-state.json"
        source = json.loads(source_path.read_text(encoding="utf-8"))
        source_digest = sha256(source_path)
        identity = {
            "expected_run_id": source["run_id"],
            "expected_problem_id": "fuel-four-state-box-control-demo",
            "expected_request_id": source["request_id"],
            "expected_route_id": "demo.affine-box-reachability",
            "expected_record_schema": source["record_schema"],
            "expected_source_sha256": source_digest,
        }
        input_path = BUNDLE / "fuel-four-state.stage-projection-batch.json"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "rendered"
            env_patch = patch.dict(os.environ, {"MPLCONFIGDIR": str(Path(temporary) / "mpl-config")})
            original_import = builtins.__import__

            def guarded_import(name, *args, **kwargs):
                if name.startswith(("csl.geometry", "csl.execution")):
                    raise AssertionError(f"offline renderer attempted live geometry/execution import: {name}")
                return original_import(name, *args, **kwargs)

            with env_patch, patch.object(subprocess, "run", side_effect=AssertionError("unexpected execution")), \
                    patch.object(subprocess, "Popen", side_effect=AssertionError("unexpected process")), \
                    patch("builtins.__import__", side_effect=guarded_import):
                outputs = render_batch(input_path, output, expected_identity=identity, style_path=STYLE)

            self.assertEqual(len(outputs), 4)
            self.assertTrue((output / "index.html").is_file())
            self.assertEqual(len(list(output.glob("*.svg"))), 4)
            self.assertEqual(len(list(output.glob("*.png"))), 4)
            rendered_html = (output / "index.html").read_text(encoding="utf-8")
            for trajectory_index in range(1, 5):
                self.assertIn(f"selected trajectory {trajectory_index}", rendered_html)
            receipt = json.loads((output / "render-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["input_content_sha256"],
                             data.read_stage_projection_batch(input_path, **identity)["content_sha256"])


if __name__ == "__main__":
    unittest.main()
