import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from test_obs04_saved_renderer import fixture_record

ROOT = Path(__file__).resolve().parents[2]
EXPORT_SPEC = importlib.util.spec_from_file_location(
    "obs05_export_tables", ROOT / "scripts/reports/obs04/export_tables.py")
export_tables = importlib.util.module_from_spec(EXPORT_SPEC)
EXPORT_SPEC.loader.exec_module(export_tables)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _seal(record):
    for attempt in record["attempts"]:
        run = json.loads(attempt["run"])
        run_text = _canonical(run)
        attempt["run"] = run_text
        attempt["run_digest"] = hashlib.sha256(run_text.encode()).hexdigest()
    identity = {"attempts": record["attempts"], "comparison_spec_id": record["comparison_spec_id"],
                "schema": "csl.comparison-record/1"}
    record["comparison_run_id"] = hashlib.sha256(_canonical(identity).encode()).hexdigest()


class Obs05ExportTests(unittest.TestCase):
    def test_exports_exact_record_and_hand_calculated_overlapping_span_tables(self):
        record = fixture_record()
        for attempt in record["attempts"]:
            run = json.loads(attempt["run"])
            run["statistics"] = {
                "clocks": [{"id": "wall", "period_numerator": "1", "period_denominator": "1000000000"}],
                "spans": [
                    {"descriptor": {"id": {"value": 0}, "clock": "wall", "task": "run",
                                    "operation": "strategy/run", "module": {"id": "csl.strategy", "version": "1"}},
                     "interval": {"kind": "ticks", "value": {"start": {"state": "available", "value": "0"},
                                                                      "end": {"state": "available", "value": "20"}}},
                     "iterations": {"state": "unavailable", "value": None, "reason": "not_instrumented", "detail": ""},
                     "execution": {"kind": "observed_return", "value": {}},
                     "status": {"kind": "returned", "value": {}}, "termination": {"state": "available", "value": "completed"}},
                    {"descriptor": {"id": {"value": 1}, "clock": "wall", "task": "nested",
                                    "operation": "strategy/family", "module": {"id": "csl.strategy", "version": "1"},
                                    "parent": {"id": {"value": 0}, "kind": "nested"}},
                     "interval": {"kind": "ticks", "value": {"start": {"state": "available", "value": "4"},
                                                                      "end": {"state": "available", "value": "9"}}},
                     "iterations": {"state": "unavailable", "value": None, "reason": "not_instrumented", "detail": ""},
                     "execution": {"kind": "observed_return", "value": {}},
                     "status": {"kind": "returned", "value": {}}, "termination": {"state": "available", "value": "completed"}},
                    {"descriptor": {"id": {"value": 1}, "clock": "wall", "task": "worker",
                                    "operation": "worker/a", "module": {"id": "csl.geometry", "version": "2"},
                                    "parent": {"id": {"value": 0}, "kind": "spawned"},
                                    "input_size": {"state": "available", "value": "3"}},
                     "interval": {"kind": "ticks", "value": {"start": {"state": "available", "value": "2"},
                                                                      "end": {"state": "available", "value": "12"}}},
                     "iterations": {"state": "available", "value": "4"},
                     "execution": {"kind": "observed_return", "value": {}},
                     "status": {"kind": "returned", "value": {}}, "termination": {"state": "available", "value": "completed"}},
                    {"descriptor": {"id": {"value": 2}, "clock": "wall", "task": "worker",
                                    "operation": "worker/a", "module": {"id": "csl.geometry", "version": "2"},
                                    "parent": {"id": {"value": 0}, "kind": "spawned"}},
                     "interval": {"kind": "ticks", "value": {"start": {"state": "available", "value": "5"},
                                                                      "end": {"state": "available", "value": "17"}}},
                     "iterations": {"state": "unavailable", "value": None, "reason": "not_instrumented", "detail": ""},
                     "execution": {"kind": "observed_return", "value": {}},
                     "status": {"kind": "returned", "value": {}}, "termination": {"state": "available", "value": "completed"}},
                ],
            }
            for span in run["statistics"]["spans"]:
                span["completion_observed"] = True
            attempt["run"] = _canonical(run)
            attempt["run_digest"] = hashlib.sha256(attempt["run"].encode()).hexdigest()
        spec = json.loads(record["spec"])
        spec["repetitions"] = 5
        record["spec"] = _canonical(spec)
        record["comparison_spec_id"] = hashlib.sha256(record["spec"].encode()).hexdigest()
        unsupported = json.loads(json.dumps(record["attempts"][-1]))
        unsupported["repetition_index"] = 4
        unsupported["run_id"] = "run-4"
        unsupported["reported_status"] = "unsupported"
        unsupported_measurement = json.loads(unsupported["measurement_payload"])
        unsupported_measurement.update(repetition=4, status="unsupported", phase_status="failed",
                                       analytic_family_checked=False, complete_family_verified=False)
        unsupported["measurement_payload"] = _canonical(unsupported_measurement)
        unsupported_run = json.loads(unsupported["run"])
        unsupported_run["run"] = "run-4"
        unsupported_run["final"] = {"kind": "unsupported", "value": {}}
        unsupported["run"] = _canonical(unsupported_run)
        unsupported["run_digest"] = hashlib.sha256(unsupported["run"].encode()).hexdigest()
        record["attempts"].append(unsupported)
        _seal(record)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, destination = root / "record.json", root / "export"
            source.write_text(_canonical(record), encoding="utf-8")
            export_tables.export_tables(source, destination)

            self.assertEqual((destination / "comparison-record.json").read_bytes(), source.read_bytes())
            manifest = json.loads((destination / "manifest.json").read_text())
            self.assertEqual(manifest["raw_record_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            with (destination / "module-spans.csv").open(newline="", encoding="utf-8") as stream:
                spans = list(csv.DictReader(stream))
            self.assertEqual(len(spans), 20)
            self.assertEqual(spans[0]["duration_ns"], "20")
            self.assertEqual(spans[1]["duration_ns"], "5")
            self.assertEqual(spans[2]["duration_ns"], "10")
            self.assertEqual(spans[2]["parent_kind"], "spawned")
            self.assertEqual(spans[2]["iterations"], "4")
            self.assertEqual(spans[2]["input_size"], "3")
            self.assertEqual(spans[2]["cpu_availability"], "unavailable")
            with (destination / "module-summary.csv").open(newline="", encoding="utf-8") as stream:
                summaries = list(csv.DictReader(stream))
            root_summary = next(row for row in summaries if row["operation"] == "strategy/run")
            self.assertEqual(root_summary["planned_spans"], "4")
            self.assertEqual(root_summary["observed_calls"], "4")
            self.assertEqual(root_summary["available_durations"], "4")
            self.assertEqual(root_summary["median_ns"], "20")
            self.assertEqual(root_summary["p95_ns"], "20")
            self.assertEqual(root_summary["available_exclusive_durations"], "4")
            self.assertEqual(root_summary["median_exclusive_wall_ns"], "5")
            self.assertEqual(root_summary["p95_exclusive_wall_ns"], "5")
            self.assertEqual(root_summary["tail_statistic"], "nearest-rank p95; spans are per attempt and are not summed")
            worker_summary = next(row for row in summaries if row["operation"] == "worker/a")
            self.assertEqual(worker_summary["planned_spans"], "8")
            self.assertEqual(worker_summary["available_durations"], "8")
            self.assertEqual(worker_summary["median_ns"], "11")
            self.assertEqual(worker_summary["p95_ns"], "12")
            self.assertEqual(worker_summary["median_exclusive_wall_ns"], "11")
            with (destination / "phase-summary.csv").open(newline="", encoding="utf-8") as stream:
                phases = list(csv.DictReader(stream))
            strategy_summary = next(row for row in phases if row["metric"] == "strategy_run_ns")
            setup_summary = next(row for row in phases if row["metric"] == "setup_ns")
            self.assertEqual(strategy_summary["available_values"], "2")
            self.assertEqual(strategy_summary["median"], "150")
            self.assertEqual(strategy_summary["p95"], "200")
            self.assertEqual(setup_summary["unavailable_values"], "4")
            self.assertIn("not_in_event_schema", setup_summary["tail_statistic"])
            with (destination / "attempts.csv").open(newline="", encoding="utf-8") as stream:
                attempts = list(csv.DictReader(stream))
            self.assertEqual(len(attempts), 5)
            self.assertEqual(attempts[3]["reported_status"], "failed")
            self.assertEqual(attempts[-1]["reported_status"], "unsupported")
            self.assertEqual(attempts[1]["strategy_run_cpu_scope"], "unavailable")
            self.assertEqual(attempts[1]["strategy_run_peak_rss_availability"], "unavailable")

    def test_export_refuses_an_existing_destination(self):
        record = fixture_record()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, destination = root / "record.json", root / "export"
            source.write_text(_canonical(record), encoding="utf-8")
            destination.mkdir()
            with self.assertRaises(FileExistsError):
                export_tables.export_tables(source, destination)

    def test_export_rejects_non_numeric_metrics_before_creating_output(self):
        record = fixture_record()
        measurement = json.loads(record["attempts"][0]["measurement_payload"])
        measurement["strategy_run_ns"] = "quick"
        record["attempts"][0]["measurement_payload"] = _canonical(measurement)
        _seal(record)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, destination = root / "record.json", root / "export"
            source.write_text(_canonical(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "strategy_run_ns"):
                export_tables.export_tables(source, destination)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
