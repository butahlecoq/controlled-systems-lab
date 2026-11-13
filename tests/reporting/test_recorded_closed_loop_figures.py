from __future__ import annotations

import sys
import unittest
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/reports"))

import recorded_closed_loop_figures as figures


class RecordedClosedLoopFigureTests(unittest.TestCase):
    def test_attempt_selection_rejects_path_escapes_and_duplicates(self) -> None:
        selections: tuple[dict[str, tuple[str, ...]], ...] = ({}, {"unknown": ("attempt",)},
                          {"syn-nl-fuel-01": ("../escape",)},
                          {"syn-nl-fuel-01": ("attempt", "attempt")})
        for selection in selections:
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                figures.validate_attempt_selection(selection)
        figures.validate_attempt_selection({"syn-nl-fuel-01": ("attempt-01",)})

    def test_v2_stage_collector_checks_references_and_keeps_canonical_plot_inputs(self) -> None:
        import hashlib
        import json
        import tempfile

        from attempt_records import STAGE_INDEX, finalize_stage, write_attempt

        with tempfile.TemporaryDirectory() as raw:
            capture_root = Path(raw)
            plane = figures.PLANES["syn-nl-lv-01"]
            attempt_id = "v2-collector-fixture"
            attempt_dir = capture_root / plane.case_id / "attempts" / attempt_id
            attempt_dir.mkdir(parents=True)
            initial, final = [1.0, 2.0], [1.1, 2.1]
            task_sha = "a" * 64
            finalize_stage(attempt_dir, 0, {
                "update_index": 0,
                "original_task_sha256": task_sha,
                "status": "applied-and-observed",
                "observed_physical": initial,
                "applied_control": [0.0],
                "observed_next_physical": final,
                "selected_plan": {"states": [initial, final]},
                "execution": {"status": "complete", "physical_states": [initial, final],
                              "times": [0.0, plane.dt]},
            })
            controls = [[0.0]]
            record = {
                "schema": "csl.closed-loop.attempt/2", "format_version": 2,
                "attempt_id": attempt_id, "task_id": plane.task_id, "task_sha256": task_sha,
                "status": "complete", "completed_holds": 1, "original_intervals": 1,
                "selected_initial_state_physical": initial, "controls": controls,
                "physical_states": [initial, final],
                "controls_sha256": hashlib.sha256(json.dumps(controls, separators=(",", ":"),
                    allow_nan=False).encode()).hexdigest(),
                "stage_records": {"path": STAGE_INDEX, "count": 1},
            }
            write_attempt(attempt_dir, record)
            (attempt_dir / "run-manifest.json").write_text(json.dumps({
                "attempt_id": attempt_id, "source_commit": figures.SOURCE_COMMIT,
                "task_sha256": task_sha, "resource_profile_id": "worker-wall-1800-cpu-1800/1",
            }))
            (attempt_dir / "resolution-receipt.json").write_text(json.dumps({
                "task_id": plane.task_id, "task_sha256": task_sha,
                "selected_controller_id": "fixture-controller",
            }))
            (attempt_dir / "postcheck-initial.json").write_text(json.dumps({
                "original_attempt_id": attempt_id, "task_sha256": task_sha,
                "overall_status": "complete",
            }))

            collected = figures._collect_run(plane, attempt_id, capture_root)
            self.assertEqual(collected["stage_count"], 1)
            self.assertEqual(collected["plant_replay"][-1]["state"], final)
            self.assertEqual(collected["raw_record"]["stage_files"][0]["path"], "stage-000.json")

            stage_path = attempt_dir / "stage-000.json"
            stage_path.write_text(stage_path.read_text() + " ")
            with self.assertRaisesRegex(ValueError, "v2 stage evidence is invalid"):
                figures._collect_run(plane, attempt_id, capture_root)

    def test_static_fixed_plan_shapes_use_dashed_outlines(self) -> None:
        import matplotlib.pyplot as plt

        figure, axis = plt.subplots()
        plane = figures.PLANES["syn-nl-lv-01"]
        run = {
            "controller_id": "native-parallelotope-mpc/1", "clouds": [], "nodes": [],
            "plant_replay": [], "planned_prediction": [],
            "initial_point": [0, 0], "target": None,
            "fixed_plan_enclosures": [{
                "role": "fixed-plan-trajectory-enclosure", "time": 0,
                "representation": "parallelotope",
                "projected_geometry": [[0, 0], [1, 0], [1, 1], [0, 1]],
            }],
        }
        try:
            figures._plot_run(axis, run, plane, plt.get_cmap("viridis"), 1)
            self.assertEqual(axis.patches[0].get_linestyle(), "--")
        finally:
            plt.close(figure)

    def test_fuel_planes_apply_requested_indices_to_physical_state_once(self) -> None:
        state = [100.0, 30.0, 2.0, 0.6]
        self.assertEqual(figures.PLANES["syn-nl-fuel-01"].project(state), (2.0, 100.0))
        self.assertEqual(figures.FUEL_FUEL_PLANE.project(state), (0.6, 30.0))
        self.assertEqual(figures.PLANES["syn-nl-fuel-01"].raw_indices, (2, 0))
        self.assertEqual(figures.FUEL_FUEL_PLANE.raw_indices, (3, 1))


    def test_recorded_outer_shapes_project_the_serialized_geometry(self) -> None:
        box = figures.project_shape(
            {"representation": "box", "lower": [0, 1, 2, 3], "upper": [4, 5, 6, 7]},
            (2, 0),
        )
        self.assertEqual(box, [[2.0, 0.0], [6.0, 0.0], [6.0, 4.0], [2.0, 4.0]])

        ellipsoid = figures.project_shape(
            {"representation": "ellipsoid", "center": [1, 2, 3, 4], "radii": [.1, .2, .3, .4]},
            (3, 1),
        )
        self.assertEqual(ellipsoid, [[4.0, 2.0], [.4, .2]])


    def test_witness_flags_do_not_materialize_regions(self) -> None:
        node = {
            "state": [1.0, 2.0, 3.0, 4.0],
            "predecessor_contains_parent": True,
            "stage_set_intersection_nonempty": True,
        }
        self.assertIsNone(figures.project_shape(node, (0, 1)))


    def test_zonotope_projection_uses_full_state_generator_columns(self) -> None:
        shape = {
            "representation": "zonotope",
            "center": [10.0, 20.0, 30.0, 40.0],
            "generators": [[1.0, 0.0], [0.0, 2.0], [3.0, 0.0], [0.0, 4.0]],
        }
        projected = figures.project_shape(shape, (2, 3))
        assert projected is not None
        self.assertEqual(len(projected), 5)
        self.assertEqual(min(point[0] for point in projected), 27.0)
        self.assertEqual(max(point[0] for point in projected), 33.0)
        self.assertEqual(min(point[1] for point in projected), 36.0)
        self.assertEqual(max(point[1] for point in projected), 44.0)

    def test_parallelotope_projection_matches_independently_enumerated_corners(self) -> None:
        frame = [[1.0, 2.0], [0.0, 1.0]]
        lower, upper = [-1.0, -2.0], [1.0, 2.0]
        shape = {"representation": "parallelotope", "frame": frame,
                 "lower": lower, "upper": upper}
        projected = figures.project_shape(shape, (0, 1))

        # Enumerate the defining input box independently, then apply x = frame * y.
        assert projected is not None
        corners = [
            [sum(frame[i][j] * y[j] for j in range(2)) for i in range(2)]
            for y in product(*zip(lower, upper, strict=False))
        ]
        expected_bounds = [
            (min(point[axis] for point in corners), max(point[axis] for point in corners))
            for axis in range(2)
        ]
        actual_bounds = [
            (min(point[axis] for point in projected), max(point[axis] for point in projected))
            for axis in range(2)
        ]
        self.assertEqual(actual_bounds, expected_bounds)
        self.assertEqual(actual_bounds, [(-5.0, 5.0), (-2.0, 2.0)])

    def test_four_dimensional_parallelotope_projection_matches_corner_enumeration(self) -> None:
        frame = [
            [1.0, 2.0, 0.0, 0.0],
            [0.0, 1.0, 1.0, 0.0],
            [1.0, 0.0, 1.0, 2.0],
            [0.0, 1.0, 0.0, 1.0],
        ]
        lower, upper = [-1.0, -2.0, 0.0, 1.0], [2.0, 1.0, 3.0, 5.0]
        projected = figures.project_shape(
            {"representation": "parallelotope", "frame": frame,
             "lower": lower, "upper": upper}, (3, 1)
        )
        assert projected is not None
        corners = [
            [sum(frame[i][j] * y[j] for j in range(4)) for i in range(4)]
            for y in product(*zip(lower, upper, strict=False))
        ]
        expected_bounds = [
            (min(point[axis] for point in corners), max(point[axis] for point in corners))
            for axis in (3, 1)
        ]
        actual_bounds = [
            (min(point[axis] for point in projected), max(point[axis] for point in projected))
            for axis in (0, 1)
        ]
        self.assertEqual(actual_bounds, expected_bounds)

    def test_output_stage_focus_includes_terminal_state_and_preceding_replay(self) -> None:
        dt = 0.5
        replay = [
            {"time": 0.0, "update_index": 0},
            {"time": 0.25, "update_index": 0},
            {"time": 0.5, "update_index": 0},
            {"time": 0.75, "update_index": 1},
            {"time": 1.0, "update_index": 1},
            {"time": 1.25, "update_index": 2},
            {"time": 1.5, "update_index": 2},
        ]
        self.assertEqual([r["time"] for r in figures.replay_for_output_stage(replay, 0, dt)], [0.0])
        self.assertEqual([r["time"] for r in figures.replay_for_output_stage(replay, 1, dt)],
                         [0.0, 0.25, 0.5])
        self.assertEqual([r["time"] for r in figures.replay_for_output_stage(replay, 3, dt)],
                         [1.0, 1.25, 1.5])

        stages = [{"absolute_stage": i, "time": i * dt} for i in range(4)]
        self.assertEqual(list(figures.output_stage_values(3)), [0, 1, 2, 3])
        self.assertEqual(figures.rows_for_output_stage(stages, 0), [stages[0]])
        self.assertEqual(figures.rows_for_output_stage(stages, 3), [stages[3]])
        self.assertEqual(figures.normalized_time(0.0, 1.5), 0.0)
        self.assertEqual(figures.normalized_time(1.5, 1.5), 1.0)
        self.assertEqual(figures.timeline_end([{
            "stage_count": 3,
            "clouds": [{"time": 1.0}],
            "nodes": [{"time": 1.5}],
            "planned_prediction": [{"time": 1.5}],
            "plant_replay": replay,
        }]), 1.5)


    def test_projected_overlap_does_not_establish_full_state_intersection(self) -> None:
        left = [0.0, 0.0, 0.0, 0.0]
        right = [0.0, 0.0, 0.0, 1.0]
        self.assertEqual(figures.PLANES["syn-nl-fuel-01"].project(left),
                         figures.PLANES["syn-nl-fuel-01"].project(right))
        self.assertNotEqual(left, right)
