"""The saved adaptive-ODE record must survive invalid renderer destinations."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
RENDERER = ROOT / "scripts/reports/render_adaptive_ode_example.py"
RECORD = ROOT / "docs/examples/adaptive-ode-replay.csv"


class AdaptiveOdeRendererPathTests(unittest.TestCase):
    def test_csv_destination_is_rejected_without_changing_record_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "adaptive-ode-replay.csv"
            record.write_bytes(RECORD.read_bytes())
            before = record.read_bytes()

            result = subprocess.run(
                [sys.executable, str(RENDERER), "--record", str(record),
                 "--output", str(record)],
                cwd=ROOT, capture_output=True, text=True, check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--output must name an .svg file", result.stderr)
            self.assertEqual(record.read_bytes(), before)

    def test_generated_sidecar_may_not_alias_input_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "adaptive-ode-replay.json"
            record.write_bytes(RECORD.read_bytes())
            output = record.with_suffix(".svg")

            result = subprocess.run(
                [sys.executable, str(RENDERER), "--record", str(record),
                 "--output", str(output)],
                cwd=ROOT, capture_output=True, text=True, check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("renderer output or sidecar would overwrite", result.stderr)


if __name__ == "__main__":
    unittest.main()
