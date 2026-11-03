"""Verify the saved MPC-01 route can augment an existing offline Pages site."""
from __future__ import annotations

import importlib.util
import hashlib
from pathlib import Path
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
            report_page = (route / "index.html").read_text(encoding="utf-8")
            self.assertIn("not a closed-loop MPC run", report_page)
            self.assertIn("TwoPoints environment report", report_page)
            stage_module.validate(site)

            # All local links in the route page resolve inside the staged Pages tree.
            import re
            for href in re.findall(r'href="([^"]+)"', report_page):
                parsed = urlparse(href)
                if parsed.scheme or parsed.netloc:
                    continue
                target = (route / urldefrag(href)[0]).resolve()
                self.assertTrue(target.is_relative_to(site.resolve()), href)
                self.assertTrue(target.is_file(), href)


if __name__ == "__main__":
    unittest.main()
