import importlib.util
import io
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "stage_ext04_affine_synthesis", ROOT / "scripts/reports/stage_ext04_affine_synthesis.py"
)
if SPEC is None or SPEC.loader is None:
    raise ImportError("Cannot load the EXT-04 affine-synthesis publisher")
stage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage)
CATALOG = ROOT / "reports/algorithm-results/ext04-affine-synthesis-publications.json"


def source_bundle() -> Path:
    if CATALOG.is_file():
        report_id = json.loads(CATALOG.read_text(encoding="utf-8"))["reports"][0][
            "source_report_id"
        ]
        return CATALOG.parent / report_id
    candidates = sorted(CATALOG.parent.glob("ext04-affine-synthesis-[0-9a-f]*"))
    if not candidates:
        raise FileNotFoundError("no saved affine-synthesis report bundle")
    return candidates[-1]


class AffineSynthesisPublicationTests(unittest.TestCase):
    def test_catalogued_bundle_stages_report_assets_and_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = source_bundle()
            bundle = root / original.name
            shutil.copytree(original, bundle)
            catalog = {
                "schema": "csl.ext04-affine-synthesis-publications/1",
                "reports": [stage.entry_for(bundle)],
            }
            catalog_path = root / "publications.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            site_dir = root / "site"
            site_dir.mkdir()
            (site_dir / "index.html").write_text(
                '<!doctype html><html lang="en"><body><ul></ul></body></html>', encoding="utf-8"
            )

            report_id = stage.stage(catalog_path, site_dir)

            report = site_dir / report_id
            self.assertIn("Environment", (report / "index.html").read_text(encoding="utf-8"))
            self.assertTrue((report / "report-envelope.json").is_file())
            manifest = json.loads(
                (report / "publication-manifest.json").read_text(encoding="utf-8")
            )
            for name, digest in manifest["files"].items():
                self.assertEqual(stage.sha((report / name).read_bytes()), digest)
            with zipfile.ZipFile(site_dir / (report_id + ".zip")) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn(report_id + "/index.html", archive.namelist())

    def test_historical_zip_metadata_cannot_be_republished(self):
        build_archive = stage.archive

        def repack(report_id, files):
            buffer = io.BytesIO(build_archive(report_id, files))
            with zipfile.ZipFile(buffer, "a") as archive:
                archive.comment = b"Different metadata, same members"
            return buffer.getvalue()

        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            landing = site / "index.html"
            landing.write_bytes(b"<html><body><ul></ul></body></html>")
            with patch.object(stage, "archive", side_effect=repack):
                with self.assertRaisesRegex(
                    ValueError, "Historical EXT-04 input or archive checksum"
                ):
                    stage.entry_for(source_bundle())
                with self.assertRaisesRegex(
                    ValueError, "Historical EXT-04 input or archive checksum"
                ):
                    stage.stage(CATALOG, site)
            self.assertEqual(list(site.iterdir()), [landing])
            self.assertEqual(landing.read_bytes(), b"<html><body><ul></ul></body></html>")

    def test_catalog_rejects_a_mutated_trial(self):
        with tempfile.TemporaryDirectory() as temporary:
            original = source_bundle()
            bundle = Path(temporary) / original.name
            shutil.copytree(original, bundle)
            trials = bundle / "trials.jsonl"
            trials.write_bytes(trials.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "native report manifest differs"):
                stage.entry_for(bundle)


if __name__ == "__main__":
    unittest.main()
