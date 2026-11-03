from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


resource = load_module("csl_ext07_resource_test", ROOT /
                       "scripts/reports/ext07/resource_observation.py")
stager = load_module("csl_ext07_resource_stager_test", ROOT /
                     "scripts/reports/stage_ext07.py")
landing = load_module("csl_ext07_resource_landing_test", ROOT /
                      "scripts/reports/landing.py")


class Ext07ResourceObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        candidates = sorted((ROOT / "reports/algorithm-results").glob(
            "ext07-resource-observation-*"))
        cls.bundle = next((path for path in candidates if path.is_dir()), None)
        if cls.bundle is None:
            raise unittest.SkipTest("EXT-07 resource report is built from saved captures")

    def test_saved_resource_bundle_regenerates_exactly(self) -> None:
        result = resource.render(self.bundle, check=True)
        self.assertEqual(result["report_id"], self.bundle.name)
        record = resource.read_json(self.bundle / "records.json")
        self.assertEqual(record["profiles"]["one_step"]["measured_calls"], 140)
        self.assertEqual(record["profiles"]["two_parameter"]["measured_calls"], 140)
        self.assertEqual(record["profiles"]["two_parameter"]["resource_observation"]
                         ["observed"]["swap_peak_bytes"], 0)

    def test_stager_publishes_nested_resource_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / self.bundle.name
            shutil.copytree(self.bundle, bundle)
            parent_source = ROOT / "reports/algorithm-results/ext07-hybrid-51d9ee2e89d240eb"
            parent = root / parent_source.name
            shutil.copytree(parent_source, parent)
            catalog = root / "ext07-publications.json"
            catalog.write_text(resource.encoded({
                "schema": "csl.ext07-publications/1",
                "reports": [stager.catalog_entry(bundle), stager.catalog_entry(parent)],
            }).decode(), encoding="utf-8")
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text(
                "<!doctype html><html lang=\"en\"><body><ul></ul></body></html>",
                encoding="utf-8")
            self.assertEqual(stager.stage(catalog, site),
                             self.bundle.name + "," + parent.name)
            self.assertTrue((site / self.bundle.name / "one_step" /
                             "resource-observation.json").is_file())
            self.assertIn("resource-scope.svg", (site / "index.html").read_text(
                encoding="utf-8"))
            self.assertNotIn('id="visual-examples-link"',
                             (site / "index.html").read_text(encoding="utf-8"))
            self.assertEqual((site / "index.html").read_text(encoding="utf-8").count("<li>"), 1)
            landing.build(site)
            page = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn("EXT-07 bounded resource observations", page)
            self.assertIn(self.bundle.name + "/index.html", page)

    def test_current_ext07_catalog_stages_all_report_routes(self) -> None:
        catalog = ROOT / "reports/algorithm-results/ext07-publications.json"
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary) / "site"
            site.mkdir()
            (site / "index.html").write_text(
                "<!doctype html><html lang=\"en\"><body><ul></ul></body></html>",
                encoding="utf-8")
            staged = stager.stage(catalog, site)
            self.assertEqual(staged.split(",")[-1], self.bundle.name)
            self.assertTrue((site / self.bundle.name / "two_parameter" /
                             "resource-observation.json").is_file())

    def test_resource_report_requires_a_hybrid_profile_route(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / self.bundle.name
            shutil.copytree(self.bundle, bundle)
            catalog = root / "ext07-publications.json"
            catalog.write_text(resource.encoded({
                "schema": "csl.ext07-publications/1",
                "reports": [stager.catalog_entry(bundle)],
            }).decode(), encoding="utf-8")
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text(
                "<!doctype html><html lang=\"en\"><body><ul></ul></body></html>",
                encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "require a hybrid report route"):
                stager.stage(catalog, site)
            self.assertEqual([path.name for path in site.iterdir()], ["index.html"])

    def test_bundle_excludes_machine_local_build_paths(self) -> None:
        for path in self.bundle.rglob("*"):
            if path.is_file():
                content = path.read_bytes()
                self.assertNotIn(b"/home/butahlecoq", content, str(path))
                self.assertNotIn(b"/var/tmp/ext07-resource-capture", content, str(path))

    def test_shared_landing_source_hash_for_frozen_b04_bundle_is_preserved(self) -> None:
        bundle = ROOT / "reports/algorithm-results/b04-c-exact-dyadic-v1"
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        expected = manifest["source_files"]["scripts/reports/landing.py"]
        actual = hashlib.sha256(
            (ROOT / "scripts/reports/landing.py").read_bytes()).hexdigest()
        self.assertEqual(actual, expected)

    def test_saved_bundle_rejects_changed_capture_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / self.bundle.name
            shutil.copytree(self.bundle, bundle)
            path = bundle / "two_parameter" / "resource-observation.json"
            path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaises(ValueError):
                resource.render(bundle, check=True)

    def test_saved_bundle_rejects_mismatched_enforced_cpu_quota(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / self.bundle.name
            shutil.copytree(self.bundle, bundle)
            record = resource.read_json(bundle / "records.json")
            profile = record["profiles"]["one_step"]
            profile["resource_observation"]["enforced_limits"][
                "cpu_quota_per_second_usec"] = 999_999
            receipt_path = bundle / "one_step" / "resource-observation.json"
            receipt = resource.read_json(receipt_path)
            receipt["enforced_limits"]["cpu_quota_per_second_usec"] = 999_999
            receipt_path.write_bytes(resource.encoded(receipt))
            unsigned = {key: value for key, value in record.items()
                        if key != "report_id"}
            record["report_id"] = resource.PREFIX + resource.sha(
                resource.encoded(unsigned))[:16]
            (bundle / "records.json").write_bytes(resource.encoded(record))
            tampered = root / record["report_id"]
            bundle.rename(tampered)
            with self.assertRaisesRegex(ValueError, "raw capture"):
                resource.render(tampered, check=True)


if __name__ == "__main__":
    unittest.main()
