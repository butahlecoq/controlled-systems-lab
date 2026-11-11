"""Behavior checks for the saved closed-loop figure boundary."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/reports"))

import recorded_closed_loop_figures as figures


class RecordedClosedLoopFigureTests(unittest.TestCase):
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
        self.assertIsNotNone(projected)
        self.assertEqual(len(projected), 5)
        self.assertEqual(min(point[0] for point in projected), 27.0)
        self.assertEqual(max(point[0] for point in projected), 33.0)
        self.assertEqual(min(point[1] for point in projected), 36.0)
        self.assertEqual(max(point[1] for point in projected), 44.0)


    def test_projected_overlap_does_not_establish_full_state_intersection(self) -> None:
        left = [0.0, 0.0, 0.0, 0.0]
        right = [0.0, 0.0, 0.0, 1.0]
        self.assertEqual(figures.PLANES["syn-nl-fuel-01"].project(left),
                         figures.PLANES["syn-nl-fuel-01"].project(right))
        self.assertNotEqual(left, right)
