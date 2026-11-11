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

    def test_custom_svg_output_has_local_figure_csv_and_stylesheet(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            svg = directory / "custom.svg"
            original = RECORD.read_bytes()

            result = subprocess.run(
                [sys.executable, str(RENDERER), "--record", str(RECORD),
                 "--output", str(svg)],
                cwd=ROOT, capture_output=True, text=True, check=False)

            self.assertEqual(result.returncode, 0, result.stderr)
            html_path = directory / "custom.html"
            csv_path = directory / "custom.csv"
            self.assertTrue(svg.is_file())
            self.assertTrue(html_path.is_file())
            self.assertTrue(csv_path.is_file())
            self.assertTrue((directory / "custom.json").is_file())
            page = html_path.read_text(encoding="utf-8")
            self.assertIn('href="custom.html"', page)
            self.assertIn('src="custom.svg"', page)
            self.assertIn('href="custom.csv"', page)
            self.assertIn("<style>", page)
            self.assertIn(Path(ROOT / "docs/examples/examples.css").read_text(encoding="utf-8"), page)
            self.assertNotIn('href="examples.css"', page)
            self.assertEqual(csv_path.read_bytes(), original)
            self.assertEqual(RECORD.read_bytes(), original)

    def test_custom_output_refuses_to_replace_unrelated_csv_sidecar(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            svg = directory / "custom.svg"
            csv_path = directory / "custom.csv"
            unrelated = b"keep this unrelated CSV exactly as written\n"
            csv_path.write_bytes(unrelated)

            result = subprocess.run(
                [sys.executable, str(RENDERER), "--record", str(RECORD),
                 "--output", str(svg)],
                cwd=ROOT, capture_output=True, text=True, check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CSV sidecar already exists", result.stderr)
            self.assertEqual(csv_path.read_bytes(), unrelated)
            self.assertFalse(svg.exists())
            self.assertFalse((directory / "custom.html").exists())
            self.assertFalse((directory / "custom.json").exists())


if __name__ == "__main__":
    unittest.main()
