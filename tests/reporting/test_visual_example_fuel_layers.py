"""Verify the saved fuel-layer gallery publisher."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))

import visual_example_fuel_layers as example  # noqa: E402


class FuelLayersExampleTests(unittest.TestCase):
    def test_stages_all_local_assets_and_gallery_links(self):
        assets, inventory, card = example.build(ROOT)
        source = ROOT / "docs/examples" / example.ROUTE
        self.assertEqual(
            assets,
            {f"{example.ROUTE}/{path.name}": path.read_bytes() for path in source.iterdir()},
        )
        [entry] = inventory
        for field in ("page", "figure", "raw_record"):
            self.assertIn(entry[field], assets)
        self.assertIn(entry["anchor"], card)

    def test_refuses_linked_fuel_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            relative = Path("docs/examples") / example.ROUTE
            source = root / relative
            shutil.copytree(ROOT / relative, source)
            chart = source / example.FIGURE
            held = root / "held.png"
            chart.rename(held)
            chart.symlink_to(held)
            with self.assertRaisesRegex(ValueError, "linked fuel"):
                example.build(root)
