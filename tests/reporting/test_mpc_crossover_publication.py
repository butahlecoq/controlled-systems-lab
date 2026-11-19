"""Verify the same frozen study is reachable from the gallery and evidence archive."""

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
landing = importlib.import_module("landing")
stage = importlib.import_module("stage_mpc_crossover")


class CrossoverPublicationTests(unittest.TestCase):
    def test_gallery_and_archive_link_the_verified_study(self) -> None:
        files, [entry], gallery_card = stage.build(ROOT)
        self.assertIn(f'href="{entry["page"]}"', gallery_card)
        for key in ("page", "figure", "raw_record"):
            self.assertIn(entry[key], files)

        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            for name, content in files.items():
                path = site / "examples" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            index = site / "index.html"
            index.write_text("<ul></ul>", encoding="utf-8")
            (site / "archive.html").touch()
            landing.build(site)
            first = index.read_bytes()
            landing.build(site)
            self.assertEqual(index.read_bytes(), first)
            [card], _ = landing.parse_index(first.decode())
            self.assertEqual(card.report_id + "/index.html", "examples/" + entry["page"])
            self.assertEqual(card.commit, stage.IDENTITY.source_commit)
            self.assertIn("workload", card.scope)
            self.assertIn("host", card.limits)
            self.assertEqual(
                {Path(path).suffix for _, path in card.links},
                {".jsonl", ".json", ".zip"},
            )
