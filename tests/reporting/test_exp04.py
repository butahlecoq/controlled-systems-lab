"""Saved EXP-04 numerical evidence and immutable site staging regressions."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
spec = importlib.util.spec_from_file_location("exp04_stage_test", ROOT / "scripts/reports/stage_exp04.py")
stage = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(stage)
BUNDLE = ROOT / "reports/algorithm-results/exp04-replay-b17d106e0b66a9b5"
CATALOG = ROOT / "reports/algorithm-results/exp04-publications.json"


class Exp04SavedReportTests(unittest.TestCase):
    def test_saved_bytes_regenerate_and_stage_offline(self) -> None:
        stage.report.render(BUNDLE, check=True)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(BUNDLE, root / BUNDLE.name)
            shutil.copyfile(CATALOG, root / CATALOG.name)
            site_dir = root / "site"
            site_dir.mkdir()
            (site_dir / "index.html").write_text("<!doctype html><html lang=\"en\"><body><ul></ul></body></html>",
                                                 encoding="utf-8")
            self.assertEqual(stage.stage(root / CATALOG.name, site_dir), BUNDLE.name)
            self.assertEqual((site_dir / BUNDLE.name / "records.json").read_bytes(),
                             (BUNDLE / "records.json").read_bytes())
            self.assertIn(BUNDLE.name + "/bundle.zip", (site_dir / "index.html").read_text())

    def test_raw_numeric_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / BUNDLE.name
            shutil.copytree(BUNDLE, copy)
            raw = copy / "measure.csv"
            raw.write_bytes(raw.read_bytes().replace(b"plane-forward", b"plane-failure", 1))
            with self.assertRaises(ValueError):
                stage.report.render(copy, check=True)

    def test_rendered_page_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / BUNDLE.name
            shutil.copytree(BUNDLE, copy)
            page = copy / "index.html"
            page.write_bytes(page.read_bytes().replace(b"28,000", b"29,000", 1))
            with self.assertRaises(ValueError):
                stage.report.render(copy, check=True)


if __name__ == "__main__":
    unittest.main()
