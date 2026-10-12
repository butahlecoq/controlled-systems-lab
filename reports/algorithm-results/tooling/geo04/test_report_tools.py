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

HERE = Path(__file__).resolve().parent
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
    for scenario in collect.SCENARIOS:
        case = collect.EXPECTED[scenario]
        row = trial(scenario)
        row.update({"lp_calls": 3 if scenario == "essential_rows_highs" else 0,
                    "lp_results": 3 if scenario == "essential_rows_highs" else 0,
                    "lp_optimal": 1 if scenario == "essential_rows_highs" else 0,
                    "lp_bounds": 0, "lp_supported_bounds": 0,
                    "reduction_status": case.get("reduction_status", "not_applicable"),
                    "vertices_json": case.get("vertices", []),
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
        "collection": {"state": "complete", "expected_trials": len(rows), "actual_trials": len(rows), "failures": 0},
        "expected": expected,
        "inputs": {"scenario_catalog_sha256": hashlib.sha256(json.dumps(expected,sort_keys=True,separators=(",", ":")).encode()).hexdigest()},
        "summary": collect.summarize(rows,True), "trials": rows,
        "evidence": {"essential_row_result": "HiGHS has no supported bounds.", "limitations": ["no speedup claim"]}}
    return payload


class ReportToolTests(unittest.TestCase):
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
        payload["payload_hash_scope"] = "canonical JSON payload excluding report_id and payload_sha256"
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

    def test_offline_export_uses_saved_records_only_and_packages_required_files(self):
        payload = valid_payload("geo04-offline-test")
        unsigned = {key:value for key,value in payload.items() if key!="report_id"}
        payload["payload_sha256"] = hashlib.sha256(json.dumps(unsigned,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        payload["payload_hash_scope"] = "canonical JSON payload excluding report_id and payload_sha256"
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
