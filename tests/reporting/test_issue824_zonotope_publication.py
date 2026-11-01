from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import stage_issue824_zonotope as publisher
sys.path.insert(0, str(ROOT / "scripts/reports/exp824"))
import make_report


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

    def test_captured_source_identity_rejects_tree_objects(self):
        source = ROOT / "reports/algorithm-results/issue824-two-points-zonotope-pilot-v2"
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / "changed"
            shutil.copytree(source, changed)
            capture_path = changed / "capture.json"
            capture = json.loads(capture_path.read_text(encoding="utf-8"))
            tree = subprocess.run(["git", "-C", str(ROOT), "show",
                f"{capture['source_commit']}:scripts"], check=True,
                capture_output=True).stdout
            capture["source_files_sha256"] = {"scripts": publisher.digest(tree)}
            capture_path.write_text(json.dumps(capture, indent=2) + "\n", encoding="utf-8")
            sums = {name: publisher.digest((changed / name).read_bytes())
                    for name in publisher.FILES if name != "SHA256SUMS"}
            (changed / "SHA256SUMS").write_text(
                "".join(f"{checksum}  {name}\n" for name, checksum in sums.items()),
                encoding="ascii")
            with self.assertRaisesRegex(ValueError, "unavailable as a blob: scripts"):
                publisher.verified_bundle(changed)

    def test_planar_projection_contains_all_four_rectangle_corners(self):
        source = ROOT / "reports/algorithm-results/issue824-two-points-zonotope-pilot-v2/result.json"
        result = json.loads(source.read_text(encoding="utf-8"))
        stage = result["planar_example"]["stages"][1]
        polygon = make_report.projected_zonotope(stage, 0, 1)
        self.assertEqual(len(polygon), 4)
        xs, ys = [point[0] for point in polygon], [point[1] for point in polygon]
        self.assertLessEqual(min(xs), -2.0)
        self.assertGreaterEqual(max(xs), 2.0)
        self.assertLessEqual(min(ys), -1.0)
        self.assertGreaterEqual(max(ys), 1.0)
        area = abs(sum(polygon[index][0] * polygon[(index + 1) % 4][1] -
                       polygon[index][1] * polygon[(index + 1) % 4][0]
                       for index in range(4))) / 2
        self.assertGreaterEqual(area, 8.0)


if __name__ == "__main__":
    unittest.main()
