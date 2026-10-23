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
        catalog = json.loads(self.catalog.read_text())
        by_source = {entry["source_report_id"]: entry["report_id"]
                     for entry in catalog["reports"] if "source_report_id" in entry}
        by_kind = {}
        for entry in catalog["reports"]:
            by_kind.setdefault(entry["report_kind"], entry["report_id"])
        for saved in gallery.SAVED_FIGURES:
            report_id = saved.get("route") or by_source[saved["source_report_id"]]
            target = self.site / report_id
            target.mkdir(exist_ok=True)
            source_id = saved.get("source_report_id", report_id)
            source = ROOT / "reports/algorithm-results" / source_id
            if not (target / "records.json").exists():
                (target / "records.json").write_text("{}", encoding="utf-8")
            if not (target / saved["page"]).exists():
                (target / saved["page"]).write_text("<html>report fixture</html>", encoding="utf-8")
            if not (target / saved["image"]).exists():
                shutil.copyfile(source / saved["image"], target / saved["image"])
        for case in gallery.visual_illustrations.CASES:
            target = self.site / by_kind[case["report_kind"]]
            target.mkdir(exist_ok=True)
            if not (target / "records.json").exists():
                (target / "records.json").write_text("{}", encoding="utf-8")
            if not (target / "index.html").exists():
                (target / "index.html").write_text("<html>report fixture</html>", encoding="utf-8")
        for report in catalog["reports"]:
            target = self.site / report["report_id"]
            target.mkdir(exist_ok=True)
            if not (target / "records.json").exists():
                (target / "records.json").write_text("{}", encoding="utf-8")
            if not (target / "index.html").exists():
                (target / "index.html").write_text("<html>report fixture</html>", encoding="utf-8")
        coverage_source = json.loads((ROOT / "scripts/reports/algorithm_visual_coverage.json").read_text())
        for family in coverage_source["families"]:
            for route in family["report_routes"]:
                target = self.site / route
                target.mkdir(exist_ok=True)
                if not (target / "records.json").exists():
                    (target / "records.json").write_text("{}", encoding="utf-8")
                if not (target / "index.html").exists():
                    (target / "index.html").write_text("<html>report fixture</html>", encoding="utf-8")

    def test_saved_outputs_match_literal_geometry(self):
        square, line, intersection, hybrid = self.examples[:4]
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
        two_parameter = next(example for example in loaded if example["kind"] == "two_parameter")
        projected = next(example for example in loaded if example["kind"] == "projected_reachability")
        self.assertEqual(two_parameter["kind"], "two_parameter")
        self.assertEqual(two_parameter["report_id"],
                         "ext07-hybrid-two-parameter-8ad871b5ea29fc7b")
        self.assertEqual([path["feasible_polygon_in_control_coordinates"]
                          for path in two_parameter["polygons"]],
                         [[[0, 0], [0.5, 0], [0.5, 0.5], [0, 1]],
                          [[0, 0], [1, 0], [0, 1]]])
        self.assertEqual(two_parameter["analytic"]["minimum_objective"], 0)
        self.assertEqual(two_parameter["analytic"]["complete_optimal_family"],
                         "every point in each labelled feasible polygon; both paths are retained")
        self.assertEqual(projected["analytic"]["projected_terminal_set"], "0<=x[1]<=0.5")
        self.assertEqual(projected["analytic"]["feasible_projection"],
                         "(u[0], x[1]) = (s, s), 0<=s<=0.5")
        self.assertEqual(projected["inputs"]["modes"][0]["flow_by_stage"],
                         [{"A": 1, "B": 1, "offset": 0}])
        self.assertEqual(projected["inputs"]["edges"][0]["guards_by_stage"],
                         [{"interval": [0, 0.5]}])
        self.assertEqual(projected["inputs"]["terminal_objectives"][0]["linear"],
                         {"coefficients": [1], "constant": 0})

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
        last_topic = gallery.SAVED_FIGURES[-1]
        last_anchor = f"saved-figure-{len(gallery.SAVED_FIGURES)}"
        self.assertIn(
            f'<a class="nav-shortcut" href="#{last_anchor}">Jump to final example: '
            f'{last_topic["title"]} ↓</a>', page)
        self.assertIn('target.scrollIntoView({behavior:"instant",block:"start"})', page)
        self.assertIn('<nav aria-label="Examples" tabindex="0">', page)
        self.assertIn(f'<article id="{last_anchor}" class="saved-figure">', page)
        stylesheet = (Path(gallery.__file__).with_name("visual_examples.css")).read_text(encoding="utf-8")
        self.assertIn("height:calc(100vh - 6rem);display:flex;flex-direction:column", stylesheet)
        self.assertIn("min-height:0;overflow-y:auto", stylesheet)
        self.assertIn("max-height:none;overflow:visible", stylesheet)
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
        self.assertIn("measured report uses rectangular parameter sets", page)
        self.assertIn("coupled triangular/quadrilateral feasible set", page)
        self.assertIn("not part of that measured fixture", page)
        self.assertIn('href="two_parameter_scalar_polytopes.json"', page)
        self.assertIn("includes both free controls", page)
        self.assertIn('href="https://github.com/butahlecoq/controlled-systems-lab/commit/c6d135c94ee0fe4fece074b455dae18bee0d22b2"', page)
        self.assertIn('href="two_stage_scalar_family.json"', page)
        self.assertIn("Project a one-step hybrid state set", page)
        self.assertIn("Projected terminal set: x₁∈[0,0.5]", page)
        self.assertIn('href="projected_hybrid_reachability.json"', page)
        self.assertIn('href="algorithm-coverage.json"', page)
        self.assertIn("065de5e45d295dfa099e25265c4014c0c46673f8", page)
        self.assertIn("blob/b83b8dc415dbe5811371b8446931ae4c6f3d2e28/reports/algorithm-results/tooling/geo04/polyhedral_intersection_driver.cpp", page)
        parser = Links()
        parser.feed(page)
        for link in parser.links:
            if not urlsplit(link).scheme and not link.startswith("#"):
                self.assertTrue((self.site / "examples" / link.split("#")[0]).is_file(), link)
        figures = list((self.site / "examples").glob("*.svg"))
        self.assertEqual(len(figures), len(self.examples) + len(gallery.visual_illustrations.CASES))
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
        projected_svg = ET.parse(self.site / "examples/one_step_projected_hybrid_reachability.svg")
        projected_text = "".join(projected_svg.getroot().itertext())
        self.assertIn("u₀ (free control)", projected_text)
        self.assertIn("x₁ (terminal state)", projected_text)
        self.assertEqual(len(projected_svg.findall(".//{http://www.w3.org/2000/svg}polyline")), 1)
        self.assertEqual([point.attrib["fill"] for point in projected_svg.findall(".//{http://www.w3.org/2000/svg}circle")],
                         ["#b4cda3", "#b4cda3"])
        projected_record = json.loads((self.site / "examples/projected_hybrid_reachability.json").read_text())
        self.assertTrue(projected_record["illustration_only"])
        self.assertEqual(projected_record["analytic"]["projected_terminal_set"], "0<=x[1]<=0.5")
        coverage = json.loads((self.site / "examples/algorithm-coverage.json").read_text())
        self.assertEqual(coverage["schema"], "csl.algorithm-visual-coverage/1")
        architecture = (ROOT / coverage["source"]).read_text(encoding="utf-8")
        self.assertTrue(all(module in architecture for family in coverage["families"] for module in family["modules"]))
        catalog_kinds = {report["report_kind"] for report in json.loads(self.catalog.read_text())["reports"]}
        mapped_kinds = {kind for family in coverage["families"] for kind in family["catalog_kinds"]}
        self.assertEqual(mapped_kinds, catalog_kinds)
        visual_coverage = json.loads((self.site / "examples/visual-coverage.json").read_text())
        visual_anchors = {entry["anchor"] for entry in visual_coverage["entries"]}
        for family in coverage["families"]:
            if family["support"].startswith("supported-"):
                self.assertTrue(family["examples"], family["id"])
            self.assertTrue(family["implementation_issues"], family["id"])
            self.assertTrue(set(family["examples"]) <= visual_anchors, family["id"])
        minkowski = json.loads((self.site / "examples/geo02-minkowski.json").read_text())
        self.assertEqual(minkowski["answer"]["vertices_ccw"], [[0, 0], [3, 0], [2, 1], [0, 2]])
        self.assertIn("visual_examples.py --catalog", minkowski["reproduction_command"])
        ns = "{http://www.w3.org/2000/svg}"
        self.assertEqual(len(ET.parse(self.site / "examples/geo02-minkowski.svg").findall(f".//{ns}polygon")), 1)
        hv = json.loads((self.site / "examples/geo03-hv-square.json").read_text())
        self.assertEqual(hv["answer"]["V_vertices_ccw"], [[0, 0], [1, 0], [1, 1], [0, 1]])
        predecessor = json.loads((self.site / "examples/geo05-predecessor.json").read_text())
        self.assertEqual(predecessor["answer"]["predecessor_X_intersect_S_minus_U"], [[0, 2], [0, 2]])
        self.assertEqual(len(ET.parse(self.site / "examples/geo05-predecessor.svg").findall(f".//{ns}polygon")), 3)
        lp = json.loads((self.site / "examples/lp-triangle.json").read_text())
        self.assertEqual((lp["answer"]["optimizer"], lp["answer"]["objective_value"]), ([0, 1], -2))
        phase_one = json.loads((self.site / "examples/opt04-phase-one.json").read_text())
        self.assertEqual(phase_one["answer"]["lambda"], [0.5, 0.25, 0.25])
        self.assertEqual(phase_one["answer"]["phase_one_violation"], 0)
        first = {p.name: p.read_bytes() for p in (self.site / "examples").iterdir()}
        gallery.build(self.catalog, self.site)
        self.assertEqual({p.name: p.read_bytes() for p in (self.site / "examples").iterdir()}, first)
        self.assertEqual((self.site / "index.html").read_text().count('id="visual-examples-link"'), 1)

    def test_every_rendered_example_is_listed_in_inventory(self):
        gallery.build(self.catalog, self.site)
        inventory_path = self.site / "examples/visual-coverage.json"
        inventory = json.loads(inventory_path.read_text())
        with self.assertRaisesRegex(ValueError, "every rendered gallery example"):
            gallery.validate_gallery_inventory(self.site / "examples", inventory["entries"][:-1])

    def test_inventory_requires_provenance_and_analytic_inputs(self):
        gallery.build(self.catalog, self.site)
        inventory = json.loads((self.site / "examples/visual-coverage.json").read_text())
        entries = [dict(entry) for entry in inventory["entries"]]
        entries[0].pop("raw_record")
        with self.assertRaisesRegex(ValueError, "missing required metadata or provenance"):
            gallery.validate_gallery_inventory(self.site / "examples", entries)
        entries = inventory["entries"]
        analytic = next(entry for entry in entries if entry["status"] == "analytic-illustration")
        record_path = self.site / "examples" / analytic["raw_record"]
        record = json.loads(record_path.read_text())
        record.pop("reproduction_command")
        record_path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "needs inputs, answer, reproduction"):
            gallery.validate_gallery_inventory(self.site / "examples", entries)

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
