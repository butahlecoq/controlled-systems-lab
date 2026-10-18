#!/usr/bin/env python3
"""Collect paired OPT-12 trials after binding the executable to a clean Release build."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import collector_common as common
import report_data as data


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_value(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--repetitions", type=int, default=7)
    args = parser.parse_args()
    if args.repetitions < 5:
        parser.error("at least five alternating paired repetitions are required")
    root = Path(__file__).resolve().parents[2]
    exe = args.exe.resolve(strict=True)
    build = args.build.resolve(strict=True)
    build_log = build / "opt12-release-build.log"
    if not build_log.is_file():
        parser.error("release build log must exist inside the selected build directory")
    head = git_value(root, "rev-parse", "HEAD")
    if head != args.source_commit or git_value(root, "status", "--porcelain"):
        parser.error("measurement requires the declared exact, clean source commit")
    try:
        common.validate_build_log(build_log, build, exe, root)
        if exe.stat().st_mtime_ns > build_log.stat().st_mtime_ns:
            raise ValueError("selected Release executable is newer than its retained build log")
        graph = common.release_graph(
            build, exe, root, target_name="csl_opt12_warm_start_measure",
            required={"csl_opt12_warm_start_measure", "csl_highs_lp", "highs",
                      "csl_optimization", "csl_registry", "csl_numeric", "csl_contracts"})
        reply = build / ".cmake" / "api" / "v1" / "reply"
        index_path = sorted(reply.glob("index-*.json"))[-1]
        index = data.parse_json(index_path.read_text(encoding="utf-8"))
        codemodel_path = reply / index["reply"]["codemodel-v2"]["jsonFile"]
        codemodel = data.parse_json(codemodel_path.read_text(encoding="utf-8"))
        paths = codemodel["paths"]
        toolchains = data.parse_json((reply / index["reply"]["toolchains-v1"]["jsonFile"]).read_text(encoding="utf-8"))["toolchains"]
        compiler = next(item for item in toolchains if item.get("language") == "CXX")
        build_owner = digest((paths["source"] + "\n" + paths["build"] + "\n" + compiler["path"]).encode())
    except (ValueError, KeyError, OSError, IndexError, StopIteration) as error:
        parser.error(f"measurement executable/build graph validation failed: {type(error).__name__}: {error}")
    if args.out.exists():
        parser.error("output destination must be new")
    args.out.mkdir(parents=True)

    before = common.machine_snapshot()
    timed_out = False
    try:
        run = subprocess.run([str(exe), str(args.repetitions)], capture_output=True, timeout=120)
        raw_stdout, raw_stderr, return_code = run.stdout, run.stderr, run.returncode
    except subprocess.TimeoutExpired as error:
        timed_out = True
        raw_stdout, raw_stderr, return_code = error.stdout or b"", error.stderr or b"", None
        if isinstance(raw_stdout, str): raw_stdout = raw_stdout.encode()
        if isinstance(raw_stderr, str): raw_stderr = raw_stderr.encode()
    after = common.machine_snapshot()
    (args.out / "raw-events.jsonl").write_bytes(raw_stdout)
    (args.out / "raw-stderr.txt").write_bytes(raw_stderr)
    build_bytes = common.sanitize(build_log.read_text(encoding="utf-8", errors="replace"), build).encode("utf-8")
    (args.out / "release-build-log.txt").write_bytes(build_bytes)
    common.save_json(args.out / "build-provenance.json", graph)
    executable_hash = digest(exe.read_bytes())
    (args.out / "measurement.exe").write_bytes(exe.read_bytes())
    (args.out / "executable.sha256").write_text(f"{executable_hash}  {exe.name}\n", encoding="ascii")

    build_record = None
    trials = []
    parse_error = None
    try:
        parsed = [data.parse_json(line) for line in raw_stdout.splitlines() if line]
        if parsed and parsed[0].get("schema") == "csl.opt12-build/1":
            build_record = parsed.pop(0)
        if not build_record:
            raise ValueError("embedded build identity event is missing")
        if (build_record.get("source_commit") != head or build_record.get("configuration") != "Release"
                or build_record.get("ndebug") is not True or build_record.get("build_owner_sha256") != build_owner
                or build_record.get("compiler") != compiler.get("id")
                or build_record.get("compiler_version") != compiler.get("version")
                or build_record.get("generator") != graph["cmake"]["generator"]):
            raise ValueError("embedded source/build/compiler identity differs from the selected Release codemodel")
        trials = parsed
        if any(row.get("schema") != "csl.opt12-cost-trial/1" for row in trials):
            raise ValueError("unknown trial schema")
        expected_count = args.repetitions * 4
        if len(trials) != expected_count:
            raise ValueError(f"expected {expected_count} trial rows, got {len(trials)}")
        if any(row.get("status") != "verified" for row in trials):
            raise ValueError("a trial failed its independent numerical checks")
        for pair in range(args.repetitions):
            for scenario in ("tiny-overhead", "small-reuse"):
                members = [row for row in trials if row["pair"] == pair and row["scenario"] == scenario]
                expected_order = ["cold", "warm"] if pair % 2 == 0 else ["warm", "cold"]
                if len(members) != 2 or [row["mode"] for row in sorted(members, key=lambda row: row["order"])] != expected_order:
                    raise ValueError("paired trials are missing or the execution order did not alternate")
        if return_code or timed_out:
            raise ValueError(f"process incomplete: return_code={return_code}, timed_out={timed_out}")
    except (UnicodeDecodeError, ValueError, KeyError) as error:
        parse_error = f"{type(error).__name__}: {error}"

    fixtures = {
        "tiny-overhead": {"rows": 1, "columns": 1, "objective": [-1.0], "coefficient": [1.0], "source_rhs": 1.0, "changed_rhs": 0.5, "expected_objective": -0.5},
        "small-reuse": {"rows": 1, "columns": 40, "objective": [-1.0] * 40, "coefficient": [1.0] * 40, "source_rhs": 20.0, "changed_rhs": 19.0, "expected_objective": -19.0},
    }
    for fixture in fixtures.values():
        fixture["sha256"] = digest(json.dumps(fixture, sort_keys=True, separators=(",", ":")).encode())
    metadata = {
        "schema": "csl.opt12-cost-report/1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": head, "adapter": "csl.lp.highs", "adapter_version": "1.1.0+highs.1.11.0",
        "native_solver": "HiGHS 1.11.0", "build_configuration": "Release",
        "build_log_sha256": digest(build_bytes), "executable_sha256": executable_hash,
        "executable_path": "Release/csl_opt12_warm_start_measure.exe",
        "host": {"system": platform.platform(), "processor": platform.processor(), "logical_cpus": os.cpu_count()},
        "build_identity": build_record, "build_graph_sha256": digest(json.dumps(graph, sort_keys=True).encode()),
        "policy": {"native_threads": 1, "presolve": "off", "parallel": "off", "seed": 0,
                   "simplex_iteration_limit": None, "repetitions_per_side_per_case": args.repetitions,
                   "warmup": "one unreported source solve in a fresh workspace per warm trial",
                   "order": "alternating cold/warm within each pair",
                   "timing": "steady-clock wall around LPWorkspace.solve; native setup components separately timed"},
        "input_fixtures": fixtures,
        "process": {"return_code": return_code, "timed_out": timed_out, "stderr_sha256": digest(raw_stderr),
                    "stdout_sha256": digest(raw_stdout), "retained_trial_count": len(trials), "parse_error": parse_error},
        "system": common.public_load(before, after),
    }
    common.save_json(args.out / "records.json", {"metadata": metadata, "trials": trials})
    columns = ["scenario", "pair", "order", "mode", "status", "cache_state", "basis_accepted", "expected_objective", "objective", "wall_ns", "model_load_seconds", "basis_transfer_seconds", "solve_seconds", "simplex_iterations"]
    with (args.out / "trials.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trials)
    (args.out / "measurement-command.txt").write_text(
        f"python scripts/reports/opt12_collect.py --exe build/dev-windows/Release/csl_opt12_warm_start_measure.exe --build build/dev-windows --source-commit {head} --repetitions {args.repetitions} --out <new-output-directory>\n",
        encoding="utf-8")
    print(json.dumps({"output": str(args.out), "record_count": len(trials), "return_code": return_code,
                      "timed_out": timed_out, "parse_error": parse_error}))
    return 1 if parse_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
