import json
import hashlib
import unittest
from pathlib import Path

from scripts.reports import stage_projection_data as data


def fixture():
    document = {
        "schema": data.SCHEMA_ID,
        "provenance": {"run_id": "run-1", "record_schema": "csl.run/1", "source_sha256": "a" * 64},
        "problem_id": "problem-1", "request_id": "request-1", "route_id": "route-1",
        "coordinates": [{"id": "x0", "name": "x1", "unit": "m"}, {"id": "x1", "name": "x2", "unit": "s"}],
        "requested_pairs": [[0, 1]],
        "stage_axis": {"kind": "stage", "points": [0, 1, 2], "unit": None},
        "relation": "equivalent", "assurance": "numerical",
        "records": [
            {"stage": stage, "physical_time": None, "pair_index": 0, "source_assurance": "numerical",
             "source_set_ids": [f"set-{stage}"],
             "outcome": {"status": "success", "relation": "equivalent", "assurance": "numerical",
                         "provider": {"id": "geometry.test", "version": "1"}, "evidence": [{"request_id": f"projection-{stage}",
                             "ideal_output_id": f"output-{stage}", "scope": "set_relation", "input_set_ids": [f"set-{stage}"],
                             "support": {"kind": "numerical_check"}, "assumptions": []}],
                         "components": [{"component_id": f"component-{stage}", "kind": kind, "vertices": vertices}]}}
            for stage, kind, vertices in (
                (0, "point", [[0, 0], [0, 0], [0, 0]]),
                (1, "segment", [[0, 0], [1, 1], [2, 2]]),
                (2, "polygon", [[0, 0], [1, 0], [0, 1]]))
        ],
        "trajectory_series": [],
    }
    canonical = json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    document["content_sha256"] = hashlib.sha256(canonical).hexdigest()
    return document


