from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))
from contracts import load_task
from native_graph_policy import _terminal_objective


def cpp_quadratic(spec: dict, point: list[float]) -> float:
    return (0.5 * sum(x * sum(a * y for a, y in zip(row, point))
                     for x, row in zip(point, spec["Q"]))
            + sum(a * x for a, x in zip(spec["linear"], point)) + spec["offset"])


class NativeSourceObjectiveParityTests(unittest.TestCase):
    def assert_source_parity(self, task: dict) -> None:
        source = task["objective"]["source_definition"]
        target = source["terminal_target"]
        scales = source["terminal_scale"]
        weights = source["terminal_weights"]
        spec = _terminal_objective(task)
        points = [target, [0.0] * len(target), [2 * x for x in target],
                  [x + 0.25 * scale for x, scale in zip(target, scales)],
                  [x + (-1 if i % 2 else 1) * scale
                   for i, (x, scale) in enumerate(zip(target, scales))]]
        for point in points:
            with self.subTest(point=point):
                expected = sum(w * ((x - t) / scale) ** 2
                               for w, x, t, scale in zip(weights, point, target, scales))
                self.assertAlmostEqual(cpp_quadratic(spec, point), expected,
                                       delta=1e-12 * max(1.0, abs(expected)))

    def test_lotka_and_fuel_match_source_at_target_and_off_target(self):
        for name in ("syn-nl-lv-01", "syn-nl-fuel-01"):
            with self.subTest(task=name):
                self.assert_source_parity(load_task(name))

    def test_nonzero_target_with_unequal_scales_and_weights(self):
        self.assert_source_parity({"model": {"case_id": "SYN-NL-LV-01"},
            "objective": {"source_definition": {"terminal_target": [2.0, -3.0],
                "terminal_scale": [4.0, 0.5], "terminal_weights": [1.0, 0.25]}}})

    def test_full_cost_ranking_retains_terminal_and_running_weight(self):
        task = {"model": {"case_id": "SYN-NL-LV-01"},
            "objective": {"source_definition": {"terminal_target": [1.0],
                "terminal_scale": [1.0], "terminal_weights": [1.0]}}}
        spec = _terminal_objective(task)
        controls = [0.0, 1 / 3, 0.4, 1.0]
        selected = min(controls, key=lambda u: cpp_quadratic(spec, [u]) + 2 * u * u)
        self.assertEqual(selected, 1 / 3)
        self.assertAlmostEqual(cpp_quadratic(spec, [selected]) + 2 * selected**2, 2 / 3)

    def test_orbit_retains_source_euclidean_norm(self):
        task = load_task("earth-orbit")
        spec = _terminal_objective(task)
        self.assertEqual(spec["kind"], "norm")
        target = task["objective"]["target"]
        point = [target["radius_km"] + 3, 0.0, 0.0,
                 target["angular_rate_rad_s"] + 4e-5]
        residual = [sum(a * x for a, x in zip(row, point)) - t
                    for row, t in zip(spec["map"], spec["target"])]
        self.assertAlmostEqual(math.sqrt(sum(w * r * r for w, r in zip(spec["weights"], residual))), 5.0)
