"""The published archive index explains every report instead of listing opaque IDs."""
import importlib.util
from html import escape
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import landing

spec = importlib.util.spec_from_file_location("report_site", ROOT / "scripts/reports/site.py")
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)

REPORTS = ROOT / "reports/algorithm-results"


def catalogue() -> dict:
    return json.loads((REPORTS / "catalog.json").read_text(encoding="utf-8"))


class LandingTests(unittest.TestCase):
    def setUp(self):
        self.catalogue = catalogue()
        self.page = site.catalogue_index(self.catalogue)

    def test_index_is_a_readable_page_not_a_bare_list(self):
        self.assertIn("<title>CSL algorithm reports</title>", self.page)
        self.assertEqual(self.page.count("<body>"), 1)
        self.assertEqual(self.page.count("</ul>"), 1)
        self.assertIn("<h1>Algorithm reports</h1>", self.page)
        self.assertIn("How to read this archive", self.page)
        published = {landing.FAMILIES[landing.family_for(report["report_id"])][0]
                     for report in self.catalogue["reports"]}
        for key, heading, _ in landing.GROUPS:
            if key in published:
                self.assertIn("<h2>" + heading + "</h2>", self.page)
            else:
                self.assertNotIn("<h2>" + heading + "</h2>", self.page)

    def test_every_published_report_has_a_plain_language_description(self):
        for report in self.catalogue["reports"]:
            report_id = report["report_id"]
            family = landing.FAMILIES[landing.family_for(report_id)]
            self.assertTrue(family[1], report_id)
            self.assertGreater(len(family[2]), 60, report_id)
            self.assertIn('href="' + report_id + '/index.html"', self.page)
            self.assertIn(family[1], self.page)
            self.assertIn(family[2], self.page)

    def test_reports_keep_their_own_measured_scope_and_evidence_limits(self):
        for report in self.catalogue["reports"]:
            self.assertIn(escape(report["measured_scope"]), self.page)
            self.assertIn(escape(report["evidence_limits"]), self.page)
            self.assertIn(report["source_commit"], self.page)

    def test_report_links_stay_inside_the_published_routes(self):
        self.assertIn('href="lp-20261012T000346Z-9b916da6a4ffd6685e99df3129f6cbaaa73d85c9f12533a828c1e1714dd12ff0/records.json"', self.page)
        self.assertIn("Repository copy (current main)", self.page)
        self.assertNotIn("<script", self.page)
        self.assertNotIn("javascript:", self.page)

    def test_unknown_report_family_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no landing description"):
            landing.family_for("mystery-report-0123456789abcdef")

    def test_every_registered_family_has_a_group_and_a_summary(self):
        for family, (group, title, summary) in landing.FAMILIES.items():
            self.assertIn(group, {key for key, _, _ in landing.GROUPS}, family)
            self.assertTrue(title, family)
            self.assertTrue(summary.endswith("."), family)


class AssembledIndexTests(unittest.TestCase):
    """The published landing page is built from the assembled staged index."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name)
        self.report_id = "app02-box-8ff979de60ea9d22"
        for name in ("records.json", "bundle.zip"):
            (self.site / self.report_id / name).parent.mkdir(parents=True, exist_ok=True)
            (self.site / self.report_id / name).write_text("{}", encoding="utf-8")
        (self.site / self.report_id / "index.html").write_text("<html><body>Report</body></html>", encoding="utf-8")
        (self.site / "app02-example").mkdir()
        (self.site / "app02-example" / "index.html").write_text("<html><body>Example</body></html>", encoding="utf-8")
        (self.site / "examples").mkdir()
        (self.site / "examples" / "index.html").write_text("<html><body>Examples</body></html>", encoding="utf-8")
        assembled = site.catalogue_index({"reports": []}).replace(
            "</ul>",
            '<li><a href="' + self.report_id + '/index.html">APP-02 box and parallelotope report</a>'
            " - five exact stored-binary64 examples and 3,500 verified measured calls"
            ' \xb7 <a href="app02-example/index.html">2D visual example</a>'
            ' \xb7 <a href="' + self.report_id + '/records.json">raw JSON</a>'
            ' \xb7 <a href="' + self.report_id + '/bundle.zip">offline ZIP</a></li></ul>')
        assembled = assembled.replace(
            "<body>", '<body><p id="visual-examples-link">'
            '<a href="examples/index.html">Visual examples</a></p>', 1)
        (self.site / "index.html").write_text(assembled, encoding="utf-8")

    def test_staged_items_become_cards_with_their_own_scope(self):
        landing.build(self.site)
        page = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn("Box and parallelotope approximations", page)
        self.assertIn("five exact stored-binary64 examples and 3,500 verified measured calls", page)
        self.assertIn('href="' + self.report_id + '/index.html"', page)
        self.assertIn('href="examples/index.html"', page)
        self.assertNotIn("APP-02 box and parallelotope report", page)

    def test_output_is_deterministic(self):
        landing.build(self.site)
        first = (self.site / "index.html").read_bytes()
        landing.build(self.site)
        self.assertEqual(first, (self.site / "index.html").read_bytes())

    def test_links_to_missing_staged_files_are_rejected(self):
        (self.site / self.report_id / "records.json").unlink()
        with self.assertRaisesRegex(ValueError, "missing staged file"):
            landing.build(self.site)

    def test_links_outside_the_staged_site_are_rejected(self):
        page = ('<!doctype html><html lang="en"><body><p class="links">'
                '<a href="https://example.com/page">Elsewhere</a></p></body></html>')
        with self.assertRaisesRegex(ValueError, "outside the staged site"):
            landing.validate(page, self.site)


if __name__ == "__main__":
    unittest.main()