def reseal(document):
    unsigned = {key: value for key, value in document.items() if key != "content_sha256"}
    canonical = json.dumps(unsigned, ensure_ascii=False, allow_nan=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    document["content_sha256"] = hashlib.sha256(canonical).hexdigest()


class StageProjectionBatchTests(unittest.TestCase):
    def read(self, document, expected_request_id="request-1", *, expected_problem_id="problem-1",
             expected_route_id="route-1", expected_record_schema="csl.run/1"):
        raw = document if isinstance(document, str) else json.dumps(document)
        return data.loads_stage_projection_batch(raw, expected_run_id="run-1",
            expected_problem_id=expected_problem_id, expected_request_id=expected_request_id,
            expected_route_id=expected_route_id, expected_record_schema=expected_record_schema,
            expected_source_sha256="a" * 64)

    def test_accepts_point_segment_polygon_and_keeps_trajectory_separate(self):
        loaded = self.read(fixture())
        self.assertEqual([row["outcome"]["components"][0]["kind"] for row in loaded["records"]],
                         ["point", "segment", "polygon"])
        self.assertEqual(loaded["trajectory_series"], [])

    def test_cpp_writer_fixture_is_python_reader_compatible(self):
        fixture_path = Path(__file__).parents[1] / "artifacts/fixtures/stage-projection-batch-v1.json"
        loaded = self.read(json.loads(fixture_path.read_text(encoding="utf-8")), expected_request_id="stage-batch",
                           expected_problem_id="fuel", expected_route_id="fuel-route",
                           expected_record_schema="csl.run-statistics/7")
        self.assertEqual(loaded["route_id"], "fuel-route")
        self.assertEqual(loaded["requested_pairs"], [[0, 2]])
        self.assertEqual(loaded["records"][0]["outcome"]["components"][0]["kind"], "polygon")
        self.assertEqual(len(loaded["records"][1]["outcome"]["components"][0]["vertices"]), 3)
        self.assertEqual(loaded["records"][1]["outcome"]["components"][0]["kind"], "segment")
        self.assertEqual(loaded["records"][1]["outcome"]["components"][0]["vertices"][1], [1e16, 1e16 + 2])
        self.assertEqual(len(loaded["records"][2]["outcome"]["components"][0]["vertices"]), 3)
        self.assertEqual(loaded["records"][2]["outcome"]["components"][0]["kind"], "point")
        self.assertEqual(loaded["records"][2]["outcome"]["components"][0]["rays"], [[0.0, 0.0]])
        self.assertEqual(loaded["records"][3]["outcome"]["components"][0]["kind"], "empty")
        self.assertEqual(loaded["records"][3]["outcome"]["components"][0]["rays"], [[1.0, 0.0]])
        self.assertEqual(loaded["trajectory_series"][0]["kind"], "trajectory")
        self.assertEqual(loaded["trajectory_series"][0]["coordinate_ids"], ["x0", "x2"])

    def test_rejects_reordered_pair_stage_grid_and_tampered_identity(self):
        document = fixture()
        document["records"][0], document["records"][1] = document["records"][1], document["records"][0]
        reseal(document)
        with self.assertRaisesRegex(data.ProjectionBatchError, "complete stage-major"):
            self.read(document)
        document = fixture()
        document["provenance"]["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(data.ProjectionBatchError, "identity mismatch"):
            self.read(document)
        document = fixture()
        document["provenance"]["record_schema"] = "csl.run/2"
        reseal(document)
        with self.assertRaisesRegex(data.ProjectionBatchError, "identity mismatch"):
            self.read(document)

    def test_rejects_duplicate_keys_and_duplicate_requested_pair(self):
        with self.assertRaisesRegex(data.ProjectionBatchError, "duplicate JSON key"):
            self.read('{"schema":"csl.stage-projection-batch/1","schema":"shadow"}')
        document = fixture()
        document["requested_pairs"] = [[0, 1], [0, 1]]
        reseal(document)
        with self.assertRaisesRegex(data.ProjectionBatchError, "duplicates an earlier"):
            self.read(document)

    def test_rejects_geometry_with_wrong_dimension(self):
        document = fixture()
        document["records"][0]["outcome"]["components"][0]["vertices"] = [[0, 0, 0]]
        reseal(document)
        with self.assertRaises(data.ProjectionBatchError):
            self.read(document)

    def test_rejects_degenerate_geometry_and_invalid_axes(self):
        for kind, vertices in (("segment", [[0, 0], [0, 0]]),
                               ("polygon", [[0, 0], [1, 1], [2, 2]])):
            document = fixture()
            component = document["records"][0]["outcome"]["components"][0]
            component.update(kind=kind, vertices=vertices)
            reseal(document)
            with self.assertRaises(data.ProjectionBatchError):
                self.read(document)
        document = fixture()
        document["records"][0]["outcome"]["components"] = [
            {"component_id": "unbounded", "kind": "unbounded", "vertices": [[0, 0]], "rays": [[0, 0]]}]
        reseal(document)
        with self.assertRaisesRegex(data.ProjectionBatchError, "nonzero ray"):
            self.read(document)
        document = fixture()
        component = document["records"][0]["outcome"]["components"][0]
        component["rays"] = [[0, 0]]
        reseal(document)
        self.assertEqual(self.read(document)["records"][0]["outcome"]["components"][0]["rays"], [[0, 0]])
        document = fixture()
        component = document["records"][0]["outcome"]["components"][0]
        component.update(kind="empty", vertices=[], rays=[[1, 0]])
        reseal(document)
        self.assertEqual(self.read(document)["records"][0]["outcome"]["components"][0]["kind"], "empty")
        document = fixture()
        document["stage_axis"]["points"] = []
        reseal(document)
        with self.assertRaises(data.ProjectionBatchError):
            self.read(document)
        document = fixture()
        document["stage_axis"] = {"kind": "physical_time", "points": [0, 2, 1], "unit": "s"}
        for row, time in zip(document["records"], document["stage_axis"]["points"]):
            row["physical_time"] = time
        reseal(document)
        with self.assertRaisesRegex(data.ProjectionBatchError, "strictly increasing"):
            self.read(document)

    def test_rejects_geometry_tampering_and_writer_reseals(self):
        document = fixture()
        document["records"][0]["outcome"]["components"][0]["vertices"][0][0] = 9
        with self.assertRaisesRegex(data.ProjectionBatchError, "content_sha256"):
            self.read(document)
        sealed = data.dumps_stage_projection_batch(fixture(), expected_run_id="run-1",
            expected_problem_id="problem-1", expected_request_id="request-1",
            expected_route_id="route-1", expected_record_schema="csl.run/1",
            expected_source_sha256="a" * 64)
        self.assertEqual(data.loads_stage_projection_batch(sealed, expected_run_id="run-1",
            expected_problem_id="problem-1", expected_request_id="request-1",
            expected_route_id="route-1", expected_record_schema="csl.run/1",
            expected_source_sha256="a" * 64), fixture())

    def test_round_trips_disconnected_unbounded_empty_and_unavailable_outcomes(self):
        document = fixture()
        document["records"][0]["outcome"]["components"].append(
            {"component_id": "component-disconnected", "kind": "point", "vertices": [[5, 5]]})
        document["records"][1]["outcome"]["components"] = [
            {"component_id": "unbounded", "kind": "unbounded", "vertices": [[0, 0]], "rays": [[1, 0]]}]
        document["records"][2]["outcome"] = {
            "status": "unavailable", "kind": "stopped", "explanation": "route stopped before R2",
            "stop_reason": "deadline_expired", "stop_diagnostics": "fixture deadline"}
        reseal(document)
        loaded = self.read(document)
        self.assertEqual(len(loaded["records"][0]["outcome"]["components"]), 2)
        self.assertEqual(loaded["records"][1]["outcome"]["components"][0]["kind"], "unbounded")
        self.assertEqual(loaded["records"][2]["outcome"]["kind"], "stopped")
        document["records"][0]["outcome"] = {
            "status": "success", "relation": "equivalent", "assurance": "numerical",
            "provider": {"id": "geometry.test", "version": "1"},
            "evidence": [{"request_id": "projection-0", "ideal_output_id": "output-0",
                "scope": "set_relation", "input_set_ids": ["set-0"],
                "support": {"kind": "numerical_check"}, "assumptions": []}],
            "components": [{"component_id": "empty", "kind": "empty", "vertices": [], "rays": []}],
        }
        reseal(document)
        self.assertEqual(self.read(document)["records"][0]["outcome"]["components"][0]["kind"], "empty")

    def test_preserves_each_unavailable_and_failure_outcome(self):
        for kind in ("missing", "unsupported", "stopped"):
            document = fixture()
            outcome = {"status": "unavailable", "kind": kind, "explanation": f"{kind} by fixture"}
            if kind == "stopped":
                outcome.update(stop_reason="deadline_expired", stop_diagnostics="fixture deadline")
            document["records"][0]["outcome"] = outcome
            reseal(document)
            self.assertEqual(self.read(document)["records"][0]["outcome"]["kind"], kind)
        document = fixture()
        document["records"][0]["outcome"] = {
            "status": "failure", "kind": "unsupported", "explanation": "provider rejected fixture",
            "diagnostics": [{"field": "geometry", "explanation": "unsupported representation"}],
        }
        reseal(document)
        loaded = self.read(document)
        self.assertEqual(loaded["records"][0]["outcome"]["diagnostics"][0]["field"], "geometry")

    def test_preserves_projection_when_optional_materialization_fails(self):
        document = fixture()
        outcome = document["records"][0]["outcome"]
        outcome["components"] = []
        outcome["materialization_failure"] = {
            "kind": "stopped", "explanation": "converter resource limit",
            "stop_reason": "resource_limit",
            "provider": {"id": "conversion.test", "version": "1"},
        }
        reseal(document)
        loaded = self.read(document)
        outcome = loaded["records"][0]["outcome"]
        self.assertEqual(outcome["status"], "success")
        self.assertEqual(outcome["components"], [])
        self.assertEqual(outcome["evidence"][0]["ideal_output_id"], "output-0")
        self.assertEqual(outcome["materialization_failure"]["kind"], "stopped")
        self.assertEqual(outcome["materialization_failure"]["stop_reason"], "resource_limit")

    def test_rejects_empty_success_without_materialization_failure(self):
        document = fixture()
        document["records"][0]["outcome"]["components"] = []
        reseal(document)
        with self.assertRaisesRegex(data.ProjectionBatchError, "materialization_failure"):
            self.read(document)


if __name__ == "__main__":
    unittest.main()
