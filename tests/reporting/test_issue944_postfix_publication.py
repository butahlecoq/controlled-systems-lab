from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import stage_issue944_each_choice as historical
import stage_issue944_postfix as publication


class Issue944PostfixPublicationTests(unittest.TestCase):
    def setUp(self):
        self.bundle = ROOT / "reports/algorithm-results/issue944-strategy-a-each-choice-postfix-v1"
        self.historical = ROOT / "reports/algorithm-results/issue944-strategy-a-each-choice-v1"

    def test_postfix_bundle_is_complete_immutable_and_source_bound(self):
        checks = (self.bundle / "SHA256SUMS").read_text(encoding="ascii").splitlines()
        self.assertEqual(len(checks), 17)
        for line in checks:
            expected, name = line.split("  ", 1)
            self.assertEqual(hashlib.sha256((self.bundle / name).read_bytes()).hexdigest(), expected)
        capture_checks = (self.bundle / "capture-SHA256SUMS").read_text(encoding="ascii").splitlines()
        self.assertGreaterEqual(len(capture_checks), 7)
        for line in capture_checks:
            expected, name = line.split("  ", 1)
            self.assertEqual(hashlib.sha256((self.bundle / name).read_bytes()).hexdigest(), expected)
        run = json.loads((self.bundle / "records.json").read_text(encoding="utf-8"))
        regression = json.loads((self.bundle / "terminal-membership-regression.json").read_text(encoding="utf-8"))
        capture = json.loads((self.bundle / "provenance.json").read_text(encoding="utf-8"))
        publication_provenance = json.loads((self.bundle / "publication-provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(run["schema"], "csl.strategy-a-each-choice-pipeline/2")
        self.assertEqual(len(run["attempts"]), 128)
        self.assertEqual(regression["schema"], "csl.strategy-a-terminal-membership-indexing-regression/1")
        self.assertEqual(capture["source_commit"], "ee677acf13fb38330dbde696a7b7bb7247eab792")
        self.assertEqual(capture["checker_result"]["status"], "passed")
        self.assertEqual(capture["checker_result"]["required_reconciliation"],
                         "64 structural exclusions + 64 completed admitted attempts")
        self.assertEqual(capture["runner_source_sha256"],
                         "b3d99cd4edd0eb76af42ea7da65ba7236f4fca372e30e52d17a21f0c958d9468")
        self.assertEqual(capture["checker_source_sha256"],
                         "32c161822ea0915fadfc9bf55f6175373dff64ebd55ebdcf1897bfddf5dc9297")
        self.assertEqual(capture["capture_harness_sha256"],
                         "1941f252c87c6b7061078a280ec5fd4f909ff9d86bf0f8e14c29870e2b1eec11")
        self.assertEqual(publication_provenance["capture_source_commit"], capture["source_commit"])
        self.assertEqual(publication_provenance["records_sha256"],
                         "abf2ea6b80260a14e344ab004e9bed7b6d4a11e4d8bc2083ebd6c10d5404d73c")
        self.assertEqual(publication_provenance["regression_sha256"],
                         "2bfce10402b25884b5de16f3ca97abb1ed6d4dac8b94b62939444938c22bfdb1")
        outcomes = {}
        for row in run["attempts"]:
            if row.get("first_unmet", "").startswith("phase_one.objective:"):
                label = "structural-contract-exclusion"
            elif row.get("first_unmet", "").startswith(("highs.matrix:", "highs.convex.matrix:")):
                label = "numeric-refusal"
            else:
                label = "completed"
            outcomes[label] = outcomes.get(label, 0) + 1
        self.assertEqual(outcomes, {"structural-contract-exclusion": 64, "completed": 64})
        old_checks = (self.historical / "SHA256SUMS").read_bytes()
        old_records = (self.historical / "records.json").read_bytes()
        old_provenance = json.loads((self.historical / "provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(old_provenance["solver_source_commit"], "5a4730c517a875400ec7b69e4c8e2c265e49016c")
        self.assertEqual((self.historical / "SHA256SUMS").read_bytes(), old_checks)
        self.assertEqual((self.historical / "records.json").read_bytes(), old_records)
        checker = ROOT / "scripts/catalogue/check_944_each_choice_pipeline.py"
        subprocess.run([sys.executable, str(checker), "--record-json", str(self.bundle / "records.json"),
                        "--regression-json", str(self.bundle / "terminal-membership-regression.json"),
                        "--expected-numeric-boundaries", "0"], check=True, capture_output=True, text=True)
        html = (self.bundle / "index.html").read_text(encoding="utf-8")
        self.assertIn("All 64 admitted attempts completed", html)
        self.assertIn("one-step nominal open-loop", html)
        self.assertIn("not feedback/MPC completion", html)
        self.assertIn("../examples/qhull-highs-strategy-a-2d.html", html)
        self.assertIn("ordered_V_vertices=[0,1;1,1;0,0;1,0]", html)
        self.assertIn("@media(max-width:600px)", html)
        self.assertIn("@media print", html)
        self.assertIn('<div class="issue944-narrow"><figure><img src="terminal-membership-regression-mobile.svg"', html)
        mobile = (self.bundle / "terminal-membership-regression-mobile.svg").read_text(encoding="utf-8")
        for label in ("Initial state x₀", "Terminal state x₁", "Control u₀"):
            self.assertIn(label, mobile)

    def test_stage_publishes_real_public_example_and_local_routes(self):
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            historical.stage(self.historical, site)
            route = publication.stage(self.bundle, site)
            staged = site / route
            examples = site / "examples"
            self.assertEqual(route, "issue944-strategy-a-each-choice-postfix-v1")
            for name in publication.EXAMPLE_FILES:
                self.assertTrue((examples / name).is_file())
            self.assertEqual((examples / "qhull-highs-strategy-a-2d-record.json").read_bytes(),
                             (ROOT / "docs/examples/qhull-highs-strategy-a-2d-record.json").read_bytes())
            self.assertTrue((examples / "examples.css").is_file())
            page = (staged / "index.html").read_text(encoding="utf-8")
            href = "../examples/qhull-highs-strategy-a-2d.html"
            self.assertTrue((staged / href).resolve().is_file())
            self.assertIn(href, page)
            public_page = (examples / "qhull-highs-strategy-a-2d.html").read_text(encoding="utf-8")
            self.assertIn("Qhull and Strategy A on a 2D control problem", public_page)
            self.assertIn("qhull-highs-strategy-a-2d-record.json", public_page)
            with self.assertRaisesRegex(ValueError, "fresh"):
                publication.stage(self.bundle, site)

    def test_workflow_cli_stages_both_bundles_and_public_example(self):
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            for script, bundle in (("stage_issue944_each_choice.py", self.historical),
                                   ("stage_issue944_postfix.py", self.bundle)):
                result = subprocess.run([
                    sys.executable, str(ROOT / "scripts/reports" / script),
                    "--source", str(bundle), "--site", str(site),
                ], check=True, capture_output=True, text=True, cwd=ROOT)
                self.assertEqual(result.stdout.strip(), bundle.name)
                for source in bundle.iterdir():
                    self.assertEqual((site / bundle.name / source.name).read_bytes(),
                                     source.read_bytes())
            for name in publication.EXAMPLE_FILES:
                self.assertTrue((site / "examples" / name).is_file())
            self.assertEqual((site / "examples/qhull-highs-strategy-a-2d-record.json").read_bytes(),
                             (ROOT / "docs/examples/qhull-highs-strategy-a-2d-record.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
