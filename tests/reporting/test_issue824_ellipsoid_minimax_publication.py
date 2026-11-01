from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import stage_issue824_zonotope as previous_publisher
import stage_issue824_ellipsoid_minimax as publisher
import visual_examples


class Issue824EllipsoidMinimaxPublicationTests(unittest.TestCase):
    def test_previous_bundle_still_stages_from_its_captured_source_commit(self):
        source = ROOT / "reports/algorithm-results/issue824-two-points-zonotope-pilot-v2"
        files = previous_publisher.verified_bundle(source)
        capture = json.loads(files["capture.json"])
        self.assertTrue(capture["source_tree_clean_before_report_generation"])
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            route = previous_publisher.stage(source, site)
            staged = site / route
            self.assertEqual({item.name for item in staged.iterdir()}, set(previous_publisher.FILES))
            for name, content in files.items():
                self.assertEqual((staged / name).read_bytes(), content)

    def test_verified_minimax_bundle_stages_without_rewriting_assets(self):
        source = ROOT / "reports/algorithm-results/issue824-two-points-ellipsoid-minimax-v1"
        files = publisher.verified_bundle(source)
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            self.assertEqual(publisher.stage(source, site), publisher.ROUTE)
            route = site / publisher.ROUTE
            self.assertEqual({item.name for item in route.iterdir()}, set(publisher.FILES))
            for name, content in files.items():
                self.assertEqual((route / name).read_bytes(), content)
            with self.assertRaisesRegex(ValueError, "route already exists"):
                publisher.stage(source, site)

    def test_minimax_bundle_rejects_record_tampering(self):
        source = ROOT / "reports/algorithm-results/issue824-two-points-ellipsoid-minimax-v1"
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / "changed"
            shutil.copytree(source, changed)
            with (changed / "result.json").open("ab") as stream:
                stream.write(b" ")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                publisher.verified_bundle(changed)

    def test_gallery_card_links_the_live_minimax_bundle(self):
        entry = next(row for row in visual_examples.SAVED_FIGURES
                     if row.get("route") == publisher.ROUTE)
        self.assertEqual(entry["records"], "result.json")
        self.assertEqual(entry["page"], "ellipsoid-planar-example.html")
        self.assertEqual(entry["image"], "ellipsoid-planar-example.svg")


if __name__ == "__main__":
    unittest.main()
