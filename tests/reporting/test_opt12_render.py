from __future__ import annotations

import hashlib
import csv
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "reports"))
import opt12_render


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fixture(root: Path) -> Path:
    identity = {"schema": "csl.opt12-build/1", "source_commit": "a" * 40,
                "build_owner_sha256": "b" * 64, "compiler": "MSVC", "compiler_version": "19.0",
                "generator": "Visual Studio 17 2022", "architecture": "x64", "configured_flags": "",
                "release_flags": "/O2", "configuration": "Release", "ndebug": True}
    graph = {"cmake": {"generator": "Visual Studio 17 2022"}, "targets": ["csl_opt12_warm_start_measure"]}
    trials = []
    for pair in range(5):
        for scenario in opt12_render.SCENARIOS:
            order = ["cold", "warm"] if pair % 2 == 0 else ["warm", "cold"]
            for index, mode in enumerate(order):
                trials.append({"schema": "csl.opt12-cost-trial/1", "scenario": scenario, "pair": pair,
                               "order": index, "mode": mode, "status": "verified", "wall_ns": 100 + index,
                               "model_load_seconds": 0.001, "basis_transfer_seconds": 0.0001 if mode == "warm" else 0.0,
                               "solve_seconds": 0.002, "simplex_iterations": 1 if mode == "cold" else 0, "cache_state": "hit",
                               "basis_accepted": mode == "warm", "diagnostics": ""})
    raw = ("\n".join(json.dumps(item, separators=(",", ":")) for item in [identity, *trials]) + "\n").encode()
    stderr = b""
    build_log = b"Release build completed\n"
    (root / "raw-events.jsonl").write_bytes(raw)
    (root / "raw-stderr.txt").write_bytes(stderr)
    (root / "release-build-log.txt").write_bytes(build_log)
    (root / "build-provenance.json").write_text(json.dumps(graph, sort_keys=True), encoding="utf-8")
    executable = b"measurement executable fixture"
    (root / "measurement.exe").write_bytes(executable)
    executable_hash = digest(executable)
    (root / "executable.sha256").write_text(f"{executable_hash}  csl_opt12_warm_start_measure.exe\n", encoding="ascii")
    (root / "measurement-command.txt").write_text("python collect.py\n", encoding="utf-8")
    metadata = {"schema": "csl.opt12-cost-report/1", "source_commit": "a" * 40,
                "adapter_version": "1.1.0+highs.1.11.0", "native_solver": "HiGHS 1.11.0",
                "build_configuration": "Release", "build_identity": identity,
                "build_log_sha256": digest(build_log), "executable_sha256": executable_hash,
                "build_graph_sha256": digest(json.dumps(graph, sort_keys=True).encode()),
                "policy": {"repetitions_per_side_per_case": 5},
                "process": {"return_code": 0, "timed_out": False, "parse_error": None,
                            "stdout_sha256": digest(raw), "stderr_sha256": digest(stderr),
                            "retained_trial_count": len(trials)},
                "input_fixtures": {}}
    records = root / "records.json"
    records.write_text(json.dumps({"metadata": metadata, "trials": trials}), encoding="utf-8")
    columns = ["scenario", "pair", "order", "mode", "status", "cache_state", "basis_accepted",
               "expected_objective", "objective", "wall_ns", "model_load_seconds",
               "basis_transfer_seconds", "solve_seconds", "simplex_iterations"]
    with (root / "trials.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trials)
    return records


class Opt12RenderTests(unittest.TestCase):
    def test_valid_saved_evidence_renders_html_svg_and_offline_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence"
            evidence.mkdir()
            records = fixture(evidence)
            out = root / "opt12-test"
            manifest = opt12_render.render(records, out)
            self.assertTrue((out / "index.html").is_file())
            self.assertIn("higher median aggregate native work for warm reuse", (out / "index.html").read_text(encoding="utf-8"))
            self.assertIn("comparison.svg", manifest["files"])
            with zipfile.ZipFile(root / "opt12-test.zip") as archive:
                self.assertIn("opt12-test/index.html", archive.namelist())

    def test_raw_jsonl_must_match_typed_trials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = fixture(root)
            payload = json.loads(records.read_text(encoding="utf-8"))
            payload["trials"][0]["wall_ns"] += 1
            records.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differ from retained raw JSONL"):
                opt12_render.parse_evidence(records)

    def test_corrupt_raw_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = fixture(root)
            with (root / "raw-stderr.txt").open("ab") as stream:
                stream.write(b"tampered")
            with self.assertRaisesRegex(ValueError, "stderr_sha256"):
                opt12_render.parse_evidence(records)

    def test_corrupt_build_log_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = fixture(root)
            with (root / "release-build-log.txt").open("ab") as stream:
                stream.write(b"tampered")
            with self.assertRaisesRegex(ValueError, "build_log_sha256"):
                opt12_render.parse_evidence(records)

    def test_corrupt_executable_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = fixture(root)
            with (root / "measurement.exe").open("ab") as stream:
                stream.write(b"tampered")
            with self.assertRaisesRegex(ValueError, "retained measurement executable"):
                opt12_render.parse_evidence(records)

    def test_missing_provenance_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = fixture(root)
            (root / "build-provenance.json").unlink()
            with self.assertRaises(FileNotFoundError):
                opt12_render.parse_evidence(records)


if __name__ == "__main__":
    unittest.main()
