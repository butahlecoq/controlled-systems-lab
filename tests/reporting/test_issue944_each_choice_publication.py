from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
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
        self.assertEqual(len(checks), 7)
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
        self.assertIn("@media(max-width:600px)", html)
        self.assertIn("one-step nominal open-loop", html)
        self.assertIn("complete-family", html)
        self.assertIn("https://github.com/butahlecoq/controlled-systems-lab/pull/976", html)
        self.assertIn("H = [[1,-1.1102230246251565e-16], [0,1], [1.1102230246251565e-16,-1], [-1,0]]", html)
        self.assertIn("b = [0.99999999999999989,1,0,0]", html)
        self.assertIn("csl.polyhedron.v", (self.bundle / "records.json").read_text(encoding="utf-8"))
        provenance = json.loads((self.bundle / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["solver_source_commit"], "5a4730c517a875400ec7b69e4c8e2c265e49016c")
        for key, source in (("runner_source_sha256", ROOT / "tools/strategy_a_each_choice_pipeline.cpp"),
                            ("checker_source_sha256", ROOT / "scripts/catalogue/check_944_each_choice_pipeline.py"),
                            ("publication_renderer_sha256", ROOT / "scripts/reports/render_issue944_each_choice.py"),
                            ("plot_renderer_sha256", ROOT / "scripts/catalogue/render_944_each_choice_example.py"),
                            ("shared_stylesheet_sha256", ROOT / "docs/examples/examples.css")):
            self.assertEqual(provenance[key], hashlib.sha256(source.read_bytes()).hexdigest())

    def test_stage_checks_hashes_local_links_and_fresh_route(self):
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            route = publication.stage(self.bundle, site)
            staged = site / route
            self.assertEqual((staged / "records.json").read_bytes(), (self.bundle / "records.json").read_bytes())
            with self.assertRaisesRegex(ValueError, "fresh"):
                publication.stage(self.bundle, site)


if __name__ == "__main__":
    unittest.main()
