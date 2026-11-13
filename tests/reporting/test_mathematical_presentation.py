"""Guard reader-facing mathematics without rewriting historical evidence."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.reports import audit_mathematical_presentation as audit


class PresentationTests(unittest.TestCase):
    def test_actual_coordinate_table_regression(self):
        # The five old control-witness cards used this exact repeated role.
        html = ('<table><caption>Exact displayed projection vertices</caption>'
                '<tr><th>Coordinates</th><th>Meaning</th></tr>'
                '<tr><th>(0, 1)</th><td>saved projection vertex</td></tr>'
                '<tr><th>(1, 0)</th><td>saved projection vertex</td></tr></table>')
        findings = audit.inspect_html(html)
        self.assertEqual([f["kind"] for f in findings], ["constant-coordinate-role"])

    def test_actual_feedback_and_direction_regressions(self):
        for html in ('<p><code>K=[[-1, -2]]</code></p>',
                     '<table><tr><td>axis</td><td>[[1,0],[0,1]]</td></tr></table>',
                     '<section>[[1,0],[0,1]]</section>',
                     '<p>[[1,1],[1,−1]]</p>'):
            with self.subTest(html=html):
                self.assertIn("numeric-nested-list", {f["kind"] for f in audit.inspect_html(html)})

    def test_default_json_and_open_details_are_primary(self):
        for html in ('<pre>{"points": [0, 1]}</pre>',
                     '<pre>{"points": [0, 1]}',
                     '<details open><pre>[\n  1,\n  2\n]</pre></details>',
                     '<details open><p>[[0,1],[1,0]]</p></details>'):
            self.assertTrue(audit.inspect_html(html))

    def test_full_site_requires_its_producer_inventories(self):
        with tempfile.TemporaryDirectory() as directory:
            result = audit.audit_site(Path(directory), {
                "routes": [], "required_inventories": ["examples/visual-coverage.json"]})
            self.assertFalse(result["passed"])
            self.assertEqual(result["findings"][0]["kind"], "missing-inventory")

    def test_secondary_data_and_source_owned_reference_exceptions(self):
        cases = [
            '<details><summary>Exact data</summary><pre>{"x": 1}</pre></details>',
            '<details><details open><p>[[0,1]]</p></details></details>',
            '<section class="lesson-reproduction"><pre>[[1,0],[0,1]]</pre></section>',
            '<section id="schema"><pre>{"type":"array"}</pre></section>',
        ]
        for html in cases:
            self.assertEqual(audit.inspect_html(html, exempt_ids={"schema"}), [])
        self.assertTrue(audit.inspect_html(cases[-1]))

    def test_informative_tables_and_matrix_markup_survive(self):
        html = ('<table><tr><th>State</th><th>Safe</th></tr>'
                '<tr><td>0</td><td>yes</td></tr><tr><td>1</td><td>yes</td></tr></table>'
                '<p>x ∈ [−1,1]²; V ∈ R²×²</p>'
                '<math><mtable><mtr><mtd><mn>1</mn></mtd></mtr></mtable></math>'
                '<script>const data = [[1,0],[0,1]];</script>')
        self.assertEqual(audit.inspect_html(html), [])

    def test_route_coverage_and_frozen_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            frozen = b'<pre>{"saved": [1,2]}</pre>'
            (site / "old.html").write_bytes(frozen)
            (site / "lesson.html").write_text('<p>V = I</p>')
            ledger = {"routes": [
                {"route": "old.html", "disposition": "frozen", "owner": "capture.py",
                 "sha256": hashlib.sha256(frozen).hexdigest(), "witness": "source capture"},
                {"route": "lesson.html", "disposition": "maintained", "owner": "lesson.py"},
            ]}
            self.assertTrue(audit.audit_site(site, ledger, required_routes={"lesson.html"})["passed"])
            (site / "new.html").write_text('<p>New lesson</p>')
            self.assertIn("unclassified-route", {
                f["kind"] for f in audit.audit_site(site, ledger)["findings"]})
            (site / "new.html").unlink()
            (site / "old.html").write_bytes(frozen + b" ")
            self.assertIn("frozen-bytes-changed", {
                f["kind"] for f in audit.audit_site(site, ledger)["findings"]})
            (site / "lesson.html").unlink()
            self.assertIn("missing-route", {f["kind"] for f in audit.audit_site(
                site, ledger, required_routes={"lesson.html"})["findings"]})

    def test_gallery_and_book_discovery_cannot_hide_new_lessons(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / "examples").mkdir()
            (site / "learn").mkdir()
            (site / "examples/visual-coverage.json").write_text(json.dumps({
                "entries": [{"page": "new.html#answer", "walkthrough_page": "steps.html"}]}))
            (site / "learn/chapter-manifest.json").write_text(json.dumps({
                "chapters": [{"id": "new-chapter"}]}))
            routes = audit.discovered_routes(site)
            self.assertTrue({"examples/new.html", "examples/steps.html",
                             "learn/new-chapter.html", "learn/module-catalogue.html"} <= routes)
            result = audit.audit_site(site, {"routes": []})
            self.assertFalse(result["passed"])
            self.assertIn("missing-route", {f["kind"] for f in result["findings"]})

    def test_checked_in_ledger_has_precise_owners_and_frozen_witnesses(self):
        ledger = json.loads(audit.REGISTRY.read_text())
        routes = [entry["route"] for entry in ledger["routes"]]
        self.assertEqual(len(routes), len(set(routes)))
        for entry in ledger["routes"]:
            self.assertTrue(entry["owner"])
            if entry["disposition"] == "frozen":
                self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
                self.assertTrue(entry["witness"])


if __name__ == "__main__":
    unittest.main()
