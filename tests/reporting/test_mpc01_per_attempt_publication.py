"""Verify the saved MPC-01 route can augment an existing offline Pages site."""
from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import shutil
from urllib.parse import urldefrag, urlparse

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/reports/mpc01/stage_per_attempt.py"
SPEC = importlib.util.spec_from_file_location("mpc01_stage_per_attempt", SCRIPT)
stage_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage_module)


class PerAttemptPublicationTests(unittest.TestCase):
    def test_summary_generator_writes_current_text_without_replacing_captured_summary(self):
        source = stage_module.SOURCE / "benchmark-summary.txt"
        captured_sha = "e8a3f56c88e300e6f787ad2033eb14bfbfbcceaa4c406376708ec125bfec70fa"
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), captured_sha)
        with tempfile.TemporaryDirectory(prefix="mpc01-current-summary-") as temporary:
            output = Path(temporary) / "benchmark-summary.txt"
            subprocess.run([sys.executable,
                            str(ROOT / "scripts/reports/mpc01/summarize_per_attempt.py"),
                            "--bundle", str(stage_module.SOURCE), "--output", str(output)],
                           cwd=ROOT, check=True, capture_output=True, text=True)
            current = output.read_text(encoding="utf-8")
            self.assertIn("../mpc01-source-mapped-profile-20261102/README.txt", current)
            self.assertNotIn("../mpc01-source-mapped-profile-20261102/README.md", current)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), captured_sha)

    def test_migrated_mpc01_sidecars_keep_their_source_commit_bytes(self):
        expected = {
            "docs/research/evidence/mpc01-external-qps-20261026-r3/benchmark-summary.txt":
                "de5ce61105e3ee8452d4618d894e3a42924d0922a73e6c8a222914d477089901",
            "docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-summary.txt":
                "8bf5c220425bc167cdebfb8937414e8dbf05608a8cc02e8dd6cc9b1c4de8c96b",
            "docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-limited-capture/strategy-ab-ts01-summary.txt":
                "30f695260aa6fefb410eb495999f6f932d91e61e4d313d59c2ac90c8dbcfc556",
            "docs/research/evidence/mpc01-external-qps-20261026-r3/b04-repeated-benchmark-projections.html":
                "db0cc4dc2203626d27a3c4c68a49a8ad085f48bc58ae7f8e6484af842df22675",
            "docs/research/evidence/mpc01-external-qps-20261026/b04-repeated-benchmark-projections.html":
                "af0f6abb79319e623e61f790caa97447174e8c24ea0e8113ddf622b48957e922",
        }
        for relative, digest in expected.items():
            with self.subTest(path=relative):
                self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest)

    def test_repeated_comparison_generator_links_its_text_summary(self):
        source = ROOT / "docs/research/evidence/mpc01-external-qps-20261102-resource-r1"
        with tempfile.TemporaryDirectory(prefix="mpc01-repeated-report-") as temporary:
            output = Path(temporary)
            script = ROOT / "scripts/reports/mpc01/summarize_repeated_comparison.py"
            subprocess.run([sys.executable, str(script), "--records",
                            str(source / "comparison-records.jsonl"), "--attempts",
                            str(source / "runner.stdout.jsonl"), "--output-dir", str(output)],
                           cwd=ROOT, check=True, capture_output=True, text=True)
            page = (output / "b04-repeated-benchmark-projections.html").read_text(encoding="utf-8")
            self.assertIn('href="benchmark-summary.txt"', page)
            self.assertTrue((output / "benchmark-summary.txt").is_file())
            self.assertFalse((output / "benchmark-summary.md").exists())

    def test_saved_summary_retains_its_historical_profile_link(self):
        summary = stage_module.SOURCE / "benchmark-summary.txt"
        relative = "../mpc01-source-mapped-profile-20261102/README.md"
        self.assertIn(relative, summary.read_text(encoding="utf-8"))
        profile = (stage_module.SOURCE.parent / "mpc01-source-mapped-profile-20261102")
        note = profile / "README.txt"
        digest = hashlib.sha256(note.read_bytes()).hexdigest()
        manifest = json.loads((profile / "profile-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifacts"]["README.txt"], digest)
        sums = (profile / "SHA256SUMS").read_text(encoding="ascii")
        self.assertIn(f"{digest}  docs/research/evidence/mpc01-source-mapped-profile-20261102/README.txt\n", sums)
        self.assertNotIn("README.md", manifest["artifacts"])

    def test_strategy_ab_bundle_has_valid_checksums_and_reproducible_render(self):
        validator = ROOT / "scripts/reports/mpc01/validate_strategy_ab_ts03_bundle.py"
        result = subprocess.run([sys.executable, str(validator)], cwd=ROOT, check=True,
                                capture_output=True, text=True)
        self.assertIn("Validated immutable MPC-01 T-S03", result.stdout)

    def test_ts02_html_replay_does_not_add_an_unmanifested_markdown_file(self):
        script = ROOT / "scripts/reports/mpc01/summarize_strategy_ab_ts02.py"
        with tempfile.TemporaryDirectory(prefix="mpc01-ts02-replay-") as temporary:
            bundle = Path(temporary) / stage_module.STRATEGY_AB_TS02_ID
            shutil.copytree(stage_module.STRATEGY_AB_TS02_SOURCE, bundle)
            output = bundle / "strategy-ab-ts02-summary.html"
            subprocess.run([
                sys.executable, str(script),
                "--events", str(bundle / "strategy-ab-ts02-events.jsonl"),
                "--stdout", str(bundle / "strategy-ab-ts02-stdout.jsonl"),
                "--scenario", str(bundle / "scenario.json"),
                "--environment", str(bundle / "strategy-ab-ts02-environment.json"),
                "--resource-profile", str(bundle / "resource-profile.json"),
                "--record", str(bundle / "strategy-ab-ts02-comparison-record.json"),
                "--output", str(output),
            ], cwd=ROOT, check=True, capture_output=True, text=True)
            self.assertFalse(output.with_suffix(".md").exists())
            stage_module._check_manifest(bundle, stage_module.STRATEGY_AB_TS02_FILES)

    def test_route_preserves_source_bundle_and_links_from_root_landing(self):
        with tempfile.TemporaryDirectory(prefix="mpc01-pages-augmentation-") as temporary:
            site = Path(temporary)
            (site / "examples").mkdir()
            (site / "examples/index.html").write_text("<html><body>Examples</body></html>", encoding="utf-8")
            (site / "index.html").write_text("<html><body>Reports</body></html>", encoding="utf-8")

            route = stage_module.stage(site)

            self.assertEqual(route.name, stage_module.REPORT_ID)
            self.assertTrue((route / "b04-repeated-projections.svg").is_file())
            self.assertTrue((route / "comparison-records.jsonl").is_file())
            self.assertTrue((route / "attempt-139.stderr").is_file())
            summary = (route / "summary.json").read_bytes()
            self.assertEqual(summary, (stage_module.SOURCE / "summary.json").read_bytes())
            route_assets = (
                (stage_module.SOURCE, route, "benchmark-summary.txt", "benchmark-summary.md"),
                (stage_module.STRATEGY_AB_SOURCE,
                 site / stage_module.STRATEGY_AB_ROUTE,
                 "strategy-ab-ts03-summary.txt", "strategy-ab-ts03-summary.md"),
                (stage_module.STRATEGY_AB_SOURCE,
                 site / stage_module.STRATEGY_AB_ROUTE,
                 "build-note.txt", "build-note.md"),
                (stage_module.STRATEGY_AB_TS02_SOURCE,
                 site / stage_module.STRATEGY_AB_TS02_ROUTE,
                 "strategy-ab-ts02-summary.txt", "strategy-ab-ts02-summary.md"),
                (stage_module.STRATEGY_AB_TS01_SOURCE,
                 site / stage_module.STRATEGY_AB_TS01_ROUTE,
                 "strategy-ab-ts01-summary.txt", "strategy-ab-ts01-summary.md"),
            )
            for source_bundle, staged_bundle, source_name, route_name in route_assets:
                with self.subTest(asset=source_name):
                    self.assertFalse((source_bundle / route_name).exists())
                    self.assertEqual((staged_bundle / route_name).read_bytes(),
                                     (source_bundle / source_name).read_bytes())
                    self.assertIn(f"  {route_name}\n",
                                  (staged_bundle / "SHA256SUMS").read_text(encoding="ascii"))
                    self.assertNotIn(f"  {source_name}\n",
                                     (staged_bundle / "SHA256SUMS").read_text(encoding="ascii"))
            historical_summary = route / "benchmark-summary.md"
            self.assertEqual(hashlib.sha256(historical_summary.read_bytes()).hexdigest(),
                             "e8a3f56c88e300e6f787ad2033eb14bfbfbcceaa4c406376708ec125bfec70fa")
            self.assertIn(
                "e8a3f56c88e300e6f787ad2033eb14bfbfbcceaa4c406376708ec125bfec70fa  benchmark-summary.md\n",
                (route / "SHA256SUMS").read_text(encoding="ascii"))
            alias_root = site / "mpc01-source-mapped-profile-20261102"
            profile_source = (ROOT / "docs/research/evidence/mpc01-source-mapped-profile-20261102/README.txt").read_bytes()
            self.assertEqual((alias_root / "README.md").read_bytes(), profile_source)
            self.assertEqual((alias_root / "README.txt").read_bytes(), profile_source)
            historical_reference = "../mpc01-source-mapped-profile-20261102/README.md"
            resolved_historical = (historical_summary.parent / historical_reference).resolve()
            self.assertEqual(resolved_historical, (alias_root / "README.md").resolve())
            for line in (route / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
                digest, name = line.split("  ", 1)
                self.assertEqual(hashlib.sha256((route / name).read_bytes()).hexdigest(), digest, name)

            landing = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn(f'href="{stage_module.REPORT_ID}/index.html"', landing)
            strategy_route = site / stage_module.STRATEGY_AB_ROUTE
            self.assertTrue((strategy_route / "strategy-ab-ts03-summary.html").is_file())
            self.assertTrue((strategy_route / "strategy-ab-ts03-control-plane.svg").is_file())
            self.assertTrue((strategy_route / "comparison-record.json").is_file())
            self.assertTrue((strategy_route / "setup-attempts/supervisor-row-count-mismatch/events.jsonl").is_file())
            strategy_href = (f'href="{stage_module.STRATEGY_AB_ROUTE.as_posix()}/'
                             'strategy-ab-ts03-summary.html"')
            self.assertIn(strategy_href, landing)
            ts01_route = site / stage_module.STRATEGY_AB_TS01_ROUTE
            self.assertTrue((ts01_route / "comparison-record.json").is_file())
            self.assertTrue((ts01_route / "strategy-ab-ts01-control-plane.svg").is_file())
            ts01_href = (f'href="{stage_module.STRATEGY_AB_TS01_ROUTE.as_posix()}/'
                         'strategy-ab-ts01-summary.html"')
            self.assertIn(ts01_href, landing)
            ts01_page = (ts01_route / "strategy-ab-ts01-summary.html").read_text(encoding="utf-8")
            self.assertIn("5 measured pairs", ts01_page)
            self.assertIn("each individual Strategy A or Strategy B attempt", ts01_page)
            strategy_page = (strategy_route / "strategy-ab-ts03-summary.html").read_text(encoding="utf-8")
            self.assertIn("exact optimal family", strategy_page)
            self.assertIn("does not satisfy that limiter profile", strategy_page)
            self.assertTrue((site / "scripts/reports/mpc01/summarize_strategy_ab_ts03.py").is_file())
            report_page = (route / "index.html").read_text(encoding="utf-8")
            self.assertIn("not a closed-loop MPC run", report_page)
            self.assertIn("TwoPoints environment report", report_page)
            stage_module.validate(site)

            # All local links in the route page resolve inside the staged Pages tree.
            import re
            for reference in re.findall(r'(?:href|src)="([^"]+)"', report_page):
                parsed = urlparse(reference)
                if parsed.scheme or parsed.netloc:
                    continue
                target = (route / urldefrag(parsed.path)[0]).resolve()
                self.assertTrue(target.is_relative_to(site.resolve()), reference)
                self.assertTrue(target.is_file(), reference)

            for reference in re.findall(r'(?:href|src)="([^"]+)"', strategy_page):
                parsed = urlparse(reference)
                if parsed.scheme or parsed.netloc:
                    continue
                target = (strategy_route / urldefrag(parsed.path)[0]).resolve()
                self.assertTrue(target.is_relative_to(site.resolve()), reference)
                self.assertTrue(target.is_file(), reference)

            for reference in re.findall(r'(?:href|src)="([^"]+)"', ts01_page):
                parsed = urlparse(reference)
                if parsed.scheme or parsed.netloc:
                    continue
                target = (ts01_route / urldefrag(parsed.path)[0]).resolve()
                self.assertTrue(target.is_relative_to(site.resolve()), reference)
                self.assertTrue(target.is_file(), reference)


if __name__ == "__main__":
    unittest.main()
