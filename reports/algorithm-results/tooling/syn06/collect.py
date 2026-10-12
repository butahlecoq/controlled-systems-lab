"""Collect one fixed-source Release SYN-06 report; never run from site staging."""
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

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import stage_syn06 as report


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=ROOT, check=True, **kwargs)


def git(*args: str) -> str:
    return run(["git", *args], capture_output=True, text=True).stdout.strip()


class CollectionFailure(RuntimeError):
    """A failed phase whose stdout/stderr were already retained in the journal."""


class Journal:
    def __init__(self, path: Path):
        self.path = path
        self.path.mkdir(parents=True, exist_ok=False)
        self.phases = []

    def capture(self, phase: str, command: list[str], *, cwd: Path = ROOT) -> tuple[bytes, bytes]:
        result = subprocess.run(command, cwd=cwd, capture_output=True, check=False)
        (self.path / f"{phase}.stdout").write_bytes(result.stdout)
        (self.path / f"{phase}.stderr").write_bytes(result.stderr)
        partial_events = len(result.stdout.splitlines())
        entry = {"phase": phase, "return_code": result.returncode,
                 "stdout_sha256": report.digest_bytes(result.stdout),
                 "stderr_sha256": report.digest_bytes(result.stderr),
                 "partial_output_lines": partial_events}
        self.phases.append(entry)
        (self.path / "status.json").write_bytes(report.json_bytes({
            "schema": "csl.syn06-collection-journal/1", "status": "failed" if result.returncode else "in_progress",
            "phases": self.phases}))
        if result.returncode:
            raise CollectionFailure(f"{phase} failed with exit code {result.returncode}; evidence: {self.path}")
        return result.stdout, result.stderr

    def finish(self) -> None:
        (self.path / "status.json").write_bytes(report.json_bytes({
            "schema": "csl.syn06-collection-journal/1", "status": "complete", "phases": self.phases}))

    def fail(self, reason: str) -> None:
        (self.path / "status.json").write_bytes(report.json_bytes({
            "schema": "csl.syn06-collection-journal/1", "status": "failed",
            "reason": reason, "phases": self.phases}))


def measured_run(executable: Path, batch: int, warmups: int, trials: int,
                 journal: Journal, phase: str) -> tuple[bytes, bytes]:
    return journal.capture(phase, [str(executable), str(batch), str(warmups), str(trials)])


def pilot(executable: Path, journal: Journal) -> tuple[dict, bytes]:
    observations = []
    raw = bytearray()
    for batch in (100, 1000, 10000):
        stdout, stderr = measured_run(executable, batch, 1, 1, journal, f"pilot-{batch}")
        if stderr:
            raise CollectionFailure("pilot emitted stderr; evidence: " + str(journal.path))
        report.raw_projection(stdout, batch, 1, 1)
        raw.extend(stdout)
        events = [json.loads(line) for line in stdout.splitlines()]
        trials = [event for event in events[1:] if not event["warmup"]]
        for event in trials:
            observations.append({"fixture": event["fixture"], "batch": batch,
                                 "elapsed_ns": event["elapsed_ns"]})
    per_call = max(event["elapsed_ns"] / event["batch"] for event in observations[-2:])
    selected = min(10_000_000, max(1000, math.ceil(125_000_000 / per_call / 1000) * 1000))
    return {"schema": "csl.syn06-pilot/1", "target_batch_ns": 125_000_000,
            "selected_batch": selected, "observations": observations,
            "raw_sha256": report.digest_bytes(raw)}, bytes(raw)


