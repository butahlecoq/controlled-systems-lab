"""Exercise the native bridge's real saved fixed-plan trace response."""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/reports"))
import recorded_closed_loop_figures as figures

FRAME = [
    [1.0, 1.0, 0.0, 0.0],
    [0.0, 1.0, 1.0, 0.0],
    [0.0, 0.0, 1.0, 1.0],
    [0.0, 0.0, 0.0, 1.0],
]


def _query(representation_index: int) -> dict:
    identity = [[float(row == col) for col in range(4)] for row in range(4)]
    names = ("exact-polytope", "box", "zonotope", "parallelotope", "ellipsoid")
    return {
        "schema": "csl.closed-loop.native-policy-query/1",
        "task_id": "syn-nl-fuel-01/continuous-receding/1",
        "task_sha256": "0" * 64,
        "source_model_id": "serialization-test/identity-plant",
        "controller_id": "native-parallelotope-fixed-plan-mpc/1",
        "action_profile_id": "serialization-test/one-action",
        "problem_id": "serialization-test/four-state",
        "request_id": "serialization-test/query-0",
        "absolute_update_index": 0,
        "observed_physical_state": [1.0, 2.0, 3.0, 4.0],
        "original_horizon": 1,
        "dt": 0.5,
        "predictor_model_id": "serialization-test/identity",
        "predictor_assurance": "binary64 numerical fixture",
        "predictor_stages": [
            {"A": identity, "B": [[0.0], [0.0], [0.0], [0.0]], "c": [0.0] * 4}
        ],
        "actions": [[0.0]],
        "state_bounds": [[-100.0, 100.0] for _ in range(4)],
        "terminal_objective": {
            "kind": "quadratic",
            "Q": identity,
            "linear": [0.0] * 4,
            "offset": 0.0,
        },
        "running_cost": {
            "objective_id": "serialization-test/zero-cost",
            "stages": [{"stage": 0, "terms": []}],
        },
        "representation_index": representation_index,
        "representation_name": names[representation_index],
        "limits": {
            "max_plans": 1,
            "max_points_per_stage": 16,
            "max_score_evaluations": 16,
            "max_generators_per_stage": 16,
        },
        "candidate_action_indices": [[0]],
        "candidate_search_policy": "serialization-test/single-history",
    }


def _run_native_query(bridge: Path, representation_index: int) -> tuple[dict, str]:
    completed = subprocess.run(
        [str(bridge)],
        input=json.dumps(_query(representation_index), separators=(",", ":")) + "\n",
        text=True,
        capture_output=True,
        check=True,
        timeout=20,
    )
    return json.loads(completed.stdout), completed.stdout


