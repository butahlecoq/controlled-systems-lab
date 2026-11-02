import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from scripts.reports import stage_env717_unlimited_bolza as publication


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/env717-unlimited-bolza-pilot-v1"


class UnlimitedBolzaPublicationTests(unittest.TestCase):
    def refresh_checksums(self, source: Path) -> None:
        names = sorted(path.name for path in source.iterdir()
                       if path.is_file() and path.name != "SHA256SUMS")
        (source / "SHA256SUMS").write_text(
            "".join(f"{hashlib.sha256((source / name).read_bytes()).hexdigest()}  {name}\n"
                    for name in names), encoding="ascii")

    def source_copy(self, root: Path) -> Path:
        source = root / "source"
        shutil.copytree(SOURCE, source)
        return source

    def test_stages_checksummed_route_and_offline_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.source_copy(root)
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text("<!doctype html><ul></ul>", encoding="utf-8")

            report_id = publication.stage(source, site)

            self.assertRegex(report_id, r"^env717-unlimited-bolza-[0-9a-f]{20}$")
            route = site / report_id
            manifest = json.loads((route / "publication-manifest.json").read_text())
            result = json.loads((source / "result.json").read_text())
            self.assertEqual(manifest["report_id"], report_id)
            self.assertEqual(manifest["source_commit"], result["provenance"]["source_commit"])
            self.assertIn("5^10", (site / "index.html").read_text(encoding="utf-8"))
            self.assertIn(f"{report_id}/index.html", (site / "index.html").read_text(encoding="utf-8"))
            with zipfile.ZipFile(site / f"{report_id}.zip") as archive:
                names = set(archive.namelist())
                self.assertIn(f"{report_id}/publication-manifest.json", names)
                self.assertIn(f"{report_id}/phase-plane.svg", names)
                self.assertIn(f"{report_id}/result.json", names)
                self.assertIn("index.html", names)
                self.assertTrue(archive.testzip() is None)

    def test_checker_cli_verifies_bundle_without_a_driver_argument(self):
        result = subprocess.run(
            [sys.executable,
             str(ROOT / "scripts/reports/env717/check_unlimited_bolza.py"),
             "--verify-bundle", str(SOURCE)],
            check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), f"verified {SOURCE}")

    def test_rejects_changed_bundle_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.source_copy(Path(temporary))
            with (source / "result.json").open("a", encoding="utf-8") as stream:
                stream.write("changed\n")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                publication._inputs(source)

    def test_rejects_tampered_result_even_with_refreshed_checksums(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.source_copy(Path(temporary))
            path = source / "result.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["finite_catalogue_optimum"]["objective"] += 1.0
            path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self.refresh_checksums(source)
            with self.assertRaisesRegex(ValueError, "finite objective"):
                publication._inputs(source)

    def test_rejects_symlinked_bundle_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.source_copy(Path(temporary))
            (source / "phase-plane.svg").unlink()
            (source / "phase-plane.svg").symlink_to(SOURCE / "phase-plane.svg")
            with self.assertRaisesRegex(ValueError, "regular files"):
                publication._inputs(source)

    def test_refuses_to_replace_existing_route(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.source_copy(root)
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text("<!doctype html><ul></ul>", encoding="utf-8")
            route = publication.stage(source, site)
            with self.assertRaisesRegex(ValueError, "route identity differs"):
                publication.stage(source, site)
            self.assertTrue((site / route / "publication-manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