def profile_run(executable: Path, batch: int, source_commit: str, journal: Journal) -> tuple[dict, bytes]:
    import psutil
    command = [str(executable), str(batch), "1", "1"]
    start = time.perf_counter_ns()
    stdout_path = journal.path / "profile.stdout"
    stderr_path = journal.path / "profile.stderr"
    with stdout_path.open("wb") as output, stderr_path.open("wb") as errors:
        with subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=errors) as process:
            observer = psutil.Process(process.pid)
            samples = []
            while process.poll() is None:
                try:
                    cpu = observer.cpu_times()
                    memory = observer.memory_info()
                    samples.append({"elapsed_ns": time.perf_counter_ns()-start,
                                    "process_cpu_seconds": cpu.user+cpu.system,
                                    "resident_bytes": memory.rss})
                except psutil.NoSuchProcess:
                    break
                time.sleep(0.01)
            process.wait()
        output.flush()
        errors.flush()
        stdout, stderr = stdout_path.read_bytes(), stderr_path.read_bytes()
        journal.phases.append({"phase": "profile", "return_code": process.returncode,
                               "stdout_sha256": report.digest_bytes(stdout),
                               "stderr_sha256": report.digest_bytes(stderr),
                               "partial_output_lines": len(stdout.splitlines())})
        (journal.path / "status.json").write_bytes(report.json_bytes({
            "schema": "csl.syn06-collection-journal/1",
            "status": "failed" if process.returncode or stderr else "in_progress",
            "phases": journal.phases}))
        if process.returncode != 0 or stderr:
            raise CollectionFailure("separate profile process failed; evidence: " + str(journal.path))
    report.raw_projection(stdout, batch, 1, 1)
    wall = time.perf_counter_ns()-start
    return {"schema": "csl.syn06-limiter-profile/1", "purpose": "non-report limiter observation",
            "source_commit": source_commit, "command": command[1:], "wall_ns": wall,
            "samples": samples, "max_observed_cpu_seconds": max((x["process_cpu_seconds"] for x in samples), default=0),
            "max_observed_resident_bytes": max((x["resident_bytes"] for x in samples), default=0),
            "raw_sha256": report.digest_bytes(stdout),
            "limits": "10 ms sampling; no source-level profiler attribution; excluded from report timings"}, stdout


def processor_name() -> str:
    if os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
    return platform.processor()


