"""Check GEO-08 saved calls, regeneration and public site staging."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "geo08_render_test", ROOT / "scripts/reports/geo08/render_saved.py")
render = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(render)
BUNDLE = ROOT / "reports/algorithm-results/geo08-lazy-f2e9c9c0daa49164"
CATALOG = ROOT / "reports/algorithm-results/geo08-publications.json"


class SavedGeo08Test(unittest.TestCase):
    def test_verified_calls_regenerate_report(self) -> None:
        render.render(BUNDLE, check=True)
        record = render.validate(BUNDLE)
        self.assertEqual(record["source_commit"],
                         "87a747a644b5d1aa9887d01d09e0921c727fa921")
        self.assertEqual(record["measurement"]["summary"]["successes"], 700)
        self.assertEqual(record["measurement"]["summary"]["failures"], 0)
        self.assertEqual([int(row["completed"]) for row in
                          record["measurement"]["trials"]], [100] * 8)
        self.assertIn(b"support 5", (BUNDLE / "lazy-2d.svg").read_bytes())

    def test_changed_completed_count_invalidates_saved_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / BUNDLE.name
            shutil.copytree(BUNDLE, copy)
            raw = copy / "measure.csv"
            self.assertIn(b"100,100,100,completed,true,", raw.read_bytes())
            raw.write_bytes(raw.read_bytes().replace(
                b"100,100,100,completed,true,",
                b"100,100,99,completed,true,", 1))
            with self.assertRaises(ValueError):
                render.render(copy, check=True)

    def test_catalog_stages_exact_report_and_example(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            (site / "index.html").write_text(
                '<!doctype html><html lang="en"><body><ul></ul></body></html>',
                encoding="utf-8")
            subprocess.run([sys.executable, str(ROOT / "scripts/reports/stage_geo08.py"),
                            "--catalog", str(CATALOG), "--site", str(site)],
                           check=True, capture_output=True, text=True)
            self.assertEqual((site / BUNDLE.name / "bundle.zip").read_bytes(),
                             (BUNDLE / "bundle.zip").read_bytes())
            self.assertIn(f'{BUNDLE.name}/example-2d.html',
                          (site / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
