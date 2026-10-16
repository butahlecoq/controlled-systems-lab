"""Public saved-data and Pages behavior for the EXT-01 numerical report."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/algorithm-results/ext01-fixed-plan-20261016-11b7bc74"
(ROOT / "build").mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts/reports"))
import stage_ext01 as stage

spec = importlib.util.spec_from_file_location("ext01_render_for_test", ROOT / "scripts/reports/ext01/render_saved.py")
render = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(render)


class Ext01SavedReportTest(unittest.TestCase):
    def test_saved_records_match_literal_outputs_and_render_exactly(self):
        record = render.validate_collection(REPORT)
        render.render(REPORT, check=True)
        observations = {row["fixture"]: row["result"] for row in record["trials"]
                        if row["round"] == 1}
        self.assertEqual(observations["l19"]["observed_objective_values"], [1, 0, 1])
        self.assertEqual(observations["integrator_violation"]["violating_successor"], [-1])
        self.assertEqual(observations["b08_rounded"]["plan_count"], 625)
        self.assertEqual(observations["b08_rounded"]["disturbance_histories"], 160000)
        self.assertAlmostEqual(observations["b08_rounded"]["minimum_worst_value"],
                               67.150601101407, delta=1e-8)
        self.assertEqual(len([row for row in record["trials"] if not row["warmup"]]), 28)
        self.assertIn("No numerical residual vector is exposed", (REPORT / "index.html").read_text())
        with zipfile.ZipFile(REPORT / "bundle.zip") as archive:
            self.assertIn(REPORT.name + "/index.html", archive.namelist())
            self.assertIn(REPORT.name + "/index.html", archive.read("index.html").decode())

    def test_raw_change_cannot_survive_saved_validation(self):
        record = render.validate_collection(REPORT)
        changed = copy.deepcopy(record)
        changed["trials"][1]["result"]["worst_value"] = 0
        self.assertNotEqual(changed["trials"], record["trials"])
        with tempfile.TemporaryDirectory(prefix="ext01-report-test-", dir=ROOT / "build") as temp:
            target = Path(temp) / REPORT.name
            self.assertTrue(target.resolve().is_relative_to((ROOT / "build").resolve()))
            shutil.copytree(REPORT, target)
            (target / "records.json").write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "raw-to-summary|collection status"):
                render.validate_collection(target)

    def test_staged_route_has_manifest_and_offline_zip(self):
        item = stage.validate(REPORT)
        catalogue = {"schema": "csl.ext01-report-extension/1",
                     "reports": [stage.catalogue_entry(REPORT)]}
        with tempfile.TemporaryDirectory(prefix="ext01-stage-test-", dir=ROOT / "build") as temp:
            root = Path(temp)
            self.assertTrue(root.resolve().is_relative_to((ROOT / "build").resolve()))
            source = root / REPORT.name
            shutil.copytree(REPORT, source)
            (root / "ext01-publications.json").write_text(json.dumps(catalogue), encoding="utf-8")
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text('<!doctype html><html lang="en"><ul></ul></html>',
                                             encoding="utf-8")
            self.assertEqual(stage.stage(root / "ext01-publications.json", site), item.report_id)
            self.assertTrue((site / item.report_id / "publication-manifest.json").is_file())
            self.assertTrue((site / (item.report_id + ".zip")).is_file())
            self.assertIn(item.report_id, (site / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
