#!/usr/bin/env python3
"""Capture and validate an MPC-06 feasibility result, then render saved data."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path

from check_tube import check_record
from render_tube import render

ROOT = Path(__file__).resolve().parents[3]
DRIVER = ROOT / "benchmarks/reporting/mpc06_tube/driver.cpp"
CHECKER = Path(__file__).with_name("check_tube.py")
SCENARIO = ROOT / "benchmarks/scenarios/mpc06-nilpotent-tube-v1.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def capture(executable: Path, output: Path) -> None:
    record = json.loads(subprocess.check_output([str(executable.resolve())], text=True))
    if record.get("build", {}).get("configuration") != "Release":
        raise ValueError("the published one-run timing must come from a Release build")
    record["source_commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    record["driver_sha256"] = sha256(DRIVER.read_bytes())
    record["checker_sha256"] = sha256(CHECKER.read_bytes())
    host = {
        "os": platform.platform(),
        "processor": platform.processor() or _linux_cpu_model(),
        "logical_cpus": __import__("os").cpu_count() or 0,
        "compiler_id": record["build"]["compiler_id"],
        "compiler_version": record["build"]["compiler_version"],
        "build_configuration": record["build"]["configuration"],
    }
    record["capture_environment"] = host
    check_record(record)
    output.mkdir(parents=True, exist_ok=True)
    scenario_bytes = SCENARIO.read_bytes()
    (output / "result.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    (output / "scenario.json").write_bytes(scenario_bytes)
    capture_record = {
        "schema": "csl.mpc06-tube-capture/1",
        "source_commit": record["source_commit"],
        "driver_sha256": record["driver_sha256"],
        "checker_sha256": record["checker_sha256"],
        "scenario_sha256": sha256(scenario_bytes),
        "capture_environment": host,
        "performance_measurement": record["measurement"],
    }
    (output / "capture.json").write_text(json.dumps(capture_record, indent=2) + "\n", encoding="utf-8")
    render(output / "result.json", output)
    (output / "README.md").write_text(
        "# Exact nilpotent tube-MPC feasibility pilot\n\n"
        "A two-state affine double integrator with continuous inputs and compact stagewise additive disturbance. "
        "Full-state feedback makes the error matrix nilpotent of index 2, giving an exact finite RPI tube. "
        "The solver checks exact H-relation inclusion; an independent rational checker enumerates the matched "
        "eight disturbance-vertex paths for the fixed zero nominal plan.\n\n"
        "The saved result contains exact support tightenings, initial tube membership, a feasible nominal plan, "
        "an empty-tightening edge case, and an exact unsafe-input witness. Objective values and approximation "
        "comparisons are not claimed. One Release analysis timing is included with n=1 and no warmups; the "
        "assessment is inconclusive, the limiter was not profiled, and there is no performance comparison. "
        "This is a new synthetic exact study, not a historical reproduction.\n\n"
        "Rebuild with `cmake -S . -B build/mpc06 -DCSL_BUILD_MPC06_REPORT=ON -DCMAKE_BUILD_TYPE=Release`, "
        "then `cmake --build build/mpc06 --target csl_mpc06_tube_pilot`; validate with "
        "`python3 scripts/reports/mpc06/check_tube.py build/mpc06/csl_mpc06_tube_pilot`.\n",
        encoding="utf-8")
    names = ("README.md", "capture.json", "figure-data.json", "index.html",
             "projection.svg", "result.json", "scenario.json")
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256((output / name).read_bytes())}  {name}\n" for name in names),
        encoding="ascii")


def _linux_cpu_model() -> str:
    path = Path("/proc/cpuinfo")
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(("model name", "Hardware")):
                return line.partition(":")[2].strip()
    return "unavailable"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    capture(args.executable, args.out)
