import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from scripts.reports import stage_env717_pendulum_terminal as publication


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/env717-pendulum-terminal-pilot-v1"


class PendulumTerminalPublicationTests(unittest.TestCase):
    def test_stages_checksummed_report_and_offline_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            source = temporary_path / "source"
            shutil.copytree(SOURCE, source)
            site = temporary_path / "site"
            site.mkdir()
            (site / "index.html").write_text("<!doctype html><ul></ul>", encoding="utf-8")

            report_id = publication.stage(source, site)

            route = site / report_id
            manifest = json.loads((route / "publication-manifest.json").read_text())
            self.assertEqual(manifest["report_id"], report_id)
            self.assertEqual(manifest["source_commit"],
                             json.loads((source / "result.json").read_text())["source_commit"])
            index = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn(f"{report_id}/index.html", index)
            with zipfile.ZipFile(site / f"{report_id}.zip") as archive:
                names = set(archive.namelist())
                self.assertIn(f"{report_id}/publication-manifest.json", names)
                self.assertIn(f"{report_id}/projection.svg", names)
                self.assertIn(f"{report_id}/index.html", names)

    def test_rejects_bundle_with_changed_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            shutil.copytree(SOURCE, source)
            (source / "result.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                publication._inputs(source)


if __name__ == "__main__":
    unittest.main()
