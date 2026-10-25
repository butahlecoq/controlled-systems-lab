import hashlib
import json
import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"/"reports"))
import control_figure_data as data
import adapt_fuel_record as fuel
import control_figures


class ControlFiguresTests(unittest.TestCase):
    def test_b06_saved_projection_keeps_four_dimensional_coordinate_mapping(self):
        root=ROOT/"reports/algorithm-results/b06-owner-confirmed-7df01ba3af5e4c46"
        doc=fuel.convert_b06(root);data.validate(doc)
        trajectory,flow,stock=doc["series"][:3]
        self.assertEqual(len(trajectory["states"]),6)
        self.assertEqual([row[0] for row in trajectory["controls"]],[-.3,1,0,0,.3])
        self.assertAlmostEqual(trajectory["states"][-1][1],6.38)
        self.assertEqual(trajectory["source"]["source_files_sha256"]["scenario.json"],fuel.digest(root/"scenario.json"))
        self.assertEqual(len(json.loads((root/"scenario.json").read_text())["model"]["A_row_major"]),15)
        self.assertIn("malformed (15 entries)",trajectory["evidence"])
        vertices=json.loads((root/"geometry.json").read_text())["winner_terminal_vertices"]
        self.assertEqual(flow["coordinate_ids"],["x1","x3"])
        self.assertEqual(flow["points"][0],[vertices[0][0],vertices[0][2]])
        self.assertEqual(stock["points"][0],[vertices[0][1],vertices[0][3]])
        self.assertIn("negative stock",stock["limitation"])

    def test_fixture_series_and_exported_files(self):
        doc={"schema":data.SCHEMA,"provenance":{"record_schema":"fixture/1","record_id":"fuel-witness","source_sha256":"a"*64,"scenario_id":"analytic-fuel-fixture","method_id":"fixture"},
             "coordinates":{"states":[{"id":"flow","name":"fuel flow x₃","unit":"kg/s"},{"id":"stock","name":"fuel stock x₄","unit":"kg"}],"controls":[{"id":"u","name":"burn command","unit":"1"}]},
             "axes":{"states":{"kind":"physical_time","points":[0,1,3],"label":"time (s)"},"controls":{"kind":"physical_time","points":[0,1],"interval_ends":[1,3],"label":"time (s)"}},
             "series":[{"kind":"trajectory","source":{"kind":"witness","id":"w-1","method_id":"analytic fixture","method_version":"1"},"witness_id":"w-1","evidence":"analytic feasibility check","assurance":"exact rational fixture","approximation":"selected witness","objective":0,"objective_label":"fixture objective","objective_evidence":"exact rational fixture",
                         "state_coordinate_ids":["flow","stock"],"control_coordinate_ids":["u"],
                         "states":[[3,2],[2,0],[1,-1]],"controls":[[1],[0]]},
                        {"kind":"projection","source":{"kind":"run","id":"fixture-run","method_id":"analytic fixture","method_version":"1"},"title":"projected terminal relation","coordinate_ids":["flow","stock"],"points":[[1,-1],[2,0]],"objective_context":"not applicable to a set projection",
                         "relation":"outer approximation","evidence":"analytic fixture","limitation":"two points only; not a full set"},
                        {"kind":"trajectory_pair","source":{"kind":"run","id":"fixture-run","method_id":"analytic fixture","method_version":"1"},"title":"selected witness pair","coordinate_ids":["flow","stock"],"paths":[{"run_id":"fixture-run","witness_id":"witness-0","method_id":"analytic fixture","method_version":"1","objective":0,"evidence":"exact fixture","assurance":"validated","points":[[3,2],[2,0],[1,-1]]}],"terminal_samples":[{"run_id":"fixture-run","source_ordinal":0,"point":[1,-1]}],"relation":"selected witness trajectories","evidence":"analytic fixture","limitation":"selected paths only; not a set projection"},
                        {"kind":"support_samples","source":{"kind":"geometry","id":"fixture-set","method_id":"analytic fixture","method_version":"1"},"title":"directional support samples","coordinate_ids":["flow","stock"],"points":[[2,0]],"samples":[{"direction":[1,0],"value":{"kind":"finite","value":2},"point":[2,0],"evidence_support":"numerical_check","assumptions":[]},{"direction":[-1,0],"value":{"kind":"empty"},"evidence_support":"unestablished","assumptions":[]}],
                         "objective_context":"not applicable to support samples","relation":"directional support samples","evidence":"analytic fixture","limitation":"two directions only; not a complete boundary"},
                        {"kind":"support_samples","source":{"kind":"geometry","id":"empty-fixture-set","method_id":"analytic fixture","method_version":"1"},"title":"empty and unbounded support outcomes","coordinate_ids":["flow","stock"],"points":[],"samples":[{"direction":[0,1],"value":{"kind":"empty"},"evidence_support":"unestablished","assumptions":[]},{"direction":[0,-1],"value":{"kind":"unbounded"},"evidence_support":"unestablished","assumptions":[]}],
                         "objective_context":"not applicable to support samples","relation":"directional support samples","evidence":"analytic fixture","limitation":"no finite maximizing points exist"},
                        {"kind":"timing","source":{"kind":"run","id":"fixture-run","method_id":"analytic fixture","method_version":"1"},"operation":"solve","metric":"wall","values":[10,12],"availability":"available","span_semantics":"inclusive"},
                        {"kind":"timing","source":{"kind":"run","id":"fixture-run","method_id":"analytic fixture","method_version":"1"},"operation":"worker CPU","metric":"cpu","values":[],"availability":"unavailable","span_semantics":"not_applicable"}]}
        data.validate(doc)
        reordered=json.loads(json.dumps(doc))
        reordered["series"][0]["state_coordinate_ids"].reverse()
        with self.assertRaisesRegex(ValueError,"state coordinate order"):
            data.validate(reordered)
        misaligned=json.loads(json.dumps(doc))
        misaligned["axes"]["controls"]["interval_ends"][0]=.5
        with self.assertRaisesRegex(ValueError,"align with consecutive state-axis points"):
            data.validate(misaligned)
        self.assertEqual([row[1] for row in doc["series"][0]["states"]],[2,0,-1])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);input_path=root/"input.json";input_path.write_text(json.dumps(doc))
            output=root/"out";style=ROOT/"scripts/reports/styles/control-v1.json"
            self.assertTrue(json.loads(style.read_text())["equal_aspect_for_matching_units"])
            receipt=control_figures.render(doc,hashlib.sha256(input_path.read_bytes()).hexdigest(),style,output)
            for name in ("trajectories.svg","trajectories.png","trajectory-pair-01.svg","trajectory-pair-01.png","projection-01.svg","projection-01.png","support-02.svg","support-02.png","support-03.svg","support-03.png","timing.svg","timing.png"):
                self.assertTrue((output/name).is_file(),name)
                self.assertGreater((output/name).stat().st_size,100,name)
                self.assertIn(name,receipt["files"])
            svg=(output/"trajectories.svg").read_text()
            self.assertIn("State coordinate flow",svg)
            self.assertIn("Stage-aligned control coordinate u",svg)
            self.assertIn("J=0 (exact rational fixture)",svg)
            projection_svg=(output/"projection-01.svg").read_text()
            self.assertIn("not applicable to a set projection",projection_svg)
            pair_svg=(output/"trajectory-pair-01.svg").read_text()
            self.assertIn("selected witness trajectories",pair_svg)
            support_svg=(output/"support-02.svg").read_text()
            self.assertIn("2 directions; 1 finite",support_svg)
            no_point_svg=(output/"support-03.svg").read_text()
            self.assertIn("No finite maximizing points",no_point_svg)
            self.assertIn("1 empty and 1 unbounded outcomes",no_point_svg)
            saved_receipt=json.loads((output/"export.json").read_text())
            self.assertFalse(saved_receipt["solve_query_latency_included"])

    def test_rejects_unbound_projection_and_wrong_control_interval_count(self):
        doc={"schema":data.SCHEMA,"provenance":{"record_schema":"x","record_id":"x","source_sha256":"b"*64,"scenario_id":"x","method_id":"x"},
             "coordinates":{"states":[{"id":"x","name":"x"}],"controls":[]},
             "axes":{"states":{"kind":"stage","points":[0]},"controls":{"kind":"stage","points":[],"interval_ends":[]}},
             "series":[{"kind":"projection","source":{"kind":"run","id":"x","method_id":"m","method_version":"v"},"coordinate_ids":["x","missing"],"points":[[0,0]],"relation":"sample","evidence":"sampled","limitation":"sample only","objective":0,"objective_label":"test","objective_evidence":"test"}]}
        with self.assertRaisesRegex(ValueError,"coordinate_ids"):
            data.validate(doc)

    def test_obs05_saved_tables_add_separate_wall_work_cpu_and_module_rows(self):
        doc={"schema":data.SCHEMA,"provenance":{"record_schema":"fixture/1","record_id":"run","source_sha256":"c"*64,"scenario_id":"s","method_id":"m"},
             "coordinates":{"states":[{"id":"x","name":"x"}],"controls":[]},
             "axes":{"states":{"kind":"stage","points":[0]},"controls":{"kind":"stage","points":[],"interval_ends":[]}},
             "series":[{"kind":"projection","source":{"kind":"run","id":"run","method_id":"m","method_version":"1"},
                        "coordinate_ids":["x","x"],"points":[[0,0]],"relation":"sample","evidence":"fixture","limitation":"one point",
                        "objective":0,"objective_label":"fixture objective","objective_evidence":"fixture"}]}
        temp_root=ROOT/"build/tmp"
        temp_root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as temp:
            root=Path(temp);raw=root/"comparison-record.json";raw.write_text("{}")
            manifest={"schema":"csl.obs05-export/1","comparison_run_id":"comparison-1","comparison_spec_id":"spec-1",
                      "raw_record_file":raw.name,"raw_record_sha256":hashlib.sha256(raw.read_bytes()).hexdigest()}
            (root/"manifest.json").write_text(json.dumps(manifest))
            with (root/"phase-summary.csv").open("w",newline="") as stream:
                writer=csv.DictWriter(stream,fieldnames=["strategy","metric","available_values","median","tail_statistic"]);writer.writeheader()
                writer.writerows([{"strategy":"a","metric":"strategy_run_ns","available_values":2,"median":"12","tail_statistic":"median"},
                                  {"strategy":"a","metric":"worker_work_ns","available_values":0,"median":"","tail_statistic":"not exposed"},
                                  {"strategy":"a","metric":"strategy_run_cpu_ns","available_values":0,"median":"","tail_statistic":"not exposed"}])
            with (root/"module-summary.csv").open("w",newline="") as stream:
                writer=csv.DictWriter(stream,fieldnames=["available_durations","median_ns","strategy","task","operation","module"]);writer.writeheader()
                writer.writerow({"available_durations":1,"median_ns":"7","strategy":"a","task":"geometry","operation":"project","module":"hull"})
            merged=data.add_obs05_tables(doc,root)
        timings=[item for item in merged["series"] if item["kind"]=="timing"]
        self.assertEqual(len(timings),4)
        self.assertEqual(timings[0]["values"],[12])
        self.assertEqual(timings[1]["availability"],"unavailable")
        self.assertEqual(timings[2]["availability"],"unavailable")
        self.assertEqual(timings[3]["span_semantics"],"inclusive")


if __name__=="__main__":unittest.main()
