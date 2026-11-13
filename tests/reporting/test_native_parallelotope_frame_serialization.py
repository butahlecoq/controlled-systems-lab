"""Exercise the native bridge's real saved fixed-plan trace response."""

from __future__ import annotations

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


def _run_native_query(bridge: Path, representation_index: int) -> dict:
    completed = subprocess.run(
        [str(bridge)],
        input=json.dumps(_query(representation_index), separators=(",", ":")) + "\n",
        text=True,
        capture_output=True,
        check=True,
        timeout=20,
    )
    return json.loads(completed.stdout)


class NativeParallelotopeFrameSerializationTests(unittest.TestCase):
    def test_four_state_frame_projects_real_native_trace_corners_to_physical_state(self):
        bridge_value = os.environ.get("CSL_NATIVE_POLICY_BRIDGE")
        self.assertTrue(bridge_value, "CSL_NATIVE_POLICY_BRIDGE must name the built native bridge")
        bridge = Path(bridge_value).resolve(strict=True)

        responses = [_run_native_query(bridge, index) for index in range(5)]
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
            plane = figures.PLANES["syn-nl-fuel-01"]
            attempt_id = "native-parallelotope-frame"
            attempt_dir = capture_root / plane.case_id / "attempts" / attempt_id
            attempt_dir.mkdir(parents=True)
            task_sha = "a" * 64
            stage_record = {
                "update_index": 0,
                "original_task_sha256": task_sha,
                "status": "applied-and-observed",
                "observed_physical": _query(3)["observed_physical_state"],
                "selected_plan": responses[3]["selected_plan"],
                "execution": {
                    "status": "complete",
                    "physical_states": responses[3]["selected_plan"]["states"],
                    "times": [0.0, 1.0],
                },
                "predicted_sets": [trace],
            }
            (attempt_dir / "stage-000.json").write_text(json.dumps(stage_record))
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
            report_data = figures._collect_run(plane, attempt_id, capture_root)
            self.assertEqual(len(report_data["fixed_plan_enclosures"]), len(trace["stages"]))
            saved_shape = report_data["fixed_plan_enclosures"][0]
            self.assertEqual(saved_shape["frame_status"], "provided")
            self.assertEqual(saved_shape["projection_status"], "projected")
            self.assertEqual(saved_shape["shape"]["frame"], FRAME)
            self.assertEqual(saved_shape["role"], "fixed-plan-trajectory-enclosure")
            self.assertTrue(saved_shape["projected_geometry"])
            self.assertEqual(saved_shape["source_pointer"], "stage-000.json#/predicted_sets/0/stages/0")
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

            # A legacy trace without the serialized frame stays source-agnostic.
            legacy_trace = dict(trace)
            legacy_trace.pop("frame")
            legacy_trace.pop("coordinate_semantics")
            stage_record["predicted_sets"] = [legacy_trace]
            (attempt_dir / "stage-000.json").write_text(json.dumps(stage_record))
            legacy_data = figures._collect_run(plane, attempt_id, capture_root)
            self.assertEqual(
                legacy_data["fixed_plan_enclosures"][0]["frame_status"],
                "missing or unrecognized coordinate semantics; not projected",
            )
            self.assertIsNone(legacy_data["fixed_plan_enclosures"][0]["projected_geometry"])


if __name__ == "__main__":
    unittest.main()
