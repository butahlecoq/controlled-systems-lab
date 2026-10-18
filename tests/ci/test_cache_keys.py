"""Check cache compatibility and trust boundaries through the CLI."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/cache_keys.py"
INPUTS = (
    "cmake/Dependencies.cmake", "cmake/DependencyArchive.cmake",
    "cmake/HighsDependencies.cmake", "cmake/QhullDependencies.cmake",
    "cmake/JsonDependencies.cmake", "cmake/ObjectivesDependencies.cmake",
    "cmake/ApplyPinnedHighsPatch.cmake", "probes/core-01/CMakeLists.txt",
    "tests/cmake/pinned_highs_patch_contract.cmake", "CMakePresets.json",
)


class CacheKeyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in INPUTS:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("literal initial dependency input", encoding="utf-8")
        self.context = {"os": "Linux", "arch": "X64", "compiler": "GCC 13.3",
                        "cmake": "3.31.6", "ccache": "4.10.2", "generator": "Ninja",
                        "configuration": "Release", "options": "highs=on qhull=on probes=on",
                        "lane": "gcc-release"}

    def keys(self, event="push", ref="refs/heads/main", revision="1" * 40):
        context = self.root / "context.json"
        context.write_text(json.dumps(self.context), encoding="utf-8")
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root),
                                 "--context", str(context)], text=True, capture_output=True,
                                env={**os.environ, "GITHUB_EVENT_NAME": event,
                                     "GITHUB_REF": ref, "GITHUB_SHA": revision,
                                     "GITHUB_OUTPUT": "", "GITHUB_STEP_SUMMARY": ""})
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_warm_revision_can_restore_compatible_compiler_snapshot(self):
        old = self.keys()
        new = self.keys(revision="2" * 40)
        self.assertEqual(old["compiler_prefix"], new["compiler_prefix"])
        self.assertNotEqual(old["compiler_key"], new["compiler_key"])
        self.assertEqual(old["archive_key"], new["archive_key"])
        self.assertEqual(old["save_allowed"], "true")

    def test_pin_and_patch_edits_invalidate_both_caches(self):
        original = self.keys()
        for name in ("cmake/HighsDependencies.cmake", "cmake/ApplyPinnedHighsPatch.cmake",
                     "tests/cmake/pinned_highs_patch_contract.cmake"):
            with self.subTest(name=name):
                path = self.root / name
                path.write_text("changed pin or patch", encoding="utf-8")
                changed = self.keys()
                self.assertNotEqual(original["archive_key"], changed["archive_key"])
                self.assertNotEqual(original["compiler_prefix"], changed["compiler_prefix"])
                path.write_text("literal initial dependency input", encoding="utf-8")

    def test_incompatible_build_context_cannot_restore_release_objects(self):
        original = self.keys()
        for field, changed in (("compiler", "Clang 18.1"), ("configuration", "Debug"),
                               ("options", "-fsanitize=address,undefined probes=off"),
                               ("os", "Windows"), ("arch", "ARM64"),
                               ("lane", "gcc-sanitizers"), ("ccache", "4.12"),
                               ("generator", "Visual Studio 17 2022")):
            with self.subTest(field=field):
                previous = self.context[field]
                self.context[field] = changed
                self.assertNotEqual(original["compiler_prefix"], self.keys()["compiler_prefix"])
                self.context[field] = previous

    def test_pr_restores_main_cache_but_cannot_publish_to_it(self):
        main = self.keys()
        pr = self.keys("pull_request", "refs/pull/123/merge")
        self.assertEqual(pr["compiler_prefix"], main["compiler_prefix"])
        self.assertEqual(pr["archive_key"], main["archive_key"])
        self.assertEqual(pr["save_allowed"], "false")

    def test_manual_branch_cache_cannot_poison_main_or_release(self):
        main = self.keys()
        branch = self.keys("workflow_dispatch", "refs/heads/cache-validation")
        self.assertEqual(branch["save_allowed"], "true")
        self.assertNotEqual(branch["archive_key"], main["archive_key"])
        self.assertNotEqual(branch["compiler_prefix"], main["compiler_prefix"])
        release = self.keys("workflow_dispatch", "refs/tags/v0.1.0")
        self.assertEqual(release["save_allowed"], "false")


if __name__ == "__main__":
    unittest.main()
