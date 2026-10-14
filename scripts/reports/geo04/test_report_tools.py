"""Unit checks for GEO-04 saved-record summaries and safe offline rendering."""
from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import tempfile
import copy
import sys
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
import geo04_catalog

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("geo04_collect", HERE / "collect.py")
collect = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = collect
SPEC.loader.exec_module(collect)
SPEC = importlib.util.spec_from_file_location("geo04_render", HERE / "render.py")
render = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = render
SPEC.loader.exec_module(render)


def trial(scenario: str, status: str = "passed") -> dict:
    return {"scenario": scenario, "repetition": 0, "status": status, "oracle_passed": status == "passed", "detail": "",
            **{key: 100 for key in collect.PHASES}}


def valid_trials() -> list[dict]:
    rows = []
    for repetition in range(7):
        for scenario in collect.SCENARIOS:
            case = collect.EXPECTED[scenario]
            row = trial(scenario)
            row["repetition"] = repetition
            row.update({"lp_calls": 3 if scenario == "essential_rows_highs" else 0,
                        "lp_results": 3 if scenario == "essential_rows_highs" else 0,
                        "lp_optimal": 1 if scenario == "essential_rows_highs" else 0,
                        "lp_bounds": 0, "lp_supported_bounds": 0,
                        "reduction_status": case.get("reduction_status", "not_applicable"),
                        "vertices_json": copy.deepcopy(case.get("vertices", [])),
                        "inequalities": case["inequalities"], "equalities": case.get("equalities", 0),
                        "vertices": len(case.get("vertices", []))})
            row["scenario_sha256"] = hashlib.sha256(json.dumps(case,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
            row["input_sha256"] = hashlib.sha256(json.dumps(case["inputs"],sort_keys=True,separators=(",", ":")).encode()).hexdigest()
            rows.append(row)
    return rows


def valid_payload(report_id: str) -> dict:
    rows = valid_trials()
    expected = collect.EXPECTED
    payload = {"schema": render.SCHEMA, "report_id": report_id,
        "algorithm": {"id": "GEO-04", "source_commit": "abc", "harness_commit": "def"},
        "collection": {"state": "complete", "expected_trials": len(rows), "actual_trials": len(rows), "failures": 0,
                       "measured_repetitions": 7, "process_return_code": 0, "aborted_or_timed_out": False, "parse_error": None},
        "expected": expected,
        "inputs": {"scenario_catalog_version": render.CATALOG_VERSION,
                   "scenario_catalog_sha256": hashlib.sha256(json.dumps(expected,sort_keys=True,separators=(",", ":")).encode()).hexdigest()},
        "summary": collect.summarize(rows,True), "trials": rows,
        "evidence": {"essential_row_result": "HiGHS has no supported bounds.", "limitations": ["no speedup claim"]}}
    return payload


class ReportToolTests(unittest.TestCase):
    def test_source_identity_rejects_changes_to_any_dependency_implementation(self):
        for changed in ("src/adapters/polyhedral/qhull.cpp", "src/adapters/lp/highs.cpp", "src/numeric/data.cpp"):
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(ValueError, "outside the report harness allowlist"):
                    collect.validate_source_tree_delta([changed])

    def test_source_identity_allows_only_declared_report_harness_paths(self):
        collect.validate_source_tree_delta([
            "reports/algorithm-results/tooling/geo04/collect.py",
        ])

    def test_cmake_provenance_allows_only_exact_geo04_report_target_insertion(self):
        baseline = collect.GEO03_CMAKE_OPTION + "\n" + collect.GEO03_CMAKE_TARGET + "\nadd_library(core src/core.cpp)\n"
        harness = baseline.replace(collect.GEO03_CMAKE_OPTION, collect.GEO03_CMAKE_OPTION + "\n" + collect.GEO04_CMAKE_OPTION, 1)
        harness = harness.replace(collect.GEO03_CMAKE_TARGET, collect.GEO03_CMAKE_TARGET + "\n" + collect.GEO04_CMAKE_TARGET, 1)
        collect.validate_cmake_delta(baseline, harness)

    def test_cmake_provenance_rejects_unrelated_compile_definition_or_source_change(self):
        baseline = collect.GEO03_CMAKE_OPTION + "\n" + collect.GEO03_CMAKE_TARGET + "\nadd_library(core src/core.cpp)\n"
        harness = baseline.replace(collect.GEO03_CMAKE_OPTION, collect.GEO03_CMAKE_OPTION + "\n" + collect.GEO04_CMAKE_OPTION, 1)
        harness = harness.replace(collect.GEO03_CMAKE_TARGET, collect.GEO03_CMAKE_TARGET + "\n" + collect.GEO04_CMAKE_TARGET, 1)
        for unrelated in ("add_compile_definitions(CSL_CHANGED=1)\n", "add_library(core src/other.cpp)\n"):
            with self.subTest(unrelated=unrelated):
                with self.assertRaisesRegex(ValueError, "beyond the exact GEO-04 report-target insertion"):
                    collect.validate_cmake_delta(baseline, harness + unrelated)

    def test_collector_oracle_rejects_duplicate_replacing_missing_vertex_within_tolerance(self):
        expected = collect.EXPECTED["crossing_octagon"]["vertices"]
        actual = [point[:] for point in expected]
        actual[1] = [1, 0.50000009]
        self.assertFalse(collect.vertices_match_expected(actual, expected))

    def test_renderer_oracle_rejects_duplicate_replacing_missing_vertex_within_tolerance(self):
        expected = collect.EXPECTED["crossing_octagon"]["vertices"]
        actual = [point[:] for point in expected]
        actual[1] = [1, 0.50000009]
        self.assertFalse(render.vertices_match_expected(actual, expected))

    def test_failure_invalidates_all_phase_summaries_instead_of_filtering_successes(self):
        rows = [trial(scenario) for scenario in collect.SCENARIOS]
        rows.append({**trial("crossing_octagon", "failed"), "repetition": 1})
        summaries = collect.summarize(rows, complete_group=False)
        self.assertEqual(summaries["crossing_octagon"]["failures"], 1)
        self.assertIsNone(summaries["crossing_octagon"]["phases"]["conversion_run_ns"]["median"])
        self.assertEqual(summaries["crossing_octagon"]["phases"]["conversion_run_ns"]["successful_trials"], 0)

    def test_rendering_escapes_untrusted_failure_detail_and_shows_scope(self):
        payload = valid_payload("geo04-test")
        payload["trials"][0]["detail"] = "<script>alert(1)</script>"
        unsigned = {key:value for key,value in payload.items() if key!="report_id"}
        payload["payload_sha256"] = hashlib.sha256(json.dumps(unsigned,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        payload["payload_hash_scope"] = "canonical JSON payload excluding report_id, payload_sha256, and payload_hash_scope"
        render.validate(payload)
        page = render.render_html(payload)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>alert", page)
        self.assertIn("not a benchmark backend", page)
        self.assertIn("reduction + LP", render.render_svg(payload))
        tampered = copy.deepcopy(payload)
        tampered["trials"][0]["vertices_json"][0][0] = 9.0
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            render.validate(tampered)

    def test_renderer_oracle_rejects_resigned_duplicate_vertex_substitution(self):
        payload = valid_payload("geo04-resigned-substitution")
        points = copy.deepcopy(payload["trials"][0]["vertices_json"])
        points[1] = [1, 0.50000009]
        payload["trials"][0]["vertices_json"] = points
        unsigned = {key:value for key,value in payload.items() if key not in ("report_id", "payload_sha256", "payload_hash_scope")}
        payload["payload_sha256"] = hashlib.sha256(json.dumps(unsigned,sort_keys=True,separators=(",", ":"),allow_nan=False).encode()).hexdigest()
        payload["payload_hash_scope"] = "canonical JSON payload excluding report_id, payload_sha256, and payload_hash_scope"
        with self.assertRaisesRegex(ValueError, "saved vertex coordinates fail independent literal oracle"):
            render.validate(payload)

    def test_renderer_rejects_fully_resigned_altered_scenario_catalog(self):
        payload = valid_payload("geo04-altered-catalog")
        payload["expected"] = copy.deepcopy(payload["expected"])
        changed = payload["expected"]["crossing_octagon"]
        changed["vertices"][1] = [1, 0.50000009]
        case = changed
        trial_row = payload["trials"][0]
        trial_row["vertices_json"] = copy.deepcopy(case["vertices"])
        trial_row["scenario_sha256"] = hashlib.sha256(json.dumps(case,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        trial_row["input_sha256"] = hashlib.sha256(json.dumps(case["inputs"],sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        payload["inputs"]["scenario_catalog_sha256"] = hashlib.sha256(json.dumps(payload["expected"],sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        unsigned = {key:value for key,value in payload.items() if key not in ("report_id", "payload_sha256", "payload_hash_scope")}
        payload["payload_sha256"] = hashlib.sha256(json.dumps(unsigned,sort_keys=True,separators=(",", ":"),allow_nan=False).encode()).hexdigest()
        payload["payload_hash_scope"] = "canonical JSON payload excluding report_id, payload_sha256, and payload_hash_scope"
        with self.assertRaisesRegex(ValueError, "scenario catalog differs from pinned catalog"):
            render.validate(payload)

    def test_renderer_oracle_is_independent_of_collector_catalog_drift(self):
        original = copy.deepcopy(geo04_catalog.EXPECTED)
        try:
            geo04_catalog.EXPECTED["crossing_octagon"]["vertices"][1] = [1, 0.50000009]
            payload = valid_payload("geo04-collector-catalog-drift")
            unsigned = {key:value for key,value in payload.items() if key not in ("report_id", "payload_sha256", "payload_hash_scope")}
            payload["payload_sha256"] = hashlib.sha256(json.dumps(unsigned,sort_keys=True,separators=(",", ":"),allow_nan=False).encode()).hexdigest()
            payload["payload_hash_scope"] = "canonical JSON payload excluding report_id, payload_sha256, and payload_hash_scope"
            with self.assertRaisesRegex(ValueError, "scenario catalog differs from pinned catalog"):
                render.validate(payload)
        finally:
            geo04_catalog.EXPECTED.clear()
            geo04_catalog.EXPECTED.update(original)

    def test_renderer_rejects_resigned_complete_report_missing_a_scenario(self):
        payload = valid_payload("geo04-missing-scenario")
        payload["trials"] = [row for row in payload["trials"] if row["scenario"] != "empty_intersection"]
        payload["collection"].update({"expected_trials": 21, "actual_trials": 21, "failures": 0})
        payload["summary"] = collect.summarize(payload["trials"], True)
        unsigned = {key:value for key,value in payload.items() if key not in ("report_id", "payload_sha256", "payload_hash_scope")}
        payload["payload_sha256"] = hashlib.sha256(json.dumps(unsigned,sort_keys=True,separators=(",", ":"),allow_nan=False).encode()).hexdigest()
        payload["payload_hash_scope"] = "canonical JSON payload excluding report_id, payload_sha256, and payload_hash_scope"
        with self.assertRaisesRegex(ValueError, "collection counts or scenario/repetition matrix"):
            render.validate(payload)

    def test_renderer_rejects_resigned_phase_summaries_inconsistent_with_trial_rows(self):
        payload = valid_payload("geo04-fabricated-phase-summary")
        for row in payload["trials"]:
            for phase in collect.PHASES:
                row[phase] = 0
        for group in payload["summary"].values():
            for stat in group["phases"].values():
                stat.update({"median": 999_999_999, "min": 999_999_999, "max": 999_999_999,
                             "range": 0, "successful_trials": 7, "trials_excluded_from_summary": 0})
        unsigned = {key:value for key,value in payload.items() if key not in ("report_id", "payload_sha256", "payload_hash_scope")}
        payload["payload_sha256"] = hashlib.sha256(json.dumps(unsigned,sort_keys=True,separators=(",", ":"),allow_nan=False).encode()).hexdigest()
        payload["payload_hash_scope"] = "canonical JSON payload excluding report_id, payload_sha256, and payload_hash_scope"
        with self.assertRaisesRegex(ValueError, "phase summary differs from saved trial timings"):
            render.validate(payload)

    def test_renderer_rejects_resigned_summary_with_unpinned_scenario(self):
        payload = valid_payload("geo04-extra-summary-scenario")
        payload["summary"]["unexpected"] = copy.deepcopy(payload["summary"]["crossing_octagon"])
        unsigned = {key:value for key,value in payload.items() if key not in ("report_id", "payload_sha256", "payload_hash_scope")}
        payload["payload_sha256"] = hashlib.sha256(json.dumps(unsigned,sort_keys=True,separators=(",", ":"),allow_nan=False).encode()).hexdigest()
        payload["payload_hash_scope"] = "canonical JSON payload excluding report_id, payload_sha256, and payload_hash_scope"
        with self.assertRaisesRegex(ValueError, "summary scenario keys differ from pinned scenario set"):
            render.validate(payload)

    def test_renderer_rejects_boolean_phase_statistics_that_compare_equal_to_integers(self):
        for field, value in (("min", True), ("trials_excluded_from_summary", False)):
            with self.subTest(field=field):
                payload = valid_payload(f"geo04-bool-phase-{field}")
                for row in payload["trials"]:
                    row["intersection_ns"] = 1
                payload["summary"] = collect.summarize(payload["trials"], True)
                payload["summary"]["crossing_octagon"]["phases"]["intersection_ns"][field] = value
                unsigned = {key:value for key,value in payload.items() if key not in ("report_id", "payload_sha256", "payload_hash_scope")}
                payload["payload_sha256"] = hashlib.sha256(json.dumps(unsigned,sort_keys=True,separators=(",", ":"),allow_nan=False).encode()).hexdigest()
                payload["payload_hash_scope"] = "canonical JSON payload excluding report_id, payload_sha256, and payload_hash_scope"
                with self.assertRaisesRegex(ValueError, "phase summary numeric types are invalid"):
                    render.validate(payload)

    def test_collector_finalized_payload_passes_renderer_using_declared_hash_scope(self):
        payload = valid_payload("placeholder")
        payload["report_id"] = None
        report_id = collect.finalize_payload(payload, "20261013T120000Z")
        self.assertEqual(payload["report_id"], report_id)
        render.validate(payload)

    def test_finalized_digest_matches_the_exact_declared_exclusion_scope(self):
        payload = valid_payload(None)
        scope = "canonical JSON payload excluding report_id, payload_sha256, and payload_hash_scope"
        collect.finalize_payload(payload, "20261013T120000Z")
        self.assertEqual(payload["payload_hash_scope"], scope)
        excluded = {"report_id", "payload_sha256", "payload_hash_scope"}
        canonical = {key:value for key,value in payload.items() if key not in excluded}
        expected = hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(",", ":"),allow_nan=False).encode()).hexdigest()
        self.assertEqual(payload["payload_sha256"], expected)

    def test_phase_chart_left_column_labels_have_non_overlapping_vertical_rows(self):
        root = ET.fromstring(render.render_svg(valid_payload("geo04-chart-layout")))
        ns = {"svg": "http://www.w3.org/2000/svg"}
        baselines = sorted(float(node.attrib["y"]) for node in root.findall(".//svg:text[@x='8']", ns))
        self.assertGreater(len(baselines), 4)
        for previous, current in zip(baselines, baselines[1:]):
            self.assertGreaterEqual(current-previous, 15, f"overlapping chart labels at y={previous} and y={current}")

    def test_report_tables_are_wrapped_in_keyboard_accessible_horizontal_scrollers(self):
        page = render.render_html(valid_payload("geo04-table-layout"))
        self.assertEqual(page.count('<div class="table-scroll"'), 2)
        self.assertEqual(page.count('tabindex="0"><table>'), 2)
        self.assertIn("overflow-x:auto", page)
        self.assertIn('tabindex="0"', page)
        self.assertIn("width:max-content;min-width:100%", page)

    def test_offline_export_uses_saved_records_only_and_packages_required_files(self):
        payload = valid_payload("geo04-offline-test")
        unsigned = {key:value for key,value in payload.items() if key!="report_id"}
        payload["payload_sha256"] = hashlib.sha256(json.dumps(unsigned,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        payload["payload_hash_scope"] = "canonical JSON payload excluding report_id, payload_sha256, and payload_hash_scope"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); collection = root / "collection"; collection.mkdir()
            (collection / "records.json").write_text(json.dumps(payload),encoding="utf-8")
            for name in render.FILES:
                path = collection / name
                if not path.exists(): path.write_text("test fixture\n",encoding="utf-8")
            bundle = root / "bundle"
            subprocess.run([sys.executable,str(HERE / "render.py"),"--collection",str(collection),"--out",str(bundle)],check=True)
            self.assertTrue((bundle / "index.html").is_file())
            self.assertTrue((bundle / "latency.svg").is_file())
            self.assertTrue((root / "geo04-offline-test.zip").is_file())

    def test_renderer_rejects_failed_group_with_success_only_summary(self):
        rows = [trial(scenario) for scenario in collect.SCENARIOS]
        summary = collect.summarize(rows, complete_group=False)
        self.assertTrue(all(stat["median"] is None for group in summary.values() for stat in group["phases"].values()))


if __name__ == "__main__":
    unittest.main()