def compiler_info(build: Path) -> dict:
    candidates = list((build / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    if len(candidates) != 1:
        raise RuntimeError("one configured C++ compiler identity required")
    text = candidates[0].read_text(encoding="utf-8")
    values = {}
    for key in ("CMAKE_CXX_COMPILER_ID", "CMAKE_CXX_COMPILER_VERSION"):
        match = re.search(rf'set\({key} "([^"]+)"\)', text)
        if match:
            values[key] = match.group(1)
    if not values.get("CMAKE_CXX_COMPILER_VERSION"):
        raise RuntimeError("compiler identity absent from configured build")
    return values


def sanitize_path(value: str, source: Path, build: Path) -> str:
    for path, replacement in ((build, "BUILD_ROOT"), (source, "SOURCE_ROOT")):
        for spelling in (str(path), str(path).replace("\\", "/")):
            value = re.sub(re.escape(spelling), replacement, value, flags=re.IGNORECASE)
    return value


def sanitize_log(content: bytes, source: Path, build: Path) -> bytes:
    return sanitize_path(content.decode("utf-8", errors="replace"), source, build).encode("utf-8")


def build_graph(build: Path, source: Path, source_commit: str) -> tuple[dict, Path]:
    cache = (build / "CMakeCache.txt").read_text(encoding="utf-8")
    require = report.require
    require(f"CMAKE_HOME_DIRECTORY:INTERNAL={source.as_posix()}" in cache or
            f"CMAKE_HOME_DIRECTORY:INTERNAL={source}" in cache,
            "CMake cache source root differs from clean checkout")
    require("CSL_BUILD_SYN06_REPORT:BOOL=ON" in cache and "BUILD_TESTING:BOOL=OFF" in cache,
            "CMake report target/build configuration differs")
    reply = build / ".cmake/api/v1/reply"
    indexes = list(reply.glob("index-*.json"))
    require(len(indexes) == 1, "one CMake File API index required")
    index = json.loads(indexes[0].read_text(encoding="utf-8"))
    codemodel = json.loads((reply / index["reply"]["codemodel-v2"]["jsonFile"]).read_text(encoding="utf-8"))
    configurations = [c for c in codemodel["configurations"] if c["name"] == "Release"]
    require(len(configurations) == 1, "Release codemodel configuration required")
    targets = {}
    for target in configurations[0]["targets"]:
        if not target["name"].startswith("csl_"):
            continue
        item = json.loads((reply / target["jsonFile"]).read_text(encoding="utf-8"))
        groups = []
        for group in item.get("compileGroups", []):
            if group.get("language") != "CXX":
                continue
            flags = " ".join(fragment["fragment"] for fragment in group.get("compileCommandFragments", []))
            require(group.get("languageStandard", {}).get("standard") == "20" and
                    re.search(r"(?:/D|-D)NDEBUG\b", flags) is not None and
                    re.search(r"(?:-std:c\+\+20|-std=c\+\+20|/std:c\+\+20)", flags) is not None,
                    "C++20/NDEBUG Release compile flags missing: " + target["name"])
            groups.append({"language_standard": "c++20", "flags": sanitize_path(flags, source, build)})
        targets[target["name"]] = {
            "type": item["type"],
            "sources": [sanitize_path(row["path"], source, build) for row in item.get("sources", [])],
            "dependencies": sorted({row["id"].split("::", 1)[0] for row in item.get("dependencies", [])
                                    if row["id"].startswith("csl_")}),
            "compile_groups": groups,
            "artifacts": [row["path"] for row in item.get("artifacts", [])],
        }
    required = {"csl_syn06_verifier_report", "csl_verification", "csl_resolved_problem"}
    require(required <= set(targets) and
            "csl_verification" in targets["csl_syn06_verifier_report"]["dependencies"] and
            any(path.endswith("verifier_driver.cpp") for path in targets["csl_syn06_verifier_report"]["sources"]) and
            any(path.endswith("trajectory.cpp") for path in targets["csl_verification"]["sources"]),
            "CMake report/verifier target graph differs")
    artifacts = [path for path in targets["csl_syn06_verifier_report"]["artifacts"]
                 if path.endswith(".exe") or not Path(path).suffix]
    require(len(artifacts) == 1, "one report executable artifact required")
    executable = (build / artifacts[0]).resolve()
    require(executable.is_file() and executable.is_relative_to(build.resolve()),
            "report executable absent from pinned build graph")
    graph = {"schema": "csl.syn06-build-graph/1", "source_commit": source_commit,
             "source_tree": git("rev-parse", "HEAD^{tree}"), "configuration": "Release",
             "generator": index["cmake"]["generator"]["name"], "targets": targets,
             "binary_artifact": artifacts[0], "binary_sha256": report.digest_bytes(executable.read_bytes())}
    return graph, executable


def collect(build: Path, source_commit: str, cmake: Path, generator: str,
            architecture: str, evidence_dir: Path) -> Path:
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("full fixed source commit required")
    if git("rev-parse", "HEAD") != source_commit or git("status", "--porcelain"):
        raise ValueError("collector requires a clean checkout at the exact full harness commit")
    if not cmake.is_file() or build.exists() or evidence_dir.exists():
        raise ValueError("CMake executable and fresh build/evidence destinations required")
    import psutil
    journal = Journal(evidence_dir)
    try:
        (build / ".cmake/api/v1/query").mkdir(parents=True)
        (build / ".cmake/api/v1/query/codemodel-v2").touch()
        configuration_command = [str(cmake), "-S", str(ROOT), "-B", str(build),
                                 "-G", generator, "-DCSL_BUILD_SYN06_REPORT=ON", "-DBUILD_TESTING=OFF"]
        if architecture:
            configuration_command += ["-A", architecture]
        configured_stdout, configured_stderr = journal.capture("configure", configuration_command)
        build_command = [str(cmake), "--build", str(build), "--config", "Release",
                         "--target", "csl_syn06_verifier_report"]
        built_stdout, built_stderr = journal.capture("build", build_command)
        graph, executable = build_graph(build, ROOT, source_commit)
        postbuild_head, _ = journal.capture("postbuild-head", ["git", "rev-parse", "HEAD"])
        postbuild_status, _ = journal.capture("postbuild-status", ["git", "status", "--porcelain"])
        if postbuild_head.decode("ascii").strip() != source_commit or postbuild_status:
            raise CollectionFailure("source changed during configure/build; evidence: " + str(journal.path))
        pilot_record, pilot_raw = pilot(executable, journal)
        batch = pilot_record["selected_batch"]
        profile_record, profile_raw = profile_run(executable, max(batch, 100000), source_commit, journal)
        host_cpu_before = psutil.cpu_percent(interval=1.0)
        raw, stderr = measured_run(executable, batch, 7, 7, journal, "measurement")
        host_cpu_after = psutil.cpu_percent(interval=1.0)
        if stderr:
            raise CollectionFailure("measurement emitted stderr; evidence: " + str(journal.path))
        trials = report.raw_projection(raw, batch, 7, 7)
        summary = report.summarize(trials, batch)
        if any(row["min_elapsed_ns"] < 50_000_000 for row in summary):
            raise CollectionFailure("measurement interval under 50 ms; evidence: " + str(journal.path))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        source_id = f"syn06-verifier-{stamp}-{source_commit[:8]}"
        bundle = ROOT / "reports" / "algorithm-results" / source_id
        bundle.mkdir(exist_ok=False)
        report_driver = Path(__file__).with_name("verifier_driver.cpp")
        configure_log = sanitize_log(configured_stdout + configured_stderr, ROOT, build)
        build_log = sanitize_log(built_stdout + built_stderr, ROOT, build)
        graph_bytes = report.json_bytes(graph)
        provenance = {
            "schema": "csl.syn06-build-provenance/2", "source_commit": source_commit,
            "source_tree": graph["source_tree"], "verifier_core_commit":
                "edf2b200209f4312b0d00a522a7a0b2e26a96d65",
            "configuration": "Release", "clean_source_before_build": True,
            "clean_source_after_build": True,
            "driver_sha256": report.digest_bytes(report_driver.read_bytes()),
            "binary_sha256": graph["binary_sha256"],
            "cmake_cache_sha256": report.digest_bytes((build / "CMakeCache.txt").read_bytes()),
            "compiler": compiler_info(build),
            "configuration_command": ["cmake", "-S", "SOURCE_ROOT", "-B", "BUILD_ROOT",
                                      "-G", generator, "-DCSL_BUILD_SYN06_REPORT=ON", "-DBUILD_TESTING=OFF"] +
                                     (["-A", architecture] if architecture else []),
            "build_command": ["cmake", "--build", "BUILD_ROOT", "--config", "Release",
                              "--target", "csl_syn06_verifier_report"],
        }
        environment = {
            "os": platform.platform(), "machine": platform.machine(), "processor": processor_name(),
            "logical_cpus": psutil.cpu_count(logical=True), "physical_cpus": psutil.cpu_count(logical=False),
            "memory_bytes": psutil.virtual_memory().total,
            "collection_utc": datetime.now(timezone.utc).isoformat(),
            "host_cpu_percent_before": host_cpu_before, "host_cpu_percent_after": host_cpu_after,
            "cache_policy": "one process, seven warmup batches per fixture, then seven measured batches",
            "seed": None, "simultaneous_work": "No intentional co-located benchmark; host may run background services",
        }
        command_text = f"{batch} 7 7 (Release driver; cwd SOURCE_ROOT)\n"
        files = {
            "configure-log.txt": configure_log, "build-log.txt": build_log,
            "build-graph.json": graph_bytes, "build-provenance.json": report.json_bytes(provenance),
            "measurement-command.txt": command_text.encode(),
            "pilot.json": report.json_bytes(pilot_record), "pilot-raw.jsonl": pilot_raw,
            "profile.json": report.json_bytes(profile_record), "profile-raw.jsonl": profile_raw,
            "process-stderr.txt": stderr, "raw-events.jsonl": raw,
            "trials.csv": report.csv_bytes(report.TRIAL_FIELDS, trials),
            "summary.csv": report.csv_bytes(report.SUMMARY_FIELDS, summary),
            "latency.svg": report.svg(summary).encode(),
            "verifier-driver.bin": executable.read_bytes(),
            "verifier_driver.cpp": report_driver.read_bytes(),
        }
        profile_fields = ("bindings", "feasibility", "objective", "optimality", "completeness",
                          "validated", "recomputed_objective")
        status_profiles = {fixture: {field: next(t for t in trials if t["fixture"] == fixture)[field]
                                     for field in profile_fields} for fixture in report.FIXTURES}
        residual_profiles = {fixture: next(t for t in trials if t["fixture"] == fixture)["residuals"]
                             for fixture in report.FIXTURES}
        payload = {
            "schema": "csl.syn06-verifier-report/2", "source_commit": source_commit,
            "module": {"id": "csl.trajectory.original", "version": "1"},
            "fixture": report.expected_fixture(), "environment": environment,
            "numerical": {"absolute": 1e-8, "relative": 1e-8},
            "workers": {"requested": 1, "actual": 1, "native_threads": 1},
            "batch": batch, "warmups": 7, "repetitions": 7,
            "timing_scope": "verify_trajectory, per-call literal checks, report assignment and complete result consumption; resolved problem and request prebuilt",
            "unavailable_timings": ["problem resolution", "setup", "end-to-end", "rendering", "internal phases"],
            "trials": trials, "summary": summary,
            "status_profiles": status_profiles, "residual_profiles": residual_profiles,
            "raw_sha256": report.digest_bytes(raw),
            "build_sha256": report.digest_bytes(files["build-provenance.json"]),
            "build_graph_sha256": report.digest_bytes(graph_bytes),
            "configure_log_sha256": report.digest_bytes(configure_log),
            "build_log_sha256": report.digest_bytes(build_log),
            "command_sha256": report.digest_bytes(files["measurement-command.txt"]),
            "pilot_sha256": report.digest_bytes(files["pilot.json"]),
            "profile_sha256": report.digest_bytes(files["profile.json"]),
            "stderr_sha256": report.digest_bytes(stderr),
        }
        record = {"schema": "csl.syn06-verifier-report/2", "report_id": source_id,
                  "payload_sha256": report.digest(payload), "payload": payload}
        files["records.json"] = report.json_bytes(record)
        files["index.html"] = report.page(record, files["latency.svg"].decode()).encode()
        files["README.md"] = (f"# SYN-06 original-data verifier report\n\n"
                              f"Clean fixed full harness source: `{source_commit}`; original verifier base: "
                              "`edf2b200209f4312b0d00a522a7a0b2e26a96d65`.\n\n"
                              "This report times two literal witnesses of a two-stage scalar integrator. "
                              "The terminal objective is `x[2]`, so its value is 1. "
                              "Every timed call is checked against literal named residuals and all six claim statuses. "
                              "A deliberately violating control produces a 0.25 domain violation and 0.5 transition residual. "
                              "No optimal-family completeness or validated proof is established.\n\n"
                              "`records.json` and `raw-events.jsonl` contain accepted measurements. "
                              "`pilot.json` and `profile.json` are separate non-report observations; the limiter "
                              "is not established. The build graph and commands use `SOURCE_ROOT`/`BUILD_ROOT` "
                              "placeholders, and the original build was fresh Release/C++20/NDEBUG. "
                              "Run the collector from a clean checkout of the fixed harness commit with a fresh "
                              "build directory and `--cmake`, `--generator`, and `--architecture` arguments.\n").encode()
        if set(files) != report.SOURCE_FILES:
            raise RuntimeError("collector source inventory differs from typed report policy")
        for name, content in files.items():
            (bundle / name).write_bytes(content)
        manifest = {"schema": "csl.syn06-source-manifest/2", "report_id": source_id,
                    "files": {name: report.digest_bytes(files[name]) for name in sorted(files)}}
        (bundle / "manifest.json").write_bytes(report.json_bytes(manifest))
        (bundle / "bundle.zip").write_bytes(report.registered.publication_zip(source_id,
            {**files, "manifest.json": (bundle / "manifest.json").read_bytes()}))
        report.validate(bundle)
        journal.finish()
        return bundle
    except Exception as error:
        journal.fail(str(error))
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
    print(collect(args.build.resolve(), args.source_commit, args.cmake.resolve(),
                  args.generator, args.architecture, args.evidence_dir.resolve()).relative_to(ROOT))


if __name__ == "__main__":
    main()
