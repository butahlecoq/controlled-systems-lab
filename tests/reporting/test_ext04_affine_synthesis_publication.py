import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "stage_ext04_affine_synthesis",
    ROOT / "scripts/reports/stage_ext04_affine_synthesis.py")
stage = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage)
CATALOG = ROOT / "reports/algorithm-results/ext04-affine-synthesis-publications.json"


def source_bundle() -> Path:
    if CATALOG.is_file():
        report_id = json.loads(CATALOG.read_text(encoding="utf-8"))["reports"][0]["source_report_id"]
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
            catalog = {"schema": "csl.ext04-affine-synthesis-publications/1",
                       "reports": [stage.entry_for(bundle)]}
            catalog_path = root / "publications.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            site_dir = root / "site"
            site_dir.mkdir()
            (site_dir / "index.html").write_text(
                "<!doctype html><html lang=\"en\"><body><ul></ul></body></html>",
                encoding="utf-8")

            report_id = stage.stage(catalog_path, site_dir)

            report = site_dir / report_id
            self.assertIn("Environment", (report / "index.html").read_text(encoding="utf-8"))
            self.assertTrue((report / "report-envelope.json").is_file())
            manifest = json.loads((report / "publication-manifest.json").read_text(encoding="utf-8"))
            for name, digest in manifest["files"].items():
                self.assertEqual(stage.sha((report / name).read_bytes()), digest)
            with zipfile.ZipFile(site_dir / (report_id + ".zip")) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn(report_id + "/index.html", archive.namelist())

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
