from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import stage_issue944_each_choice as publication


class Issue944ChoicePipelinePublicationTests(unittest.TestCase):
    def setUp(self):
        self.bundle = ROOT / "reports/algorithm-results/issue944-strategy-a-each-choice-v1"

    def test_saved_bundle_and_page_are_source_bound_and_complete(self):
        checks = (self.bundle / "SHA256SUMS").read_text(encoding="ascii").splitlines()
        self.assertEqual(len(checks), 11)
        for line in checks:
            expected, name = line.split("  ", 1)
            self.assertEqual(hashlib.sha256((self.bundle / name).read_bytes()).hexdigest(), expected)
        run = json.loads((self.bundle / "records.json").read_text(encoding="utf-8"))
        regression = json.loads((self.bundle / "terminal-membership-regression.json").read_text(encoding="utf-8"))
        self.assertEqual(run["schema"], "csl.strategy-a-each-choice-pipeline/2")
        self.assertEqual(len(run["attempts"]), 128)
        self.assertEqual(regression["schema"], "csl.strategy-a-terminal-membership-indexing-regression/1")
        outcomes = {}
        for attempt in run["attempts"]:
            if attempt.get("first_unmet", "").startswith("phase_one.objective:"):
                outcome = "structural-contract-exclusion"
            elif attempt.get("first_unmet", "").startswith(("highs.matrix:", "highs.convex.matrix:")):
                outcome = "numeric-refusal"
            else:
                outcome = "completed"
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
        self.assertEqual(outcomes, {"structural-contract-exclusion": 64, "completed": 62, "numeric-refusal": 2})
        with (self.bundle / "role-matrix.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 128)
        self.assertEqual(rows[0]["vertex_reducer"], run["attempts"][0]["vertex_reducer"])
        self.assertEqual(sum(row["outcome_class"] == "structural-contract-exclusion" for row in rows), 64)
        self.assertEqual(sum(row["outcome_class"] == "numeric-refusal" for row in rows), 2)
        html = (self.bundle / "index.html").read_text(encoding="utf-8")
        self.assertIn('name="viewport"', html)
        self.assertIn("A = [[1, 0], [0, 1]]", html)
        self.assertIn("H = [[2,0],[0,2]]", html)
        self.assertIn("X₀ = [−1,1]", html)
        self.assertIn((ROOT / "docs/examples/examples.css").read_text(encoding="utf-8"), html)
        self.assertIn("@media print", html)
        self.assertIn("@media(max-width:600px)", html)
        self.assertIn(".issue944-print{display:block!important}", html)
        self.assertIn(".issue944-stat{", html)
        self.assertIn('<div class="issue944-narrow"><figure><img src="terminal-membership-regression-mobile.svg"', html)
        self.assertIn(".issue944-narrow{display:block}", html)
        self.assertIn("background:var(--surface)", html)
        self.assertNotIn("--bg:", html)
        self.assertNotIn("--ink:", html)
        self.assertIn("one-step nominal open-loop", html)
        self.assertIn("complete-family", html)
        self.assertIn("https://github.com/butahlecoq/controlled-systems-lab/pull/976", html)
        self.assertIn("H = [[1,-1.1102230246251565e-16], [0,1], [1.1102230246251565e-16,-1], [-1,0]]", html)
        self.assertIn("b = [0.99999999999999989,1,0,0]", html)
        self.assertIn("csl.polyhedron.v", (self.bundle / "records.json").read_text(encoding="utf-8"))
        provenance = json.loads((self.bundle / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["solver_source_commit"], "5a4730c517a875400ec7b69e4c8e2c265e49016c")
        historical_sources = {
            "runner_source_sha256": "tools/strategy_a_each_choice_pipeline.cpp",
            "checker_source_sha256": "scripts/catalogue/check_944_each_choice_pipeline.py",
        }
        for key, relative in historical_sources.items():
            historical = subprocess.check_output([
                "git", "-C", str(ROOT), "show",
                f'{provenance["solver_source_commit"]}:{relative}',
            ])
            self.assertEqual(provenance[key], hashlib.sha256(historical).hexdigest())
        for key, source in (("publication_renderer_sha256", ROOT / "scripts/reports/render_issue944_each_choice.py"),
                            ("plot_renderer_sha256", ROOT / "scripts/catalogue/render_944_each_choice_example.py"),
                            ("shared_stylesheet_sha256", ROOT / "docs/examples/examples.css")):
            self.assertEqual(provenance[key], hashlib.sha256(source.read_bytes()).hexdigest())
        pipeline = (self.bundle / "pipeline-2d.svg").read_text(encoding="utf-8")
        mobile_pipeline = (self.bundle / "pipeline-2d-mobile.svg").read_text(encoding="utf-8")
        pipeline_print = (self.bundle / "pipeline-2d-print.svg").read_text(encoding="utf-8")
        regression_svg = (self.bundle / "terminal-membership-regression.svg").read_text(encoding="utf-8")
        regression_mobile = (self.bundle / "terminal-membership-regression-mobile.svg").read_text(encoding="utf-8")
        regression_print = (self.bundle / "terminal-membership-regression-print.svg").read_text(encoding="utf-8")
        self.assertIn("#a6e22e", pipeline)
        self.assertIn("#a6e22e", mobile_pipeline)
        self.assertIn("#a6e22e", regression_svg)
        self.assertIn('viewBox="0 0 420 1080"', regression_mobile)
        self.assertIn("Initial state x₀", regression_mobile)
        self.assertIn("Terminal state x₁", regression_mobile)
        self.assertIn("Control u₀", regression_mobile)
        self.assertIn("#a6e22e", regression_mobile)
        self.assertIn("LP: x₀=(0,0), x₁=(1,0), u₀=(1,0)", mobile_pipeline)
        self.assertIn("QP: x₀=(0,0), x₁=(0,0), u₀=(0,0)", mobile_pipeline)
        self.assertIn("#fff", pipeline_print)
        self.assertIn("#111", pipeline_print)
        self.assertIn("#fff", regression_print)
        self.assertIn("#111", regression_print)
        self.assertNotIn("#2878b5", pipeline)
        self.assertNotIn("#101615", regression_svg)

    def test_independent_checker_accepts_immutable_source_5a_capture(self):
        checker = ROOT / "scripts/catalogue/check_944_each_choice_pipeline.py"
        subprocess.run([
            sys.executable, str(checker),
            "--record-json", str(self.bundle / "records.json"),
            "--regression-json", str(self.bundle / "terminal-membership-regression.json"),
            "--expected-numeric-boundaries", "2",
        ], check=True, capture_output=True, text=True)

    def test_stage_checks_hashes_local_links_and_fresh_route(self):
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            route = publication.stage(self.bundle, site)
            staged = site / route
            self.assertEqual((staged / "records.json").read_bytes(), (self.bundle / "records.json").read_bytes())
            with self.assertRaisesRegex(ValueError, "fresh"):
                publication.stage(self.bundle, site)

    def test_cli_rejects_symlinked_site_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            site = root / "site"
            site.mkdir()
            alias = root / "alias"
            alias.symlink_to(site, target_is_directory=True)
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/reports/stage_issue944_each_choice.py"),
                "--source", str(self.bundle), "--site", str(alias),
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("existing site directory", result.stderr)
            self.assertEqual(list(site.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
