from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/reports/learning_book.py"
SPEC = importlib.util.spec_from_file_location("learning_book", SCRIPT)
learning_book = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = learning_book
SPEC.loader.exec_module(learning_book)


class LearningBookTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "docs/catalogue/learning-book-v1.json").read_text())
        self.inventory = json.loads((ROOT / "docs/catalogue/module-composition-inventory-v1.json").read_text())
        self.figures = {"schema": "csl.closed-loop.figure-index/1", "figures": [
            {"id": key, "availability": "pending", "reason": "No source fixture is staged."}
            for key in ("lotka-populations", "earth-orbit", "fuel-state", "fuel-fuel-flow")]}

    def test_module_claims_are_executable_and_navigation_is_derived(self):
        chapters = learning_book.validate(self.manifest, self.inventory, self.figures)
        covered = {module for chapter in chapters for module in chapter["module_ids"]}
        expected = {module["identity"].get("id") or module["identity"].get("symbol")
                    for module in self.inventory["modules"]}
        self.assertTrue(covered)
        self.assertTrue(covered < expected)
        for chapter in chapters:
            if chapter["module_ids"]:
                self.assertEqual(chapter["kind"], "installed consumer")
                self.assertTrue(chapter["example_sources"])
                self.assertTrue(all((ROOT / source).is_file() for source in chapter["example_sources"]))
        self.assertEqual(chapters[0]["previous"], None)
        self.assertEqual(chapters[0]["next"], chapters[1]["id"])
        self.assertEqual(chapters[-1]["previous"], chapters[-2]["id"])
        self.assertEqual(chapters[-1]["next"], None)
        self.assertEqual({"orientation", "vertex_lp_simplex", "reachable_set_representation",
                          "controller", "supporting_operations", "capstones"},
                         {chapter["group"] for chapter in chapters})

    def test_known_module_without_an_executable_source_witness_is_rejected(self):
        broken = json.loads(json.dumps(self.manifest))
        broken["chapters"][2]["module_ids"].append("csl.hull.grouped-membership")
        with self.assertRaisesRegex(ValueError, "no executable source witness"):
            learning_book.validate(broken, self.inventory, self.figures)

    def test_ready_lessons_have_complete_reproduction_fields_and_pending_is_explicit(self):
        chapters = learning_book.validate(self.manifest, self.inventory, self.figures)
        ready = [chapter for chapter in chapters if chapter["status"] == "ready"]
        self.assertGreaterEqual(len(ready), 10)
        self.assertTrue(all(chapter["command"] and chapter["expected_output"] and
                            chapter["mathematical_input"] and chapter["intermediate_geometry"] and
                            chapter["support_limits"] for chapter in ready))
        pending = next(chapter for chapter in chapters if chapter["id"] == "native-substitution-matrix")
        self.assertEqual(pending["status"], "pending")
        self.assertIn("#943", pending["summary"])
        self.assertFalse(pending["command"])

    def test_runnable_lesson_inputs_are_math_first_and_match_source_fixtures(self):
        chapters = learning_book.validate(self.manifest, self.inventory, self.figures)
        by_id = {chapter["id"]: chapter for chapter in chapters}
        for chapter in (item for item in chapters if item["status"] == "ready"):
            chapter_id = chapter["id"]
            self.assertTrue(by_id[chapter_id].get("mathematical_displays") or
                            by_id[chapter_id].get("mathematical_tables"), chapter_id)
            html = learning_book._chapter_page(by_id[chapter_id], chapters,
                (learning_book.CHAPTER_ROOT / by_id[chapter_id]["source"]).read_text(),
                self.figures, self.inventory)
            self.assertIn('<h2>Mathematical input</h2>', html)
            if chapter.get("mathematical_displays"):
                self.assertIn('class="math-matrix"', html)
            else:
                self.assertIn('<table>', html)
            self.assertIn('<details class="lesson-input-details">', html)
            self.assertNotIn('<h3>Input</h3><pre', html)

        terminal = by_id["terminal-optimization"]
        self.assertIn("{(x,y)=(s,1−s) : 0≤s≤1}", terminal["mathematical_conclusion"])
        terminal_source = (learning_book.CHAPTER_ROOT / terminal["source"]).read_text()
        self.assertNotIn("selects (0,1)", terminal_source)
        operations = by_id["set-operations"]
        self.assertIn("[0,1]+[0,1]=[0,2]", operations["mathematical_conclusion"])
        self.assertIn("=[1,3]", operations["mathematical_conclusion"])
        operation_source = (learning_book.CHAPTER_ROOT / operations["source"]).read_text()
        self.assertNotIn("[1,3]×[0,1]", operation_source)

        finite = by_id["finite-controller-consumers"]
        self.assertEqual(len(finite["mathematical_tables"]), 6)
        self.assertIn("finite reachability game", finite["mathematical_conclusion"])
        self.assertIn("finite causal minimax cost game", finite["mathematical_conclusion"])
        broken = json.loads(json.dumps(self.manifest))
        game = next(item for item in broken["chapters"] if item["id"] == "finite-controller-consumers")
        game["mathematical_tables"][0]["rows"][0][2] = "0"
        with self.assertRaisesRegex(ValueError, "transition table differs from its executable fixture"):
            learning_book.validate(broken, self.inventory, self.figures)
        broken = json.loads(json.dumps(self.manifest))
        game = next(item for item in broken["chapters"] if item["id"] == "finite-controller-consumers")
        game["source_witnesses"][0]["contains"][0] = "Game{states, actions, inputs}"
        with self.assertRaisesRegex(ValueError, "source fixture changed"):
            learning_book.validate(broken, self.inventory, self.figures)

    def test_ready_figure_page_shows_scope_gaps_and_data_links(self):
        chapters = learning_book.validate(self.manifest, self.inventory, self.figures)
        chapter = next(item for item in chapters if item["id"] == "lotka-capstone")
        index = {"schema": "csl.closed-loop.figure-index/1", "figures": [
            {"id": "lotka-populations", "availability": "ready",
             "href": "examples/closed-loop/figures/lotka-populations.html",
             "plotted_data_href": "examples/closed-loop/figures/lotka-populations.plotted-data.json",
             "layer_scopes": ["observed plant replay", "retained graph nodes"],
             "missing_layers": ["all-admissible-control forward sets", "full-state intersections"]},
            {"id": "earth-orbit", "availability": "pending", "reason": "Not in this chapter."},
            {"id": "fuel-state", "availability": "pending", "reason": "Not in this chapter."},
        ]}
        html = learning_book._chapter_page(chapter, chapters,
            (ROOT / "docs/examples/learning/chapters/lotka-capstone.html").read_text(), index,
            self.inventory)
        self.assertIn("observed plant replay; retained graph nodes", html)
        self.assertIn("all-admissible-control forward sets; full-state intersections", html)
        self.assertIn("lotka-populations.plotted-data.json", html)

    def test_fuel_coordinate_maps_render_as_accessible_mathml_matrices(self):
        chapters = learning_book.validate(self.manifest, self.inventory, self.figures)
        chapter = next(item for item in chapters if item["id"] == "fuel-capstone")
        html = learning_book._chapter_page(chapter, chapters,
            (ROOT / "docs/examples/learning/chapters/fuel-capstone.html").read_text(),
            self.figures, self.inventory)
        self.assertIn('role="math" aria-label="Physical state x, rows [m_ox, m_f, q_ox, q_f]: 100; 30; 2; 0.6"', html)
        self.assertIn('aria-label="Oxidizer projection P_ox x = [q_ox, m_ox]^T: 0, 0, 1, 0; 1, 0, 0, 0"', html)
        self.assertIn('aria-label="Fuel flow-mass point P_f x, rows [q_f, m_f]: 0.6; 30"', html)
        self.assertEqual(html.count('<math display="inline" aria-hidden="true">'), 5)
        self.assertEqual(html.count('class="scroll" tabindex="0" role="region"'), 5)

    def test_rejects_missing_modules_and_figures(self):
        broken = json.loads(json.dumps(self.manifest))
        broken["chapters"][2]["module_ids"].append("invented.module")
        with self.assertRaisesRegex(ValueError, "unknown module IDs"):
            learning_book.validate(broken, self.inventory, self.figures)
        broken = json.loads(json.dumps(self.manifest))
        broken["chapters"][10]["figure_ids"] = ["missing-figure"]
        with self.assertRaisesRegex(ValueError, "absent from the figure index"):
            learning_book.validate(broken, self.inventory, self.figures)

    def test_five_representation_example_prints_the_recorded_values(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/reports/learning_geometry_toy.py")],
                                check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout, """d=(1.0, 0.0); exact_square=1; outer_disk=1.41421
d=(1.0, 1.0); exact_square=2; outer_disk=2
polytope=exact zonotope=exact parallelotope=exact ellipsoid=outer box=exact
Q subset E; E subset [-sqrt(2),sqrt(2)]^2; Q is [-1,1]^2
""")

    def test_build_emits_navigable_pages_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / "examples").mkdir()
            (site / "examples/examples.css").write_text("body { color: black; }")
            gallery = b'<html><body><a id="frozen-anchor" href="saved-report.zip">Raw record</a></body></html>'
            (site / "examples/index.html").write_bytes(gallery)
            (site / "saved-report.zip").write_bytes(b"frozen evidence bytes")
            index = site / "figure-index.json"
            index.write_text(json.dumps(self.figures))
            result = learning_book.build(site, figure_index_path=index)
            self.assertEqual(result["chapters"], len(self.manifest["chapters"]))
            landing = (site / "learn/index.html").read_text()
            self.assertIn('href="install-consumer.html"', landing)
            self.assertIn('href="native-substitution-matrix.html"', landing)
            self.assertIn('href="module-catalogue.html"', landing)
            catalogue = (site / "learn/module-catalogue.html").read_text()
            self.assertEqual(catalogue.count('id="module-'), len(self.inventory["modules"]))
            self.assertIn("reference-only in this book", catalogue)
            page = (site / "learn/install-consumer.html").read_text()
            self.assertIn('rel="next"', page)
            self.assertIn("installed_public_client", page)
            self.assertTrue((site / "learn/chapter-manifest.json").is_file())
            self.assertTrue((site / "examples/closed-loop/figure-index.json").is_file())
            self.assertEqual((site / "examples/index.html").read_bytes(), gallery)
            self.assertEqual((site / "saved-report.zip").read_bytes(), b"frozen evidence bytes")

    def test_built_primary_math_contains_runnable_fixture_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            index = site / "figure-index.json"
            index.write_text(json.dumps(self.figures))
            learning_book.build(site, figure_index_path=index)
            expected = {
                "install-consumer": [
                    "Constraint matrix A for Ax ≤ b: -1, 0; 0, -1; 1, 1",
                    "Constraint bounds b: 0; 0; 1",
                    "Objective coefficients c, with constant 7: -1, -2",
                ],
                "coordinates-and-outcomes": [
                    "Physical state x, rows [m_ox, m_f, q_ox, q_f]: 100; 30; 2; 0.6",
                    "Raw scale vector s: 100; 30; 3; 1",
                ],
                "vertex-membership": [
                    "Ordered V input. Row 4 is the midpoint candidate: 0, 0; 1, 0; 1, 1; 0, 1; 0.5, 0.5",
                ],
                "simplex-and-comparators": [
                    "Ordered source cloud, one point per row: 0, 0; 1, 0; 1, 1; 0, 1; 0.5, 0; 0, 0; 0.3333333333333333, 0.3333333333333333",
                    "Affine map matrix A: 1, 0; 0.5, 1",
                    "Affine offset b: 0.25; -0.5",
                    "One-step sum translation x₀: 0.25; 0.5",
                    "BTULSHOR near-tolerance refusal cloud: 0, 0; 1, 0; 1, 1; 0, 1; 0.5, 1.00000001",
                    "Near-tolerance affine map, also legacy REACH state map A: 1, 0; 0, 1",
                    "Near-tolerance affine offset: 0; 0",
                    "Installed legacy MODIF matrix A: 1; 2; -1",
                    "Installed legacy MODIF initial x: 1; 2; -1",
                    "<td>MODIF initial status</td><td>1</td>",
                    "Installed legacy KPABEP input cloud: 0, 0; 1, 0; 1, 1; 0, 1; 0.5, 0.5",
                    "Installed legacy REACH control map B: 1; 2",
                    "Installed legacy REACH initial vertices: 0, 0; 1, 0",
                    "Installed legacy REACH control vertices: 0; 1",
                ],
                "terminal-optimization": [
                    "Terminal constraints Ax ≤ b in variables (x,y): -1, 0; 0, -1; -1, -1; 1, 0; 0, 1",
                    "Terminal constraint bounds b: 0; 0; -1; 1; 1",
                    "Terminal LP objective coefficients c: 1, 1",
                    "Convex residual map A: 1; 0",
                    "Convex residual target r: 3; -4",
                    "Convex scalar bounds: 0; 2",
                    "One-step nominal state map A: 0, 0; 0, 0",
                    "One-step nominal control map B: 1, 0; 0, 1",
                    "Initial state and affine offset, both zero: 0; 0",
                    "Control box lower and upper bounds, rows for u and v: 0, 1; 0, 1",
                    "{(x,y)=(s,1−s) : 0≤s≤1}",
                ],
                "same-geometry-five-representations": [
                    "H representation: rows aᵢᵀ in Ax ≤ b: 1, 0; -1, 0; 0, 1; 0, -1",
                    "H bounds b: 1; 1; 1; 1",
                    "V representation: square vertices: -1, -1; 1, -1; 1, 1; -1, 1",
                    "Zonotope generator columns G: 1, 0; 0, 1",
                    "Parallelotope map A: 1, 0; 0, 1",
                    "Ellipsoid shape matrix Q for xᵀQ⁻¹x ≤ 1: 2, 0; 0, 2",
                    "Common zonotope, parallelotope and ellipsoid center: 0; 0",
                    "Support query directions, one per row: 1, 0; 1, 1",
                    "Box lower and upper bounds, rows for x and y: -1, 1; -1, 1",
                    "−1≤ξ₁,ξ₂≤1",
                ],
                "representation-consumers": [
                    "Shared diamond V input for box and parallelotope clients: 0, 2; 2, 0; 0, -2; -2, 0",
                    "Fixed parallelotope direction matrix: 1, 1; 1, -1",
                    "Zonotope generator columns before reduction: 1, 0, 0.5; 0, 1, 0.5",
                    "Zonotope center: 0; 0",
                    "Square V input for ellipsoid family: -1, -1; 1, -1; 1, 1; -1, 1",
                    "<td>axis</td><td>[[1,0],[0,1]]</td>",
                    "<td>rotated</td><td>[[1,1],[1,−1]]</td>",
                    "−1≤ξ₁,ξ₂,ξ₃≤1; no factor constraints",
                ],
                "closed-loop-semantics": [
                    "Scalar plant state update x[k+1]=Ax[k]+Bu[k]: 1",
                    "Control input map B: 1",
                    "Initial state and one-stage target: 0; 1",
                    "u[k]=1−x[k]",
                    "<td>0</td><td>0</td><td>1</td><td>1</td>",
                    "<td>1</td><td>1</td><td>0</td><td>1</td>",
                ],
                "finite-controller-consumers": [
                    "<td>0</td><td>yes</td><td>1</td>",
                    "<td>1</td><td>yes</td><td>1</td>",
                    "<td>0</td><td>yes</td><td>no</td>",
                    "<td>1</td><td>yes</td><td>yes</td>",
                    "<td>0</td><td>0</td><td>2</td>",
                    "<td>1</td><td>1</td><td>1</td>",
                ],
                "set-operations": [
                    "Unit-square H matrix A in Ax ≤ b: 1, 0; -1, 0; 0, 1; 0, -1",
                    "Unit-square H bounds b: 1; 0; 1; 0",
                    "Unit-square V vertices. The V-to-H client uses the same rows.: 0, 0; 1, 0; 1, 1; 0, 1",
                    "Interval-sum V endpoints for [0,1]: 0; 1",
                    "Integrator state map A: 1",
                    "Integrator control map B: 1",
                    "Target state: 2",
                    "Admissible control interval endpoints: -1; 1",
                    "<td>x ≤ 1</td><td>1</td>",
                    "<td>−x ≤ 0</td><td>0</td>",
                    "[0,1]+[0,1]=[0,2]",
                ],
                "lotka-capstone": [
                    "Initial population state x₀=[P,R]ᵀ in thousand individuals: 120; 60",
                    "Continuous control bound for u in 1/day: 0; 0.05",
                ],
                "orbit-capstone": [
                    "Initial orbit state x₀=[r,v,θ,ω]ᵀ: 7000; 0; 0; 0.0010780614796240577",
                    "Bounds for each force component uᵣ,uₜ in N: -0.5; 0.5",
                ],
                "fuel-capstone": [
                    "Physical state x, rows [m_ox, m_f, q_ox, q_f]: 100; 30; 2; 0.6",
                    "Oxidizer projection P_ox x = [q_ox, m_ox]^T: 0, 0, 1, 0; 1, 0, 0, 0",
                    "Fuel projection P_f x = [q_f, m_f]^T: 0, 0, 0, 1; 0, 1, 0, 0",
                ],
                "controller-composition": [
                    "Control bounds for each stage u₀,u₁ ∈ [0,1]: 0; 1",
                    "<td>terminal objective</td><td>minimize (x₂−1)²</td>",
                    "Complete optimal histories (x₀,x₁,x₂,u₀,u₁)=(0,s,1,s,1−s), 0≤s≤1",
                ],
                "optimization-backends": [
                    "Residual map A for r(x)=Ax−b, shared by both programs: 1; 0",
                    "Residual target b, shared by both programs: 3; -4",
                    "First program scalar bounds 0≤x≤2: 0; 2",
                    "Second program scalar bounds 1≤x≤2: 1; 2",
                    "Second program equality row 0≤0x≤0: 0, 0, 0",
                    "minimize ‖Ax−b‖₂",
                    "(x−3)²+16",
                ],
            }
            self.assertEqual(set(expected), {chapter["id"] for chapter in self.manifest["chapters"]
                                             if chapter["status"] == "ready"})
            for chapter_id, values in expected.items():
                page = (site / f"learn/{chapter_id}.html").read_text()
                primary = page.split('<section class="learning-math">', 1)[1].split('</section>', 1)[0]
                self.assertNotIn('<details', primary)
                for value in values:
                    with self.subTest(chapter=chapter_id, value=value):
                        self.assertIn(value, primary)

    def test_build_joins_and_copies_ready_recorded_figure_assets(self):
        entries = []
        for figure_id in ("fuel-state", "fuel-fuel-flow"):
            route = f"examples/closed-loop/figures/{figure_id}"
            entries.append({"id": figure_id, "availability": "ready",
                "href": route + ".html", "plotted_data_href": route + ".plotted-data.json",
                "svg_href": route + ".svg", "png_href": route + ".png",
                "layer_scopes": ["observed plant replay"],
                "missing_layers": ["all-admissible-control forward sets"]})
        entries.extend({"id": figure_id, "availability": "pending", "reason": "Not part of this smoke."}
                       for figure_id in ("lotka-populations", "earth-orbit"))
        index = {"schema": "csl.closed-loop.figure-index/1", "figures": entries}
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / "examples").mkdir()
            (site / "examples/examples.css").write_text("body { color: black; }")
            figure_index = site / "input-figure-index.json"
            figure_index.write_text(json.dumps(index))
            learning_book.build(site, figure_index_path=figure_index)
            page = (site / "learn/fuel-capstone.html").read_text()
            self.assertIn("observed plant replay", page)
            self.assertIn("all-admissible-control forward sets", page)
            for figure_id in ("fuel-state", "fuel-fuel-flow"):
                for suffix in ("html", "plotted-data.json", "svg", "png"):
                    rel = f"examples/closed-loop/figures/{figure_id}.{suffix}"
                    source = ROOT / "docs" / rel
                    self.assertEqual((site / rel).read_bytes(), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
