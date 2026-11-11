from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.reports import pages_route_retirement as retirement


class PagesRouteRetirementTests(unittest.TestCase):
    def make_site(self, root: Path, *, gallery: str | None = None,
                  route: str | None = None) -> tuple[Path, str]:
        site = root / "site"
        (site / "examples").mkdir(parents=True)
        (site / "examples/examples.css").write_text("body{color:inherit}")
        route = route or next(iter(retirement.BARE_ROUTE_LESSONS))
        (site / "catalog.json").write_text(json.dumps({
            "schema": "csl.algorithm-report-catalog/3",
            "reports": [{"report_id": route.split("/", 1)[0], "report_kind": "finite-feedback"}],
        }))
        (site / route).parent.mkdir(parents=True)
        (site / route).write_text("<!doctype html><html><body><h1>Saved report</h1></body></html>")
        replacement = retirement.BARE_ROUTE_REPLACEMENTS.get(route)
        if replacement:
            replacement_path = site / replacement.split("#", 1)[0]
            replacement_path.parent.mkdir(parents=True, exist_ok=True)
            replacement_path.write_text("<!doctype html><html><body><h1>Related example</h1></body></html>")
        (site / "index.html").write_text(
            f'<!doctype html><html><body><ul><li><a href="{route}">Bare report</a></li></ul></body></html>')
        (site / "examples/index.html").write_text(gallery or
            f'<!doctype html><html><body><h1 id="algorithm-coverage">Examples</h1><a href="../index.html">All numerical reports ↗</a>'
            f'<a href="../{route}">Saved report</a></body></html>')
        with zipfile.ZipFile(site / (route.split("/", 1)[0] + ".zip"), "w") as archive:
            archive.writestr("result.json", '{"saved":true}\n')
        return site, route

    def test_finalization_is_idempotent_and_keeps_evidence_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site, route = self.make_site(Path(temporary))
            original_root = (site / "index.html").read_bytes()
            report_page = site / route
            report_hash = hashlib.sha256(report_page.read_bytes()).hexdigest()
            archive_path = site / (route.split("/", 1)[0] + ".zip")
            zip_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()

            first = retirement.finalize(site, source_commit="fixture")
            legacy = (site / "legacy-index.html").read_bytes()
            second = retirement.finalize(site, source_commit="fixture")

            self.assertEqual(legacy, original_root)
            self.assertEqual((site / "legacy-index.html").read_bytes(), legacy)
            self.assertEqual(hashlib.sha256(archive_path.read_bytes()).hexdigest(), zip_hash)
            self.assertEqual(hashlib.sha256(report_page.read_bytes()).hexdigest(), report_hash)
            self.assertEqual(first["html_route_count"], second["html_route_count"])
            self.assertEqual(second["navigation_transition"]["new_root_report_link_count"], 0)
            self.assertIn(route, (site / "archive.html").read_text())
            self.assertIn("../archive.html#", (site / "examples/index.html").read_text())
            self.assertNotIn("../" + route, (site / "examples/index.html").read_text())
            self.assertIn(route, second["html_routes"])
            self.assertEqual(second["artifact_transition"]["preserved_immutable_html"],
                             sorted([route, "examples/finite-feedback-timing-v1.html"]))
            self.assertEqual(second["artifact_transition"]["preserved_zip_routes"], [archive_path.name])
            self.assertIn('class="shell"', (site / "index.html").read_text())
            self.assertIn('class="report-home"', (site / "index.html").read_text())
            self.assertIn('class="coverage-row"', (site / "archive.html").read_text())

            (site / "late-report").mkdir()
            (site / "late-report/index.html").write_text("<!doctype html><html><body>Late</body></html>")
            catalog = json.loads((site / "catalog.json").read_text())
            catalog["reports"].append({"report_id": "late-report", "report_kind": "finite-feedback"})
            (site / "catalog.json").write_text(json.dumps(catalog))
            third = retirement.finalize(site, source_commit="fixture")
            self.assertIn("late-report/index.html", third["html_routes"])
            self.assertIn("late-report/index.html", (site / "archive.html").read_text())

    def test_finalization_retains_pre_augmentation_root_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site, _ = self.make_site(Path(temporary))
            original_root = (site / "index.html").read_bytes()
            (site / "index.html").write_bytes(original_root + b'<p id="augmentation">Added later</p>')

            retirement.finalize(site, source_commit="fixture", original_root_bytes=original_root)

            self.assertEqual((site / "legacy-index.html").read_bytes(), original_root)

    def test_archive_links_orphaned_named_report_after_root_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site, _ = self.make_site(Path(temporary))
            route = "docs/research/evidence/fixture/strategy-summary.html"
            report = site / route
            report.parent.mkdir(parents=True)
            report.write_text("<!doctype html><html><body><h1>Named report</h1></body></html>")
            original_root = (site / "index.html").read_bytes()
            (site / "index.html").write_text(
                '<html><body><a href="' + route + '">Strategy summary</a></body></html>')

            result = retirement.finalize(site, source_commit="fixture", original_root_bytes=original_root)

            archive = (site / "archive.html").read_text()
            self.assertIn(f'href="{route}"', archive)
            self.assertIn("archive.html", result["html_routes"][route]["inbound_html_references"])
            self.assertEqual(result["navigation_transition"]["ordinary_archive_html_routes"].count(route), 1)

    def test_bad_figure_link_fails_before_writing_navigation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site, _ = self.make_site(Path(temporary), gallery=
                '<!doctype html><html><body><img src="missing.svg" alt="missing"></body></html>')
            root_before = (site / "index.html").read_bytes()
            gallery_before = (site / "examples/index.html").read_bytes()

            with self.assertRaisesRegex(ValueError, "broken local figure references"):
                retirement.finalize(site, source_commit="fixture")

            self.assertEqual((site / "index.html").read_bytes(), root_before)
            self.assertEqual((site / "examples/index.html").read_bytes(), gallery_before)
            self.assertFalse((site / "archive.html").exists())

    def test_hidden_evidence_is_separated_from_ordinary_archive(self) -> None:
        route = "review05-family-query-d6af180b0e398d78ebd2/review05-build-phases-20261110-468cc0eb/index.html"
        with tempfile.TemporaryDirectory() as temporary:
            site, _ = self.make_site(Path(temporary), route=route)
            result = retirement.finalize(site, source_commit="fixture")
            archive = (site / "archive.html").read_text()
            ordinary, hidden = archive.split('<section id="hidden-evidence">', 1)

            self.assertNotIn(route, ordinary)
            self.assertIn(route, hidden)
            self.assertEqual(result["navigation_transition"]["hidden_evidence_routes"], [route])
            self.assertIn("Hidden and superseded evidence", hidden)

    def test_missing_replacement_fragment_fails_before_navigation_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site, route = self.make_site(Path(temporary))
            root_before = (site / "index.html").read_bytes()
            gallery_before = (site / "examples/index.html").read_bytes()
            with patch.dict(retirement.BARE_ROUTE_REPLACEMENTS,
                            {route: "examples/index.html#missing-example-anchor"}):
                with self.assertRaisesRegex(ValueError, "replacement lesson fragment is missing"):
                    retirement.finalize(site, source_commit="fixture")

            self.assertEqual((site / "index.html").read_bytes(), root_before)
            self.assertEqual((site / "examples/index.html").read_bytes(), gallery_before)
            self.assertFalse((site / "archive.html").exists())

    def test_archive_navigation_is_added_when_gallery_has_no_legacy_label(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site, _ = self.make_site(
                Path(temporary),
                gallery='<html><body><h1 id="algorithm-coverage">Examples</h1></body></html>')
            retirement.finalize(site, source_commit="fixture")
            gallery = (site / "examples/index.html").read_text()

            self.assertIn('<a href="../index.html">Learn</a>', gallery)
            self.assertIn('<a href="../archive.html">Evidence archive</a>', gallery)
            self.assertIn('<nav aria-label="Site">', gallery)

    def test_symlinked_stylesheet_is_rejected_before_any_output_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site, _ = self.make_site(Path(temporary))
            external = Path(temporary) / "external.css"
            sentinel = b"leave this file untouched\n"
            external.write_bytes(sentinel)
            stylesheet = site / "examples/examples.css"
            stylesheet.unlink()
            stylesheet.symlink_to(external)
            root_before = (site / "index.html").read_bytes()
            gallery_before = (site / "examples/index.html").read_bytes()

            with self.assertRaisesRegex(ValueError, "Pages output is not a regular file"):
                retirement.finalize(site, source_commit="fixture")

            self.assertEqual(external.read_bytes(), sentinel)
            self.assertEqual((site / "index.html").read_bytes(), root_before)
            self.assertEqual((site / "examples/index.html").read_bytes(), gallery_before)
            self.assertFalse((site / "archive.html").exists())

    def test_output_parent_alias_is_rejected_by_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site, _ = self.make_site(Path(temporary))
            examples = site / "examples"
            shutil.rmtree(examples)
            examples.symlink_to(site, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "Pages output parent is not a regular directory"):
                retirement.preflight(site)


if __name__ == "__main__":
    unittest.main()
