from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
STAGER_PATH = ROOT / "scripts/reports/stage_issue824_matched_minimax.py"
SPEC = importlib.util.spec_from_file_location("issue824_matched_stage", STAGER_PATH)
assert SPEC is not None and SPEC.loader is not None
STAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAGER)
VISUAL_SPEC = importlib.util.spec_from_file_location("issue824_visual_examples", ROOT / "scripts/reports/visual_examples.py")
assert VISUAL_SPEC is not None and VISUAL_SPEC.loader is not None
VISUAL = importlib.util.module_from_spec(VISUAL_SPEC)
VISUAL_SPEC.loader.exec_module(VISUAL)
BUNDLE = ROOT / "reports/algorithm-results/issue824-two-points-matched-minimax-v1"


class Issue824MatchedMinimaxPublicationTest(unittest.TestCase):
    def test_bundle_has_five_matched_verified_tracks(self) -> None:
        files = STAGER.verified_bundle(BUNDLE)
        result = json.loads(files["result.json"])
        check = json.loads(files["check.json"])
        capture = json.loads(files["capture.json"])
        self.assertEqual(result["methods"], ["exact_polytope", "box", "zonotope", "parallelotope", "ellipsoid"])
        self.assertEqual(check["status"], "verified")
        self.assertEqual(check["measurement_samples_verified"], 25)
        self.assertEqual(check["exact_finite_minimax_value"], 14.58094225)
        self.assertTrue(capture["source_tree_clean_before_report_generation"])
        self.assertTrue(STAGER.report_source_identity.source_hashes_match_commit_or_checkout(
            ROOT, "0" * 40, capture["source_files_sha256"]))
        self.assertEqual(capture["resource_accounting"]["policy"], "uncapped local exploratory run")
        self.assertEqual(capture["resource_accounting"]["enforced_limits"], {
            "algorithm_wall_time": False, "process_tree_memory": False})
        self.assertEqual(len(json.loads(files["e2e-timing.json"])["trials"]), 5)

    def test_stages_exact_inventory_and_phase_plane_figures(self) -> None:
        files = STAGER.verified_bundle(BUNDLE)
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            self.assertEqual(STAGER.stage(BUNDLE, site), BUNDLE.name)
            staged = site / BUNDLE.name
            self.assertEqual({path.name for path in staged.iterdir()}, set(files))
            for name in ("geometry-reference-ellipsoid.svg", "geometry-reference-parallelotope.svg"):
                self.assertEqual((staged / name).read_bytes(), files[name])

    def test_rejects_corrupt_measurement_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / BUNDLE.name
            shutil.copytree(BUNDLE, copied)
            (copied / "result.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                STAGER.verified_bundle(copied)

    def test_preserves_failed_attempt_as_incomplete_evidence(self) -> None:
        result = json.loads((BUNDLE / "result.json").read_text(encoding="utf-8"))
        failed = result["samples"][0]
        failed["status"] = "failed"
        failed["error"] = "synthetic captured selector failure"
        failed.pop("outcome")
        check = STAGER.check_matched_minimax.check(result)
        self.assertEqual(check["status"], "incomplete")
        self.assertEqual(check["failures"], 1)
        self.assertEqual(check["measurement_samples_verified"], 24)
        self.assertEqual(check["failed_attempts"], [failed])
        self.assertEqual(check["missing_attempts_by_method"][failed["method"]], 0)

    def test_gallery_discloses_incomplete_checker_status(self) -> None:
        result = json.loads((BUNDLE / "result.json").read_text(encoding="utf-8"))
        failed = result["samples"][0]
        failed["status"] = "failed"
        failed["error"] = "synthetic captured selector failure"
        failed.pop("outcome")
        check = STAGER.check_matched_minimax.check(result)
        original_figures = VISUAL.SAVED_FIGURES
        VISUAL.SAVED_FIGURES = tuple(
            example for example in original_figures if example.get("route") == BUNDLE.name)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                site = Path(temporary)
                STAGER.stage(BUNDLE, site)
                route = site / BUNDLE.name
                (route / "check.json").write_text(json.dumps(check), encoding="utf-8")
                cards, _ = VISUAL.saved_figure_sections(ROOT / "reports/algorithm-results/catalog.json", site)
                self.assertIn("Incomplete evidence", cards)
                self.assertIn("24 completed outcomes checked across 25/25 attempts", cards)
                self.assertNotIn("each score all 27 plans", cards)
        finally:
            VISUAL.SAVED_FIGURES = original_figures

    def test_does_not_overwrite_an_existing_route(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            route = site / BUNDLE.name
            route.mkdir()
            authored = route / "keep.txt"
            authored.write_text("authored", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                STAGER.stage(BUNDLE, site)
            self.assertEqual(authored.read_text(encoding="utf-8"), "authored")


if __name__ == "__main__":
    unittest.main()
