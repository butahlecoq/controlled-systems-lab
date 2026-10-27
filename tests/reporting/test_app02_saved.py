"""Check APP-02 saved numerical evidence and exact-byte regeneration."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
spec = importlib.util.spec_from_file_location("app02_render_test", ROOT / "scripts/reports/app02/render_saved.py")
render = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(render)
BUNDLE = ROOT / "reports/algorithm-results/app02-box-8ff979de60ea9d22"
CATALOG = ROOT / "reports/algorithm-results/app02-publications.json"


def snapshot(root: Path):
    return {path.relative_to(root).as_posix():
            ("symlink", str(path.readlink())) if path.is_symlink() else
            ("file", path.read_bytes()) if path.is_file() else ("directory", None)
            for path in root.rglob("*")}


def catalog_with_saved_bundle(path: Path) -> Path:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    shutil.copytree(BUNDLE, path.parent / data["reports"][0]["report_id"])
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class SavedApp02Test(unittest.TestCase):
    def test_raw_cases_regenerate_complete_report(self) -> None:
        render.render(BUNDLE, check=True)
        record = render.validate(BUNDLE)
        self.assertEqual(record["source_commit"],
                         "8fecba49e34c37e5e01c40218a8f014a179818fd")
        self.assertEqual([row["case"] for row in record["measurement"]["summary"]],
                         list(render.collect.CASES))
        self.assertEqual(sum(row["successes"] for row in record["measurement"]["summary"]),
                         3500)
        self.assertEqual(sum(row["failures"] for row in record["measurement"]["summary"]), 0)

    def test_changed_raw_timing_cannot_keep_the_saved_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / BUNDLE.name
            shutil.copytree(BUNDLE, copy)
            raw = copy / "measure.csv"
            raw.write_bytes(raw.read_bytes().replace(b"warmup,interval-box,0,100,enclosed,true,",
                                                   b"warmup,interval-box,0,100,enclosed,false,"))
            with self.assertRaises(ValueError):
                render.render(copy, check=True)

    def test_staging_writes_reviewed_routes_only_after_complete_validation(self) -> None:
        import stage_app02
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            site_dir = Path(temporary) / "site"
            site_dir.mkdir()
            (site_dir / "index.html").write_text(
                "<html><body><h1>Reports</h1><ul><li>Existing</li></ul></body></html>", encoding="utf-8")
            catalog = catalog_with_saved_bundle(root / "catalog.json")
            report_id = stage_app02.stage(catalog, site_dir)
            self.assertEqual((site_dir / report_id / "records.json").read_bytes(),
                             (BUNDLE / "records.json").read_bytes())
            self.assertTrue((site_dir / "app02-example/polygons.svg").is_file())
            self.assertIn("app02-example/index.html", (site_dir / "index.html").read_text())

    def test_invalid_second_catalog_entry_leaves_site_bytes_unchanged(self) -> None:
        import stage_app02
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            site_dir = root / "site"
            site_dir.mkdir()
            index = site_dir / "index.html"
            index.write_text("<html><body><ul></ul></body></html>", encoding="utf-8")
            catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
            catalog["reports"].append(dict(catalog["reports"][0]))
            broken_catalog = root / "catalog.json"
            broken_catalog.write_text(json.dumps(catalog), encoding="utf-8")
            before = snapshot(site_dir)
            with self.assertRaisesRegex(ValueError, "catalog differs"):
                stage_app02.stage(broken_catalog, site_dir)
            self.assertEqual(snapshot(site_dir), before)

    def test_missing_or_ambiguous_index_insertion_leaves_site_bytes_unchanged(self) -> None:
        import stage_app02
        for index_text in ("<html><body><p>no list</p></body></html>",
                           "<html><body><ul></ul><ul></ul></body></html>"):
            with self.subTest(index=index_text), tempfile.TemporaryDirectory() as temporary:
                site_dir = Path(temporary) / "site"
                site_dir.mkdir()
                (site_dir / "index.html").write_text(index_text, encoding="utf-8")
                catalog = catalog_with_saved_bundle(Path(temporary) / "catalog.json")
                before = snapshot(site_dir)
                with self.assertRaisesRegex(ValueError, "insertion point"):
                    stage_app02.stage(catalog, site_dir)
                self.assertEqual(snapshot(site_dir), before)

    def test_commit_io_failure_keeps_existing_index_and_reports_partial_additions(self) -> None:
        import stage_app02
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            site_dir = Path(temporary) / "site"
            site_dir.mkdir()
            index = site_dir / "index.html"
            index.write_text("<html><body><ul></ul></body></html>", encoding="utf-8")
            original_index = index.read_bytes()
            catalog = catalog_with_saved_bundle(root / "catalog.json")
            real_commit = stage_app02.site_additions.commit

            def fail_after_one(plan):
                writes = 0

                def writer(path, content):
                    nonlocal writes
                    writes += 1
                    if writes == 2:
                        raise OSError("injected commit failure")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)

                real_commit(plan, writer=writer)

            with patch.object(stage_app02.site_additions, "commit", side_effect=fail_after_one):
                with self.assertRaisesRegex(OSError, "injected commit failure"):
                    stage_app02.stage(catalog, site_dir)
            self.assertEqual(index.read_bytes(), original_index)
            self.assertTrue(any(path.is_file() for path in site_dir.rglob("*")))


if __name__ == "__main__":
    unittest.main()
