"""Exercise the routing CLI with real event payloads and Git history."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/route_changes.py"


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.area = Path(self.temp.name)
        self.repo = self.area / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "routing@example.invalid")
        self.git("config", "user.name", "Routing tests")
        self.write("README.md", "base")
        self.write("src/existing.cpp", "base")
        self.base = self.commit()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def route(self, event_name="pull_request", payload=None):
        if payload is None:
            payload = {"pull_request": {"base": {"sha": self.base},
                                         "head": {"sha": self.git("rev-parse", "HEAD")}}}
        event = self.area / "event.json"
        event.write_text(json.dumps(payload), encoding="utf-8")
        output = self.area / "output.txt"
        output.unlink(missing_ok=True)
        result = subprocess.run([sys.executable, str(SCRIPT)], cwd=self.repo,
                                env={**os.environ, "GITHUB_EVENT_NAME": event_name,
                                     "GITHUB_EVENT_PATH": str(event),
                                     "GITHUB_OUTPUT": str(output)},
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        outputs = dict(line.split("=", 1) for line in output.read_text().splitlines())
        return outputs["native"], outputs["reports"]

    def test_educational_renderer_and_test_use_complete_reporting_only(self):
        self.write("scripts/reports/visual_examples.py", "legend, CSS and hyperlinks")
        self.write("tests/reporting/test_visual_examples.py", "educational assertions")
        self.commit()
        self.assertEqual(self.route(), ("false", "true"))

    def test_gallery_stylesheet_alone_uses_complete_reporting_only(self):
        self.write("scripts/reports/visual_examples.css", "/* gallery style */")
        self.commit()
        self.assertEqual(self.route(), ("false", "true"))

    def test_coupled_and_unknown_executables_keep_both_gates(self):
        for name in ("scripts/reports/collector_common.py", "scripts/reports/geo07/check_smoke.py",
                     "scripts/reports/visual_examples_new.py", "tests/reporting/test_render.py",
                     "benchmarks/reporting/app01/plan_driver.cpp", "src/new.cpp",
                     "cmake/HighsDependencies.cmake", "schemas/scenario/v1.schema.json",
                     ".github/workflows/native.yml", "CMakePresets.json"):
            with self.subTest(name=name):
                self.git("reset", "--hard", self.base)
                self.write(name, "changed")
                self.commit()
                self.assertEqual(self.route(), ("true", "true"))

    def test_mixed_change_keeps_native(self):
        self.write("scripts/reports/visual_examples.py", "legend")
        self.write("src/existing.cpp", "changed")
        self.commit()
        self.assertEqual(self.route(), ("true", "true"))

    def test_push_and_manual_events(self):
        self.write("scripts/reports/visual_examples.py", "legend")
        head = self.commit()
        self.assertEqual(self.route("push", {"before": self.base, "after": head}),
                         ("false", "true"))
        self.assertEqual(self.route("workflow_dispatch", {}), ("true", "true"))

    def test_unavailable_history_and_empty_diff_are_conservative(self):
        self.assertEqual(self.route(), ("true", "true"))
        self.assertEqual(self.route("push", {"before": "0" * 40, "after": self.base}),
                         ("true", "true"))
        self.assertEqual(self.route("pull_request", {}), ("true", "true"))

    def test_deleted_native_file_cannot_hide_as_renamed_presentation(self):
        (self.repo / "scripts/reports").mkdir(parents=True)
        self.git("mv", "src/existing.cpp", "scripts/reports/visual_examples.py")
        self.commit()
        self.assertEqual(self.route(), ("true", "true"))

    def test_pr_uses_merge_base_and_ignores_unrelated_base_branch_changes(self):
        self.write("scripts/reports/visual_examples.py", "legend")
        head = self.commit()
        self.git("checkout", "-qb", "advanced-base", self.base)
        self.write("src/existing.cpp", "unrelated base change")
        base = self.commit()
        self.assertEqual(self.route(payload={"pull_request": {
            "base": {"sha": base}, "head": {"sha": head}}}), ("false", "true"))

    def test_docs_and_saved_bundles_keep_existing_non_native_scope(self):
        self.write("docs/build/readme.md", "docs")
        self.commit()
        self.assertEqual(self.route(), ("false", "false"))
        self.write("reports/algorithm-results/frozen/records.json", "saved")
        self.commit()
        self.assertEqual(self.route(), ("false", "true"))
        self.write("reports/algorithm-results/tooling/check.py", "executable")
        self.commit()
        self.assertEqual(self.route(), ("true", "true"))


if __name__ == "__main__":
    unittest.main()
