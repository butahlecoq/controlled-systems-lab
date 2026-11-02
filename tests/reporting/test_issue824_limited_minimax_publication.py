from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
STAGER_PATH = ROOT / "scripts/reports/stage_issue824_limited_minimax.py"
SPEC = importlib.util.spec_from_file_location("issue824_limited_stage", STAGER_PATH)
assert SPEC is not None and SPEC.loader is not None
STAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAGER)
sys.path.insert(0, str(ROOT / "scripts/reports"))
VISUAL_SPEC = importlib.util.spec_from_file_location("issue824_limited_visual_examples", ROOT / "scripts/reports/visual_examples.py")
assert VISUAL_SPEC is not None and VISUAL_SPEC.loader is not None
VISUAL = importlib.util.module_from_spec(VISUAL_SPEC)
VISUAL_SPEC.loader.exec_module(VISUAL)
BUNDLE = ROOT / "reports/algorithm-results/issue824-two-points-matched-minimax-resource-v1"


class Issue824LimitedMinimaxPublicationTest(unittest.TestCase):
    def test_resource_profile_and_five_tracks_are_verified(self) -> None:
        files = STAGER.verified_bundle(BUNDLE)
        resource = json.loads(files["resource-profile.json"])
        capture = json.loads(files["capture.json"])
        check = json.loads(files["check.json"])
        self.assertTrue(STAGER.report_source_identity.source_hashes_match_commit_or_checkout(
            ROOT, "0" * 40, capture["source_files_sha256"]))
        self.assertEqual(check["status"], "verified")
        self.assertEqual(check["measurement_samples_verified"], 25)
        self.assertEqual(resource["status"], "completed")
        self.assertEqual(resource["requested_limits"]["process_tree_wall_time_seconds"], 300)
        self.assertEqual(resource["requested_limits"]["process_tree_memory_bytes"], 8 * 1024**3)
        self.assertTrue(capture["resource_accounting"]["enforced_limits"]["process_tree_wall_time"])
        self.assertTrue(capture["resource_accounting"]["enforced_limits"]["process_tree_memory"])
        self.assertEqual(capture["limiter_profile_source_bundle"], "issue824-two-points-matched-minimax-v1")

    def test_stages_exact_inventory(self) -> None:
        files = STAGER.verified_bundle(BUNDLE)
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            self.assertEqual(STAGER.stage(BUNDLE, site), BUNDLE.name)
            staged = site / BUNDLE.name
            self.assertEqual({path.name for path in staged.iterdir()}, set(files))
            for name in files:
                self.assertEqual((staged / name).read_bytes(), files[name])

    def test_gallery_includes_resource_limited_route(self) -> None:
        original_figures = VISUAL.SAVED_FIGURES
        VISUAL.SAVED_FIGURES = tuple(
            example for example in original_figures if example.get("route") == BUNDLE.name)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                site = Path(temporary)
                STAGER.stage(BUNDLE, site)
                cards, _ = VISUAL.saved_figure_sections(ROOT / "reports/algorithm-results/catalog.json", site)
                self.assertIn("Compare five minimax set tracks under shared resource limits", cards)
                self.assertIn("8 GiB process-tree profile", cards)
        finally:
            VISUAL.SAVED_FIGURES = original_figures

    def test_rejects_corrupt_resource_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / BUNDLE.name
            shutil.copytree(BUNDLE, copied)
            profile_path = copied / "resource-profile.json"
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["enforced_limits"]["process_tree_memory"] = False
            profile_path.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            sums = [
                f"{STAGER.digest(path.read_bytes())}  {path.name}"
                for path in sorted(copied.iterdir()) if path.name != "SHA256SUMS"
            ]
            (copied / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "incomplete or inconsistent"):
                STAGER.verified_bundle(copied)


if __name__ == "__main__":
    unittest.main()
