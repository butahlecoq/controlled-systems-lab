"""Check the educational gallery against reviewed native data and literal geometry."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import visual_examples as gallery


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.links.extend(value for name, value in attrs if name in {"href", "src"})


class GalleryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = ROOT / "reports/algorithm-results/catalog.json"
        cls.examples = gallery.load_examples(cls.catalog)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name)
        (self.site / "index.html").write_text("<html><body><h1>Reports</h1></body></html>")
        for example in self.examples:
            target = self.site / example["report_id"]
            target.mkdir(exist_ok=True)
            shutil.copyfile(example["records_path"], target / "records.json")
            (target / "index.html").write_text("<html><body>Reviewed report</body></html>")

    def test_saved_outputs_match_literal_geometry(self):
        square, line, intersection, hybrid, _ = self.examples
        self.assertEqual(square["points"], [[0,0],[1,0],[1,1],[0,1],[.5,.5],[0,0],[1,0]])
        self.assertEqual(square["indices"], [0,1,2,3])
        self.assertEqual(line["indices"], [1,3])
        self.assertEqual(len(intersection["vertices"]), 8)
        expected = {(1,.5),(1,-.5),(-1,.5),(-1,-.5),(.5,1),(-.5,1),(.5,-1),(-.5,-1)}
        self.assertEqual({tuple(round(x, 7) for x in p) for p in intersection["vertices"]}, expected)
        self.assertEqual(intersection["vertices"][0], [-1.0000000000000002, -.5000000000000001])
        self.assertEqual(hybrid["analytic"]["feasible_projection"], "(u[0], x[2]) = (s, s), 0<=s<=0.5")
        self.assertEqual(hybrid["analytic"]["complete_minimizer"], "all joint coordinates are zero")
        self.assertEqual(hybrid["inputs"]["horizon"], 2)
        loaded = gallery.load_examples(self.catalog)
        two_parameter = loaded[4]
        self.assertEqual(two_parameter["kind"], "two_parameter")
        self.assertEqual(two_parameter["report_id"],
                         "ext07-hybrid-two-parameter-00ac6fb75d7cab95")
        self.assertEqual([path["feasible_polygon_in_control_coordinates"]
                          for path in two_parameter["polygons"]],
                         [[[0, 0], [0.5, 0], [0.5, 0.5], [0, 1]],
                          [[0, 0], [1, 0], [0, 1]]])
        self.assertEqual(two_parameter["analytic"]["minimum_objective"], 0)
        self.assertEqual(two_parameter["analytic"]["complete_optimal_family"],
                         "every point in each labelled feasible polygon; both paths are retained")

    def test_build_preserves_reports_and_has_resolvable_links(self):
        before = {p.relative_to(self.site): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in self.site.rglob("*") if p.is_file() and p.name != "index.html"}
        original_reports = {e["report_id"]: (self.site / e["report_id"] / "index.html").read_bytes()
                            for e in self.examples}
        gallery.build(self.catalog, self.site)
        for path, digest in before.items():
            self.assertEqual(hashlib.sha256((self.site / path).read_bytes()).hexdigest(), digest)
        for rid, content in original_reports.items():
            self.assertEqual((self.site / rid / "index.html").read_bytes(), content)
        self.assertIn('href="examples/index.html"', (self.site / "index.html").read_text())
        page = (self.site / "examples/index.html").read_text(encoding="utf-8")
        self.assertIn("Original point ID", page)
        self.assertIn("explicit analytic constructions", page)
        self.assertIn("duplicate of point 0", page)
        self.assertIn("binary64", page)
        self.assertIn("two-stage scalar family", page)
        self.assertIn("not part of that measured fixture", page)
        self.assertIn("unique minimum", page)
        self.assertIn("x_pre[1] in [0,0.5]", page)
        self.assertIn("Two labelled optimal polygons", page)
        self.assertIn("The objective is identically zero", page)
        self.assertIn("measured objective is x_terminal=u0", page)
        self.assertIn("not part of that measured fixture", page)
        self.assertIn('href="two_parameter_scalar_polytopes.json"', page)
        self.assertIn("includes both free controls", page)
        self.assertIn('href="https://github.com/butahlecoq/controlled-systems-lab/commit/c6d135c94ee0fe4fece074b455dae18bee0d22b2"', page)
        self.assertIn('href="two_stage_scalar_family.json"', page)
        self.assertIn("blob/b83b8dc415dbe5811371b8446931ae4c6f3d2e28/reports/algorithm-results/tooling/geo04/polyhedral_intersection_driver.cpp", page)
        parser = Links()
        parser.feed(page)
        for link in parser.links:
            if not urlsplit(link).scheme and not link.startswith("#"):
                self.assertTrue((self.site / "examples" / link.split("#")[0]).is_file(), link)
        figures = list((self.site / "examples").glob("*.svg"))
        self.assertEqual(len(figures), 5)
        for figure in figures:
            tree = ET.fromstring(figure.read_text())
            self.assertEqual(tree.attrib["role"], "img")
            self.assertIsNotNone(tree.find("{http://www.w3.org/2000/svg}desc"))
        square = ET.parse(self.site / "examples/square_duplicates.svg")
        boundary = square.find(".//{http://www.w3.org/2000/svg}polygon")
        self.assertEqual(boundary.attrib["points"],
                         "146.666667,373.333333 413.333333,373.333333 413.333333,106.666667 146.666667,106.666667")
        self.assertEqual(len(square.findall(".//{http://www.w3.org/2000/svg}circle")), 5)
        self.assertEqual(len(ET.parse(self.site / "examples/collinear_endpoints.svg")
                             .findall(".//{http://www.w3.org/2000/svg}polyline")), 1)
        hybrid_svg = ET.parse(self.site / "examples/two_stage_scalar_family.svg")
        self.assertIn("x₂ (terminal state)", "".join(hybrid_svg.getroot().itertext()))
        record = json.loads((self.site / "examples/two_stage_scalar_family.json").read_text())
        self.assertTrue(record["illustration_only"])
        self.assertEqual(record["analytic"]["minimum_objective"], 0)
        self.assertEqual(record["inputs"]["state_dimension"], 1)
        self.assertEqual(record["inputs"]["modes"][0]["controls_by_stage"],
                         [{"interval": [0, 1]}, {"singleton": 0}])
        two_parameter_svg = ET.parse(self.site / "examples/two_parameter_scalar_polytopes.svg")
        two_parameter_svg_text = "".join(two_parameter_svg.getroot().itertext())
        self.assertIn("objective = 0 everywhere", two_parameter_svg_text)
        self.assertIn("u₁ (second free control)", two_parameter_svg_text)
        polygons = two_parameter_svg.findall(".//{http://www.w3.org/2000/svg}polygon")
        self.assertEqual([polygon.attrib["points"] for polygon in polygons],
                         ["80.000000,440.000000 480.000000,440.000000 80.000000,40.000000",
                          "80.000000,440.000000 280.000000,440.000000 280.000000,240.000000 80.000000,40.000000"])
        two_record = json.loads((self.site / "examples/two_parameter_scalar_polytopes.json").read_text())
        self.assertTrue(two_record["illustration_only"])
        self.assertEqual(two_record["inputs"]["terminal_objective"],
                         {"type": "linear", "coefficients": [0], "constant": 0})
        self.assertEqual(len(two_record["analytic"]["paths"]), 2)
        first = {p.name: p.read_bytes() for p in (self.site / "examples").iterdir()}
        gallery.build(self.catalog, self.site)
        self.assertEqual({p.name: p.read_bytes() for p in (self.site / "examples").iterdir()}, first)
        self.assertEqual((self.site / "index.html").read_text().count('id="visual-examples-link"'), 1)

    def test_modified_staged_results_are_rejected_before_writes(self):
        target = self.site / self.examples[0]["report_id"] / "records.json"
        record = json.loads(target.read_text())
        record["rows"][0]["indices"] = "0:1:2"
        target.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "staged records"):
            gallery.build(self.catalog, self.site)
        self.assertFalse((self.site / "examples").exists())

    def test_missing_reviewed_route_is_rejected(self):
        (self.site / self.examples[-1]["report_id"] / "index.html").unlink()
        with self.assertRaisesRegex(ValueError, "staged report"):
            gallery.build(self.catalog, self.site)

    def test_cli_stages_the_downloaded_values(self):
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "scripts/reports/visual_examples.py"),
                        "--catalog", str(self.catalog), "--site", str(self.site)], check=True)
        result = json.loads((self.site / "examples/minimal-inputs.json").read_text())
        self.assertEqual(result["examples"][0]["indices"], [0,1,2,3])
        self.assertEqual(result["examples"][1]["vertices"], [[0,0],[3,3]])
        self.assertEqual(result["examples"][2]["vertices"][0], [-1.0000000000000002, -.5000000000000001])
        self.assertEqual(result["examples"][3]["kind"], "hybrid")
        self.assertEqual(result["examples"][4]["kind"], "two_parameter")


if __name__ == "__main__":
    unittest.main()
