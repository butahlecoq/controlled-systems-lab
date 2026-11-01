from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[3]
SCENARIO = ROOT / "benchmarks/scenarios/ext02-analytic-two-state-mixed-v1.json"
BUILD_CACHE = ROOT / "build/highs/CMakeCache.txt"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def cpu_model() -> str | None:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith(("model name", "hardware")):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or None


def cache_value(cache: str, key: str) -> str | None:
    prefix = key + ":"
    for line in cache.splitlines():
        if line.startswith(prefix):
            return line.split("=", 1)[1]
    return None


def process_capture(command: list[str]) -> dict:
    process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    samples: list[int] = []

    def sample_rss() -> None:
        status = Path(f"/proc/{process.pid}/status")
        while process.poll() is None:
            try:
                for line in status.read_text().splitlines():
                    if line.startswith("VmRSS:"):
                        samples.append(int(line.split()[1]) * 1024)
                        break
            except (OSError, ValueError):
                pass
            time.sleep(0.002)

    monitor = threading.Thread(target=sample_rss, daemon=True)
    monitor.start()
    started = time.perf_counter_ns()
    stdout, stderr = process.communicate()
    wall_ns = time.perf_counter_ns() - started
    monitor.join()
    return {"return_code": process.returncode, "stdout": stdout, "stderr": stderr,
            "process_wall_ns": wall_ns, "rss_samples_bytes": samples,
            "max_sampled_process_rss_bytes": max(samples, default=None)}


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: collect.py RELEASE_EXECUTABLE OUTPUT_DIRECTORY")
    executable = Path(sys.argv[1]).resolve(strict=True)
    output = Path(sys.argv[2]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    status = git("status", "--porcelain", "--untracked-files=all")
    if status:
        raise ValueError("source tree must be clean before capture")
    source_commit = git("rev-parse", "HEAD")
    scenario = SCENARIO.read_bytes()
    if not BUILD_CACHE.is_file():
        raise ValueError("Release CMake cache absent; build the highs report preset first")
    cache = BUILD_CACHE.read_text(encoding="utf-8", errors="replace")
    compiler = cache_value(cache, "CMAKE_CXX_COMPILER")
    compiler_version = (subprocess.check_output([compiler, "--version"], text=True).splitlines()[0]
                        if compiler else None)
    cmake = cache_value(cache, "CMAKE_COMMAND")
    ninja = cache_value(cache, "CMAKE_MAKE_PROGRAM")
    cmake_version = subprocess.check_output([cmake, "--version"], text=True).splitlines()[0]
    ninja_version = subprocess.check_output([ninja, "--version"], text=True).strip()
    load_before = Path("/proc/loadavg").read_text().split()[:3] if Path("/proc/loadavg").is_file() else None
    capture = process_capture([str(executable), "--measure", "7"])
    (output / "raw.jsonl").write_bytes(capture["stdout"])
    (output / "stderr.txt").write_bytes(capture["stderr"])
    if capture["return_code"] != 0 or capture["stderr"]:
        raise ValueError("report executable failed; raw stdout and stderr were retained")
    trials = [json.loads(line) for line in capture["stdout"].splitlines()]
    if len(trials) != 8:
        raise ValueError(f"expected one warmup plus seven measured trials, observed {len(trials)}")
    expected_branches = [
        {"catalogue_index": 0, "discrete_value": -1, "objective": 0,
         "complete_family_verified": True},
        {"catalogue_index": 1, "discrete_value": 0, "objective": 0,
         "complete_family_verified": True},
        {"catalogue_index": 2, "discrete_value": 1, "objective": 0,
         "complete_family_verified": True},
    ]
    for index, trial in enumerate(trials):
        if (trial.get("schema") != "csl.ext02-portfolio-trial/1" or
            trial.get("trial") != index or trial.get("warmup") is not (index == 0) or
            trial.get("horizon") != 1 or trial.get("catalogue_size") != 3 or
            trial.get("history_count") != 3 or trial.get("status") != "complete" or
            trial.get("optimum") != 0 or trial.get("branches") != expected_branches or
            type(trial.get("elapsed_ns")) is not int or trial["elapsed_ns"] <= 0 or
            trial.get("retained_numeric_bytes") != trial.get("retained_relation_scalars") * 8):
            raise ValueError(f"analytic portfolio oracle mismatch at trial {index}")
    measured = [row for row in trials if not row["warmup"]]
    times = [row["elapsed_ns"] for row in measured]
    summary = {"trials": len(measured), "failures": 0,
               "median_elapsed_ns": statistics.median(times),
               "minimum_elapsed_ns": min(times), "maximum_elapsed_ns": max(times),
               "horizon": 1, "catalogue_size": 3,
               "history_count": measured[0]["history_count"],
               "retained_relation_rows": measured[0]["retained_relation_rows"],
               "retained_relation_scalars": measured[0]["retained_relation_scalars"],
               "retained_numeric_bytes": measured[0]["retained_numeric_bytes"],
               "timed_interval": "one solve_finite_mixed_branch_portfolio API call; excludes process startup, registry/scenario construction, JSON serialization and rendering"}
    environment = {"os": platform.platform(), "python": platform.python_version(),
                   "cpu_model": cpu_model(), "logical_cpu_count": os.cpu_count(),
                   "compiler": compiler_version, "cmake": cmake_version,
                   "ninja": ninja_version,
                   "build_type": "Release", "native_threads": 1,
                   "load_average_before_capture": load_before,
                   "process_rss_scope": "sampled whole report process every 2 ms; includes process startup and all eight trials; not an allocation peak guarantee"}
    build = {"cache_sha256": digest(BUILD_CACHE.read_bytes()),
             "compiler_path": compiler,
             "cmake_path": cmake, "ninja_path": ninja,
             "highs_enabled": cache_value(cache, "CSL_ENABLE_HIGHS"),
             "qhull_enabled": cache_value(cache, "CSL_ENABLE_QHULL"),
             "report_enabled": cache_value(cache, "CSL_BUILD_EXT02_REPORT")}
    record = {"schema": "csl.ext02-portfolio-record/1", "source_commit": source_commit,
              "scenario": SCENARIO.relative_to(ROOT).as_posix(),
              "scenario_sha256": digest(scenario),
              "executable_sha256": digest(executable.read_bytes()),
              "summary": summary, "environment": environment, "build": build, "trials": trials,
              "process": {key: value for key, value in capture.items()
                          if key not in ("stdout", "stderr")}}
    (output / "measurement.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    with (output / "trials.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["trial", "warmup", "elapsed_ns",
            "history_count", "retained_relation_rows", "retained_relation_scalars",
            "retained_numeric_bytes", "status", "optimum"])
        writer.writeheader()
        for trial in trials:
            writer.writerow({key: trial[key] for key in writer.fieldnames})


if __name__ == "__main__":
    main()
