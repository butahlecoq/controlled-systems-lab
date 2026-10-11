"""Literal saved-record oracles; every duration in this file is TEST data."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))


class RecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.find_spec("report_data")
        cls.data = __import__("report_data") if spec else None

    def setUp(self):
        self.assertIsNotNone(self.data, "saved-record validation is not implemented")

    def fixture(self):
        return self.data.load_view(ROOT / "tests/reporting/fixtures/view-v1.json")

    def test_literal_medians_and_no_unit_conversion(self):
        self.assertEqual(self.data.statistics([10, 20, 30, 40, 50]),
                         {"median": 30, "min": 10, "max": 50, "count": 5})
        self.assertEqual(self.data.statistics([10, 20, 30, 40])["median"], 25)
        with self.assertRaises(ValueError):
            self.data.statistics([])

    def test_duplicate_keys_nonfinite_and_unknown_schema_rejected(self):
        for text in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.data.parse_json(text)
        view = self.fixture()
        view["schema"] = "unknown/2"
        with self.assertRaises(ValueError):
            self.data.validate_view(view)

    def test_canonical_binary64_and_integer_hash_vocabulary(self):
        # Independent literal UTF-8 bytes: declared floats are hexadecimal tags.
        self.assertEqual(self.data.canonical_bytes({"z": -0.0, "a": [1, 1.5]}),
                         b'{"a":[1,{"$binary64":"0x1.8000000000000p+0"}],"z":{"$binary64":"-0x0.0p+0"}}')
        self.assertEqual(self.data.digest({"a": 1, "b": 2}),
                         self.data.digest({"b": 2, "a": 1}))
        self.assertNotEqual(self.data.digest(-0.0), self.data.digest(0.0))
        view = self.fixture()
        original = view["payload"]["scenarios"][0]["input"]
        integer_spelling = copy.deepcopy(original)
        integer_spelling["offset"] = 7
        self.assertEqual(self.data.input_digest(original), self.data.input_digest(integer_spelling))
        integer_spelling["offset"] = 8
        self.assertNotEqual(self.data.input_digest(original), self.data.input_digest(integer_spelling))
        integer_view=self.fixture()
        integer_view["payload"]["trials"][0]["result"]["original_objective"]=5
        self.assertEqual(self.data.seal(integer_view["payload"])["payload_sha256"],view["payload_sha256"])

    def test_hash_tamper_duplicate_round_and_invalid_intervals_rejected(self):
        for mutate in (
            lambda v: v["payload"]["scenarios"][0]["input"].update(offset=8.0),
            lambda v: v["payload"]["trials"].append(copy.deepcopy(v["payload"]["trials"][0])),
            lambda v: v["payload"]["trials"][0]["timings"]["public_run"].update(duration_ns=-1),
            lambda v: v["payload"]["trials"][0]["timings"]["public_run"].update(unit="ms"),
            lambda v: v["payload"]["trials"][0]["result"].update(outcome="unbounded"),
            lambda v: v["payload"]["trials"][0]["result"]["primal_residuals"]["context"]["subject"].update(program="wrong"),
        ):
            view = self.fixture()
            mutate(view)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                # Reseal envelope: nested structural/oracle checks must still run.
                self.data.validate_view(self.data.seal(view["payload"]))

    def test_failed_trial_retained_and_success_subset_not_summarized(self):
        view = self.fixture()
        trial = view["payload"]["trials"][0]
        trial["validation"] = {"passed": False, "errors": ["literal mismatch"]}
        view = self.data.seal(view["payload"])
        self.data.validate_view(view)
        group = self.data.aggregate(view)[0]
        self.assertEqual(group["failed"], 1)
        self.assertEqual(group["attempts"], 5)
        self.assertIsNone(group["phases"]["public_run"])
        self.assertFalse(group["valid"])

    def test_test_records_never_publishable_and_nested_phases_not_summed(self):
        view = self.fixture()
        self.assertFalse(self.data.publishable(view))
        group = self.data.aggregate(view)[0]
        self.assertEqual(group["phases"]["public_run"]["median"], 30)
        self.assertEqual(group["phases"]["end_to_end"]["median"], 100)
        self.assertEqual(group["expected"], 5)
        self.assertEqual(group["matched"], 5)

    def test_diagnostics_parser_accepts_only_versioned_prefix(self):
        raw = "adapter.version=1.0.0+highs.1.11.0\nnative.version=1.11.0\nnative.info=available\nnative.simplex_iterations=3\nnative.log:\nnative.simplex_iterations=999"
        self.assertEqual(self.data.native_iterations(raw)["value"], 3)
        for bad in (raw.replace("1.0.0", "2.0.0"), raw.replace("=3", "=3\nnative.simplex_iterations=4")):
            with self.assertRaises(ValueError):
                self.data.native_iterations(bad)
        self.assertFalse(self.data.native_iterations("adapter.version=1.0.0+highs.1.11.0\nnative.version=1.11.0\nnative.info=unavailable")["available"])

    def test_round_order_overlap_and_missing_provenance_fail_even_when_resealed(self):
        for mutate in (
            lambda v:v["payload"]["trials"][0].update(round=999),
            lambda v:v["payload"]["trials"].reverse(),
            lambda v:v["payload"]["trials"][0]["timings"]["workspace_creation"].update(start_tick="0",end_tick="3"),
            lambda v:v["payload"]["environment"].pop("absolute_tolerance"),
        ):
            view=self.fixture();mutate(view)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):
                self.data.validate_view(self.data.seal(view["payload"]))

    def test_collector_retains_aborted_prefix_without_inventing_success(self):
        import collect_lp
        view=self.fixture();p=view["payload"]
        header={"schema":self.data.EVENT_SCHEMA,"event":"header","purpose":"test","repetitions":5,
                "warmups":0,"clock":p["environment"]["clock"],"scenarios":p["scenarios"]}
        events=[header,{"schema":self.data.EVENT_SCHEMA,"event":"trial","trial":p["trials"][0]}]
        payload=collect_lp.event_payload(events,9,b"partial",b"crashed",p["provenance"],p["environment"],p["profile"],True)
        aborted=self.data.validate_view(self.data.seal(payload))
        group=self.data.aggregate(aborted)[0]
        self.assertEqual(group["attempts"],1)
        self.assertEqual(group["missing"],4)
        self.assertFalse(group["valid"])
        self.assertIsNone(group["phases"]["public_run"])
        self.assertTrue(aborted["payload"]["process"]["aborted"])

    def test_profile_adapter_uses_separate_cpu_deltas_and_nonadditive_phase_totals(self):
        import collect_lp
        metric=lambda x:{"available":True,"value":x,"unit":"ns","scope":"process lifetime CPU at snapshot"}
        unavailable={"available":False,"reason":"not exposed"}
        event={"purpose":"profile","rounds":1,"trials":5,"failures":0,"phase_totals_ns":[10,20,30,100,40,250],
               "before":{"user_cpu":metric(10),"kernel_cpu":metric(3),"peak_resident":unavailable},
               "after":{"user_cpu":metric(40),"kernel_cpu":metric(8),"peak_resident":unavailable}}
        result=collect_lp.profile_assessment(event)
        self.assertEqual(result["user_cpu_delta"]["value"],30)
        self.assertEqual(result["kernel_cpu_delta"]["value"],5)
        self.assertEqual(result["dominant_measured_phase"],"public_run")
        self.assertEqual(result["end_to_end_total_ns"],250)
        self.assertIn("unresolved",result["inner_limiter"])
        self.assertFalse(result["peak_resident"]["available"])

    def test_truncated_final_event_retains_only_complete_aborted_prefix(self):
        import collect_lp
        raw=b'{"schema":"csl.lp-report-events/1","event":"header"}\n{"unfinished":"\xe2'
        self.assertEqual(collect_lp.events_from_bytes(raw,aborted=True),
                         [{"schema":"csl.lp-report-events/1","event":"header"}])
        with self.assertRaises(ValueError): collect_lp.events_from_bytes(raw)
        with self.assertRaises(ValueError): collect_lp.events_from_bytes(b'{bad}\n',aborted=True)

    def test_relabelling_test_as_measurement_does_not_invent_provenance(self):
        view=self.fixture();p=view["payload"]
        p["purpose"]="measurement"
        for trial in p["trials"]: trial["purpose"]="measurement"
        p["provenance"]["tracked_clean"]=True
        p["provenance"]["build"]["configuration"]="Release"
        self.assertFalse(self.data.publishable(self.data.seal(p)))


if __name__ == "__main__":
    unittest.main()
