from __future__ import annotations

import importlib.util
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


render_saved = load_module("csl_ext07_test_renderer", ROOT / "scripts/reports/ext07/render_saved.py")
stage_ext07 = load_module("csl_ext07_test_stager", ROOT / "scripts/reports/stage_ext07.py")
collect = render_saved.collect


class Ext07SavedReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        bundles = sorted((ROOT / "reports/algorithm-results").glob("ext07-hybrid-*"))
        cls.bundle = next((path for path in bundles if path.is_dir()), None)
        cls.two_parameter_bundle = next(
            (path for path in bundles if path.is_dir() and
             path.name.startswith("ext07-hybrid-two-parameter-")), None)
        if cls.bundle is None:
            raise unittest.SkipTest("EXT-07 report bundle is created from a frozen measured source")

    def test_saved_report_rebuilds_and_catalogue_binds_every_file(self) -> None:
        self.assertEqual(render_saved.render(self.bundle, check=True)["report_id"], self.bundle.name)
        entry = stage_ext07.catalog_entry(self.bundle)
        self.assertEqual(entry["source_commit"], collect.read_json(self.bundle / "records.json")["source_commit"])
        self.assertEqual(entry["collector_sha256"], collect.sha(
            (ROOT / "scripts/reports/ext07/ext07_collect.py").read_bytes()))
        self.assertEqual(entry["zip_sha256"], collect.sha((self.bundle / (self.bundle.name + ".zip")).read_bytes()))

    def test_stager_copies_only_the_validated_bundle_and_adds_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged_bundle = root / self.bundle.name
            shutil.copytree(self.bundle, staged_bundle)
            catalog = root / "ext07-publications.json"
            catalog.write_text(json.dumps({"schema": "csl.ext07-publications/1",
                                           "reports": [stage_ext07.catalog_entry(staged_bundle)]}),
                               encoding="utf-8")
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text(
                "<!doctype html><html lang=\"en\"><body><ul></ul></body></html>", encoding="utf-8")
            self.assertEqual(stage_ext07.stage(catalog, site), self.bundle.name)
            self.assertTrue((site / self.bundle.name / "example-2d.html").is_file())
            self.assertIn("example-2d.html", (site / "index.html").read_text(encoding="utf-8"))

    def test_published_example_has_complete_inputs_reproduction_and_provenance(self) -> None:
        record = collect.read_json(self.bundle / "records.json")
        source = record["source_commit"]
        scenario = record["scenario"]
        page = (self.bundle / "example-2d.html").read_text(encoding="utf-8")
        self.assertEqual(scenario["allowed_terminal_modes"], ["terminal"])
        self.assertEqual(scenario["terminal_mode_data"], {
            "flow": {"A": [[1]], "B": [[1]], "offset": [0]},
            "control_set": "universal",
            "active_stages": [1],
            "flow_used_by_horizon": False,
        })
        for phrase in ("state dimension is one", "one stage", "initial mode is", "coast-to-terminal",
                       "allowed terminal set is the singleton", "terminal-mode flow has",
                       "universal control set", "because the horizon ends at stage 1",
                       "mode invariants are universal",
                       "sets (they impose no additional state restrictions)", "no external channels",
                       "x₀=0", "u₀∈[0,1]", "x_pre∈[0,0.5]", "identity reset", "minimize x₁",
                       "scripts/reports/ext07/capture.py", "scripts/reports/ext07/ext07_collect.py"):
            self.assertIn(phrase, page)
        self.assertLess(page.index("ext07_collect.py"), page.index("render_saved.py --bundle", page.index("Reproduce")))
        render_lines = [line for line in page.splitlines() if "render_saved.py --bundle" in line]
        self.assertEqual(len(render_lines), 2)
        self.assertIn("--check", render_lines[1])
        self.assertNotIn("--check", render_lines[0])
        self.assertIn('href="records.json"', page)
        self.assertIn(f'href="https://github.com/butahlecoq/controlled-systems-lab/commit/{source}"', page)
        self.assertIn(f'commit {source}', page)

    def test_offline_html_allows_only_repository_commit_links(self) -> None:
        source = collect.read_json(self.bundle / "records.json")["source_commit"]
        source_url = f"https://github.com/butahlecoq/controlled-systems-lab/commit/{source}"
        stage_ext07.site.OfflineHTML(set()).feed(f'<a href="{source_url}">source</a>')
        for url in (f"https://github.com/another/repository/commit/{source}",
                    "https://github.com/butahlecoq/controlled-systems-lab/commit/not-a-hash",
                    f"http://github.com/butahlecoq/controlled-systems-lab/commit/{source}"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                stage_ext07.site.OfflineHTML(set()).feed(f'<a href="{url}">source</a>')

    def test_report_identity_rejects_tampered_raw_trial(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / self.bundle.name
            shutil.copytree(self.bundle, copied)
            with (copied / "measure.jsonl").open("a", encoding="utf-8") as stream:
                stream.write("{}\n")
            with self.assertRaises(ValueError):
                render_saved.validate(copied)

    def test_two_parameter_report_and_visual_example_rebuild_from_saved_rows(self) -> None:
        if self.two_parameter_bundle is None:
            self.skipTest("Two-parameter bundle is created from a frozen Release capture")
        renderer = load_module(
            "csl_ext07_two_parameter_test_renderer",
            ROOT / "scripts/reports/ext07/two_parameter_render_saved.py")
        self.assertEqual(renderer.render(self.two_parameter_bundle, check=True)
                         ["report_id"], self.two_parameter_bundle.name)
        record = renderer.validate(self.two_parameter_bundle)
        self.assertEqual(record["analytic"]["global_minimum"], 0)
        self.assertEqual(record["analytic"]["tied_paths"], ["enter-half", "enter-full"])
        self.assertEqual(record["measurement"]["measured_calls"], 140)
        example = (self.two_parameter_bundle / "two-control-example.html").read_text(
            encoding="utf-8")
        self.assertIn("u0 &lt;= 0.5", example)
        self.assertIn("u0 = 0, 0 &lt;= u1 &lt;= 1", example)
        self.assertIn("two_parameter_driver.cpp", example)

    def test_stager_publishes_both_ext07_report_profiles(self) -> None:
        if self.two_parameter_bundle is None:
            self.skipTest("Two-parameter bundle is created from a frozen Release capture")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundles = (self.bundle, self.two_parameter_bundle)
            copied = []
            for source in bundles:
                destination = root / source.name
                shutil.copytree(source, destination)
                copied.append(destination)
            catalog = root / "ext07-publications.json"
            catalog.write_text(json.dumps({
                "schema": "csl.ext07-publications/1",
                "reports": [stage_ext07.catalog_entry(bundle) for bundle in copied],
            }), encoding="utf-8")
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text(
                "<!doctype html><html lang=\"en\"><body><ul></ul></body></html>",
                encoding="utf-8")
            staged = stage_ext07.stage(catalog, site)
            self.assertEqual(staged, ",".join(bundle.name for bundle in copied))
            self.assertTrue((site / copied[0].name / "example-2d.html").is_file())
            self.assertTrue((site / copied[1].name / "two-control-example.html").is_file())
            index = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn("two-control-example.html", index)
            self.assertIn("example-2d.html", index)

    def test_stager_validates_all_catalog_entries_before_writing(self) -> None:
        if self.two_parameter_bundle is None:
            self.skipTest("Two-parameter bundle is created from a frozen Release capture")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copied = []
            for source in (self.bundle, self.two_parameter_bundle):
                destination = root / source.name
                shutil.copytree(source, destination)
                copied.append(destination)
            entries = [stage_ext07.catalog_entry(bundle) for bundle in copied]
            entries[1]["zip_sha256"] = "0" * 64
            catalog = root / "ext07-publications.json"
            catalog.write_text(json.dumps({"schema": "csl.ext07-publications/1",
                                           "reports": entries}), encoding="utf-8")
            site = root / "site"
            site.mkdir()
            original_index = "<!doctype html><html lang=\"en\"><body><ul></ul></body></html>"
            (site / "index.html").write_text(original_index, encoding="utf-8")
            with self.assertRaises(ValueError):
                stage_ext07.stage(catalog, site)
            self.assertFalse((site / copied[0].name).exists())
            self.assertFalse((site / copied[1].name).exists())
            self.assertEqual((site / "index.html").read_text(encoding="utf-8"), original_index)


if __name__ == "__main__":
    unittest.main()
