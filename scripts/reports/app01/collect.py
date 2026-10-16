"""Collect a fixed, clean Release APP-01 plan-check report from fresh paths."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import stage_app01 as report


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout.strip()


def require_clean_source(source: str) -> None:
    report.require(git("rev-parse", "HEAD") == source and not git("status", "--porcelain"),
                   "collector source changed after fixed-source check")


class Journal:
    def __init__(self, path: Path):
        self.path = path
        path.mkdir(parents=True, exist_ok=False)
        self.phases = []

    def capture(self, phase: str, command: list[str]) -> tuple[bytes, bytes]:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
        (self.path / f"{phase}.stdout").write_bytes(result.stdout)
        (self.path / f"{phase}.stderr").write_bytes(result.stderr)
        self.phases.append({"phase": phase, "return_code": result.returncode,
                            "stdout_sha256": report.sha(result.stdout),
                            "stderr_sha256": report.sha(result.stderr),
                            "output_lines": len(result.stdout.splitlines())})
        self.status("in_progress" if result.returncode == 0 else "failed")
        if result.returncode:
            raise RuntimeError(f"{phase} failed; retained evidence: {self.path}")
        return result.stdout, result.stderr

    def status(self, state: str, reason: str = "") -> None:
        (self.path / "status.json").write_bytes(report.json_bytes({
            "schema": "csl.app01-collection-journal/1", "status": state,
            "reason": reason, "phases": self.phases}))


def processor_name() -> str:
    if os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
    return platform.processor()


def compiler_info(build: Path) -> dict:
    candidates = list((build / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    report.require(len(candidates) == 1, "one configured compiler identity required")
    content = candidates[0].read_text(encoding="utf-8")
    values = {}
    for key in ("CMAKE_CXX_COMPILER_ID", "CMAKE_CXX_COMPILER_VERSION"):
        match = re.search(rf'set\({key} "([^"]+)"\)', content)
        report.require(match is not None, "C++ compiler identity absent")
        values[key] = match.group(1)
    return values


def sanitize(content: bytes, build: Path) -> bytes:
    value = content.decode("utf-8", errors="replace")
    for path, replacement in ((build, "BUILD_ROOT"), (ROOT, "SOURCE_ROOT")):
        for spelling in (str(path), str(path).replace("\\", "/")):
            value = re.sub(re.escape(spelling), replacement, value, flags=re.IGNORECASE)
    return value.encode()


def build_graph(build: Path, source_commit: str) -> tuple[dict, Path]:
    cache = (build / "CMakeCache.txt").read_text(encoding="utf-8")
    report.require("CSL_BUILD_APP01_REPORT:BOOL=ON" in cache and
                   "BUILD_TESTING:BOOL=OFF" in cache and
                   "CSL_ENABLE_HIGHS:BOOL=OFF" in cache, "report build configuration differs")
    reply = build / ".cmake/api/v1/reply"
    indexes = list(reply.glob("index-*.json"))
    report.require(len(indexes) == 1, "one CMake File API index required")
    index = json.loads(indexes[0].read_text(encoding="utf-8"))
    model = json.loads((reply / index["reply"]["codemodel-v2"]["jsonFile"]).read_text(encoding="utf-8"))
    configs = [item for item in model["configurations"] if item["name"] == "Release"]
    report.require(len(configs) == 1, "Release codemodel configuration required")
    matches = [item for item in configs[0]["targets"] if item["name"] == "csl_app01_plan_report"]
    report.require(len(matches) == 1, "APP-01 report target required")
    target = json.loads((reply / matches[0]["jsonFile"]).read_text(encoding="utf-8"))
    groups = [group for group in target["compileGroups"] if group["language"] == "CXX"]
    report.require(len(groups) == 1 and groups[0].get("languageStandard", {}).get("standard") == "20",
                   "APP-01 C++20 compile group required")
    flags = " ".join(item["fragment"] for item in groups[0].get("compileCommandFragments", []))
    report.require(re.search(r"(?:/D|-D)NDEBUG\b", flags) is not None and
                   re.search(r"(?:-std:c\+\+20|-std=c\+\+20|/std:c\+\+20)", flags) is not None,
                   "APP-01 Release/NDEBUG/C++20 flags required")
    sources = [item["path"] for item in target.get("sources", [])]
    report.require(any(path.endswith("plan_driver.cpp") for path in sources), "APP-01 driver absent from target")
    dependencies = sorted({item["id"].split("::", 1)[0] for item in target.get("dependencies", [])
                           if item["id"].startswith("csl_")})
    report.require("csl_approximation" in dependencies, "APP-01 target misses approximation module")
    artifacts = [item["path"] for item in target.get("artifacts", [])
                 if item["path"].endswith(".exe") or not Path(item["path"]).suffix]
    report.require(len(artifacts) == 1, "one APP-01 report binary required")
    executable = (build / artifacts[0]).resolve()
    report.require(executable.is_file() and executable.is_relative_to(build), "APP-01 binary absent from fresh build")
    return ({"schema": "csl.app01-build-graph/1", "source_commit": source_commit,
             "source_tree": git("rev-parse", "HEAD^{tree}"), "configuration": "Release",
             "generator": index["cmake"]["generator"]["name"], "target": "csl_app01_plan_report",
             "dependencies": dependencies, "sources": [sanitize(path.encode(), build).decode() for path in sources],
             "flags": sanitize(flags.encode(), build).decode(), "release_cxx20_ndebug": True,
             "binary_artifact": artifacts[0], "binary_sha256": report.sha(executable.read_bytes())}, executable)


def profile_run(executable: Path, batch: int, source: str, journal: Journal) -> tuple[dict, bytes]:
    import psutil
    command = [str(executable), str(batch), "1", "1"]
    start = time.perf_counter_ns()
    with (journal.path / "profile.stdout").open("wb") as output, (journal.path / "profile.stderr").open("wb") as errors:
        with subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=errors) as process:
            observer = psutil.Process(process.pid)
            samples = []
            while process.poll() is None:
                try:
                    cpu = observer.cpu_times()
                    memory = observer.memory_info()
                    samples.append({"elapsed_ns": time.perf_counter_ns() - start,
                                    "process_cpu_seconds": cpu.user + cpu.system,
                                    "resident_bytes": memory.rss})
                except psutil.NoSuchProcess:
                    break
                time.sleep(.01)
            process.wait()
    raw = (journal.path / "profile.stdout").read_bytes()
    stderr = (journal.path / "profile.stderr").read_bytes()
    report.require(process.returncode == 0 and not stderr, "separate APP-01 profile failed")
    report.raw_projection(raw, batch, 1, 1)
    return ({"schema": "csl.app01-profile/1", "purpose": "separate non-report limiter observation",
             "source_commit": source, "batch": batch, "wall_ns": time.perf_counter_ns() - start,
             "samples": samples, "raw_sha256": report.sha(raw),
             "limits": "10 ms process sampling; no source-level profiler attribution; excluded from report timings"}, raw)


def collect(build: Path, source: str, cmake: Path, generator: str,
            architecture: str, evidence: Path) -> Path:
    report.require(re.fullmatch(r"[0-9a-f]{40}", source) is not None,
                   "collector requires a full fixed harness commit")
    require_clean_source(source)
    report.require(cmake.is_file() and not build.exists() and not evidence.exists() and
                   build.is_relative_to(ROOT) and evidence.is_relative_to(ROOT),
                   "fresh in-worktree build and evidence destinations required")
    import psutil
    journal = Journal(evidence)
    try:
        (build / ".cmake/api/v1/query").mkdir(parents=True)
        (build / ".cmake/api/v1/query/codemodel-v2").touch()
        command = [str(cmake), "-S", str(ROOT), "-B", str(build), "-G", generator,
                   "-DCSL_BUILD_APP01_REPORT=ON", "-DBUILD_TESTING=OFF",
                   "-DCSL_ENABLE_HIGHS=OFF", "-DCSL_ENABLE_QHULL=OFF"]
        if architecture:
            command += ["-A", architecture]
        configure_stdout, configure_stderr = journal.capture("configure", command)
        build_stdout, build_stderr = journal.capture("build", [str(cmake), "--build", str(build),
                                                            "--config", "Release", "--target", "csl_app01_plan_report"])
        graph, executable = build_graph(build, source)
        require_clean_source(source)
        pilot_batch = 1000
        pilot_raw, pilot_stderr = journal.capture("pilot", [str(executable), str(pilot_batch), "1", "1"])
        report.require(not pilot_stderr, "APP-01 pilot emitted stderr")
        pilot_trials = report.raw_projection(pilot_raw, pilot_batch, 1, 1)
        fastest = min(row["elapsed_ns"] / pilot_batch for row in pilot_trials)
        batch = min(1000000, max(1000, math.ceil(125000000 / fastest / 1000) * 1000))
        pilot = {"schema": "csl.app01-pilot/1", "pilot_batch": pilot_batch,
                 "selected_batch": batch, "raw_sha256": report.sha(pilot_raw),
                 "observations": [{"fixture": row["fixture"], "elapsed_ns": row["elapsed_ns"]}
                                  for row in pilot_trials]}
        profile, profile_raw = profile_run(executable, max(batch, 100000), source, journal)
        cpu_before = psutil.cpu_percent(interval=1.0)
        raw, stderr = journal.capture("measurement", [str(executable), str(batch), "7", "7"])
        cpu_after = psutil.cpu_percent(interval=1.0)
        report.require(not stderr, "APP-01 measurement emitted stderr")
        require_clean_source(source)
        trials = report.raw_projection(raw, batch, 7, 7)
        summary = report.summarize(trials, batch)
        report.require(all(row["min_elapsed_ns"] >= 50000000 for row in summary),
                       "APP-01 measured batch under 50 ms")
        source_id = f"app01-plan-{datetime.now(timezone.utc):%Y%m%d}-{source[:8]}"
        bundle = ROOT / "reports" / "algorithm-results" / source_id
        report.require(not bundle.exists(), "APP-01 source bundle already exists")
        driver = ROOT / "benchmarks/reporting/app01/plan_driver.cpp"
        driver_bytes = driver.read_bytes()
        require_clean_source(source)
        configure_log = sanitize(configure_stdout + configure_stderr, build)
        build_log = sanitize(build_stdout + build_stderr, build)
        graph_bytes = report.json_bytes(graph)
        provenance = {"schema": "csl.app01-build-provenance/1", "source_commit": source,
                      "source_tree": graph["source_tree"], "configuration": "Release",
                      "clean_source_before_build": True, "clean_source_after_build": True,
                      "driver_sha256": report.sha(driver_bytes),
                      "binary_sha256": graph["binary_sha256"],
                      "cmake_cache_sha256": report.sha((build / "CMakeCache.txt").read_bytes()),
                      "compiler": compiler_info(build),
                      "configure_command": ["cmake", "-S", "SOURCE_ROOT", "-B", "BUILD_ROOT", "-G", generator,
                                            "-DCSL_BUILD_APP01_REPORT=ON", "-DBUILD_TESTING=OFF",
                                            "-DCSL_ENABLE_HIGHS=OFF", "-DCSL_ENABLE_QHULL=OFF"] +
                                           (["-A", architecture] if architecture else []),
                      "build_command": ["cmake", "--build", "BUILD_ROOT", "--config", "Release",
                                        "--target", "csl_app01_plan_report"]}
        environment = {"os": platform.platform(), "machine": platform.machine(),
                       "processor": processor_name(), "logical_cpus": psutil.cpu_count(logical=True),
                       "physical_cpus": psutil.cpu_count(logical=False),
                       "memory_bytes": psutil.virtual_memory().total,
                       "collection_utc": datetime.now(timezone.utc).isoformat(),
                       "host_cpu_percent_before": cpu_before, "host_cpu_percent_after": cpu_after,
                       "cache_policy": "one process, seven warmup batches then seven measured batches per fixture",
                       "seed": None, "simultaneous_work": "No intentional co-located benchmark; host may run services"}
        files = {"configure-log.txt": configure_log, "build-log.txt": build_log,
                 "build-graph.json": graph_bytes, "build-provenance.json": report.json_bytes(provenance),
                 "measurement-command.txt": f"{batch} 7 7 (Release driver; cwd SOURCE_ROOT)\n".encode(),
                 "pilot.json": report.json_bytes(pilot), "pilot-raw.jsonl": pilot_raw,
                 "profile.json": report.json_bytes(profile), "profile-raw.jsonl": profile_raw,
                 "process-stderr.txt": stderr, "raw-events.jsonl": raw,
                 "trials.csv": report.csv_bytes(report.CSV_FIELDS, trials),
                 "summary.csv": report.csv_bytes(report.SUMMARY, summary),
                 "latency.svg": report.svg(summary).encode(),
                 "plan_driver.cpp": driver_bytes, "plan-driver.bin": executable.read_bytes()}
        fixture = {"initial": 2, "transition": "x[1] = u[0]", "control": 3,
                   "reference_interval": [2, 4], "objective": "x[1]", "expected_value": 3,
                   "stage": 1, "state_coordinates": [0]}
        inputs = report.fixture_inputs()
        payload = {"schema": "csl.app01-plan-report/1", "source_commit": source,
                   "module": {"id": "csl.geometry.approximation.check_inner_state_plan", "version": "1"},
                   "provider": {"id": "app01.literal-provider", "version": "1"},
                   "verifier": {"id": "csl.trajectory.original", "version": "1"},
                   "fixture": fixture, "fixture_sha256": report.digest(fixture),
                   "inputs": inputs, "input_sha256": {name: report.digest(value) for name, value in inputs.items()},
                   "numerical": {"absolute": 1e-8, "relative": 1e-8},
                   "workers": {"requested": 1, "actual": 1, "native_threads": 1},
                   "environment": environment, "batch": batch, "warmups": 7, "repetitions": 7,
                   "timing_scope": "registered public plan check, per-call literal checks, report assignment and consumption; prebuilt problem and fixtures",
                   "unavailable_timings": ["problem resolution", "setup", "rendering", "end-to-end", "internal phases"],
                   "trials": trials, "summary": summary,
                   "status_profiles": {name: report.expected_profile(name) for name in report.FIXTURES},
                   "residual_profiles": {name: report.expected_residuals(name) for name in report.FIXTURES},
                   "raw_sha256": report.sha(raw), "build_sha256": report.sha(files["build-provenance.json"]),
                   "build_graph_sha256": report.sha(graph_bytes),
                   "configure_log_sha256": report.sha(configure_log), "build_log_sha256": report.sha(build_log),
                   "command_sha256": report.sha(files["measurement-command.txt"]),
                   "pilot_sha256": report.sha(files["pilot.json"]),
                   "profile_sha256": report.sha(files["profile.json"]), "stderr_sha256": report.sha(stderr)}
        record = {"schema": payload["schema"], "report_id": source_id,
                  "payload_sha256": report.digest(payload), "payload": payload}
        files["records.json"] = report.json_bytes(record)
        files["index.html"] = report.page(record, files["latency.svg"].decode()).encode()
        files["README.md"] = (f"# APP-01 registered inner state-plan check\n\n"
                              f"Clean fixed Release harness source: `{source}`. The original scalar model has "
                              "initial state 2, transition x[1] = u[0], singleton control 3, terminal objective "
                              "x[1], and analytic value 3. The valid witness returns numerical achievable value "
                              "3 only after original-problem verification. The altered witness with control 5 "
                              "and state 3 fails original feasibility. A zero-vertex V inner set fails membership. "
                              "Both retain no value. Supplied binary64 membership is not a "
                              "validated real-model inclusion proof. No optimal-family or completeness claim.\n\n"
                              "`records.json` and `raw-events.jsonl` retain seven accepted Release observations "
                              "per fixture. `pilot.json` and `profile.json` are separate unreported observations. "
                              "The limiter is not established. Build graph/logs use SOURCE_ROOT and BUILD_ROOT "
                              "placeholders. Regenerate from saved records with `stage_app01.py --source`; "
                              "staging requires a typed catalogue.\n").encode()
        report.require(set(files) == report.FILES, "APP-01 collector inventory differs")
        bundle.mkdir(exist_ok=False)
        for name, content in files.items():
            (bundle / name).write_bytes(content)
        (bundle / "manifest.json").write_bytes(report.json_bytes({
            "schema": "csl.app01-source-manifest/1", "report_id": source_id,
            "files": {name: report.sha(content) for name, content in sorted(files.items())}}))
        (bundle / "bundle.zip").write_bytes(report.registered.publication_zip(source_id,
            {**files, "manifest.json": (bundle / "manifest.json").read_bytes()}))
        report.validate(bundle)
        journal.status("complete")
        return bundle
    except Exception as error:
        journal.status("failed", str(error))
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--cmake", type=Path, required=True)
    parser.add_argument("--generator", required=True)
    parser.add_argument("--architecture", default="")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    print(collect(args.build.resolve(), args.source_commit, args.cmake.resolve(), args.generator,
                  args.architecture, args.evidence_dir.resolve()).relative_to(ROOT))


if __name__ == "__main__":
    main()
