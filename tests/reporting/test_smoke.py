"""Bounded actual registered-driver functional smoke; never a benchmark."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts/reports"))
import report_data as data

EXE=None


class SmokeTests(unittest.TestCase):
    def test_registered_driver_to_saved_records_and_offline_render(self):
        if not EXE:
            self.skipTest("run with --exe; ordinary discovery does not execute the smoke")
        self.assertTrue(Path(EXE).is_file(), "real report driver is missing")
        self.assertIsNotNone(importlib.util.find_spec("collect_lp"), "collector is missing")
        import collect_lp
        import render
        completed=subprocess.run([EXE,"--smoke"],capture_output=True,timeout=60)
        self.assertEqual(completed.returncode,0,completed.stderr.decode(errors="replace"))
        events=[data.parse_json(line) for line in completed.stdout.decode().splitlines()]
        self.assertEqual(events[0]["purpose"],"test")
        self.assertEqual(events[-1]["emitted_trials"],5)
        build=next(parent for parent in Path(EXE).parents if (parent/"report-build-info.json").is_file())
        configured=data.parse_json((build/"report-build-info.json").read_text(encoding="utf-8"))
        collect_lp.verify_build_identity(events[0],configured["source_commit"])
        graph=collect_lp.file_api(build)
        targets={target["name"]:target for target in graph["targets"]}
        self.assertTrue(targets["highs"]["compileGroups"])
        self.assertTrue(targets["csl_lp_report"]["link"]["commandFragments"])
        self.assertTrue(all(targets[name]["artifacts"] for name in ("highs","csl_highs_lp","csl_lp_report")))
        with self.assertRaises(ValueError): collect_lp.verify_build_identity(events[0],"f"*40)
        view=collect_lp.test_view(events,EXE,completed.returncode,completed.stdout,completed.stderr)
        self.assertFalse(data.publishable(view))
        self.assertEqual([t["result"]["outcome"] for t in view["payload"]["trials"]],
                         ["optimal","optimal","optimal","infeasible","unbounded"])
        self.assertEqual([t["result"]["original_objective"] for t in view["payload"]["trials"][:3]],[5,-1,-6])
        self.assertTrue(all(t["validation"]["passed"] for t in view["payload"]["trials"]))
        self.assertTrue(all(t["native_iterations"]["available"] for t in view["payload"]["trials"]))
        with tempfile.TemporaryDirectory() as temp:
            render.render(view,Path(temp)/"smoke")
            self.assertTrue((Path(temp)/"smoke/index.html").is_file())
        # Input errors exercise CLI admission without running any profile/calibration.
        for args in (["--profile","--rounds","1000001"],["--measure","--repetitions","1"],
                     ["--smoke","--rounds","1000"],["--unknown"]):
            invalid=subprocess.run([EXE,*args],capture_output=True,timeout=10)
            self.assertNotEqual(invalid.returncode,0)
            self.assertEqual(invalid.stdout,b"")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--exe",required=True)
    options,remaining=parser.parse_known_args()
    EXE=str(Path(options.exe).resolve())
    unittest.main(argv=[sys.argv[0],*remaining])
