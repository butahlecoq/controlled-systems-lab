from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "stage_mpc09_output_feedback_test", ROOT / "scripts/reports/stage_mpc09_output_feedback.py")
stage_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage_report)
LANDING_SPEC = importlib.util.spec_from_file_location("landing_mpc09", ROOT / "scripts/reports/landing.py")
landing = importlib.util.module_from_spec(LANDING_SPEC)
assert LANDING_SPEC.loader is not None
LANDING_SPEC.loader.exec_module(landing)


class Mpc09PublicationTests(unittest.TestCase):
    def test_source_fingerprints_remain_bound_to_the_captured_commit(self) -> None:
        source = ROOT / "reports/algorithm-results/mpc09-two-particle-output-feedback-v1"
        with tempfile.TemporaryDirectory(prefix="mpc09-source-history-") as temporary:
            checkout = Path(temporary)
            shutil.copytree(source, checkout / source.name)
            scenario = ROOT / "benchmarks/scenarios/mpc09-two-particle-output-feedback-v1.json"
            scenario_target = checkout / "benchmarks/scenarios/mpc09-two-particle-output-feedback-v1.json"
            scenario_target.parent.mkdir(parents=True)
            shutil.copyfile(scenario, scenario_target)
            workflow = checkout / ".github/workflows/algorithm-reports.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text("later unrelated workflow edit\n", encoding="utf-8")

            with patch.object(stage_report, "ROOT", checkout), \
                 patch.object(stage_report.report, "ROOT", checkout):
                _, _, _, capture = stage_report.validate_bundle(checkout / source.name)

            self.assertEqual(capture["source_commit"], "46da55a5967c0db326b7126ced55654b20bc570d")
            self.assertEqual(capture["source_sha256"][
                ".github/workflows/algorithm-reports.yml"],
                "12e18a9080f7c6485d0628e17efa73d5ab1fc05447020ca36554dd68ef65fc87")

    def test_report_rerenders_and_stages_offline_bundle(self) -> None:
        source = ROOT / "reports/algorithm-results/mpc09-two-particle-output-feedback-v1"
        with tempfile.TemporaryDirectory(prefix="mpc09-publication-") as temporary:
            root = Path(temporary)
            bundle = root / source.name
            shutil.copytree(source, bundle)
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text("<!doctype html><html><body><ul></ul></body></html>", encoding="utf-8")

            route = stage_report.stage(bundle, site)
            landing.build(site)

            self.assertRegex(route, r"^mpc09-output-feedback-[0-9a-f]{20}$")
            page = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn("TwoParticleGame output-feedback MPC", page)
            self.assertIn(route + "/result.json", page)
            self.assertIn(route + ".zip", page)
            with ZipFile(site / f"{route}.zip") as archive:
                names = archive.namelist()
                self.assertIn(f"{route}/projections.svg", names)
                self.assertIn(f"{route}/publication-manifest.json", names)
                self.assertIn(f"{route}/build.log", names)

    def test_rejects_changed_saved_artifact(self) -> None:
        source = ROOT / "reports/algorithm-results/mpc09-two-particle-output-feedback-v1"
        with tempfile.TemporaryDirectory(prefix="mpc09-tamper-") as temporary:
            bundle = Path(temporary) / source.name
            shutil.copytree(source, bundle)
            (bundle / "result.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                stage_report.read_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
