"""The differential-game saved-data adapter feeds the common stage renderer."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

from scripts.reports import stage_projection_data as data
from scripts.reports.env717.adapt_two_points_stage_projection import build_batch
from scripts.reports.stage_projection_figures import render_batch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/env717-two-points-feedback-v1/figure-data.json"


class TwoPointsStageProjectionAdapterTests(unittest.TestCase):
    def test_saved_forward_backward_and_intersection_layers_round_trip(self) -> None:
        batch, identity = build_batch(SOURCE)
        raw = data.dumps_stage_projection_batch(batch, **identity)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "two-points.stage-projection-batch.json"
            path.write_bytes(raw)
            loaded = data.read_stage_projection_batch(path, **identity)

        self.assertEqual(loaded["requested_pairs"], [[0, 1], [2, 3]])
        self.assertEqual(loaded["stage_axis"]["points"], [0.0, 0.1, 0.2, 0.3])
        self.assertEqual(len(loaded["records"]), 8)
        self.assertEqual(len(loaded["trajectory_series"]), 4)
        roles = {
            component.get("role")
            for record in loaded["records"]
            for component in record["outcome"]["components"]
        }
        self.assertEqual(roles, {"forward", "backward_winning", "intersection"})

        first = loaded["records"][0]["outcome"]["components"]
        self.assertEqual(first[0]["role"], "forward")
        self.assertEqual(first[0]["branch_id"], "control-prefix/initial")
        self.assertEqual(first[0]["kind"], "point")
        self.assertTrue(any(component["role"] == "backward_winning" for component in first))
        stage_one = loaded["records"][2]["outcome"]["components"]
        forward_components = [component for component in stage_one if component["role"] == "forward"]
        self.assertEqual(len(forward_components), 3)
        self.assertEqual({component["branch_id"] for component in forward_components},
                         {"control-prefix/-2.5", "control-prefix/0", "control-prefix/2.5"})

    def test_adapter_binds_the_exact_saved_source_bytes(self) -> None:
        _, identity = build_batch(SOURCE)
        source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        self.assertEqual(identity["expected_source_sha256"], source_hash)
        self.assertEqual(identity["expected_record_schema"], "csl.env717-two-points-figure-data/1")

    @unittest.skipUnless(importlib.util.find_spec("matplotlib"), "renderer dependencies are optional locally")
    def test_shared_renderer_writes_two_openable_projection_figures(self) -> None:
        batch, identity = build_batch(SOURCE)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch_path = root / "two-points.stage-projection-batch.json"
            output = root / "figures"
            batch_path.write_bytes(data.dumps_stage_projection_batch(batch, **identity))
            rendered = render_batch(
                batch_path,
                output,
                expected_identity=identity,
                style_path=ROOT / "scripts/reports/styles/control-v1.json",
            )
            self.assertEqual(len(rendered), 2)
            self.assertTrue((output / "index.html").is_file())
            self.assertEqual(len(list(output.glob("*.svg"))), 2)
            html = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("backward-winning", html)
            self.assertIn("forward ∩ backward", html)


if __name__ == "__main__":
    unittest.main()
