import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).parents[2] / "scripts/reports/stage_mpc08_nonunique.py"
SPEC = importlib.util.spec_from_file_location("stage_mpc08_nonunique", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NonuniquePublicationTests(unittest.TestCase):
    def test_saved_bundle_has_integral_raw_evidence_and_immutable_hashes(self):
        bundle = MODULE.BUNDLE
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["report_id"], MODULE.REPORT_ID)
        self.assertEqual(set(manifest["files_sha256"]), set(MODULE.FILES) - {"manifest.json"})
        self.assertTrue(all(MODULE.digest(bundle / name) == checksum
                            for name, checksum in manifest["files_sha256"].items()))
        self.assertEqual(len((bundle / "csl-nonunique-observations.jsonl").read_text(encoding="utf-8").splitlines()), 810)
        provenance = json.loads((bundle / "build-provenance.json").read_text(encoding="utf-8"))
        self.assertTrue(all(MODULE.digest(bundle / Path(name).name) == checksum
                            for name, checksum in provenance["source_sha256"].items()))

    def test_report_staging_adds_archive_and_discoverable_figure_links(self):
        with TemporaryDirectory() as temporary:
            site = Path(temporary)
            (site / "examples").mkdir()
            (site / "index.html").write_text("<ul></ul>", encoding="utf-8")
            (site / "examples/index.html").write_text(
                '<section id="analytic-illustrations"></section>', encoding="utf-8")

            MODULE.stage(site)

            self.assertTrue((site / MODULE.REPORT_ID / "index.html").is_file())
            self.assertTrue((site / f"{MODULE.REPORT_ID}.zip").is_file())
            self.assertIn(MODULE.REPORT_ID, (site / "index.html").read_text(encoding="utf-8"))
            self.assertIn(MODULE.REPORT_ID, (site / "examples/index.html").read_text(encoding="utf-8"))