class NativeParallelotopeFrameSerializationTests(unittest.TestCase):
    def test_four_state_frame_projects_real_native_trace_corners_to_physical_state(self):
        self._check_native_trace(render_cli=False)

    @unittest.skipUnless(importlib.util.find_spec("matplotlib"),
                         "Public figure rendering requires the optional reporting matplotlib dependency")
    def test_public_cli_renders_current_referenced_native_capture(self):
        self._check_native_trace(render_cli=True)

    def _check_native_trace(self, *, render_cli: bool):
        bridge_value = os.environ.get("CSL_NATIVE_POLICY_BRIDGE")
        assert bridge_value, "CSL_NATIVE_POLICY_BRIDGE must name the built native bridge"
        bridge = Path(bridge_value).resolve(strict=True)

        native_runs = [_run_native_query(bridge, index) for index in range(5)]
        responses = [response for response, _ in native_runs]
        self.assertEqual([response["status"] for response in responses], ["accepted"] * 5)
        self.assertEqual(
            [response["predicted_sets"][0]["representation"] for response in responses],
            ["exact-polytope", "box", "zonotope", "parallelotope", "ellipsoid"],
        )
        for index, response in enumerate(responses):
            request = _query(index)
            self.assertEqual(response["task_id"], request["task_id"])
            self.assertEqual(response["task_sha256"], request["task_sha256"])
            self.assertEqual(response["action_profile_id"], request["action_profile_id"])
            self.assertEqual(response["policy_id"], request["controller_id"] + "/receding-fixed-plan-mpc/1")
            if index != 3:
                self.assertNotIn("frame", response["predicted_sets"][0])
        trace = responses[3]["predicted_sets"][0]
        self.assertIn("frame", trace)
        self.assertIn("coordinate_semantics", trace)
        self.assertEqual(trace["frame"], FRAME)
        self.assertEqual(
            trace["coordinate_semantics"],
            {
                "physical_state": "x",
                "frame_state": "y",
                "mapping": "x = frame * y",
                "stage_bounds": "lower and upper are frame coordinates y",
            },
        )

        plan_states = responses[3]["selected_plan"]["states"]
        for stage_index, bounds in enumerate(trace["stages"]):
            y_corners = itertools.product(*zip(bounds["lower"], bounds["upper"], strict=False))
            physical_corners = [
                [sum(FRAME[row][col] * corner[col] for col in range(4)) for row in range(4)]
                for corner in y_corners
            ]
            shape = {
                "representation": "parallelotope",
                "frame": trace["frame"],
                "lower": bounds["lower"],
                "upper": bounds["upper"],
            }
            projected = figures.project_shape(shape, (0, 1))
            assert projected is not None
            for projected_axis, physical_axis in enumerate((0, 1)):
                expected = [point[physical_axis] for point in physical_corners]
                actual = [point[projected_axis] for point in projected]
                self.assertAlmostEqual(min(actual), min(expected), places=9)
                self.assertAlmostEqual(max(actual), max(expected), places=9)
            for coordinate in range(4):
                lower = min(point[coordinate] for point in physical_corners)
                upper = max(point[coordinate] for point in physical_corners)
                state = plan_states[stage_index][coordinate]
                self.assertLessEqual(lower - 1e-9, state)
                self.assertLessEqual(state, upper + 1e-9)

        # The first frame coordinate is near -2 while physical x1 is near 1;
        # treating serialized y-bounds as physical axis bounds cannot pass.
        first = trace["stages"][0]
        self.assertAlmostEqual(plan_states[0][0], 1.0, places=10)
        self.assertNotAlmostEqual((first["lower"][0] + first["upper"][0]) / 2, 1.0, places=3)

        # Feed the actual packet through the saved-stage collector that builds
        # report data, not only its lower-level geometry helper.
        with tempfile.TemporaryDirectory() as temporary:
            capture_root = Path(temporary)
            from attempt_records import (
                STAGE_INDEX,
                finalize_stage,
                persist_native_capture,
                write_attempt,
            )

            plane = figures.PLANES["syn-nl-fuel-01"]
            task_sha = _query(3)["task_sha256"]

            current_source = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True
            ).strip()

            def write_referenced_attempt(name: str, raw_response: str,
                                         request: dict | None = None,
                                         capture_index: int = 0) -> str:
                request_payload = request or _query(3)
                request_bytes = (json.dumps(request_payload, separators=(",", ":")) + "\n").encode()
                attempt_id = f"native-parallelotope-{name}"
                attempt_dir = capture_root / plane.case_id / "attempts" / attempt_id
                attempt_dir.mkdir(parents=True)
                capture = {
                    "schema": "csl.closed-loop.native-query-capture/2",
                    "capture_kind": "bridge-exchange",
                    "bridge_request_sent": True,
                    "bridge_request_transmission_status": "sent",
                    "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
                    "bridge_request_raw": request_bytes.decode(),
                    "bridge_response_sha256": hashlib.sha256(raw_response.encode()).hexdigest(),
                    "bridge_response_raw": raw_response,
                    "response_parse_status": "parsed",
                }
                capture_reference = persist_native_capture(attempt_dir, capture_index, capture, {})
                plan_states = json.loads(raw_response)["selected_plan"]["states"]
                control = json.loads(raw_response)["control"]
                stage_record = {
                    "update_index": 0,
                    "original_task_sha256": task_sha,
                    "status": "applied-and-observed",
                    "observed_physical": _query(3)["observed_physical_state"],
                    "applied_control": control,
                    "observed_next_physical": plan_states[-1],
                    "execution": {
                        "status": "complete",
                        "physical_states": plan_states,
                        "times": [0.0, plane.dt],
                    },
                    "native_query_capture": capture_reference,
                }
                finalize_stage(attempt_dir, 0, stage_record)
                controls = [control]
                attempt = {
                    "schema": "csl.closed-loop.attempt/2",
                    "format_version": 2,
                    "attempt_id": attempt_id,
                    "task_id": plane.task_id,
                    "task_sha256": task_sha,
                    "status": "complete",
                    "original_intervals": 1,
                    "completed_holds": 1,
                    "selected_initial_state_physical": _query(3)["observed_physical_state"],
                    "controls": controls,
                    "physical_states": [_query(3)["observed_physical_state"], plan_states[-1]],
                    "controls_sha256": hashlib.sha256(
                        json.dumps(controls, separators=(",", ":"), allow_nan=False).encode()
                    ).hexdigest(),
                    "stage_records": {"path": STAGE_INDEX, "count": 1},
                }
                write_attempt(attempt_dir, attempt)
                (attempt_dir / "run-manifest.json").write_text(json.dumps({
                    "attempt_id": attempt_id,
                    "source_commit": current_source,
                    "task_sha256": task_sha,
                    "resource_profile_id": "frame-serialization-functional/1",
                }))
                (attempt_dir / "resolution-receipt.json").write_text(json.dumps({
                    "task_id": plane.task_id,
                    "task_sha256": task_sha,
                    "selected_controller_id": "native-parallelotope-fixed-plan-mpc/1",
                }))
                (attempt_dir / "postcheck-initial.json").write_text(json.dumps({
                    "original_attempt_id": attempt_id,
                    "task_sha256": task_sha,
                    "overall_status": "complete",
                }))
                return attempt_id

            attempt_id = write_referenced_attempt("frame", native_runs[3][1])
            report_data = figures._collect_run(plane, attempt_id, capture_root)
            self.assertEqual(report_data["source_commit"], current_source)
            self.assertEqual(report_data["profile_id"], "frame-serialization-functional/1")
            self.assertEqual(len(report_data["fixed_plan_enclosures"]), len(trace["stages"]))
            saved_shape = report_data["fixed_plan_enclosures"][0]
            self.assertEqual(saved_shape["frame_status"], "provided")
            self.assertEqual(saved_shape["projection_status"], "projected")
            self.assertEqual(saved_shape["shape"]["frame"], FRAME)
            self.assertEqual(saved_shape["role"], "fixed-plan-trajectory-enclosure")
            self.assertTrue(saved_shape["projected_geometry"])
            self.assertEqual(saved_shape["source_pointer"],
                             "native-query-000-response.jsonl#/predicted_sets/0/stages/0")
            response_file = capture_root / plane.case_id / "attempts" / attempt_id / "native-query-000-response.jsonl"
            self.assertEqual(saved_shape["source_file_sha256"], hashlib.sha256(response_file.read_bytes()).hexdigest())
            stage_payload = json.loads(
                (capture_root / plane.case_id / "attempts" / attempt_id / "stage-000.json").read_text()
            )
            self.assertIn("native_query_capture", stage_payload)
            self.assertNotIn("predicted_sets", stage_payload)
            self.assertNotIn("selected_plan", stage_payload)
            self.assertEqual(
                {item["path"] for item in report_data["raw_record"]["native_capture_files"]},
                {
                    stage_payload["native_query_capture"]["path"],
                    "native-query-000-request.jsonl",
                    response_file.name,
                },
            )
            stage_bounds = trace["stages"][0]
            physical_corners = [
                [sum(FRAME[row][col] * point[col] for col in range(4)) for row in range(4)]
                for point in itertools.product(*zip(stage_bounds["lower"], stage_bounds["upper"], strict=False))
            ]
            projected = saved_shape["projected_geometry"]
            for projected_axis, physical_axis in enumerate(plane.raw_indices):
                expected = [point[physical_axis] for point in physical_corners]
                actual = [point[projected_axis] for point in projected]
                self.assertAlmostEqual(min(actual), min(expected), places=9)
                self.assertAlmostEqual(max(actual), max(expected), places=9)

            if render_cli:
                # The actual public CLI can select this fresh, referenced capture.
                output = capture_root / "rendered"
                script = Path(figures.__file__).resolve()
                subprocess.run(
                    [sys.executable, str(script), "--capture-root", str(capture_root),
                     "--output", str(output), "--attempt", f"{plane.case_id}={attempt_id}"],
                    text=True, capture_output=True, check=True, timeout=60,
                )
                figure_index = json.loads((output / "figure-index.json").read_text())
                self.assertEqual(len(figure_index["figures"]), 2)
                for entry in figure_index["figures"]:
                    self.assertEqual(entry["source_commits"], [current_source])
                    self.assertEqual(entry["profile_ids"], ["frame-serialization-functional/1"])
                    self.assertIn(f"--attempt {plane.case_id}={attempt_id}", entry["reproduction_command"])
                    page = (output / "figures" / (entry["id"] + ".html")).read_text()
                    self.assertIn(current_source, page)
                    self.assertNotIn(figures.SOURCE_COMMIT, page)
                    data = json.loads((output / "figures" / (entry["id"] + ".plotted-data.json")).read_text())
                    self.assertEqual(data["source_commit"], current_source)
                    self.assertEqual(data["reproduction_command"], entry["reproduction_command"])

            # A legacy referenced response without the serialized frame stays source-agnostic.
            legacy_response = json.loads(native_runs[3][1])
            legacy_response["predicted_sets"][0].pop("frame")
            legacy_response["predicted_sets"][0].pop("coordinate_semantics")
            legacy_raw = json.dumps(legacy_response, separators=(",", ":")) + "\n"
            legacy_attempt_id = write_referenced_attempt("legacy-frame", legacy_raw)
            legacy_data = figures._collect_run(plane, legacy_attempt_id, capture_root)
            self.assertEqual(
                legacy_data["fixed_plan_enclosures"][0]["frame_status"],
                "missing or unrecognized coordinate semantics; not projected",
            )
            self.assertIsNone(legacy_data["fixed_plan_enclosures"][0]["projected_geometry"])

            # Graph responses use their own offset receipt; retain that supported path.
            graph_query = _query(1)
            graph_query.update({
                "search_policy": "stage-layered-backward-viability",
                "reachable_set_method": {"id": "csl.geometry.affine-sum", "version": "1.0.0"},
                "hull_provider": {"id": "csl.hull.lp-membership", "version": "1.0.0"},
                "vertex_lp_provider": {"id": "phase-one-bland", "version": "1"},
                "conversion_provider": "not_used",
                "checker_budget": {"max_points": 64, "wall_ms": 5000},
                "control_optimizer": {
                    "id": "csl.optimization.finite-action-stage-layered-graph", "version": "1.0.0"
                },
            })
            graph_packet = subprocess.run([str(bridge)], input=json.dumps(graph_query) + "\n",
                                          text=True, capture_output=True, check=True, timeout=20)
            self.assertEqual(json.loads(graph_packet.stdout)["status"], "accepted")
            graph_id = write_referenced_attempt("graph", graph_packet.stdout, graph_query)
            graph_data = figures._collect_run(plane, graph_id, capture_root)
            self.assertTrue(graph_data["nodes"])

            # A valid later query cannot be relabelled as the initial query.
            later_query = _query(3)
            later_query["absolute_update_index"] = 1
            later_query["original_horizon"] = 2
            later_query["running_cost"]["stages"][0]["stage"] = 1
            later = subprocess.run([str(bridge)], input=json.dumps(later_query) + "\n",
                                   text=True, capture_output=True, check=True, timeout=20)
            self.assertEqual(json.loads(later.stdout)["status"], "accepted")
            swapped = write_referenced_attempt("later-query-swap", later.stdout, later_query)
            with self.assertRaisesRegex(ValueError, "query identity"):
                figures._collect_run(plane, swapped, capture_root)

            wrong_state = _query(3)
            wrong_state["observed_physical_state"] = [9.0, 2.0, 3.0, 4.0]
            wrong_receipt = json.loads(native_runs[3][1])
            wrong_receipt["query_receipt"]["original_horizon"] = 2
            for name, raw, request, capture_index in (
                ("observed-state", native_runs[3][1], wrong_state, 0),
                ("receipt-horizon", json.dumps(wrong_receipt), _query(3), 0),
                ("metadata-stage", native_runs[3][1], _query(3), 1),
            ):
                bad_id = write_referenced_attempt(name, raw, request, capture_index)
                with self.subTest(identity=name), self.assertRaisesRegex(ValueError, "query identity"):
                    figures._collect_run(plane, bad_id, capture_root)

            response_file.write_text(response_file.read_text() + " ")
            with self.assertRaisesRegex(ValueError, "v2 stage evidence is invalid"):
                figures._collect_run(plane, attempt_id, capture_root)


if __name__ == "__main__":
    unittest.main()
