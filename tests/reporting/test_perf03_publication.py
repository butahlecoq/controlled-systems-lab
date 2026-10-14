from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import stage_perf03

SOURCE = ROOT / "reports" / "algorithm-results" / stage_perf03.BUNDLE_NAME
HARNESS_PATH = "reports/algorithm-results/tooling/syn04/strategy_b_measure.cpp"
HARNESS_COMMIT = "4fc8e28587a7fe0e4130f1cb435cf6502ba0e4e2"


class Perf03PublicationTests(unittest.TestCase):
    def test_reproduction_patch_applies_to_pinned_harness_blob(self):
        pinned_blob = subprocess.check_output(
            ["git", "rev-parse", f"{HARNESS_COMMIT}:{HARNESS_PATH}"], cwd=ROOT, text=True
        ).strip()
        worktree_blob = subprocess.check_output(["git", "hash-object", HARNESS_PATH], cwd=ROOT, text=True).strip()
        self.assertEqual(worktree_blob, pinned_blob)
        subprocess.run(
            ["git", "apply", "--check", str(SOURCE / "harness-change.patch")],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )

    def test_stages_immutable_page_and_all_local_download_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            bundle = temp / stage_perf03.BUNDLE_NAME
            shutil.copytree(SOURCE, bundle)
            site = temp / "site"
            site.mkdir()
            (site / "index.html").write_text(
                '<!doctype html><html lang="en"><body><h1>Reports</h1><ul></ul></body></html>',
                encoding="utf-8",
            )
            route = stage_perf03.stage(bundle, site)
            self.assertRegex(route, r"^" + stage_perf03.PREFIX + r"[0-9a-f]{16}$")
            page = site / route / "index.html"
            self.assertTrue(page.is_file())
            content = page.read_text(encoding="utf-8")
            for filename in ("profile-summary.json", "paired-timings.csv", "profile-symbols.csv", "README.md"):
                self.assertIn(f'href="{filename}"', content)
                self.assertTrue((page.parent / filename).is_file())
            home = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn(f'href="{route}/index.html"', home)
            with self.assertRaisesRegex(ValueError, "already exists"):
                stage_perf03.stage(bundle, site)

    def test_rejects_tampered_sidecar_before_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / stage_perf03.BUNDLE_NAME
            shutil.copytree(SOURCE, bundle)
            with (bundle / "profile-symbols.csv").open("a", encoding="utf-8") as stream:
                stream.write("tampered\n")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                stage_perf03.validate(bundle)


if __name__ == "__main__":
    unittest.main()
