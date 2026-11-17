"""Check the frozen four-state approximation report and gallery integration."""

from __future__ import annotations

import csv
import importlib
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))

stage = importlib.import_module("stage_four_state_projection_approximations")
visual_examples = importlib.import_module("visual_examples")


class FourStateProjectionApproximationPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "reports/algorithm-results" / stage.ROUTE
        shutil.copytree(ROOT / "reports/algorithm-results" / stage.ROUTE, self.bundle)

    def test_saved_rows_bundle_and_gallery_entry_are_consistent(self) -> None:
        outputs, entries, card = stage.build(self.root)
        manifest = json.loads((self.bundle / "manifest.json").read_text(encoding="utf-8"))
        with (self.bundle / "approximation-summary.csv").open(encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 128)
        self.assertTrue(
            all(all(int(row[f"rep{index}_ns"]) > 0 for index in range(5)) for row in rows)
        )
        self.assertEqual(manifest["run_scope"]["approximation_calls"], len(rows))
        self.assertEqual(len(entries), 1)
        self.assertIn(entries[0]["figure"], outputs)
        self.assertIn(entries[0]["raw_record"], outputs)
        self.assertIn(f'id="{stage.ROUTE}"', card)

        with zipfile.ZipFile(self.bundle / f"{stage.ROUTE}.zip") as archive:
            names = set(archive.namelist())
            self.assertIn("manifest.json", names)
            self.assertIn("approximation-summary.csv", names)
            self.assertEqual(len(names), len(archive.namelist()))

        examples = self.root / "site/examples"
        examples.mkdir(parents=True)
        for name, content in outputs.items():
            target = examples / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        index = (
            '<!doctype html><html lang="en"><body><section id="saved-report-figures">'
            + card
            + "</section></body></html>"
        )
        (examples / "index.html").write_text(index, encoding="utf-8")
        visual_examples.validate_gallery_inventory(examples, entries)

    def test_changed_saved_figure_is_rejected(self) -> None:
        figure = self.bundle / "x1-x2-approximation-stages.svg"
        figure.write_bytes(figure.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "asset hash differs"):
            stage.build(self.root)


if __name__ == "__main__":
    unittest.main()
