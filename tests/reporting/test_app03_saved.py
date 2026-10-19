"""Check APP-03 saved public calls and exact-byte report regeneration."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "app03_render_test", ROOT / "scripts/reports/app03/render_saved.py")
render = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(render)
BUNDLE = ROOT / "reports/algorithm-results/app03-zonotope-4522855018fa9b0b"


class SavedApp03Test(unittest.TestCase):
    def test_verified_trials_regenerate_the_2d_report(self) -> None:
        render.render(BUNDLE, check=True)
        record = render.validate(BUNDLE)
        self.assertEqual(record["source_commit"],
                         "e105a86b8e2ab7d09b1e7042fc5f0d5bc0ce5c40")
        self.assertEqual([row["case"] for row in record["measurement"]["summary"]],
                         list(render.collect.CASES))
        self.assertEqual(sum(row["successes"] for row in record["measurement"]["summary"]),
                         2100)
        self.assertEqual(sum(row["failures"] for row in record["measurement"]["summary"]), 0)
        self.assertIn(b"Input planar zonotope", (BUNDLE / "zonotope-2d.svg").read_bytes())

    def test_changed_public_outcome_invalidates_saved_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / BUNDLE.name
            shutil.copytree(BUNDLE, copy)
            raw = copy / "measure.csv"
            raw.write_bytes(raw.read_bytes().replace(
                b"trial,diamond-axis-cover,0,100,completed,true,",
                b"trial,diamond-axis-cover,0,100,completed,false,", 1))
            with self.assertRaises(ValueError):
                render.render(copy, check=True)


if __name__ == "__main__":
    unittest.main()
