"""Focused contract tests for immutable GEO-02 numerical reports."""

import copy
import csv
import hashlib
import importlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if TYPE_CHECKING:
    from scripts.reports.geo02 import collect, provenance, render
else:
    collect = importlib.import_module("collect")
    provenance = importlib.import_module("provenance")
    render = importlib.import_module("render")


SAVED = HERE.parents[2] / "reports" / "algorithm-results" / "geo02-20261013T061151Z-338ff7d1d63c"


class ContractTests(unittest.TestCase):
    def run_saved_driver(self, stdout, stderr, expected_exit):
        records = json.loads((SAVED / "records.json").read_bytes())
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            exe = scratch / "driver.exe"
            exe.write_bytes(b"simulated GEO-02 driver")
            note = scratch / "note.txt"
            note.write_text("simulated collection", encoding="utf-8")
            output = scratch / "collection"
            argv = [
                "collect.py",
                "--exe",
                str(exe),
                "--build-dir",
                str(scratch),
                "--source-commit",
                records["algorithm"]["source_commit"],
                "--harness-commit",
                records["algorithm"]["harness_commit"],
                "--concurrent-work",
                str(note),
                "--profile-evidence",
                str(note),
                "--out",
                str(output),
                "--reviewed",
            ]
            (scratch / "stdout").write_bytes(stdout)
            (scratch / "stderr").write_bytes(stderr)

            def run_driver(_command, **kwargs):
                return subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        "from pathlib import Path; import sys; "
                        "sys.stdout.buffer.write(Path('stdout').read_bytes()); "
                        "sys.stderr.buffer.write(Path('stderr').read_bytes())",
                    ],
                    **kwargs,
                )

            process = mock.Mock(wraps=subprocess)
            process.run.side_effect = run_driver
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(collect, "subprocess", process),
                mock.patch.object(provenance, "git", return_value=str(HERE.parents[2])),
                mock.patch.object(provenance, "require_clean_tracked_tree"),
                mock.patch.object(
                    provenance, "final_build_provenance", return_value=({}, "", "", "")
                ),
            ):
                self.assertEqual(collect.main(), expected_exit)
            self.assertEqual((output / "raw-driver-output.csv").read_bytes(), stdout)
            self.assertEqual((output / "process-stderr.txt").read_bytes(), stderr)
            return (
                json.loads((output / "records.json").read_bytes()),
                json.loads((output / "collection-status.json").read_bytes()),
            )

    def test_collector_preserves_the_archived_driver_rows(self):
        records = json.loads((SAVED / "records.json").read_bytes())
        replay, receipt = self.run_saved_driver(
            (SAVED / "raw-driver-output.csv")
            .read_text(encoding="utf-8")
            .replace("\n", "\r\n")
            .encode(),
            (SAVED / "process-stderr.txt")
            .read_text(encoding="utf-8")
            .replace("\n", "\r\n")
            .encode(),
            0,
        )
        self.assertEqual(receipt["state"], "complete")
        self.assertEqual(json.dumps(replay["trials"]), json.dumps(records["trials"]))
        self.assertEqual(replay["summary"], records["summary"])
        render.validate(replay)

    def test_malformed_geometry_retains_raw_output_and_failed_status(self):
        stdout = (SAVED / "raw-driver-output.csv").read_text(encoding="utf-8")
        stderr = (SAVED / "process-stderr.txt").read_text(encoding="utf-8")
        cases = (
            ("trial", "support_values", "null"),
            ("trial", "support_values", "[NaN,2]"),
            ("trial", "output_points", "[[1e999],[2]]"),
            ("warmup", "support_values", "[NaN,2]"),
            ("warmup", "output_points", "[null]"),
            ("warmup", "support_checks", "NaN"),
        )
        for stage, field, value in cases:
            with self.subTest(stage=stage, field=field, value=value):
                trial_stdout, trial_stderr = stdout, stderr
                if stage == "trial":
                    rows = list(csv.reader(io.StringIO(stdout)))
                    rows[1][rows[0].index(field)] = value
                    output = io.StringIO()
                    csv.writer(output, lineterminator="\n").writerows(rows)
                    trial_stdout = output.getvalue()
                else:
                    lines = stderr.splitlines(keepends=True)
                    index = next(
                        i for i, line in enumerate(lines) if line.startswith("geo02_warmup=")
                    )
                    row = json.loads(lines[index].removeprefix("geo02_warmup="))
                    row[field] = json.loads(value)
                    lines[index] = "geo02_warmup=" + json.dumps(row) + "\n"
                    trial_stderr = "".join(lines)
                replay, receipt = self.run_saved_driver(
                    trial_stdout.encode(), trial_stderr.encode(), 2
                )
                self.assertEqual(receipt["state"], "failed")
                error_key = "parse_error" if stage == "trial" else "warmup_parse_error"
                self.assertIn(field, receipt[error_key])
                self.assertEqual(receipt[error_key], replay["collection"][error_key])

    def test_collector_preserves_valid_rows_from_timed_out_partial_csv(self):
        root = HERE.parents[2]
        saved = root / "reports" / "algorithm-results" / "geo02-20261013T061151Z-338ff7d1d63c"
        records = json.loads((saved / "records.json").read_bytes())
        raw_rows = (saved / "raw-driver-output.csv").read_text(encoding="utf-8").splitlines()
        partial_output = "\n".join(raw_rows[:2]) + "\n"
        stderr = (saved / "process-stderr.txt").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            exe = scratch / "driver.exe"
            exe.write_bytes(b"simulated GEO-02 driver")
            note = scratch / "note.txt"
            note.write_text("simulated collection", encoding="utf-8")
            output = scratch / "collection"
            argv = [
                "collect.py",
                "--exe",
                str(exe),
                "--build-dir",
                str(scratch),
                "--source-commit",
                records["algorithm"]["source_commit"],
                "--harness-commit",
                records["algorithm"]["harness_commit"],
                "--concurrent-work",
                str(note),
                "--profile-evidence",
                str(note),
                "--out",
                str(output),
                "--reviewed",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    subprocess,
                    "run",
                    side_effect=subprocess.TimeoutExpired(
                        [str(exe)], 600, output=partial_output, stderr=stderr
                    ),
                ),
                mock.patch.object(provenance, "git", return_value=str(root)),
                mock.patch.object(provenance, "require_clean_tracked_tree"),
                mock.patch.object(
                    provenance, "final_build_provenance", return_value=({}, "", "", "")
                ),
            ):
                self.assertEqual(collect.main(), 2)
            replay = json.loads((output / "records.json").read_bytes())
            events = [
                json.loads(line)
                for line in (output / "raw-events.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(replay["collection"]["state"], "failed")
            self.assertTrue(replay["collection"]["aborted_or_timed_out"])
            self.assertEqual(replay["collection"]["actual_trials"], 1)
            self.assertEqual(replay["collection"]["parse_error"], "missing/duplicate trial rows")
            self.assertEqual(len(replay["trials"]), 1)
            self.assertEqual(events, replay["trials"])
            self.assertEqual((output / "raw-driver-output.csv").read_text(), partial_output)
            render.validate(replay)
    def test_duplicate_warmup_geometry_key_is_rejected_before_validation(self):
        stdout = (SAVED / "raw-driver-output.csv").read_bytes()
        stderr = (SAVED / "process-stderr.txt").read_bytes()
        malformed = stderr.replace(
            b'"support_values":[', b'"support_values":null,"support_values":[', 1
        )
        self.assertNotEqual(malformed, stderr)
        _, receipt = self.run_saved_driver(stdout, malformed, 2)
        self.assertEqual(receipt["state"], "failed")
        self.assertIn("duplicate JSON key: support_values", receipt["warmup_parse_error"])

    def test_out_of_segment_point_fails_the_oracle_in_trials_and_warmups(self):
        with mock.patch.object(sys, "path", [str(HERE.parent), *sys.path]):
            adapter = importlib.import_module("geo02_registered_reports")

        stdout = (SAVED / "raw-driver-output.csv").read_bytes()
        stderr = (SAVED / "process-stderr.txt").read_bytes()
        scenario = "singular_map_box_segment"
        largest = sys.float_info.max
        points = [[0, 0], [2, 4], [largest, -largest]]
        reader = csv.DictReader(io.StringIO(stdout.decode()))
        rows = list(reader)
        trial = next(row for row in rows if row["scenario"] == scenario)
        trial["output_points"] = json.dumps(points)
        trial["materialized_output_point_count"] = "3"
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=collect.FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        lines = stderr.decode().splitlines(keepends=True)
        prefix = "geo02_warmup="
        index = next(
            i for i, line in enumerate(lines) if line.startswith(prefix) and scenario in line
        )
        warmup = json.loads(lines[index].removeprefix(prefix))
        for stage in ("trial", "warmup", "warmup_count"):
            with self.subTest(stage=stage):
                if stage == "trial":
                    trial_stdout, trial_stderr = output.getvalue().encode(), stderr
                else:
                    row = warmup.copy()
                    if stage == "warmup":
                        row.update(output_points=points, materialized_output_point_count=3)
                    else:
                        row["support_checks"] = 0
                    lines[index] = prefix + json.dumps(row) + "\n"
                    trial_stdout, trial_stderr = stdout, "".join(lines).encode()
                replay, receipt = self.run_saved_driver(trial_stdout, trial_stderr, 2)
                self.assertEqual(receipt["state"], "failed")
                results = replay["trials"] if stage == "trial" else receipt["warmup_results"]
                failed = next(row for row in results if row["scenario"] == scenario)
                self.assertEqual(failed["status"], "oracle_failed")
                with self.assertRaises(ValueError):
                    adapter.adapt_payload(replay)

    def test_signed_payload_hash_and_tamper_detection(self):
        p = collect.fixture_payload("20261013T000000Z")
        self.assertEqual(p["schema"], "csl.geo02-affine-sum-report/2")
        render.validate(p)
        q = copy.deepcopy(p)
        q["trials"][0]["operation_ns"] += 1
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            render.validate(q)

    def test_summaries_recompute_from_all_trials_and_fail_closed(self):
        rows = [
            {
                "scenario": "scalar_interval_affine_image",
                "repetition": i,
                "status": "passed",
                "oracle_passed": True,
                "setup_ns": i + 1,
                "operation_ns": 10 + i,
                "oracle_ns": 2,
                "total_ns": 20 + i,
            }
            for i in range(7)
        ]
        got = collect.summarize(rows, True)["scalar_interval_affine_image"]["phases"][
            "operation_ns"
        ]
        self.assertEqual((got["median"], got["min"], got["max"], got["range"]), (13, 10, 16, 6))
        rows[0]["status"] = "oracle_failed"
        self.assertIsNone(
            collect.summarize(rows, True)["scalar_interval_affine_image"]["phases"]["operation_ns"][
                "median"
            ]
        )

    def test_independent_oracle_pins_literal_points_and_supports(self):
        self.assertTrue(render.check_oracle("scalar_interval_affine_image", [[-2.0], [0.0], [2.0]]))
        self.assertFalse(render.check_oracle("scalar_interval_affine_image", [[-2.0], [2.1]]))
        self.assertTrue(
            render.check_oracle("singular_map_box_segment", [[0, 0], [1, 2], [1, 2], [2, 4]])
        )
        self.assertFalse(
            render.check_oracle("singular_map_box_segment", [[0, 0], [1, 2], [2, 3], [2, 4]])
        )
        self.assertFalse(
            render.check_oracle(
                "singular_map_box_segment",
                [[0, 0], [2, 4], [sys.float_info.max, -sys.float_info.max]],
            )
        )
        self.assertTrue(render.check_supports("scalar_interval_affine_image", [2, 2]))
        self.assertFalse(render.check_supports("scalar_interval_affine_image", [2, 1.999]))

    def test_candidate_reduction_claim_is_bound_to_materialized_cloud(self):
        p = collect.fixture_payload("20261013T000000Z")
        render.validate(p)
        reduced = next(t for t in p["trials"] if t["scenario"] == "redundant_interval_candidates")
        self.assertEqual(
            (
                reduced["generated_candidate_count"],
                reduced["materialized_output_point_count"],
                reduced["reduction_status"],
            ),
            (5, 2, "reduced"),
        )
        forged = copy.deepcopy(p)
        forged["trials"][0]["reduction_status"] = "reduced"
        collect.finalize(forged, "forged")
        with self.assertRaisesRegex(ValueError, "candidate reduction evidence"):
            render.validate(forged)
        forged = copy.deepcopy(p)
        forged["trials"][0]["materialized_output_point_count"] += 1
        collect.finalize(forged, "forged")
        with self.assertRaisesRegex(ValueError, "candidate reduction evidence"):
            render.validate(forged)

    def test_safe_render_escapes_untrusted_driver_detail(self):
        p = collect.fixture_payload("20261013T000000Z")
        p["trials"][0]["detail"] = "<script>alert(1)</script>"
        collect.finalize(p, "20261013T000000Z")
        page = render.render_html(p)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>alert", page)
        self.assertIn("Generated candidates", page)
        self.assertIn("Reduction status", page)

    def test_resigned_fabricated_summary_and_wrong_inputs_are_rejected(self):
        p = collect.fixture_payload("test")
        p["summary"]["scalar_interval_affine_image"]["phases"]["total_ns"]["median"] = 999
        collect.finalize(p, "test")
        with self.assertRaisesRegex(ValueError, "phase summaries"):
            render.validate(p)
        p = collect.fixture_payload("test")
        p["trials"][0]["input_sha256"] = "0" * 64
        collect.finalize(p, "test")
        with self.assertRaisesRegex(ValueError, "input hash"):
            render.validate(p)

    def test_bundle_manifest_and_deterministic_offline_zip(self):
        payload = collect.fixture_payload("20261013T000000Z")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            collection = root / "collection"
            collection.mkdir()
            (collection / "records.json").write_text(json.dumps(payload), encoding="utf8")
            for name in (
                "collection-status.json",
                "raw-events.jsonl",
                "summary.csv",
                "raw-driver-output.csv",
                "build-provenance.txt",
                "measurement-command.txt",
                "environment.json",
                "scenarios.json",
                "profile-evidence.txt",
                "process-stderr.txt",
                "concurrent-work.txt",
            ):
                (collection / name).write_text("fixture\n", encoding="utf8")
            output = root / "bundle"
            subprocess.run(
                [
                    sys.executable,
                    str(HERE / "render.py"),
                    "--collection",
                    str(collection),
                    "--out",
                    str(output),
                ],
                check=True,
            )
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf8"))
            self.assertEqual(manifest["schema"], "csl.geo02-bundle/1")
            self.assertTrue(
                all(
                    hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
                    for name, digest in manifest["files"].items()
                )
            )
            archive = root / (payload["report_id"] + ".zip")
            with zipfile.ZipFile(archive) as z:
                self.assertEqual(set(z.namelist()), {x.name for x in output.iterdir()})

    def test_bundle_preserves_malformed_csv_failure_diagnostics(self):
        payload = collect.fixture_payload("malformed")
        payload["collection"].update(
            {
                "state": "failed",
                "actual_trials": 0,
                "failures": payload["collection"]["expected_trials"],
                "process_return_code": 0,
                "parse_error": "<script>alert(1)</script>",
            }
        )
        payload["trials"] = []
        payload["summary"] = collect.summarize([], complete=False)
        collect.finalize(payload, "malformed")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            collection = root / "collection"
            collection.mkdir()
            (collection / "records.json").write_text(json.dumps(payload), encoding="utf8")
            for name in render.COLLECTION_FILES - {"records.json"}:
                (collection / name).write_text("fixture\n", encoding="utf8")
            output = root / "bundle"
            subprocess.run(
                [
                    sys.executable,
                    str(HERE / "render.py"),
                    "--collection",
                    str(collection),
                    "--out",
                    str(output),
                ],
                check=True,
            )
            page = (output / "index.html").read_text(encoding="utf8")
            self.assertIn("Collection state: failed", page)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
            self.assertNotIn("<script>alert(1)</script>", page)

    def test_saved_source_accepts_malformed_warmup_diagnostics(self):
        payload = collect.fixture_payload("warmup-malformed")
        payload["collection"].update(
            {
                "state": "failed",
                "warmup_results": [],
                "warmup_failures": len(collect.SCENARIOS),
                "warmup_parse_error": "malformed warmup CSV",
            }
        )
        payload["summary"] = collect.summarize(payload["trials"], complete=False)
        collect.finalize(payload, "warmup-malformed")
        render.validate(payload)
        page = render.render_html(payload)
        self.assertIn("Collection state: failed", page)
        self.assertIn("malformed warmup CSV", page)

    def test_provenance_allows_only_pinned_report_paths_and_cmake_delta(self):
        provenance.validate_harness_paths(
            ["reports/algorithm-results/tooling/geo02/collect.py", "scripts/reports/site.py"]
        )
        with self.assertRaisesRegex(ValueError, "allowlist"):
            provenance.validate_harness_paths(["src/geometry/affine_sum.cpp"])
        source = "\n".join(
            (provenance.GEO04_OPTION, provenance.CMAKE_CONFLICT, provenance.GEO04_TARGET, "")
        )
        expected = provenance.expected_harness_cmake(source)
        provenance.validate_harness_cmake(source, expected)
        with self.assertRaisesRegex(ValueError, "CMakeLists.txt"):
            provenance.validate_harness_cmake(source, expected + "\nadd_library(unreviewed x.cpp)")

    def test_provenance_accepts_unchanged_cmake_when_target_is_in_baseline(self):
        source = "\n".join((provenance.GEO02_OPTION, provenance.GEO02_TARGET, ""))
        provenance.validate_harness_cmake(source, source)
        with self.assertRaisesRegex(ValueError, "CMakeLists.txt"):
            provenance.validate_harness_cmake(source, source + "\nadd_library(unreviewed x.cpp)")

    def test_collector_rejects_unknown_commit_before_build_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            concurrent = root / "concurrent.txt"
            profile = root / "profile.txt"
            concurrent.write_text("none\n", encoding="utf8")
            profile.write_text("none\n", encoding="utf8")
            args = [
                "collect.py",
                "--exe",
                str(root / "missing.exe"),
                "--build-dir",
                str(root / "build"),
                "--source-commit",
                "0" * 40,
                "--harness-commit",
                "0" * 40,
                "--concurrent-work",
                str(concurrent),
                "--profile-evidence",
                str(profile),
                "--out",
                str(root / "collection"),
                "--reviewed",
            ]
            with mock.patch.object(sys, "argv", args), self.assertRaises(SystemExit) as raised:
                collect.main()
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
