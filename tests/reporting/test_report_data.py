"""Literal saved-record oracles; every duration in this file is TEST data."""
import copy
import importlib.util
import json
import hashlib
import tempfile
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
            lambda v: v["payload"]["trials"][0]["result"].update(support={"kind":"exact_farkas_verified"}),
            lambda v: v["payload"]["trials"][3]["result"].update(support={"kind":"untrusted"}),
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
        p["provenance"]["build"].update(configuration="Release",source_commit="0"*40)
        self.assertFalse(self.data.publishable(self.data.seal(p)))

    def test_functional_debug_identity_is_distinct_from_measurement_admission(self):
        import collect_lp
        header={"purpose":"test","build":{"source_commit":"a"*40,"configuration":"Debug","ndebug":False,"cxx_standard":20}}
        collect_lp.verify_build_identity(header,"a"*40,functional=True)
        with self.assertRaises(ValueError): collect_lp.verify_build_identity(header,"a"*40)
        with self.assertRaises(ValueError): collect_lp.verify_build_identity(header,"b"*40,functional=True)
        view=self.fixture();view["payload"]["provenance"]["build"].update(configuration="Debug",source_commit="0"*40)
        self.data.validate_view(self.data.seal(view["payload"]))

    def test_executable_b_cannot_borrow_same_commit_build_a_provenance(self):
        import collect_lp
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';build=root/'A';other=root/'B'
            for path in (source,build,other): path.mkdir()
            exe=build/'csl_lp_report.exe';exe.write_bytes(b'fake A; never executed')
            foreign=other/exe.name;foreign.write_bytes(b'fake B; never executed')
            paths={"source":source.as_posix(),"build":build.as_posix()};compiler={"path":"C:/compiler.exe","id":"LiteralCC","version":"1.2"}
            target={"name":"csl_lp_report","type":"EXECUTABLE","artifacts":[{"path":exe.name}],"compileGroups":[{"language":"CXX","compileCommandFragments":[{"fragment":"-base -O2 -DNDEBUG"}]}]}
            graph={"paths":paths,"configuration":"Release","cmake":{"generator":{"name":"Literal generator"}},"targets":[target,{**target,"name":"csl_report_support"}],"toolchains":{"toolchains":[{"language":"CXX","compiler":compiler}]}}
            owner=hashlib.sha256((paths['source']+'\n'+paths['build']+'\n'+compiler['path']).encode()).hexdigest()
            header={"build":{"configuration":"Release","compiler":"LiteralCC","compiler_version":"1.2","generator":"Literal generator","configured_flags":"-base","release_flags":"-O2 -DNDEBUG","build_owner_sha256":owner}}
            collect_lp.verify_artifact(header,graph,build,exe,source)
            with self.assertRaises(ValueError): collect_lp.verify_artifact(header,graph,build,foreign,source)
            for field,value in (("compiler","DifferentCC"),("compiler_version","9.0"),("release_flags","-O0"),("build_owner_sha256","f"*64),("configuration","Debug")):
                changed=copy.deepcopy(header);changed['build'][field]=value
                with self.subTest(field=field),self.assertRaises(ValueError): collect_lp.verify_artifact(changed,graph,build,exe,source)
            with self.assertRaises(ValueError): collect_lp.verify_artifact(header,graph,other,exe,source)
            with self.assertRaises(ValueError): collect_lp.verify_artifact(header,graph,build,exe,other)

    def test_success_requires_spans_actual_method_and_consistent_typed_iterations(self):
        for mutate in (
            lambda t:t.update(timings={p:{"available":False,"reason":"not observed"} for p in self.data.PHASES}),
            lambda t:t['registry'].update(actual=None),
            lambda t:t['native_iterations'].update(unit='ns'),
            lambda t:t['native_iterations'].update(value=999),
            lambda t:t['native_iterations'].update(value=False),
            lambda t:t['native_iterations'].update(scope='end_to_end'),
            lambda t:t['result'].update(raw_diagnostics=t['result']['raw_diagnostics'].replace('adapter.version=1.0.0','adapter.version=9.0.0')),
        ):
            view=self.fixture();mutate(view['payload']['trials'][0])
            with self.subTest(mutate=mutate),self.assertRaises(ValueError): self.data.validate_view(self.data.seal(view['payload']))
        view=self.fixture();trial=view['payload']['trials'][0]
        trial['timings']={p:{"available":False,"reason":"not reached after failure"} for p in self.data.PHASES}
        trial['validation']={"passed":False,"errors":["failed before phase observation"]}
        retained=self.data.validate_view(self.data.seal(view['payload']))
        self.assertFalse(self.data.aggregate(retained)[0]['valid'])

    def test_synthetic_measurement_shape_cannot_hide_spans_or_change_source(self):
        # Literal data only, no process execution or real measurement claim.
        view=self.fixture();p=view['payload'];p['purpose']='measurement'
        p['provenance']['build'].update(configuration='Release',source_commit='0'*40)
        for trial in p['trials']: trial['purpose']='measurement'
        shaped=self.data.validate_view(self.data.seal(p))
        self.assertFalse(self.data.publishable(shaped))
        self.assertEqual([g['matched'] for g in self.data.aggregate(shaped)],[5,5,5,5,5])
        for mutation in ('missing spans','changed source','wrong attempt'):
            changed=copy.deepcopy(p)
            if mutation=='missing spans':
                changed['trials'][0]['timings']={phase:{'available':False,'reason':'not observed'} for phase in self.data.PHASES}
            elif mutation=='changed source': changed['provenance']['build']['source_commit']='b'*40
            else: changed['trials'][0]['attempt']['number']=2
            with self.subTest(mutation=mutation),self.assertRaises(ValueError): self.data.validate_view(self.data.seal(changed))

    def test_unwind_inclusive_scope_is_visible_only_on_failed_trials(self):
        view=self.fixture();p=view['payload'];trial=p['trials'][0]
        trial['timings']['end_to_end']['scope']='end_to_end_including_unwind'
        with self.assertRaises(ValueError): self.data.validate_view(self.data.seal(p))
        trial['validation']={'passed':False,'errors':['controlled exceptional unwind']}
        saved=self.data.validate_view(self.data.seal(p))
        self.assertEqual(saved['payload']['trials'][0]['timings']['end_to_end']['scope'],'end_to_end_including_unwind')
        self.assertIsNone(self.data.aggregate(saved)[0]['phases']['end_to_end'])


if __name__ == "__main__":
    unittest.main()
