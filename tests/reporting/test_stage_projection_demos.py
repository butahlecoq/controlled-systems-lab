import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "benchmarks/reporting/stage-projection/prepare_demos.py"
SPEC = importlib.util.spec_from_file_location("stage_projection_demos", SCRIPT)
DEMOS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(DEMOS)


class StageProjectionDemoTests(unittest.TestCase):
    def make_batch(self, stem):
        path = DEMOS.EXAMPLES / f"{stem}.json"
        source, raw = DEMOS._parse(path)
        if stem == "fuel-four-state":
            source = dict(source, route_id="demo.affine-box-reachability")
        batch = DEMOS._batch(source, raw)
        expected = {
            "expected_run_id": source["run_id"],
            "expected_problem_id": source["problem_id"],
            "expected_request_id": source["request_id"],
            "expected_route_id": source["route_id"],
            "expected_record_schema": source["record_schema"],
            "expected_source_sha256": hashlib.sha256(raw).hexdigest(),
        }
        from scripts.reports.stage_projection_data import loads_stage_projection_batch
        encoded = DEMOS.dumps_stage_projection_batch(batch, **expected)
        return loads_stage_projection_batch(encoded, **expected)

    def test_fuel_demo_contains_all_four_ordered_pairs_at_every_stage(self):
        batch = self.make_batch("fuel-four-state")
        self.assertEqual(batch["requested_pairs"], [[0, 2], [1, 3], [0, 3], [1, 2]])
        self.assertEqual(batch["stage_axis"]["points"], [0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
        self.assertEqual(len(batch["records"]), 6 * 4)
        final_stock_rows = [row for row in batch["records"]
                            if row["stage"] == 5 and row["pair_index"] == 1]
        self.assertTrue(any(point[1] < 0 for point in final_stock_rows[0]["outcome"]["components"][0]["vertices"]))
        self.assertEqual(len(batch["trajectory_series"]), 4)
        self.assertTrue(all("not optimized" in item["evidence"] for item in batch["trajectory_series"]))
        initial_stock = batch["records"][1]["outcome"]["components"][0]["vertices"]
        self.assertEqual(initial_stock, [[302.0, 207.0]])
        first_flow_points = batch["records"][4]["outcome"]["components"][0]["vertices"]
        rounded = {(round(point[0], 6), round(point[1], 6)) for point in first_flow_points}
        self.assertEqual(rounded, {(28.61, 20.687333), (30.01, 20.020667)})

    def test_every_fuel_projection_matches_independent_closed_form_oracle(self):
        batch = self.make_batch("fuel-four-state")
        initial = (29.31, 302.0, 20.354, 207.0)
        controls = (-1.0, 1.0)
        for stage in range(6):
            projected_control_count = 1 if stage == 0 else 2 ** stage
            histories = itertools.product(controls, repeat=stage)
            oracle_states = []
            for history in histories:
                control_sum = sum(history)
                weighted_sum = sum((stage - 1 - index) * value
                                   for index, value in enumerate(history[:-1]))
                oracle_states.append((
                    initial[0] + 0.7 * control_sum,
                    initial[1] - 2.0 * stage * initial[0] - 1.4 * weighted_sum,
                    initial[2] - (1.0 / 3.0) * control_sum,
                    initial[3] - 2.0 * stage * initial[2] + (2.0 / 3.0) * weighted_sum,
                ))
            self.assertEqual(len(oracle_states), projected_control_count)
            for pair_index, (first, second) in enumerate(batch["requested_pairs"]):
                record = batch["records"][stage * len(batch["requested_pairs"]) + pair_index]
                observed = record["outcome"]["components"][0]["vertices"]
                observed_points = {(round(point[0], 9), round(point[1], 9)) for point in observed}
                expected_points = {(round(state[first], 9), round(state[second], 9))
                                   for state in oracle_states}
                self.assertEqual(observed_points, expected_points, (stage, pair_index))

    def test_nonfuel_demo_uses_the_same_batch_contract(self):
        batch = self.make_batch("nonfuel-integrator")
        self.assertEqual(batch["requested_pairs"], [[0, 1]])
        self.assertEqual(batch["stage_axis"]["points"], [0.0, 1.0, 2.0, 3.0])
        self.assertEqual(len(batch["records"]), 4)
        self.assertEqual(batch["route_id"], "demo.affine-box-reachability")

    def test_route_capability_index_is_valid_json(self):
        value = json.loads((ROOT / "scripts/reports/stage_projection_route_capabilities.json").read_text())
        self.assertEqual(value["schema"], "csl.stage-projection-route-capabilities/1")
        routes = {route["route_id"]: route for route in value["routes"]}
        self.assertEqual(routes["issue6.b06-finite-action-minimax"]["capability"], "terminal_set_only")
        self.assertEqual(routes["simulation.replay"]["capability"], "trajectory_only")
        self.assertIn("explicit gaps", routes["reachability.nominal_forward"]["adapter_status"])
        self.assertEqual(set(routes), {
            "demo.affine-box-reachability",
            "issue6.b06-finite-action-minimax",
            "issue6.b09-nonlinear-replay",
            "reachability.nominal_forward",
            "reachability.fixed_plan_disturbance",
            "reachability.nominal_predecessor",
            "reachability.finite_feedback",
            "synthesis.strategy_a",
            "synthesis.strategy_b.direct_joint",
            "synthesis.terminal_minimizers",
            "synthesis.hybrid_projected_reachability",
            "simulation.replay",
        })

    def test_checked_in_bundle_uses_portable_paths_and_current_file_hashes(self):
        bundle = ROOT / "benchmarks/reporting/stage-projection/bundle-v1"
        for index in bundle.glob("*-figures/index.html"):
            html = index.read_text()
            self.assertIn("Output directory: <code class=\"path\">this bundle directory</code>", html)
            self.assertNotIn("bundle-v1-check", html)
            receipt = json.loads((index.parent / "render-manifest.json").read_text())
            self.assertEqual(receipt["output_directory"], ".")
            self.assertEqual(receipt["files"]["index.html"], hashlib.sha256(index.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
