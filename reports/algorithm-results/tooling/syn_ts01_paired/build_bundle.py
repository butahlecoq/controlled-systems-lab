"""Build a versioned paired T-S01 report from saved process/events only; never runs the solver."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import report

FILES = {
    "README.md", "build-provenance.json", "commands.json", "environment.json", "index.html",
    "limiter-profile.json", "measurement-events.jsonl", "process-run.json", "process-stderr.bin",
    "process-stdout.bin", "records.json", "scenario.json", "performance.svg", "trials.csv", "validation.json",
}


def sha_bytes(value): return hashlib.sha256(value).hexdigest()
def sha_file(path): return sha_bytes(Path(path).read_bytes())
def canonical(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
def pretty(value): return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
def read_json(path): return json.loads(Path(path).read_text(encoding="utf-8"))


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def build_provenance(source_root, build_root, dependency_root, library_prefix):
    source_root, build_root = Path(source_root), Path(build_root)
    commit = git(source_root, "rev-parse", "HEAD")
    if commit != report.SOURCE_COMMIT or git(source_root, "status", "--porcelain"):
        raise ValueError("measured source checkout must be clean at the pinned source commit")
    source_file = source_root / "examples/registered_synthesis_comparison.cpp"
    if sha_file(source_file) != report.SOURCE_FILE_SHA256:
        raise ValueError("measured source file hash differs from selector-request source pin")
    executable = build_root / "Release/registered_synthesis_comparison.exe"
    project = build_root / "registered_synthesis_comparison.vcxproj"
    cache = (build_root / "CMakeCache.txt").read_text(encoding="utf-8", errors="replace")
    tree = ET.parse(project).getroot()
    namespace = tree.tag.partition("}")[0].removeprefix("{")
    tag = lambda name: "{" + namespace + "}" + name
    group = next((g for g in tree.findall(tag("ItemDefinitionGroup")) if "Release|x64" in g.attrib.get("Condition", "")), None)
    cl = group.find(tag("ClCompile")) if group is not None else None
    props = {node.tag.rsplit("}", 1)[-1]: (node.text or "") for node in cl} if cl is not None else {}
    if props.get("LanguageStandard") != "stdcpp20" or props.get("Optimization") != "MaxSpeed" or "NDEBUG" not in props.get("PreprocessorDefinitions", ""):
        raise ValueError("Release project does not prove C++20 optimized NDEBUG configuration")
    if "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" not in cache or "CMAKE_GENERATOR_PLATFORM:INTERNAL=x64" not in cache:
        raise ValueError("build cache does not prove the expected Visual Studio x64 generator")

    dep_root = Path(dependency_root)
    dep_commit = git(dep_root, "rev-parse", "HEAD")
    diff = subprocess.run(["git", "-C", str(source_root), "diff", "--quiet", commit, dep_commit, "--", "src", "include", "CMakeLists.txt", "cmake"], check=False)
    if diff.returncode not in (0, 1): raise ValueError("could not compare linked library source identity")
    code_equivalent = diff.returncode == 0

    libraries = []
    prefix = Path(library_prefix)
    link = group.find(tag("Link")) if group is not None else None
    deps = link.find(tag("AdditionalDependencies")) if link is not None else None
    for item in (deps.text or "").split(";") if deps is not None else []:
        p = Path(item)
        if p.is_absolute() and p.suffix.lower() == ".lib" and p.is_file() and str(p).lower().startswith(str(prefix).lower()):
            libraries.append({"name": p.name, "sha256": sha_file(p)})
    compiler_file = next(build_root.glob("CMakeFiles/*/CMakeCXXCompiler.cmake"), None)
    compiler_text = compiler_file.read_text(encoding="utf-8", errors="replace") if compiler_file else ""
    compiler_version = next((line.split('"')[1] for line in compiler_text.splitlines() if line.startswith('set(CMAKE_CXX_COMPILER_VERSION "')), "unavailable")
    return {
        "schema": "csl.paired-ts01-build-provenance/1",
        "measured_source_commit": commit,
        "measured_source_file_sha256": report.SOURCE_FILE_SHA256,
        "executable_sha256": sha_file(executable),
        "build_configuration": "Release",
        "generator": "Visual Studio 17 2022",
        "platform": "x64",
        "compiler": "MSVC " + compiler_version,
        "language_standard": "C++20",
        "optimization": "MaxSpeed",
        "ndebug": True,
        "warnings_as_errors": props.get("TreatWarningAsError") == "true",
        "linked_library_source_commit": dep_commit,
        "linked_algorithm_code_equivalent_to_measured_source": code_equivalent,
        "library_source_comparison_scope": ["src", "include", "CMakeLists.txt", "cmake"],
        "linked_installed_libraries": sorted(libraries, key=lambda item: item["name"]),
        "dependency_library_hash_count": len(libraries),
    }


def make_record(run_root, source_root, build_info):
    run_root, source_root = Path(run_root), Path(source_root)
    events_path = run_root / "events.jsonl"
    raw = events_path.read_bytes()
    events = [json.loads(line) for line in raw.decode("utf-8", errors="strict").splitlines() if line.strip()]
    event_error = None
    try:
        if len(events) != 17: event_error = "expected 1 header and 16 trial events"
    except Exception as error:
        event_error = str(error)
    if event_error: raise ValueError(event_error)
    header = events[0]
    scenario_raw = (source_root / "examples/scenarios/two-stage-integrator.json").read_bytes()
    if sha_bytes(scenario_raw) != report.SCENARIO_SHA256 or header.get("scenario_sha256") != report.SCENARIO_SHA256:
        raise ValueError("scenario file hash differs from the measured event header")
    scenario_value = json.loads(scenario_raw.decode("utf-8"))
    validation = read_json(run_root / "validation.json")
    external_process = read_json(run_root / "process-run.json")
    raw_stdout = (run_root / "stdout.bin").read_bytes()
    raw_stderr = (run_root / "stderr.bin").read_bytes()
    events_sha = sha_bytes(raw)
    if raw_stdout.replace(b"\r\n", b"\n") != raw:
        raise ValueError("captured stdout differs from raw events beyond Windows newline translation")
    request = {
        "problem_identity": header["problem"],
        "profile": header["profile"],
        "target": header["target"],
        "representation": header["representation"],
        "assurance": header["assurance"],
        "absolute_tolerance": header["absolute_tolerance"],
        "relative_tolerance": header["relative_tolerance"],
        "materialization_limit": None,
        "selector": dict(report.EXPECTED_SELECTOR),
        "selector_source": {"commit": report.SOURCE_COMMIT, "file_sha256": report.SOURCE_FILE_SHA256},
        "resource_policy": header["resource_policy"],
    }
    try:
        measurement = {
            "events_sha256": events_sha,
            "stdout_sha256": sha_bytes(raw_stdout),
            "stderr_sha256": sha_bytes(raw_stderr),
            "events": events,
            "algorithm_return_code": external_process["return_code"],
            "launcher_exit_code": 1,
            "stdout_normalized_to_events": True,
            "wrapper_issue": validation["launcher_validation_error"],
            "warmup_pairs": validation["warmup_pairs"],
            "measured_pairs": validation["measured_pairs"],
            "passed_trials": validation["passed_trials"],
            "failed_trials": validation["failed_trials"],
            "summary": report.timing_summary(events[1:]),
            "performance_conclusion": "inconclusive",
            "limiter_profile": {"performed": False, "limiter_identified": False,
                "reason": "No separate limiter profile was performed; the latency limiter remains unknown and this exact-fixture comparison is inconclusive."},
            "phase_counters_unavailable": events[0]["phase_counters_unavailable"],
        }
    except (KeyError, TypeError) as error:
        raise ValueError("saved process or validation metadata is malformed") from error
    environment_snapshot = read_json(run_root / "environment-pre.json")
    environment = {
        "schema": "csl.paired-ts01-environment/1",
        "captured_utc": environment_snapshot["captured_utc"],
        "computer_alias": "measurement-host-1",
        "os": "Windows 11 Home",
        "os_version": environment_snapshot["os_version"],
        "processor": environment_snapshot["processor"],
        "physical_cores": environment_snapshot["physical_cores"],
        "logical_processors": environment_snapshot["logical_processors"],
        "memory_bytes": environment_snapshot["memory_bytes"],
        "cpu_samples": environment_snapshot["cpu_samples"],
        "cpu_samples_summary": "0% total processor utilization in all five 1-second pre-run samples",
        "concurrent_benchmark_detected": False,
        "concurrent_build_or_test_detected": False,
        "observed_idle_background": ["Three persistent MSBuild node-reuse workers were idle.", "One localhost Python process served a previously staged static report; no collection or benchmark work was active."],
        "snapshot_sha256": sha_file(run_root / "environment-pre.json"),
        "requested_concurrency": header["resource_policy"],
    }
    process = {
        "schema": "csl.paired-ts01-process-run/1",
        "command": ["registered_synthesis_comparison.exe", "--measure", "two-stage-integrator.json", "measurement-events.jsonl"],
        "started_utc": external_process["started_utc"],
        "ended_utc": external_process["ended_utc"],
        "external_wall_ns": external_process["external_wall_ns"],
        "algorithm_return_code": external_process["return_code"],
        "launcher_exit_code": 1,
        "events_sha256": events_sha,
        "stdout_sha256": sha_bytes(raw_stdout),
        "stderr_sha256": sha_bytes(raw_stderr),
        "stdout_equals_events_exactly": False,
        "stdout_equals_events_after_crlf_normalization": True,
        "wrapper_exit_reason": "Incorrect byte-for-byte stdout/event-file comparison ignored CRLF conversion on Windows; the preserved streams differ only by CRLF-to-LF normalization.",
        "record_count": len(events),
    }
    record = {
        "schema": report.SCHEMA,
        "report_id": report.REPORT_ID,
        "created_utc": external_process["ended_utc"],
        "source": {"harness_commit": report.SOURCE_COMMIT, "measurement_source_file_sha256": report.SOURCE_FILE_SHA256},
        "scenario": {"sha256": report.SCENARIO_SHA256, "canonical_sha256": sha_bytes(canonical(scenario_value)), "value": scenario_value},
        "request": request,
        "strategies": list(report.STRATEGIES),
        "build": build_info,
        "environment": environment,
        "process": process,
        "measurement": measurement,
        "evidence_limits": [
            "Complete-family status is exact-profile and registered-verifier evidence for this admitted T-S01 fixture under Assurance::numerical; validated arithmetic is unavailable.",
            "This is one tiny scalar two-stage integrator fixture; the observed timing distributions do not establish an application-scale or general strategy performance ranking.",
            "No separate limiter profile was performed. The source-level latency limiter is unknown; the result is explicitly inconclusive and claims no winner.",
            "The live complete-family proof payload is not serialized. Original-data witness checks establish bindings, feasibility, and objective only; independent optimality and completeness statuses remain unsupported.",
            "Internal LP/convex, projection, affine-sum, conversion, hull-membership, verifier subphase durations/call counts, CPU time, and per-call peak memory are unavailable.",
            "The collector launcher exited 1 on an overly strict stdout byte comparison; algorithm return code was 0 and retained stdout matches the raw event file after CRLF-to-LF normalization.",
        ],
    }
    errors = report.validate(record)
    if errors: raise ValueError("saved records failed validation: " + ", ".join(errors))
    return record, scenario_raw, raw, raw_stdout, raw_stderr, validation, process


def write_bundle(args):
    output = Path(args.out)
    if output.exists(): raise SystemExit("refusing to overwrite report bundle")
    output.mkdir(parents=True)
    run_root = Path(args.run_root)
    source_root = Path(args.source_root)
    build_info = build_provenance(source_root, args.build_root, args.dependency_source_root, args.library_prefix)
    record, scenario_raw, raw, stdout, stderr, validation, process = make_record(run_root, source_root, build_info)
    files = {}
    files["records.json"] = pretty(record)
    files["scenario.json"] = scenario_raw
    files["measurement-events.jsonl"] = raw
    files["process-stdout.bin"] = stdout
    files["process-stderr.bin"] = stderr
    files["build-provenance.json"] = pretty(build_info)
    files["environment.json"] = pretty(record["environment"])
    files["process-run.json"] = pretty(process)
    files["validation.json"] = pretty(validation)
    files["limiter-profile.json"] = pretty(record["measurement"]["limiter_profile"])
    files["commands.json"] = pretty({
        "schema": "csl.paired-ts01-reproduction-commands/1",
        "clean_source_commit": report.SOURCE_COMMIT,
        "configuration": ["cmake -S <source>/examples -B <build> -G \"Visual Studio 17 2022\" -A x64 -DCMAKE_PREFIX_PATH=<installed-prefix>", "cmake --build <build> --config Release --target registered_synthesis_comparison --parallel 4"],
        "measurement": ["registered_synthesis_comparison.exe --measure examples/scenarios/two-stage-integrator.json <new-output>/measurement-events.jsonl"],
        "collection_policy": "Preserve stdout, stderr, JSONL, process exit status and failures before validating. On Windows compare stdout with JSONL after explicit CRLF-to-LF normalization; never discard failed trial events.",
        "report_regeneration": ["python reports/algorithm-results/tooling/syn_ts01_paired/build_bundle.py --run-root <saved-run> --source-root <clean-source> --build-root <release-build> --dependency-source-root <linked-library-source> --library-prefix <installed-prefix> --out reports/algorithm-results/syn-ts01-paired-20261014-b7f1ac0"],
        "saved_record_only": True,
    })
    files["README.md"] = ("# Paired registered synthesis T-S01 report\n\n"
        "This report preserves one exact T-S01 paired experiment on the two-stage scalar integrator. It records one excluded A/B warmup and seven measured alternating pairs. Both strategies use the same resolved problem, family request, selector request, provider registrations, and requested resource policy.\n\n"
        "The conclusion is **inconclusive; no winner is claimed**. The timing medians are descriptive for this tiny fixture. No separate limiter profile was performed, so the latency limiter is unknown. The report does not support a general performance ranking, speedup, application-scale, or scalability claim.\n\n"
        "The event file is the exact binary JSONL sidecar. The original Windows stdout bytes and stderr bytes are retained. The collector wrapper exited 1 because it compared CRLF stdout with the LF JSONL sidecar byte-for-byte. Algorithm exit code was 0, and both streams match after CRLF-to-LF normalization. The failed wrapper attempt is explicitly retained in process and validation metadata.\n\n"
        "The selector request parameters are copied from source commit `b7f1ac0a9800326c825b6d8e35a8f23656496682`, pinned by the measurement source file SHA-256 in `records.json`. Each event retains its actual family/objective identity and module provenance. The live complete-family proof payload is not serialized.\n\n"
        "Rebuild and regeneration commands are in `commands.json`. Regenerating this bundle uses saved measurement outputs only; it does not rerun the algorithm. Live GitHub Pages publication remains pending review and main-branch deployment. This partial report does not close OBS-04/#83.\n").encode("utf-8")
    # The renderer uses the saved typed record only; it never launches an algorithm.
    files["performance.svg"] = report.render_svg(record).encode("utf-8")
    files["index.html"] = report.render_html(record).encode("utf-8")
    trial_fields = ["repetition", "warmup", "order_position", "strategy", "status", *report.PHASES]
    import io
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=trial_fields, lineterminator="\n")
    writer.writeheader()
    for event in record["measurement"]["events"][1:]:
        row = {key: event[key] for key in trial_fields if key in event}
        for phase in report.PHASES:
            row[phase] = event["timings_ns"][phase]["value"]
        writer.writerow(row)
    files["trials.csv"] = stream.getvalue().encode("utf-8")
    for name, content in files.items():
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    manifest = {"schema": "csl.paired-ts01-bundle-manifest/1", "report_id": report.REPORT_ID,
        "files": {name: sha_bytes(content) for name, content in sorted(files.items())}}
    (output / "manifest.json").write_bytes(pretty(manifest))
    actual = {item.name for item in output.iterdir() if item.is_file()}
    if actual != FILES | {"manifest.json"}: raise ValueError("generated bundle inventory differs")
    print(json.dumps({"report_id": report.REPORT_ID, "out": str(output), "files": len(files),
        "report_errors": report.validate(record), "events_sha256": sha_bytes(raw), "stdout_sha256": sha_bytes(stdout)}, sort_keys=True, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--dependency-source-root", type=Path, required=True)
    parser.add_argument("--library-prefix", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    write_bundle(args)


if __name__ == "__main__": main()
