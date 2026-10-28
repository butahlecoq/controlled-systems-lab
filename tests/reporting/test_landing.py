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
        published = {landing.FAMILIES[landing.family_for(report["report_id"])].group
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
            self.assertTrue(family.title, report_id)
            self.assertGreater(len(family.summary), 60, report_id)
            self.assertIn('href="' + report_id + '/index.html"', self.page)
            self.assertIn(family.title, self.page)
            self.assertIn(family.summary, self.page)

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

    def test_an_unregistered_route_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no landing description"):
            landing.family_for("mystery-report-0123456789abcdef")
        with self.assertRaisesRegex(ValueError, "no landing description"):
            landing.family_for("geo07-generator-sets-fast-0123456789abcdef")

    def test_every_registered_family_has_a_group_and_a_summary(self):
        for family, description in landing.FAMILIES.items():
            self.assertIn(description.group, {key for key, _, _ in landing.GROUPS}, family)
            self.assertTrue(description.title, family)
            self.assertTrue(description.summary.endswith("."), family)

    def test_repeated_it17_dyadic_pilot_has_a_geometry_family_description(self):
        family = landing.FAMILIES[landing.family_for(
            "exp02-it17-dyadic-interior-20261027-r1")]
        self.assertEqual(family.group, "geometry")
        self.assertIn("six", family.summary)
        self.assertIn("inconclusive", family.summary)

    def test_a44_v2_description_does_not_relabel_the_historical_adaptation_route(self):
        historical = landing.FAMILIES[landing.family_for(
            "quickhull-it17-paper-adaptations-20261024-r1")]
        current = landing.FAMILIES[landing.family_for(
            "exp02-it17-a44-paper-order-20261027-r2")]
        self.assertIn("A43 and A44 are paper-informed adaptations", historical.summary)
        self.assertNotIn("A44 v2", historical.summary)
        self.assertIn("A44 interpretation", current.summary)

    def test_max_coordinate_game_route_has_a_differential_game_description(self):
        family = landing.FAMILIES[landing.family_for(
            "env717-max-coordinate-0123456789abcdefabcd")]
        self.assertEqual(family.group, "synthesis")
        self.assertIn("eight fixed control plans", family.summary)
        self.assertIn("one descriptive observation", family.summary)
        self.assertIn("not a performance comparison", family.summary)

    def test_sphere_game_route_has_a_differential_game_description(self):
        family = landing.FAMILIES[landing.family_for(
            "env717-sphere-game-0123456789abcdefabcd")]
        self.assertEqual(family.group, "synthesis")
        self.assertIn("27 fixed control plans", family.summary)
        self.assertIn("open-loop minimax value", family.summary)
        self.assertIn("no performance comparison", family.summary)

    def test_point_on_plane_route_describes_both_physical_projections(self):
        family = landing.FAMILIES[landing.family_for(
            "env717-point-on-plane-0123456789abcdefabcd")]
        self.assertEqual(family.group, "synthesis")
        self.assertIn("position (x1,x2)", family.summary)
        self.assertIn("velocity (x3,x4)", family.summary)
        self.assertIn("three stages", family.summary)

    def test_time_sphere_route_describes_nominal_target_reachability(self):
        family = landing.FAMILIES[landing.family_for(
            "env717-time-sphere-0123456789abcdefabcd")]
        self.assertEqual(family.group, "synthesis")
        self.assertIn("unit-disk", family.summary)
        self.assertIn("backward finite-feedback sweep", family.summary)
        self.assertIn("fixed at zero", family.summary)
        self.assertIn("not the continuous two-player RL optimum", family.summary)


class AssembledIndexTests(unittest.TestCase):
    """The published landing page is built from the assembled staged index."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name)
        self.report_id = "app02-box-8ff979de60ea9d22"
        (self.site / self.report_id).mkdir(parents=True)
        (self.site / self.report_id / "records.json").write_text(json.dumps({
            "scope": "Five authored interval and 2D polygon fixtures",
            "limits": ["Exact containment applies to stored binary64 vertices.",
                       "No comparator or speedup claim is supported."],
            "source_commit": "8fecba49e34c37e5e01c40218a8f014a179818fd"}), encoding="utf-8")
        (self.site / self.report_id / "index.html").write_text("<html><body>Report</body></html>", encoding="utf-8")
        (self.site / self.report_id / "bundle.zip").write_text("{}", encoding="utf-8")
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

    def test_staged_items_become_cards_with_the_scope_recorded_with_the_report(self):
        landing.build(self.site)
        page = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn("Box and parallelotope approximations", page)
        self.assertIn("Five authored interval and 2D polygon fixtures", page)
        self.assertIn("Exact containment applies to stored binary64 vertices.", page)
        self.assertIn("8fecba49e34c37e5e01c40218a8f014a179818fd", page)
        self.assertNotIn("3,500 verified measured calls", page)
        self.assertIn('href="' + self.report_id + '/index.html"', page)
        self.assertIn('href="examples/index.html"', page)
        self.assertNotIn("APP-02 box and parallelotope report", page)

    def test_output_is_deterministic(self):
        landing.build(self.site)
        first = (self.site / "index.html").read_bytes()
        landing.build(self.site)
        self.assertEqual(first, (self.site / "index.html").read_bytes())

    def test_saved_mpc03_pilot_is_added_to_the_archive_from_its_record(self):
        report_id = "mpc03-open-loop-pilot-v1"
        report = self.site / report_id
        report.mkdir()
        (report / "index.html").write_text("<html><body>MPC-03</body></html>", encoding="utf-8")
        (report / "record.json").write_text(json.dumps({
            "source_commit": "1b5ec86a7b5d1cc91b707a0588a43cd6517b23b2",
            "measured_scope": "One synthetic two-stage scalar formulation cross-check; no timing measured",
            "evidence_limits": ["No performance timing or comparative winner"],
        }), encoding="utf-8")
        for filename in ("pilot-output.json", "build-provenance.json"):
            (report / filename).write_text("{}", encoding="utf-8")
        landing.build(self.site)
        first = (self.site / "index.html").read_bytes()
        landing.build(self.site)
        page = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertEqual(first, (self.site / "index.html").read_bytes())
        self.assertEqual(page.count('href="' + report_id + '/index.html"'), 1)
        self.assertIn('href="' + report_id + '/index.html"', page)
        self.assertIn('href="' + report_id + '/record.json"', page)
        self.assertIn("no timing measured", page)
        self.assertIn("1b5ec86a7b5d1cc91b707a0588a43cd6517b23b2", page)

    def test_links_to_missing_staged_files_are_rejected(self):
        (self.site / self.report_id / "records.json").unlink()
        with self.assertRaisesRegex(ValueError, "missing staged file"):
            landing.build(self.site)

    def test_links_outside_the_staged_site_are_rejected(self):
        page = ('<!doctype html><html lang="en"><body><p class="links">'
                '<a href="https://example.com/page">Elsewhere</a></p></body></html>')
        with self.assertRaisesRegex(ValueError, "outside the staged site"):
            landing.validate(page, self.site)


class StagedCatalogueTests(unittest.TestCase):
    """The landing page is rendered over the real staged catalogue."""

    def test_real_staged_catalogue_renders_a_card_for_every_report(self):
        with tempfile.TemporaryDirectory() as temp:
            staged = Path(temp) / "site"
            site.stage(REPORTS / "catalog.json", staged, check=True)
            landing.build(staged)
            page = (staged / "index.html").read_text(encoding="utf-8")
            for report in catalogue()["reports"]:
                report_id = report["report_id"]
                self.assertIn('href="' + report_id + '/index.html"', page)
                self.assertIn(escape(report["measured_scope"]), page)
                self.assertIn(escape(report["evidence_limits"]), page)
            self.assertEqual(page.count("</ul>"), 1)


if __name__ == "__main__":
    unittest.main()
