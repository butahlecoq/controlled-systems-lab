import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import viz10_plot_companions as renderer


class Viz10SavedPlotCompanionTests(unittest.TestCase):
    def test_companions_replay_saved_records_with_quantitative_axes_and_provenance(self):
        with tempfile.TemporaryDirectory(prefix="viz10-render-", dir=ROOT) as temporary:
            out = Path(temporary) / "gallery"
            renderer.build(out)
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], "csl.viz10-gallery/1")
            self.assertEqual(manifest["quantitative_axis_policy"], "csl-report-quantitative-v1")
            self.assertEqual(len([name for name in manifest["figures"] if name.endswith(".svg")]), 15)
            self.assertEqual(len([name for name in manifest["figures"] if name.endswith(".png")]), 15)

            b07 = (out / "b07-b07-reconstruction-s0-l0-d0.svg").read_text(encoding="utf-8")
            self.assertIn("Oxidizer flow x₁ (kg/s)", b07)
            self.assertIn("Fuel flow x₃ (kg/s)", b07)
            self.assertIn("Oxidizer stock balance x₂ (kg)", b07)
            self.assertIn("Fuel stock balance x₄ (kg)", b07)
            self.assertIn("B07 four-state fuel projections", b07)

            b09 = (out / "b09-lambda-0.svg").read_text(encoding="utf-8")
            self.assertIn("Open-loop replay terminal state", b09)
            self.assertIn("Receding-horizon replay terminal state", b09)
            self.assertIn("no projected hull is recomputed", b09.lower())

            for path, expected_hash in manifest["inputs"].items():
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected_hash, path)
            for name, expected_hash in manifest["figures"].items():
                self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), expected_hash, name)
            self.assertIn("../../issue6-b07-reference-a394915af10636430cdcd757d95a9d987eaa6c4c0b742bef7ba1aa04638a2cdd/index.html",
                          (out / "index.html").read_text(encoding="utf-8"))
            self.assertIn("No solver, hull query, numerical experiment or benchmark ran during rendering",
                          (out / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
