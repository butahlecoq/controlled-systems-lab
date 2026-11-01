from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/reports/stage_issue824_nominal.py"
SPEC = importlib.util.spec_from_file_location("issue824_nominal_stage", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
STAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAGER)


class Issue824NominalPublicationTest(unittest.TestCase):
    def test_verified_bundle_stages_with_exact_inventory(self) -> None:
        bundle = ROOT / "reports/algorithm-results/issue824-two-points-nominal-v1"
        files = STAGER.verified_bundle(bundle)
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            self.assertEqual(STAGER.stage(bundle, site), "issue824-two-points-nominal-v1")
            staged = site / "issue824-two-points-nominal-v1"
            self.assertEqual({path.name for path in staged.iterdir()}, set(files))
            self.assertEqual((staged / "projections.svg").read_bytes(), files["projections.svg"])

    def test_existing_route_is_not_overwritten(self) -> None:
        bundle = ROOT / "reports/algorithm-results/issue824-two-points-nominal-v1"
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            route = site / "issue824-two-points-nominal-v1"
            route.mkdir()
            sentinel = route / "keep.txt"
            sentinel.write_text("authored", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                STAGER.stage(bundle, site)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "authored")


if __name__ == "__main__":
    unittest.main()
