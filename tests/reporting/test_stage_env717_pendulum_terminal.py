import hashlib
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
    def refresh_checksums(self, source: Path) -> None:
        names = sorted(path.name for path in source.iterdir()
                       if path.is_file() and path.name != "SHA256SUMS")
        (source / "SHA256SUMS").write_text(
            "".join(f"{hashlib.sha256((source / name).read_bytes()).hexdigest()}  {name}\n"
                    for name in names), encoding="ascii")

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

    def test_rejects_symlinked_bundle_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            source = temporary_path / "source"
            shutil.copytree(SOURCE, source)
            (source / "result.json").unlink()
            (source / "result.json").symlink_to(SOURCE / "result.json")
            with self.assertRaisesRegex(ValueError, "regular files"):
                publication._inputs(source)

    def test_rejects_saved_replay_that_disagrees_with_oracle(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            shutil.copytree(SOURCE, source)
            result_path = source / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["linearized_plan_source_replay"]["source_accumulated_cost"] += 1.0
            result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            self.refresh_checksums(source)
            with self.assertRaisesRegex(ValueError, "saved report evidence"):
                publication._inputs(source)

    def test_rejects_saved_html_that_differs_from_the_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            shutil.copytree(SOURCE, source)
            page = source / "index.html"
            page.write_text(page.read_text(encoding="utf-8") + "Changed result", encoding="utf-8")
            self.refresh_checksums(source)
            with self.assertRaisesRegex(ValueError, "HTML differs"):
                publication._inputs(source)


if __name__ == "__main__":
    unittest.main()
