from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import stage_issue824_box_minimax as publisher
import visual_examples


class Issue824BoxMinimaxPublicationTests(unittest.TestCase):
    def test_verified_bundle_stages_without_rewriting_assets(self):
        files = publisher.verified_bundle(publisher.SOURCE)
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            self.assertEqual(publisher.stage(publisher.SOURCE, site), publisher.ROUTE)
            route = site / publisher.ROUTE
            self.assertEqual({item.name for item in route.iterdir()}, set(publisher.FILES))
            for name, content in files.items():
                self.assertEqual((route / name).read_bytes(), content)
            with self.assertRaisesRegex(ValueError, "route already exists"):
                publisher.stage(publisher.SOURCE, site)

    def test_bundle_rejects_tampered_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / "changed"
            shutil.copytree(publisher.SOURCE, changed)
            with (changed / "result.json").open("ab") as stream:
                stream.write(b" ")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                publisher.verified_bundle(changed)

    def test_bundle_contains_both_player_projections_and_replay(self):
        figure = publisher.verified_bundle(publisher.SOURCE)["projections.svg"].decode()
        for label in ("x1 position", "x2 velocity", "x3 position", "x4 velocity",
                      "Box-selected plan replay"):
            self.assertIn(label, figure)

    def test_gallery_card_links_the_box_report(self):
        entry = next(row for row in visual_examples.SAVED_FIGURES
                     if row.get("route") == publisher.ROUTE)
        self.assertEqual(entry["records"], "result.json")
        self.assertEqual(entry["page"], "index.html")
        self.assertEqual(entry["image"], "projections.svg")


if __name__ == "__main__":
    unittest.main()
