"""Keep the interactive capstone tied to full-state saved native evidence."""

import copy
import importlib
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
episodes = importlib.import_module("native_fixed_tail_episode_report")
geometry = importlib.import_module("native_fixed_tail_geometry")


class SavedGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets, _, _ = episodes.build()
        cls.data = geometry.collect(cls.assets)

    def test_all_five_matched_families_keep_every_stage_and_original_horizon(self):
        for task in self.data.values():
            self.assertEqual(len(task["runs"]), 5)
            for run in task["runs"]:
                self.assertEqual(
                    [r["stage"] for r in run["stages"]], list(range(task["horizon"] + 1))
                )
                self.assertEqual(len(run["candidate"]), task["horizon"] + 1)
                self.assertEqual(len(run["execution"]), task["horizon"] + 1)
                self.assertTrue(run["containment_verified"])
            self.assertEqual(len({r["task_sha256"] for r in task["runs"]}), 1)
            self.assertEqual(len({r["action_profile_id"] for r in task["runs"]}), 1)

    def test_fuel_is_flow_mass_without_rescaling(self):
        task = self.data["syn-nl-fuel-01"]
        self.assertEqual(task["display_permutation"], [2, 0, 3, 1])
        self.assertEqual([p["indices"] for p in task["planes"]], [[2, 0], [3, 1]])
        for run in task["runs"]:
            self.assertEqual(run["execution"][0], [100, 30, 2, 0.6])
        bad = copy.deepcopy(task)
        bad["planes"][0]["indices"] = [0, 2]
        with self.assertRaisesRegex(ValueError, "coordinate"):
            geometry.validate_task(bad)

    def test_unplotted_coordinate_cannot_escape_carrier(self):
        task = self.data["syn-nl-fuel-01"]
        run = copy.deepcopy(next(r for r in task["runs"] if r["family"] == "box"))
        # Coordinate one is absent from the oxidizer plot but remains constrained.
        run["stages"][10]["membership"]["center"][1] = 1e8
        with self.assertRaisesRegex(ValueError, "carrier"):
            geometry.validate_run(run, task)

    def test_stage_and_projected_coordinate_tampering_is_rejected(self):
        task = self.data["syn-nl-lv-01"]
        for change in ("stage", "projection"):
            with self.subTest(change=change):
                run = copy.deepcopy(task["runs"][0])
                if change == "stage":
                    run["stages"][1]["stage"] = 2
                else:
                    run["stages"][1]["projections"][0]["B"][0][0] += 1e6
                with self.assertRaises(ValueError):
                    geometry.validate_run(run, task)

    def test_factor_projection_axes_match_independent_full_state_support(self):
        for task in self.data.values():
            for run in task["runs"]:
                if run["family"] == "polytope":
                    continue
                for stage in run["stages"]:
                    member = stage["membership"]
                    for p, plane in zip(stage["projections"], task["planes"], strict=True):
                        for axis, index in enumerate(plane["indices"]):
                            row = member["factor"][index]
                            radius = (
                                sum(abs(v) for v in row)
                                if member["factor_domain_norm"] == "linf"
                                else math.sqrt(sum(v * v for v in row))
                            )
                            # Saved ellipsoid boundaries use 128 straight segments.
                            tolerance = max(1e-8, radius * 0.001)
                            values = [point[axis] for point in p["B"]]
                            center = member["center"][index]
                            self.assertAlmostEqual(min(values), center - radius, delta=tolerance)
                            self.assertAlmostEqual(max(values), center + radius, delta=tolerance)

    def test_cost_action_identity_and_raw_archive_changes_are_rejected(self):
        bad = copy.deepcopy(self.data["earth-orbit"])
        bad["runs"][0]["action_profile_id"] = "different-domain"
        with self.assertRaisesRegex(ValueError, "unmatched"):
            geometry.validate_task(bad)
        assets = dict(self.assets)
        key = episodes.ROUTE + "/records/earth-orbit-box/raw.zip"
        assets[key] = assets[key] + b"changed"
        with self.assertRaisesRegex(ValueError, "archive identity"):
            geometry.collect(assets)

    def test_terminal_polytope_projection_matches_full_state_H_oracle(self):
        projector = importlib.import_module("plot_feedback_history")
        for task in self.data.values():
            region = next(r for r in task["runs"] if r["family"] == "polytope")["stages"][-1]
            for projection, plane in zip(region["projections"], task["planes"], strict=True):
                actual = projector.project_member(
                    {"kind": "h", **region["membership"]},
                    len(task["coordinates"]),
                    *plane["indices"],
                )["points"]
                for axis in (0, 1):
                    expected = [p[axis] for p in projection["B"]]
                    replay = [p[axis] for p in actual]
                    scale = max(1, max(abs(v) for v in expected))
                    self.assertAlmostEqual(min(expected), min(replay), delta=scale * 1e-7)
                    self.assertAlmostEqual(max(expected), max(replay), delta=scale * 1e-7)

    def test_existing_published_assets_survive_new_reading_layer_unchanged(self):
        original = {name: value for name, value in self.assets.items()}
        new_assets, entry, card = geometry.build(self.assets)
        self.assertEqual(self.assets, original)
        self.assertTrue(all(name not in original for name in new_assets))
        self.assertIn(entry["page"], new_assets)
        self.assertIn(entry["page"], card)
        page = new_assets[entry["page"]].decode()
        for control in (
            "task-choice",
            "stage-choice",
            "fit-visible",
            "family-controls",
            "layer-controls",
        ):
            self.assertIn(control, page)
        self.assertIn("soft objective", page)
        for name in self.data:
            for suffix in (".json", "-plane-0.svg", "-plane-0.png"):
                self.assertIn(geometry.ROUTE + "/" + name + suffix, new_assets)


if __name__ == "__main__":
    unittest.main()
