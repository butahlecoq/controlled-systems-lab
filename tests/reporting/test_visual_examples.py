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
import stage_syn03_nominal_exact_example as nominal_exact_example


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
        self.catalog_reports = catalog["reports"]
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
                if (source / "records.json").is_file():
                    shutil.copyfile(source / "records.json", target / "records.json")
                else:
                    (target / "records.json").write_text("{}", encoding="utf-8")
            if not (target / saved["page"]).exists():
                (target / saved["page"]).write_text("<html>report fixture</html>", encoding="utf-8")
            if not (target / saved["image"]).exists():
                shutil.copyfile(source / saved["image"], target / saved["image"])
        for case in gallery.visual_illustrations.CASES:
            if "report_kind" not in case:
                continue
            target = self.site / by_kind[case["report_kind"]]
            target.mkdir(exist_ok=True)
            if not (target / "records.json").exists():
                (target / "records.json").write_text("{}", encoding="utf-8")
            if not (target / "index.html").exists():
                (target / "index.html").write_text("<html>report fixture</html>", encoding="utf-8")
        for report in catalog["reports"]:
            target = self.site / report["report_id"]
            target.mkdir(exist_ok=True)
            raw_name = "results.jsonl" if report["report_kind"] == "issue6-b07-reference" else "records.json"
            if not (target / raw_name).exists():
                (target / raw_name).write_text("{}", encoding="utf-8")
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
        last_topic_title = "B06 fuel terminal set: readable 4D-to-2D projections"
        last_anchor = "visual-fuel-b06-viz03"
        self.assertIn(
            f'<a class="nav-shortcut" href="#{last_anchor}">Jump to final example: '
            f'{last_topic_title} ↓</a>', page)
        self.assertIn('target.scrollIntoView({behavior:"instant",block:"start"})', page)
        self.assertIn('<nav aria-label="Examples" tabindex="0">', page)
        self.assertIn(f'<article class="saved-figure" id="{last_anchor}">', page)
        fuel_page = self.site / "examples/fuel-b06-viz03.html"
        self.assertTrue(fuel_page.is_file())
        fuel_links = Links(); fuel_links.feed(fuel_page.read_text(encoding="utf-8"))
        for link in fuel_links.links:
            if not urlsplit(link).scheme:
                self.assertTrue((fuel_page.parent / link.split("#")[0]).is_file(), link)
        readable_fuel_page = self.site / "examples/fuel-b06-viz06.html"
        self.assertTrue(readable_fuel_page.is_file())
        readable_html=readable_fuel_page.read_text(encoding="utf-8")
        self.assertIn("One 4D fuel set",readable_html)
        self.assertIn("issue #668",readable_html)
        self.assertIn("30.26",readable_html)
        self.assertIn("fuel-b06-viz06-source.json",readable_html)
        readable_links=Links();readable_links.feed(readable_html)
        for link in readable_links.links:
            if not urlsplit(link).scheme and not link.startswith("#"):
                self.assertTrue((readable_fuel_page.parent/link.split("#")[0]).is_file(),link)
        stylesheet = (Path(gallery.__file__).with_name("visual_examples.css")).read_text(encoding="utf-8")
        self.assertIn("height:calc(100vh - 6rem);display:flex;flex-direction:column", stylesheet)
        self.assertIn("min-height:0;max-height:min(42vh,24rem);overflow-y:auto", stylesheet)
        self.assertIn("max-height:35vh;overflow-y:auto;overscroll-behavior:contain", stylesheet)
        self.assertIn("@media(max-height:500px) and (min-width:651px)", stylesheet)
        self.assertNotIn("overflow:visible", stylesheet)
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
        self.assertIn('href="issue3-control-walkthrough.html"', page)
        self.assertIn("End-to-end walkthrough", page)
        self.assertIn('href="lotka-volterra-sampled-v1.html"', page)
        self.assertIn("065de5e45d295dfa099e25265c4014c0c46673f8", page)
        self.assertIn("blob/b83b8dc415dbe5811371b8446931ae4c6f3d2e28/reports/algorithm-results/tooling/geo04/polyhedral_intersection_driver.cpp", page)
        parser = Links()
        parser.feed(page)
        for link in parser.links:
            if not urlsplit(link).scheme and not link.startswith("#"):
                self.assertTrue((self.site / "examples" / link.split("#")[0]).is_file(), link)
        figures = list((self.site / "examples").glob("*.svg"))
        self.assertEqual(len(figures), len(self.examples) + len(gallery.visual_illustrations.CASES) + 13)
        for figure in figures:
            if figure.name == "fuel-b06-viz06-before.svg":
                self.assertEqual(hashlib.sha256(figure.read_bytes()).hexdigest(),
                                 "ac5997b750ef20fb80c90b46549a1110cf10f7ff37bbb5f9d72ab1cc44461f20")
                continue
            tree = ET.fromstring(figure.read_text())
            self.assertEqual(tree.attrib["role"], "img")
            self.assertIsNotNone(tree.find("{http://www.w3.org/2000/svg}desc"))
        workflow = (self.site / "examples/issue3-control-walkthrough.html").read_text()
        for step in ("1. Define the problem", "2. Run the supported profile",
                     "3. Select from the complete finite family", "4. Independently verify the answer",
                     "5. Inspect the saved export and provenance", "validated_bounds [0,0]"):
            self.assertIn(step, workflow)
        self.assertIn("blob/1c606969b0d15700b61e43effdbbd545e9d0ed73/benchmarks/reporting/issue3/validated_driver.cpp", workflow)
        self.assertIn("blob/c72f3480c8fea2575ba860890502857006e9b9f4/include/csl/optimization/validated_finite_action_minimax.hpp", workflow)
        workflow_links = Links()
        workflow_links.feed(workflow)
        for link in workflow_links.links:
            if not urlsplit(link).scheme and not link.startswith("#"):
                self.assertTrue((self.site / "examples" / link.split("#")[0]).is_file(), link)
        workflow_svg = ET.parse(self.site / "examples/issue3-control-walkthrough.svg")
        self.assertIn("action 0: (0,0), cost 1", "".join(workflow_svg.getroot().itertext()))
        self.assertIn("action 1: (1,0), cost 0", "".join(workflow_svg.getroot().itertext()))
        lotka_page = (self.site / "examples/lotka-volterra-sampled-v1.html").read_text()
        self.assertIn("frozen record directly; it does not re-run the recurrence", lotka_page)
        self.assertIn("not an exact reachability set", lotka_page)
        lotka_svg = ET.parse(self.site / "examples/lotka-volterra-sampled-v1.svg").getroot()
        lotka_description = lotka_svg.find("{http://www.w3.org/2000/svg}desc")
        self.assertIn("csl-report-quantitative-v1", lotka_description.text)
        visual_inventory = json.loads((self.site / "examples/visual-coverage.json").read_text())
        lotka_entry = next(entry for entry in visual_inventory["entries"]
                           if entry["anchor"] == "saved-figure-lotka-quantitative")
        self.assertEqual(lotka_entry["figure"], "lotka-volterra-sampled-v1.svg")
        for stem, expected_text in (("app02-diamond-v1", "saved input and rotated outer bound"),
                                   ("app04-square-v1", "diagonal orientation")):
            companion_page = (self.site / "examples" / (stem + ".html")).read_text()
            self.assertIn("csl-report-quantitative-v1", companion_page)
            self.assertIn("Frozen values", companion_page)
            companion_svg = ET.parse(self.site / "examples" / (stem + ".svg")).getroot()
            description = companion_svg.find("{http://www.w3.org/2000/svg}desc")
            self.assertIn("csl-report-quantitative-v1", description.text)
            self.assertIn(expected_text, " ".join(companion_svg.itertext()))
            entry = next(entry for entry in visual_inventory["entries"] if entry["anchor"] == stem)
            self.assertEqual(entry["figure"], stem + ".svg")
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
        issue3_entry = next(entry for entry in visual_coverage["entries"]
                            if entry["anchor"] == "visual-issue3-validated-minimax-2d")
        self.assertEqual(issue3_entry["walkthrough_page"], "issue3-control-walkthrough.html")
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
        validated = json.loads((self.site / "examples/issue3-validated-minimax.json").read_text())
        self.assertEqual(validated["inputs"]["ordered_actions"], [[0, 0], [1, 0]])
        self.assertEqual(validated["answer"]["action_0"]["worst_objective"], "sqrt(1/8)")
        self.assertEqual(validated["answer"]["action_1"]["witness"]["residual"], "1/4")
        self.assertIn("not a replay", validated["evidence"])
        self.assertIn("a2c0736f43e4ff15d9a9323a51296e1b416d8809", validated["source_commit"])
        self.assertEqual(len(validated["source_urls"]), 2)
        self.assertTrue(all(url.startswith("https://github.com/butahlecoq/controlled-systems-lab/blob/a2c0736f43e4ff15d9a9323a51296e1b416d8809/")
                            for url in validated["source_urls"]))
        self.assertIn("--catalog reports/algorithm-results/catalog.json --site build/report-site",
                      validated["reproduction_command"])
        self.assertIn("<code>python scripts/reports/visual_examples.py", page)
        for url in validated["source_urls"]:
            self.assertIn(f'href="{url}"', page)
        validated_svg = ET.parse(self.site / "examples/issue3-validated-minimax.svg")
        self.assertEqual(len(validated_svg.findall(f".//{ns}polygon")), 3)
        self.assertIn("u=(1,0): bad", "".join(validated_svg.getroot().itertext()))
        self.assertIn("gap=¼", "".join(validated_svg.getroot().itertext()))
        slew = json.loads((self.site / "examples/ext03-slew-memory.json").read_text())
        self.assertEqual(slew["answer"]["feasible_polygon_ccw"],
                         [[-1,-1],[-.75,-1],[1,.75],[1,1],[.75,1],[-1,-.75]])
        self.assertEqual(slew["answer"]["complete_minimizer_segment"], [[-.125,.125],[.125,-.125]])
        self.assertEqual(slew["inputs"]["temporal_constraint"], "|u1-u0|<=1/4")
        self.assertIn("not a replay or measurement", slew["evidence"])
        self.assertIn("temporal-slew-integrator.json", slew["source_path"])
        slew_svg = ET.parse(self.site / "examples/ext03-slew-memory.svg")
        self.assertEqual(len(slew_svg.findall(f".//{ns}polygon")), 1)
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

    def test_nominal_exact_example_stages_its_hash_checked_bundle(self):
        source = ROOT / "reports/algorithm-results/syn03-nominal-exact-2d-8b94095"
        stage_root = self.site / "custom-stage"
        stage_root.mkdir()
        report_id = nominal_exact_example.stage(source, stage_root)
        staged = stage_root / report_id
        self.assertEqual(report_id, "syn03-nominal-exact-2d-8b94095")
        self.assertEqual((staged / "records.json").read_bytes(), (source / "records.json").read_bytes())
        self.assertIn("optimal-face.svg", (staged / "index.html").read_text())

    def test_nominal_exact_example_rejects_changed_bytes(self):
        source = ROOT / "reports/algorithm-results/syn03-nominal-exact-2d-8b94095"
        copied = self.site / "modified-bundle"
        shutil.copytree(source, copied)
        (copied / "optimal-face.svg").write_text("changed")
        stage_root = self.site / "modified-stage"
        stage_root.mkdir()
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            nominal_exact_example.stage(copied, stage_root)

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
        coverage=json.loads((self.site/"examples/algorithm-coverage.json").read_text())
        b07=next(report for report in self.catalog_reports if report["report_kind"]=="issue6-b07-reference")
        family=next(entry for entry in coverage["families"] if "issue6-b07-reference" in entry["catalog_kinds"])
        linked=next(report for report in family["catalog_reports"] if report["report_kind"]=="issue6-b07-reference")
        self.assertEqual(linked["report_id"],b07["report_id"])
        self.assertTrue(linked["raw_record"].endswith(b07["report_id"]+"/results.jsonl"))


if __name__ == "__main__":
    unittest.main()
