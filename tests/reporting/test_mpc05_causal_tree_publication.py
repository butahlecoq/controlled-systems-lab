from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "stage_mpc05_causal_tree_test", ROOT / "scripts/reports/stage_mpc05_causal_tree.py")
stage_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage_report)


class Mpc05PublicationTests(unittest.TestCase):
    def test_report_rerenders_stages_and_downloads_offline(self) -> None:
        source = ROOT / "reports/algorithm-results/mpc05-causal-tree-pilot-v2"
        with tempfile.TemporaryDirectory(prefix="mpc05-publication-test-") as temporary:
            root = Path(temporary)
            bundle = root / source.name
            shutil.copytree(source, bundle)
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text("<!doctype html><body></body>", encoding="utf-8")

            report_id = stage_report.stage(bundle, site)

            self.assertRegex(report_id, r"^mpc05-causal-tree-[0-9a-f]{20}$")
            page = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn(report_id + "/index.html", page)
            self.assertIn(report_id + ".zip", page)
            with ZipFile(site / f"{report_id}.zip") as archive:
                names = archive.namelist()
                self.assertIn(f"{report_id}/projections.svg", names)
                self.assertIn(f"{report_id}/build.log", names)
                self.assertIn(f"{report_id}/publication-manifest.json", names)

    def test_rejects_modified_saved_result(self) -> None:
        source = ROOT / "reports/algorithm-results/mpc05-causal-tree-pilot-v2"
        with tempfile.TemporaryDirectory(prefix="mpc05-tamper-test-") as temporary:
            bundle = Path(temporary) / source.name
            shutil.copytree(source, bundle)
            (bundle / "result.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                stage_report.inputs(bundle)


if __name__ == "__main__":
    unittest.main()
