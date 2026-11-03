"""Verify the saved MPC-01 route can augment an existing offline Pages site."""
from __future__ import annotations

import importlib.util
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import urldefrag, urlparse

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/reports/mpc01/stage_per_attempt.py"
SPEC = importlib.util.spec_from_file_location("mpc01_stage_per_attempt", SCRIPT)
stage_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage_module)


class PerAttemptPublicationTests(unittest.TestCase):
    def test_strategy_ab_bundle_has_valid_checksums_and_reproducible_render(self):
        validator = ROOT / "scripts/reports/mpc01/validate_strategy_ab_ts03_bundle.py"
        result = subprocess.run([sys.executable, str(validator)], cwd=ROOT, check=True,
                                capture_output=True, text=True)
        self.assertIn("Validated immutable MPC-01 T-S03", result.stdout)

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
