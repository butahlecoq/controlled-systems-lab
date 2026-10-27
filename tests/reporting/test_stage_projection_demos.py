import hashlib
import importlib.util
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


if __name__ == "__main__":
    unittest.main()
