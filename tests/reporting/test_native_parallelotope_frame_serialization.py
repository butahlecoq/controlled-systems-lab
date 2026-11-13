"""Exercise the native bridge's real saved fixed-plan trace response."""

from __future__ import annotations

import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

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
        "task_id": "serialization-test/four-state",
        "task_sha256": "0" * 64,
        "source_model_id": "serialization-test/identity-plant",
        "controller_id": "native-parallelotope-fixed-plan-mpc/1",
        "action_profile_id": "serialization-test/one-action",
        "problem_id": "serialization-test/four-state",
        "request_id": "serialization-test/query-0",
        "absolute_update_index": 0,
        "observed_physical_state": [1.0, 2.0, 3.0, 4.0],
        "original_horizon": 1,
        "dt": 1.0,
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
        bridge_value = os.environ.get("CSL_NATIVE_POLICY_BRIDGE")
        self.assertTrue(bridge_value, "CSL_NATIVE_POLICY_BRIDGE must name the built native bridge")
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
            y_corners = itertools.product(*zip(bounds["lower"], bounds["upper"]))
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
            self.assertIsNotNone(projected)
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
            from attempt_records import STAGE_INDEX, finalize_stage, persist_native_capture, write_attempt

            plane = figures.PLANES["syn-nl-fuel-01"]
            plane = figures.Plane(**{**plane.__dict__, "task_id": _query(3)["task_id"]})
            task_sha = _query(3)["task_sha256"]
            request_bytes = (json.dumps(_query(3), separators=(",", ":")) + "\n").encode()

            def write_referenced_attempt(name: str, raw_response: str) -> str:
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
                capture_reference = persist_native_capture(attempt_dir, 0, capture, {})
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
                        "times": [0.0, 1.0],
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
                    "source_commit": figures.SOURCE_COMMIT,
                    "task_sha256": task_sha,
                    "resource_profile_id": "worker-wall-1800-cpu-1800/1",
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
                for point in itertools.product(*zip(stage_bounds["lower"], stage_bounds["upper"]))
            ]
            projected = saved_shape["projected_geometry"]
            for projected_axis, physical_axis in enumerate(plane.raw_indices):
                expected = [point[physical_axis] for point in physical_corners]
                actual = [point[projected_axis] for point in projected]
                self.assertAlmostEqual(min(actual), min(expected), places=9)
                self.assertAlmostEqual(max(actual), max(expected), places=9)

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

            response_file.write_text(response_file.read_text() + " ")
            with self.assertRaisesRegex(ValueError, "v2 stage evidence is invalid"):
                figures._collect_run(plane, attempt_id, capture_root)


if __name__ == "__main__":
    unittest.main()
