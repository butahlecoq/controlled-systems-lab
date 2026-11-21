from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/reports/learning_book.py"
SPEC = importlib.util.spec_from_file_location("learning_book", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"Cannot load the learning-book generator from {SCRIPT}")
learning_book = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = learning_book
SPEC.loader.exec_module(learning_book)


class PageElements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()
        self.main_classes = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.add(attributes["id"])
        if tag == "a" and "href" in attributes:
            self.links.append(attributes["href"])
        if tag == "main":
            self.main_classes.update(attributes.get("class", "").split())


class LearningBookTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "docs/catalogue/learning-book-v1.json").read_text())
        self.inventory = json.loads(
            (ROOT / "docs/catalogue/module-composition-inventory-v1.json").read_text()
        )
        self.campaign_figures = [
            {
                "id": figure_id,
                "task_id": {
                    "campaign-syn-nl-lv-01-lotka": "syn-nl-lv-01/continuous-receding/1",
                    "campaign-earth-orbit-orbit": "env717-earth-orbit/continuous-receding/1",
                    "campaign-syn-nl-fuel-01-oxidizer": "syn-nl-fuel-01/continuous-receding/1",
                    "campaign-syn-nl-fuel-01-fuel": "syn-nl-fuel-01/continuous-receding/1",
                }[figure_id],
                "availability": "ready",
                "href": f"examples/closed-loop/figures/{figure_id}.html",
                "layer_scopes": ["retained graph nodes", "observed plant replay"],
                "missing_layers": ["continuous reachable-set boundaries", "global optimality"],
            }
            for figure_id in (
                "campaign-syn-nl-lv-01-lotka",
                "campaign-earth-orbit-orbit",
                "campaign-syn-nl-fuel-01-oxidizer",
                "campaign-syn-nl-fuel-01-fuel",
            )
        ]
        pending_figures = [
            {"id": key, "availability": "pending", "reason": "No source fixture is staged."}
            for key in ("lotka-populations", "earth-orbit", "fuel-state", "fuel-fuel-flow")
        ]
        self.figures = {
            "schema": "csl.closed-loop.figure-index/1",
            "figures": [*pending_figures, *self.campaign_figures],
        }

    def test_module_claims_are_executable_and_navigation_is_derived(self):
        chapters = learning_book.validate(self.manifest, self.inventory, self.figures)
        covered = {module for chapter in chapters for module in chapter["module_ids"]}
        expected = {
            module["identity"].get("id") or module["identity"].get("symbol")
            for module in self.inventory["modules"]
        }
        self.assertTrue(covered)
        self.assertTrue(covered < expected)
        for chapter in chapters:
            if chapter["module_ids"]:
                self.assertEqual(chapter["kind"], "installed consumer")
                self.assertTrue(chapter["example_sources"])
                self.assertTrue(
                    all((ROOT / source).is_file() for source in chapter["example_sources"])
                )
        self.assertEqual(chapters[0]["previous"], None)
        self.assertEqual(chapters[0]["next"], chapters[1]["id"])
        self.assertEqual(chapters[-1]["previous"], chapters[-2]["id"])
        self.assertEqual(chapters[-1]["next"], None)
        self.assertEqual(
            {
                "orientation",
                "vertex_lp_simplex",
                "reachable_set_representation",
                "controller",
                "supporting_operations",
                "capstones",
            },
            {chapter["group"] for chapter in chapters},
        )

    def test_task_capstones_distinguish_figures_pilots_and_full_profile_outcomes(self):
        ledger = "examples/closed-loop/campaign-2026-11-18/raw/coverage.json"
        coverage = json.loads((ROOT / "docs" / ledger).read_bytes())
        tasks = {
            "lotka-capstone": ("syn-nl-lv-01", {"lotka-populations": [0, 1]}),
            "orbit-capstone": ("earth-orbit", {"earth-orbit": [0, 3]}),
            "fuel-capstone": (
                "syn-nl-fuel-01", {"fuel-state": [2, 0], "fuel-fuel-flow": [3, 1]}
            ),
        }
        chapters = {chapter["id"]: chapter for chapter in self.manifest["chapters"]}
        index = json.loads((ROOT / "docs/examples/closed-loop/figure-index.json").read_bytes())
        figure_records = {figure["id"]: figure for figure in index["figures"]}
        outcomes = ("complete", "failed", "inconclusive", "unsupported")
        for chapter_id, (task, figures) in tasks.items():
            with self.subTest(chapter=chapter_id):
                chapter = chapters[chapter_id]
                counts = Counter(
                    cell["attempts"][-1]["category"]
                    for cell in coverage["cells"]
                    if cell["task_name"] == task
                )
                limits = chapter["support_limits"]
                self.assertEqual(chapter["figure_ids"], list(figures))
                self.assertIn("separate local-NLP pilot report", chapter["expected_output"])
                for figure_id, indices in figures.items():
                    figure = figure_records[figure_id]
                    self.assertEqual(figure["coordinate_transform"]["raw_indices"], indices)
                    plotted = json.loads((ROOT / "docs" / figure["plotted_data_href"]).read_bytes())
                    controllers = {run["controller_id"] for run in plotted["runs"]}
                    self.assertTrue(all(name.startswith("native-") for name in controllers))
                    self.assertIn(f"{len(controllers)} saved native controller runs", limits)
                self.assertIn(f"admitted {sum(counts.values())} graphs", limits)
                self.assertIn(", ".join(f"{counts[name]} {name}" for name in outcomes), limits)
                self.assertNotIn("#943", chapter["summary"] + limits)
                self.assertIn("../" + ledger, {record["href"] for record in chapter["records"]})

        geometry = chapters["orbit-capstone"]["intermediate_geometry"]
        self.assertIn("angular rate ω [rad/s]", geometry)
        body = (ROOT / "docs/examples/learning/chapters/orbit-capstone.html").read_text()
        self.assertIn("radius r [km] and angular rate ω [rad/s]", body)
        self.assertNotIn("Plot r against v", body)

    def test_generated_capstone_pages_match_reviewed_preservation_pins(self):
        preservation = ROOT / "reports/published-route-preservation/manifest.json"
        manifest = json.loads(preservation.read_bytes())
        pins = manifest["mutable_routes_reviewed_sha256"]
        routes = (
            "learn/index.html", "learn/lotka-capstone.html",
            "learn/orbit-capstone.html", "learn/fuel-capstone.html",
        )
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            learning_book.build(
                site, figure_index_path=ROOT / "docs/examples/closed-loop/figure-index.json"
            )
            for route in routes:
                with self.subTest(route=route):
                    self.assertIn(route, manifest["mutable_routes_reviewed_separately"])
                    self.assertEqual(hashlib.sha256((site / route).read_bytes()).hexdigest(), pins[route])

    def test_campaign_tables_match_frozen_full_profile_coverage(self):
        chapter = next(
            item for item in self.manifest["chapters"] if item["id"] == "native-substitution-matrix"
        )
        raw = ROOT / "docs/examples/closed-loop/campaign-2026-11-18/raw"
        coverage = json.loads((raw / "coverage.json").read_text())
        supplemental = json.loads((raw / "targeted-reruns-summary.json").read_text())
        tasks = {
            "syn-nl-lv-01": "Lotka–Volterra",
            "earth-orbit": "Earth orbit",
            "syn-nl-fuel-01": "Fuel transfer",
        }
        outcomes = ("complete", "failed", "inconclusive", "unsupported")
        counts = {name: Counter() for name in tasks}
        for cell in coverage["cells"]:
            counts[cell["task_name"]][cell["attempts"][-1]["category"]] += 1
        summary = coverage["outcomes"]
        tables = {table["label"]: table for table in chapter["mathematical_tables"]}
        graph_table = tables["Final graph outcomes by task"]
        self.assertEqual(graph_table["columns"], ["task", "admitted", *outcomes])
        expected_rows = [
            [
                label,
                str(sum(counts[task].values())),
                *(str(counts[task][name]) for name in outcomes),
            ]
            for task, label in tasks.items()
        ]
        expected_rows.append(
            [
                "Total",
                str(summary["admitted_graphs"]),
                *(str(summary["by_graph_outcome"][name]) for name in outcomes),
            ]
        )
        self.assertEqual(graph_table["rows"], expected_rows)
        self.assertEqual(
            dict(tables["Campaign accounting"]["rows"]),
            {
                "admitted and attempted full-profile graphs": str(summary["attempted_graphs"]),
                "full-profile attempt records including retries": str(summary["attempt_rows"]),
                "completed reruns in the separate compatible profile": str(
                    supplemental["outcomes"]["complete"]
                ),
                "source-incompatible candidates with recorded reasons": str(
                    summary["incompatible_candidates"]
                ),
                "duplicate catalogue graph references": str(
                    summary["duplicate_catalogue_references"]
                ),
            },
        )

    def test_source_permalinks_bind_to_the_executed_example_bytes(self):
        prefix = "https://github.com/butahlecoq/controlled-systems-lab/blob/"
        for chapter in self.manifest["chapters"]:
            for record in chapter.get("records", []):
                if not record["href"].startswith(prefix):
                    continue
                with self.subTest(chapter=chapter["id"], source=record["href"]):
                    commit, separator, source = record["href"][len(prefix) :].partition("/")
                    self.assertTrue(separator)
                    self.assertRegex(commit, r"^[0-9a-f]{40}$")
                    self.assertIn(source, chapter["example_sources"])
                    result = subprocess.run(
                        ["git", "show", f"{commit}:{source}"], cwd=ROOT, capture_output=True
                    )
                    self.assertEqual(result.returncode, 0, result.stderr.decode())
                    if "source_sha256" in record:
                        self.assertEqual(
                            hashlib.sha256(result.stdout).hexdigest(),
                            record["source_sha256"],
                            "Source permalink differs from its pinned source digest",
                        )
                    else:
                        self.assertEqual(
                            result.stdout,
                            (ROOT / source).read_bytes(),
                            "Source permalink differs from the executed example",
                        )

    def test_native_tracks_link_existing_formulations_and_actual_outcomes(self):
        chapters = learning_book.validate(self.manifest, self.inventory, self.figures)
        page = learning_book._model_tracks_page(chapters, self.figures)
        links = PageElements()
        links.feed(page)
        root = ROOT / "reports/algorithm-results"
        expected = json.loads((root / "native-discrete-models-v1/catalogue.json").read_text())[
            "models"
        ]
        route = "native-model-tracking-first-pass-v1"
        with ZipFile(root / route / (route + ".zip")) as bundle:
            results = list(
                csv.DictReader(io.StringIO(bundle.read("checks/independent_results.csv").decode()))
            )
            self.assertEqual({r["model"] for r in results}, {m["id"] for m in expected})
            for key in links.links:
                if key.startswith(f"../examples/{route}/"):
                    self.assertIn(
                        urlsplit(key).path.removeprefix(f"../examples/{route}/"), bundle.namelist()
                    )
        catalogue = PageElements()
        catalogue.feed((ROOT / "docs/examples/native-discrete-models.html").read_text())
        for model in expected:
            anchor = model["id"].split("/")[1]
            self.assertIn(anchor, catalogue.ids)
            self.assertIn("../examples/native-discrete-models.html#" + anchor, links.links)
            self.assertIn(model["id"], page)
        self.assertEqual(page.count("Nominal external input: supplied by the source"), 22)
        self.assertEqual(page.count("Nominal external input: unspecified by the source"), 13)
        self.assertIn("Preserved solver refusal", page)
        self.assertIn("Source-defined MPC task", page)
        self.assertTrue(any("Ten%2Dgenerator" in link for link in links.links))
        self.assertTrue(any("Twenty%2Dzone" in link for link in links.links))
        self.assertIn("flexible-pitch/synthetic-12-state/1", page)
        self.assertIn("bulaev-2016-slide33/literal-eight/1", page)
        self.assertIn("../examples/native-four-state-reachability.html", links.links)
        self.assertIn("bulaev-2016-slide50/authored-box/literal-six/1", page)
        self.assertIn("spatial-flight/b-consistent-body9-synthetic/1", page)
        self.assertIn("reachability-formulations", links.ids)
        self.assertIn("discrete-formulations", links.ids)
        self.assertIn("discrete-model-21", links.ids)

    def test_native_formulation_receipt_must_be_contained_in_report_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            root = repo / "reports/algorithm-results"
            root.mkdir(parents=True)
            untracked = repo / "untracked.txt"
            untracked.write_text("case=untracked")
            (root / "link.txt").symlink_to(untracked)
            for path in (str(untracked), "../../untracked.txt", "link.txt"):
                chapter = {"id": "native-forward-models", "records": [{"formulation_record": path}]}
                with (
                    self.subTest(path=path),
                    self.assertRaisesRegex(ValueError, "unsafe native formulation"),
                ):
                    learning_book.learning_model_tracks.native_sections(repo, [chapter])

    def test_model_tracks_are_generated_from_contracts_and_saved_results(self):
        chapters = learning_book.validate(self.manifest, self.inventory, self.figures)
        tracks = learning_book._task_contracts(chapters)
        self.assertEqual(len(tracks), 3)
        page = learning_book._model_tracks_page(chapters, self.figures)
        self.assertIn("System formulations and model tracks", page)
        for chapter, source, contract in tracks:
            with self.subTest(task=contract["task_id"]):
                self.assertIn(contract["model"]["model_id"], page)
                self.assertIn(contract["prediction"]["affine_model_id"], page)
                self.assertIn(chapter["id"] + ".html", page)
                self.assertIn("Visuals:", page)
                detail = learning_book._model_tracks_section(chapter)
                self.assertIn(contract["task_id"], detail)
                self.assertIn(contract["model"]["equations"][0], detail)
                self.assertIn("State ordering and coordinates", detail)
                self.assertIn("Parameters", detail)
                self.assertIn("Qualification", detail)
                self.assertIn("Disturbances", detail)
                self.assertIn("Observation supplied to the controller", detail)
                self.assertIn("State and terminal constraints", detail)
                self.assertIn(contract["source"]["path"], detail)
                self.assertIn(source, detail)

                saved_model_ids = learning_book._saved_result_model_ids().get(
                    contract["task_id"], ()
                )
                self.assertTrue(saved_model_ids)
                self.assertTrue(
                    all(model_id == contract["model"]["model_id"] for model_id in saved_model_ids)
                )
                saved_prediction_ids = learning_book._saved_result_prediction_ids().get(
                    contract["task_id"], ()
                )
                self.assertTrue(saved_prediction_ids)
                self.assertTrue(
                    all(
                        prediction_id == contract["prediction"]["affine_model_id"]
                        for prediction_id in saved_prediction_ids
                    )
                )

                generated = PageElements()
                generated.feed(detail)
                anchor = learning_book._track_anchor(contract["model"]["model_id"])
                self.assertIn(anchor, generated.ids)
                self.assertIn(anchor + "-plant", generated.ids)
                self.assertIn(anchor + "-prediction", generated.ids)
                self.assertIn(chapter["id"] + ".html#" + anchor + "-plant", page)

    def test_model_track_source_identity_must_match_task_contract(self):
        chapter = next(item for item in self.manifest["chapters"] if item["id"] == "lotka-capstone")
        contract = json.loads((ROOT / chapter["example_sources"][0]).read_text())
        contract["source"]["model_id"] = "different/source-model/1"
        with self.assertRaisesRegex(ValueError, "differs from plant track"):
            learning_book._validate_model_track_contract(
                chapter, chapter["example_sources"][0], contract
            )

    def test_model_track_prediction_identity_must_match_saved_execution_records(self):
        chapter = next(item for item in self.manifest["chapters"] if item["id"] == "lotka-capstone")
        contract = json.loads((ROOT / chapter["example_sources"][0]).read_text())
        contract["prediction"]["affine_model_id"] = "different/predictor/1"
        with self.assertRaisesRegex(ValueError, "predictor identity disagrees"):
            learning_book._validate_model_track_contract(
                chapter, chapter["example_sources"][0], contract
            )

    @staticmethod
    def _is_retained_source_commit(
        repo: Path, commit: str, *, allow_in_flight_head: bool = False
    ) -> bool:
        main_ref = "refs/remotes/origin/main"
        main_result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, main_ref],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if main_result.returncode == 0:
            return True
        if main_result.returncode != 1:
            raise AssertionError(f"Cannot check {main_ref}: {main_result.stderr.strip()}")

        if allow_in_flight_head:
            head_result = subprocess.run(
                ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            if head_result.returncode == 0:
                return True
            if head_result.returncode != 1:
                raise AssertionError(f"Cannot check HEAD: {head_result.stderr.strip()}")

        tags_result = subprocess.run(
            ["git", "tag", "--list", "evidence/*-source-*"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if tags_result.returncode != 0:
            raise AssertionError(f"Cannot list evidence source tags: {tags_result.stderr.strip()}")
        for tag in tags_result.stdout.splitlines():
            tag_ref = f"refs/tags/{tag}"
            tagged_commit = subprocess.run(
                ["git", "rev-parse", "--verify", f"{tag_ref}^{{commit}}"],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            if tagged_commit.returncode != 0:
                raise AssertionError(
                    f"Cannot resolve evidence source tag {tag}: " + tagged_commit.stderr.strip()
                )
            tag_result = subprocess.run(
                ["git", "merge-base", "--is-ancestor", commit, tagged_commit.stdout.strip()],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            if tag_result.returncode == 0:
                return True
            if tag_result.returncode != 1:
                raise AssertionError(
                    f"Cannot check evidence source tag {tag}: {tag_result.stderr.strip()}"
                )
        return False

    def test_source_permalinks_are_retained_by_main_evidence_tags_or_in_flight_head(self):
        prefix = "https://github.com/butahlecoq/controlled-systems-lab/blob/"
        sources = {
            record["href"][len(prefix) :].partition("/")[0]
            for chapter in self.manifest["chapters"]
            for record in chapter.get("records", [])
            if record["href"].startswith(prefix)
        }
        self.assertTrue(sources)
        for commit in sorted(sources):
            with self.subTest(commit=commit):
                self.assertTrue(
                    self._is_retained_source_commit(ROOT, commit, allow_in_flight_head=True),
                    f"Source permalink commit {commit} is not retained by origin/main, an evidence source tag, or HEAD",
                )

    def test_source_retention_rejects_feature_only_history_and_accepts_durable_refs(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)

            def git(*args: str) -> str:
                result = subprocess.run(
                    ["git", *args], cwd=repo, check=True, capture_output=True, text=True
                )
                return result.stdout.strip()

            git("init", "--initial-branch=main")
            git("config", "user.name", "Learning book test")
            git("config", "user.email", "learning-book-test@example.invalid")
            (repo / "main-source.cpp").write_text("int main_source = 1;\n")
            git("add", "main-source.cpp")
            git("commit", "-m", "main source")
            main_source = git("rev-parse", "HEAD")
            git("update-ref", "refs/remotes/origin/main", main_source)

            git("checkout", "-b", "feature")
            (repo / "feature-source.cpp").write_text("int feature_source = 1;\n")
            git("add", "feature-source.cpp")
            git("commit", "-m", "feature-only source")
            feature_source = git("rev-parse", "HEAD")
            self.assertEqual(
                subprocess.run(
                    ["git", "merge-base", "--is-ancestor", feature_source, "HEAD"], cwd=repo
                ).returncode,
                0,
            )
            self.assertFalse(self._is_retained_source_commit(repo, feature_source))

            git("checkout", "--orphan", "tagged-source")
            (repo / "snapshot-source.cpp").write_text("int snapshot_source = 1;\n")
            git("add", "snapshot-source.cpp")
            git("commit", "-m", "frozen source snapshot")
            tagged_source = git("rev-parse", "HEAD")
            git("tag", "-a", "evidence/fixture-source-v1", "-m", "Retain the frozen source commit")
            self.assertEqual(
                subprocess.run(
                    [
                        "git",
                        "merge-base",
                        "--is-ancestor",
                        tagged_source,
                        "refs/remotes/origin/main",
                    ],
                    cwd=repo,
                ).returncode,
                1,
            )
            self.assertTrue(self._is_retained_source_commit(repo, main_source))
            self.assertTrue(self._is_retained_source_commit(repo, tagged_source))

    def test_known_module_without_an_executable_source_witness_is_rejected(self):
        broken = json.loads(json.dumps(self.manifest))
        broken["chapters"][2]["module_ids"].append("csl.hull.grouped-membership")
        with self.assertRaisesRegex(ValueError, "no executable source witness"):
            learning_book.validate(broken, self.inventory, self.figures)

    def test_ready_lessons_have_complete_reproduction_fields(self):
        chapters = learning_book.validate(self.manifest, self.inventory, self.figures)
        ready = [chapter for chapter in chapters if chapter["status"] == "ready"]
        self.assertGreaterEqual(len(ready), 10)
        self.assertTrue(
            all(
                chapter["command"]
                and chapter["expected_output"]
                and chapter["mathematical_input"]
                and chapter["intermediate_geometry"]
                and chapter["support_limits"]
                for chapter in ready
            )
        )
        campaign = next(
            chapter for chapter in chapters if chapter["id"] == "native-substitution-matrix"
        )
        self.assertEqual(campaign["status"], "ready")
        self.assertIn("513 admitted", campaign["summary"])
        self.assertTrue(campaign["command"])
        self.assertFalse(any(chapter["status"] == "pending" for chapter in chapters))

    def test_runnable_lesson_inputs_are_math_first_and_match_source_fixtures(self):
        chapters = learning_book.validate(self.manifest, self.inventory, self.figures)
        by_id = {chapter["id"]: chapter for chapter in chapters}
        for chapter in (item for item in chapters if item["status"] == "ready"):
            chapter_id = chapter["id"]
            self.assertTrue(
                by_id[chapter_id].get("mathematical_displays")
                or by_id[chapter_id].get("mathematical_tables"),
                chapter_id,
            )
            html = learning_book._chapter_page(
                by_id[chapter_id],
                chapters,
                (learning_book.CHAPTER_ROOT / by_id[chapter_id]["source"]).read_text(),
                self.figures,
                self.inventory,
            )
            self.assertIn("<h2>Mathematical input</h2>", html)
            if chapter.get("mathematical_displays"):
                self.assertIn('class="math-matrix"', html)
            else:
                self.assertIn("<table>", html)
            self.assertIn('<details class="lesson-input-details">', html)
            self.assertNotIn("<h3>Input</h3><pre", html)
            if chapter_id == "representation-consumers":
                preservation = json.loads(
                    (ROOT / "reports/published-route-preservation/manifest.json").read_text()
                )
                self.assertEqual(
                    hashlib.sha256(html.encode()).hexdigest(),
                    preservation["mutable_copy_reviewed_sha256"][
                        "learn/representation-consumers.html"
                    ],
                )

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
        game = next(
            item for item in broken["chapters"] if item["id"] == "finite-controller-consumers"
        )
        game["mathematical_tables"][0]["rows"][0][2] = "0"
        with self.assertRaisesRegex(
            ValueError, "transition table differs from its executable fixture"
        ):
            learning_book.validate(broken, self.inventory, self.figures)
        broken = json.loads(json.dumps(self.manifest))
        game = next(
            item for item in broken["chapters"] if item["id"] == "finite-controller-consumers"
        )
        game["source_witnesses"][0]["contains"][0] = "Game{states, actions, inputs}"
        with self.assertRaisesRegex(ValueError, "source fixture changed"):
            learning_book.validate(broken, self.inventory, self.figures)

    def test_ready_figure_page_shows_scope_gaps_and_data_links(self):
        chapters = learning_book.validate(self.manifest, self.inventory, self.figures)
        chapter = next(item for item in chapters if item["id"] == "lotka-capstone")
        index = {
            "schema": "csl.closed-loop.figure-index/1",
            "figures": [
                {
                    "id": "lotka-populations",
                    "availability": "ready",
                    "href": "examples/closed-loop/figures/lotka-populations.html",
                    "plotted_data_href": "examples/closed-loop/figures/lotka-populations.plotted-data.json",
                    "layer_scopes": ["observed plant replay", "retained graph nodes"],
                    "missing_layers": [
                        "all-admissible-control forward sets",
                        "full-state intersections",
                    ],
                },
                {"id": "earth-orbit", "availability": "pending", "reason": "Not in this chapter."},
                {"id": "fuel-state", "availability": "pending", "reason": "Not in this chapter."},
            ],
        }
        html = learning_book._chapter_page(
            chapter,
            chapters,
            (ROOT / "docs/examples/learning/chapters/lotka-capstone.html").read_text(),
            index,
            self.inventory,
        )
        self.assertIn("observed plant replay; retained graph nodes", html)
        self.assertIn("all-admissible-control forward sets; full-state intersections", html)
        self.assertIn("lotka-populations.plotted-data.json", html)

    def test_fuel_coordinate_maps_render_as_accessible_mathml_matrices(self):
        chapters = learning_book.validate(self.manifest, self.inventory, self.figures)
        chapter = next(item for item in chapters if item["id"] == "fuel-capstone")
        html = learning_book._chapter_page(
            chapter,
            chapters,
            (ROOT / "docs/examples/learning/chapters/fuel-capstone.html").read_text(),
            self.figures,
            self.inventory,
        )
        self.assertIn(
            'role="math" aria-label="Physical state x, rows [m_ox, m_f, q_ox, q_f]: 100; 30; 2; 0.6"',
            html,
        )
        self.assertIn(
            'aria-label="Oxidizer projection P_ox x = [q_ox, m_ox]^T: 0, 0, 1, 0; 1, 0, 0, 0"', html
        )
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

    def test_analytic_book_commands_print_the_recorded_values(self):
        cases = (
            (
                "same-geometry-five-representations",
                "learning_geometry_toy.py",
                "d=(1.0, 0.0); exact_square=1; outer_disk=1.41421\n"
                "d=(1.0, 1.0); exact_square=2; outer_disk=2\n"
                "polytope=exact zonotope=exact parallelotope=exact ellipsoid=outer box=exact\n"
                "Q subset E; E subset [-sqrt(2),sqrt(2)]^2; Q is [-1,1]^2\n",
            ),
            (
                "closed-loop-semantics",
                "learning_closed_loop_toy.py",
                "update=0 observation=0 action=1 prediction_end=1 plant_state=1\n"
                "update=1 observation=1 action=0 prediction_end=1 plant_state=1\n",
            ),
        )
        for lesson_id, script, expected in cases:
            with self.subTest(lesson=lesson_id):
                chapter = next(
                    item for item in self.manifest["chapters"] if item["id"] == lesson_id
                )
                path = f"scripts/reports/{script}"
                self.assertEqual(chapter["command"], f"python3 {path}")
                result = subprocess.run(
                    [sys.executable, path], cwd=ROOT, check=True, capture_output=True, text=True
                )
                self.assertEqual(result.stdout, expected)
                self.assertEqual(chapter["expected_output"] + "\n", expected)

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
            self.assertIn('href="model-tracks.html"', landing)
            tracks = (site / "learn/model-tracks.html").read_text()
            self.assertIn("syn-nl-lv-01/ode/1", tracks)
            self.assertIn("env717-earth-orbit/two-body-force-ode/continuous/1", tracks)
            self.assertIn("syn-nl-fuel-01/ode/1", tracks)
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

    def test_chapters_link_sources_checks_and_evidence_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            figure_index = site / "figure-index.json"
            figure_index.write_text(json.dumps(self.figures))
            learning_book.build(site, figure_index_path=figure_index)
            modules = {
                item["identity"].get("id") or item["identity"].get("symbol"): item
                for item in self.inventory["modules"]
            }
            for chapter in self.manifest["chapters"]:
                path = site / f"learn/{chapter['id']}.html"
                page = PageElements()
                page.feed(path.read_text())
                with self.subTest(chapter=chapter["id"]):
                    self.assertIn("Evidence class:", path.read_text())
                    for source in chapter["example_sources"]:
                        self.assertIn(learning_book._repository_href(source), page.links)
                    lesson_check = learning_book._repository_href(
                        "tests/reporting/test_learning_book.py"
                    )
                    self.assertIn(lesson_check, page.links)
                    chapter_modules = [modules[module_id] for module_id in chapter["module_ids"]]
                    for test_path in learning_book._module_test_declarations(chapter_modules):
                        self.assertIn(learning_book._repository_href(test_path), page.links)
                    self.assertIn("not a numerical algorithm verifier", path.read_text())

    def test_module_catalogue_exposes_source_contract_limits_and_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            figure_index = site / "figure-index.json"
            figure_index.write_text(json.dumps(self.figures))
            learning_book.build(site, figure_index_path=figure_index)
            page = (site / "learn/module-catalogue.html").read_text()
            modules = self.inventory["modules"]
            self.assertIn("registered_provider", page)
            self.assertEqual(page.count("Actual interface or route."), len(modules))
            for module in modules:
                identity = module["identity"].get("id") or module["identity"].get("symbol")
                with self.subTest(module=identity):
                    self.assertIn(identity, page)
                    self.assertIn(str(module.get("assurance", "unspecified")), page)
                    self.assertIn(str(module.get("build", "unspecified")), page)
                    interface, interface_path, interface_note = learning_book._module_interface(
                        module
                    )
                    self.assertIn(learning_book._repository_href(interface_path), page)
                    self.assertIn(interface, page)
                    self.assertIn(interface_note, page)
                    source = module.get("source", {}).get("path")
                    if source:
                        self.assertIn(learning_book._repository_href(source), page)

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
                    "Axis ellipsoid directions, 2 by 2; one direction per row in x,y order: 1, 0; 0, 1",
                    "Rotated ellipsoid directions, 2 by 2; one direction per row in x,y order: 1, 1; 1, -1",
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
                "native-substitution-matrix": [
                    "Retained graph layers and selected policy path",
                    "I_ret[k] = F_ret[k] ∩ B_ret[k]",
                    "<td>Total</td><td>513</td><td>483</td><td>7</td><td>15</td><td>8</td>",
                    "513",
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
            expected["native-quadcopter-mpc"] = [
                "Q diagonal; terminal QN=Q: 0, 0, 10, 10, 10, 10, 0, 0, 0, 5, 5, 5",
                "Reference r: 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0",
            ]
            expected["native-forward-models"] = [
                "Slide 50",
                "Separately authored box; historical X0 unavailable",
                "Spatial flight",
                "Authored deviation set about a synthetic nonlinear reference",
            ]
            expected["native-model-tracking-first-pass"] = [
                "records",
                "34 · horizon-free",
                "Authored three-stage zero-target quadratic tracking",
            ]
            self.assertEqual(
                set(expected),
                {
                    chapter["id"]
                    for chapter in self.manifest["chapters"]
                    if chapter["status"] == "ready"
                },
            )
            for chapter_id, values in expected.items():
                page = (site / f"learn/{chapter_id}.html").read_text()
                primary = page.split('<section class="learning-math">', 1)[1].split(
                    "</section>", 1
                )[0]
                self.assertNotIn("<details", primary)
                for value in values:
                    with self.subTest(chapter=chapter_id, value=value):
                        self.assertIn(value, primary)

    def test_built_pages_retain_shared_layout_and_resolve_saved_report_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            index = site / "figure-index.json"
            index.write_text(json.dumps(self.figures))
            (site / "examples").mkdir()
            (site / "examples/index.html").write_text('<h1 id="gallery">Examples</h1>')
            report = "issue824-two-points-nominal-v2/index.html"
            (site / report).parent.mkdir()
            (site / report).write_bytes((ROOT / "reports/algorithm-results" / report).read_bytes())
            learning_book.build(site, figure_index_path=index)
            for path in (site / "learn").glob("*.html"):
                page = PageElements()
                page.feed(path.read_text())
                with self.subTest(page=path.name):
                    self.assertIn("page-content", page.main_classes)
            path = site / "learn/simplex-and-comparators.html"
            page = PageElements()
            page.feed(path.read_text())
            links = [href for href in page.links if "issue824-two-points-nominal-v2" in href]
            self.assertEqual(len(links), 2)
            for href in links:
                target = urlsplit(href)
                destination = (path.parent / unquote(target.path)).resolve()
                self.assertTrue(destination.is_file(), href)
                if target.fragment:
                    destination_page = PageElements()
                    destination_page.feed(destination.read_text())
                    self.assertIn(unquote(target.fragment), destination_page.ids, href)

    def test_build_joins_and_copies_ready_recorded_figure_assets(self):
        entries = []
        for figure_id in ("fuel-state", "fuel-fuel-flow"):
            route = f"examples/closed-loop/figures/{figure_id}"
            entries.append(
                {
                    "id": figure_id,
                    "availability": "ready",
                    "href": route + ".html",
                    "plotted_data_href": route + ".plotted-data.json",
                    "svg_href": route + ".svg",
                    "png_href": route + ".png",
                    "layer_scopes": ["observed plant replay"],
                    "missing_layers": ["all-admissible-control forward sets"],
                }
            )
        entries.extend(
            {"id": figure_id, "availability": "pending", "reason": "Not part of this smoke."}
            for figure_id in ("lotka-populations", "earth-orbit")
        )
        entries.extend(self.campaign_figures)
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
