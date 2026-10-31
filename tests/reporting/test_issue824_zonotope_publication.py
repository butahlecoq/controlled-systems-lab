from pathlib import Path
import sys
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import stage_issue824_zonotope as publisher


class Issue824ZonotopePublicationTests(unittest.TestCase):
    def test_verified_bundle_stages_as_gallery_route_without_rewriting_assets(self):
        source = ROOT / "reports/algorithm-results/issue824-two-points-zonotope-pilot-v2"
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

    def test_bundle_contains_verified_planar_example_and_rejects_tampering(self):
        source = ROOT / "reports/algorithm-results/issue824-two-points-zonotope-pilot-v2"
        files = publisher.verified_bundle(source)
        self.assertIn("planar-example.svg", files)
        self.assertIn("planar_zonotope_inclusion", files["check.json"].decode())
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / "changed"
            shutil.copytree(source, changed)
            with (changed / "result.json").open("ab") as stream:
                stream.write(b" ")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                publisher.verified_bundle(changed)


if __name__ == "__main__":
    unittest.main()
