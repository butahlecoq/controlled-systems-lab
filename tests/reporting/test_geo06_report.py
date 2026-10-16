"""Observable saved-record checks for the GEO-06 report."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import copy

MODULE = Path(__file__).resolve().parents[2] / "scripts" / "reports" / "geo06_report.py"
SPEC = importlib.util.spec_from_file_location("geo06_report", MODULE)
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


class Geo06ReportTests(unittest.TestCase):
    def rows(self):
        rows = []
        for name in report.ORDER:
            rows.append({"scenario": name, "repetition": 0, "warmup": 1, "calls": 10,
                         "duration_ns": 200, "status": "passed",
                         "observed_vertices": 10 * len(report.CASES[name]["indices"].split(":")),
                         "indices": report.CASES[name]["indices"]})
        for repetition in range(7):
            for name in (report.ORDER if repetition % 2 == 0 else report.ORDER[::-1]):
                rows.append({"scenario": name, "repetition": repetition, "warmup": 0,
                             "calls": 10, "duration_ns": 100 + repetition * 10,
                             "status": "passed", "observed_vertices": 10 * len(report.CASES[name]["indices"].split(":")),
                             "indices": report.CASES[name]["indices"]})
        return rows

    def test_full_matrix_has_literal_median_and_range(self):
        rows = self.rows()
        report.validate_rows(rows, 7, 1, 10)
        self.assertEqual(report.summarize(rows)["square_duplicates"],
                         {"trials": 7, "median_batch_ns": 130, "min_batch_ns": 100, "max_batch_ns": 160})

    def test_failed_oracle_is_rejected_for_publication(self):
        rows = self.rows()
        rows[4]["indices"] = "0:2:3"
        with self.assertRaisesRegex(ValueError, "output or work count"):
            report.validate_rows(rows, 7, 1, 10)

    def test_missing_trial_is_not_summarized(self):
        with self.assertRaisesRegex(ValueError, "missing or extra"):
            report.validate_rows(self.rows()[:-1], 7, 1, 10)

    def test_failed_driver_retains_partial_raw_output_and_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "rejected"
            script = ("import sys; "
                      "print('scenario,repetition,warmup,calls,duration_ns,status,observed_vertices,indices'); "
                      "print('square_duplicates,0,1,10,100,oracle_failed,0,'); "
                      "print('literal oracle failed', file=sys.stderr); sys.exit(7)")
            with self.assertRaisesRegex(ValueError, "raw output retained"):
                report.execute_driver([sys.executable, "-c", script], out, 7, 10)
            self.assertIn("square_duplicates,0,1,10,100,oracle_failed", (out / "raw-driver-output.csv").read_text(encoding="utf-8"))
            self.assertEqual((out / "process-stderr.txt").read_text(encoding="utf-8").strip(), "literal oracle failed")
            status = json.loads((out / "collection-status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["process_exit_code"], 7)
            self.assertFalse(status["publishable"])

    def test_release_admission_rejects_optimization_override(self):
        settings = {"CMAKE_CXX_FLAGS": "/DWIN32 /D_WINDOWS /EHsc",
                    "CMAKE_CXX_FLAGS_RELEASE": "/O2 /Ob2 /DNDEBUG",
                    "CMAKE_EXE_LINKER_FLAGS": "/machine:x64",
                    "CMAKE_EXE_LINKER_FLAGS_RELEASE": "/INCREMENTAL:NO",
                    "CMAKE_STATIC_LINKER_FLAGS": "/machine:x64",
                    "CMAKE_STATIC_LINKER_FLAGS_RELEASE": ""}
        compile_settings = {"Optimization": "MaxSpeed", "InlineFunctionExpansion": "AnySuitable",
                            "LanguageStandard": "stdcpp20", "RuntimeLibrary": "MultiThreadedDLL",
                            "PreprocessorDefinitions": "%(PreprocessorDefinitions);NDEBUG;CMAKE_INTDIR=Release"}
        targets = {"driver": {"compile": compile_settings,
                              "link": {"GenerateDebugInformation": "false",
                                       "AdditionalOptions": "%(AdditionalOptions) /machine:x64",
                                       "AdditionalDependencies": "Release\\csl_quickhull_2d.lib;kernel32.lib"}},
                   "quickhull_library": {"compile": copy.deepcopy(compile_settings),
                                         "archive": {"AdditionalOptions": "%(AdditionalOptions) /machine:x64"}}}
        self.assertEqual(report.admit_release_settings(settings, targets)["cache_flags"]["CMAKE_CXX_FLAGS_RELEASE"],
                         "/O2 /Ob2 /DNDEBUG")
        settings["CMAKE_CXX_FLAGS_RELEASE"] = "/Od /DNDEBUG"
        with self.assertRaisesRegex(ValueError, "unreviewed Release flag"):
            report.admit_release_settings(settings, targets)
        settings["CMAKE_CXX_FLAGS_RELEASE"] = "/O2 /Ob2 /DNDEBUG"
        targets["quickhull_library"]["compile"]["Optimization"] = "Disabled"
        with self.assertRaisesRegex(ValueError, "quickhull_library"):
            report.admit_release_settings(settings, targets)

    def test_successful_raw_csv_survives_later_collection_error(self):
        import csv
        import io
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=report.FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(self.rows())
        expected = stream.getvalue()
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "collection"
            script = "import sys; sys.stdout.write(" + repr(expected) + ")"
            result, rows = report.execute_driver([sys.executable, "-c", script], out, 7, 10)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(len(rows), 24)
            report.mark_post_driver_failure(out, OSError("later provenance read failed"))
            self.assertEqual((out / "trials.csv").read_text(encoding="utf-8"), expected)
            status = json.loads((out / "collection-status.json").read_text(encoding="utf-8"))
            self.assertFalse(status["publishable"])
            self.assertIn("later provenance read failed", status["reason"])


if __name__ == "__main__":
    unittest.main()
