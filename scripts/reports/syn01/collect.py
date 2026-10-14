"""Build and collect the versioned SYN-01 nominal-forward report driver."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import shlex
import zipfile
import xml.etree.ElementTree as ET

import report
import publication_map

ROOT = Path(__file__).resolve().parents[3]
TOOLING = Path(__file__).resolve().parent
TRIAL_FIELDS = ("scenario", "repetition", "warmup", "status", "outcome", "oracle_passed",
                "expected_marginals", "observed_marginals", "setup_ns", "setup_state", "solve_ns", "solve_state",
                "oracle_ns", "oracle_state", "execute_ns", "execute_state", "provider_identities",
                "execution_settings", "provider_operation_counts", "provider_operation_timing_ns", "detail")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(content):
    return hashlib.sha256(content).hexdigest()


def project_version():
    import re
    source = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    match = re.search(r"(?m)^project\(CSL VERSION ([^ ]+) LANGUAGES", source)
    if match is None:
        raise ValueError("CMake project version could not be identified")
    return match.group(1)


def _cache_values(path):
    values = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line and not line.startswith(("//", "#")) and "=" in line and ":" in line.split("=", 1)[0]:
            key = line.split("=", 1)[0].split(":", 1)[0]
            values[key] = line.split("=", 1)[1]
    return values


def build_configuration(build, compiler_id, compiler_version, compiler_executable, cmake_version, build_log):
    cache_path = build / "CMakeCache.txt"
    cache = _cache_values(cache_path)
    generator = cache.get("CMAKE_GENERATOR", "")
    platform_name = cache.get("CMAKE_GENERATOR_PLATFORM", "") or "default"
    global_flags = cache.get("CMAKE_CXX_FLAGS_RELEASE", "")
    evidence = {"CMakeCache.txt": sha(cache_path.read_bytes()), "release_build_log": sha(build_log)}
    if "Visual Studio" in generator:
        config_path = build / "csl_syn01_nominal_forward_report.vcxproj"
        root = ET.parse(config_path).getroot()
        namespace = root.tag.partition("}")[0].removeprefix("{")
        qualified = (lambda name: "{" + namespace + "}" + name) if namespace else (lambda name: name)
        group = next((item for item in root.findall(qualified("ItemDefinitionGroup"))
                      if "Release|" in item.attrib.get("Condition", "")), None)
        compile = group.find(qualified("ClCompile")) if group is not None else None
        if compile is None:
            raise ValueError("Release ClCompile properties missing from generated Visual Studio project")
        properties = {item.tag.rsplit("}", 1)[-1]: (item.text or "").strip() for item in compile}
        if properties.get("LanguageStandard") != "stdcpp20":
            raise ValueError("generated report target is not configured for C++20")
        flags = ["/std:c++20"] + shlex.split(global_flags)
        for property_name, value_to_flag in (("Optimization", {"MaxSpeed": "/O2"}),
                                              ("WarningLevel", {"Level4": "/W4"})):
            value = properties.get(property_name)
            if value not in value_to_flag:
                raise ValueError("unexpected generated Release property: " + property_name)
            flags.append(value_to_flag[value])
        if properties.get("TreatWarningAsError") == "true":
            flags.append("/WX")
        if properties.get("ConformanceMode") == "true":
            flags.append("/permissive-")
        evidence["build_configuration_file"] = sha(config_path.read_bytes())
        cxx_standard = "c++20"
        target_properties = properties
    else:
        config_path = build / "compile_commands.json"
        commands = json.loads(config_path.read_text(encoding="utf-8"))
        entry = next((item for item in commands if item.get("file", "").endswith("nominal_forward_driver.cpp")), None)
        if entry is None:
            raise ValueError("compile command for nominal-forward driver is missing")
        command_args = entry.get("arguments") or shlex.split(entry["command"])
        flags = command_args[1:]
        standard = next((flag.split("=", 1)[1] for flag in flags if flag.startswith("-std=")), "")
        if standard not in ("c++20", "gnu++20"):
            raise ValueError("effective compiler command does not select C++20")
        cxx_standard = "c++20"
        target_properties = {"compile_command": entry.get("command", " ".join(command_args))}
        evidence["build_configuration_file"] = sha(config_path.read_bytes())
    if not flags or not global_flags:
        raise ValueError("effective Release flag evidence is incomplete")
    return {"configuration": "Release", "generator": generator, "generator_platform": platform_name,
            "cxx_standard": cxx_standard, "compiler_id": compiler_id, "compiler_version": compiler_version,
            "compiler_executable": compiler_executable, "cmake_version": cmake_version,
            "cmake_release_flags": global_flags, "target_release_properties": target_properties,
            "effective_release_flags": list(dict.fromkeys(flags)), "evidence_sha256": evidence}


def run(command, **kwargs):
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=False, **kwargs)


def run_preserving_timeout(command, timeout, streams, label):
    try:
        return run(command, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        for key, value in ((label + "-timeout-stdout.txt", error.stdout),
                           (label + "-timeout-stderr.txt", error.stderr)):
            if value is not None:
                streams[key] = value if isinstance(value, bytes) else str(value).encode("utf-8", errors="replace")
        raise


def git(root, *arguments):
    result = run(["git", "-C", str(root), *arguments])
    if result.returncode:
        raise RuntimeError("git command failed: " + result.stderr.strip())
    return result.stdout.strip()


def validate_checkout(source_commit, harness_commit):
    if git(ROOT, "rev-parse", "HEAD") != harness_commit:
        raise ValueError("harness commit does not match checkout HEAD")
    if git(ROOT, "status", "--porcelain"):
        raise ValueError("collection requires a clean checkout")
    changed = git(ROOT, "diff", "--name-only", source_commit + ".." + harness_commit).splitlines()
    allowed_prefixes = ("reports/algorithm-results/tooling/syn01/", "scripts/reports/", "tests/reporting/")
    allowed_files = {"CMakeLists.txt", "reports/algorithm-results/catalog.json",
                     "benchmarks/reporting/syn01/nominal_forward_driver.cpp"}
    unexpected = [name for name in changed if name not in allowed_files and not name.startswith(allowed_prefixes)]
    if unexpected:
        raise ValueError("source commit differs outside the reporting-only allowlist: " + ", ".join(unexpected))


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def host_observation():
    try:
        import psutil
        return {"cpu_percent_over_1s": psutil.cpu_percent(interval=1.0),
                "physical_cpus": psutil.cpu_count(logical=False),
                "memory_bytes": psutil.virtual_memory().total}
    except (ImportError, OSError):
        return {"cpu_percent_over_1s": None, "physical_cpus": None,
                "memory_bytes": None, "unavailable_reason": "psutil CPU/memory observation unavailable"}


def persist_failure(out_root, stage, source_commit, harness_commit, command, streams, error):
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = Path(out_root) / "collection-failures" / f"syn01-{stamp}-{os.getpid()}"
    target.mkdir(parents=True, exist_ok=False)
    file_hashes = {}
    for filename, content in streams.items():
        _write(target / filename, content)
        file_hashes[filename] = sha(content)
    failure = {"schema": "csl.syn01-collection-failure/1", "accepted_measurement": False,
               "stage": stage, "error": str(error), "source_commit": source_commit,
               "harness_commit": harness_commit, "command": list(command), "files": file_hashes}
    _write(target / "failure.json", canonical(failure) + b"\n")
    return target


def _csv_bytes(fields, rows):
    from io import StringIO
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: json.dumps(row.get(key), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                         if isinstance(row.get(key), (dict, list)) else row.get(key) for key in fields})
    return stream.getvalue().encode("utf-8")


def trials_csv(rows):
    return _csv_bytes(TRIAL_FIELDS, rows)


def summary_rows(record):
    rows = []
    for item in record["summary"]:
        for phase, stats in item["phases"].items():
            rows.append({"scenario": item["scenario"], "phase": phase, **stats})
    return rows


SUMMARY_FIELDS = ("scenario", "phase", "median_ns", "min_ns", "max_ns", "range_ns",
                  "available_trials", "partial_trials", "not_reached_trials", "unavailable_trials", "coverage")


def summary_csv(record):
    return _csv_bytes(SUMMARY_FIELDS, summary_rows(record))


def zip_bundle(bundle, destination):
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        page = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>SYN-01 offline report</title>'
                '<a href="' + bundle.name + '/index.html">Open the standalone SYN-01 report</a></html>').encode("utf-8")
        archive.writestr("index.html", page)
        for path in sorted(bundle.iterdir()):
            info = zipfile.ZipInfo(bundle.name + "/" + path.name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def collect(args):
    source_commit = args.source_commit
    harness_commit = args.harness_commit
    streams = {}
    stage = "checkout_validation"
    command = []
    try:
        validate_checkout(source_commit, harness_commit)
        stage = "configure"
        build = Path(args.build_dir).resolve()
        if build.exists():
            raise ValueError("build directory must be new/empty")
        configure = [str(args.cmake), "-S", str(ROOT), "-B", str(build), "-G", args.generator,
                     "-DCSL_BUILD_SYN01_REPORT=ON", "-DBUILD_TESTING=OFF", "-DCMAKE_BUILD_TYPE=Release",
                     "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"]
        if args.architecture:
            configure.extend(["-A", args.architecture])
        command = configure
        result = run_preserving_timeout(configure, args.timeout, streams, "configure")
        streams["configure-stdout.txt"] = result.stdout.encode()
        streams["configure-stderr.txt"] = result.stderr.encode()
        if result.returncode:
            raise RuntimeError("CMake configure failed: " + result.stderr[-2000:])
        stage = "build"
        build_command = [str(args.cmake), "--build", str(build), "--config", "Release", "--target",
                         "csl_syn01_nominal_forward_report", "--parallel", str(args.jobs), "--verbose"]
        command = build_command
        result = run_preserving_timeout(build_command, args.timeout, streams, "build")
        streams["build-stdout.txt"] = result.stdout.encode()
        streams["build-stderr.txt"] = result.stderr.encode()
        if result.returncode:
            raise RuntimeError("Release build failed: " + result.stderr[-2000:])
        executable = build / "Release" / "csl_syn01_nominal_forward_report.exe"
        if not executable.exists():
            executable = build / "csl_syn01_nominal_forward_report"
        if not executable.is_file():
            raise RuntimeError("built report driver is missing")
        compiler_file = next(iter((build / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake")), None)
        compiler_text = compiler_file.read_text(encoding="utf-8", errors="replace") if compiler_file else ""
        import re
        compiler_id = re.search(r'set\(CMAKE_CXX_COMPILER_ID "([^"]+)"\)', compiler_text)
        compiler_version = re.search(r'set\(CMAKE_CXX_COMPILER_VERSION "([^"]+)"\)', compiler_text)
        cache_text = (build / "CMakeCache.txt").read_text(encoding="utf-8", errors="replace")
        compiler_path = re.search(r"CMAKE_CXX_COMPILER:FILEPATH=(.+)", cache_text)
        compiler_source = re.search(r'set\(CMAKE_CXX_COMPILER "([^"]+)"\)', compiler_text)
        cmake_version = run([str(args.cmake), "--version"]).stdout.splitlines()[0]
        compiler_executable = Path(compiler_path.group(1) if compiler_path else
                                   compiler_source.group(1) if compiler_source else "unavailable").name
        build_log = streams["build-stdout.txt"] + streams["build-stderr.txt"]
        build_evidence = build_configuration(build, compiler_id.group(1) if compiler_id else "unavailable",
            compiler_version.group(1) if compiler_version else "unavailable", compiler_executable,
            cmake_version, build_log)
        stage = "driver"
        command = [str(executable)]
        load_before = host_observation()
        measured = run_preserving_timeout(command, args.timeout, streams, "driver")
        load_after = host_observation()
        streams["driver-stdout.jsonl"] = measured.stdout.encode()
        streams["driver-stderr.txt"] = measured.stderr.encode()
        if measured.returncode:
            raise RuntimeError("driver returned nonzero status " + str(measured.returncode))
        trials = [json.loads(line) for line in measured.stdout.splitlines() if line.strip()]
        stage = "record_validation"
        providers = next((row.get("provider_identities") for row in trials if row.get("provider_identities")), {})
        record = report.make_record(trials, source_commit=source_commit, harness_commit=harness_commit,
                                    environment={"os": platform.platform(), "machine": platform.machine(),
                                                 "processor": platform.processor() or "unavailable",
                                                 "logical_cpus": os.cpu_count(), "requested_workers": 1,
                                                 "configured_native_threads": 1,
                                                 "physical_cpus": load_before.get("physical_cpus"),
                                                 "memory_bytes": load_before.get("memory_bytes"),
                                                 "host_load_before": load_before,
                                                 "host_load_after": load_after},
                                    provenance={"algorithm_module": {"id": "csl.reachability.nominal-forward",
                                                                     "version": project_version()},
                                                "providers": providers,
                                                "dependency_edges": {"affine_sum": ["hull_reducer", "lp_backend", "conversion"],
                                                                     "conversion": ["lp_backend"]},
                                                "runtime_settings": trials[0].get("execution_settings"),
                                                "native_thread_observation": {
                                                    "status": "unavailable", "observed_threads": None,
                                                    "reason": "The driver has no supported runtime API to observe effective native worker threads."},
                                                "build_configuration": build_evidence,
                                                "configuration": "Release", "generator": args.generator,
                                                "cmake_version": cmake_version,
                                                "compiler_id": compiler_id.group(1) if compiler_id else "unavailable",
                                                "compiler_version": compiler_version.group(1) if compiler_version else "unavailable",
                                                "compiler_executable": compiler_executable,
                                                "driver_sha256": sha(executable.read_bytes()),
                                                "driver_source_sha256": sha((ROOT / "benchmarks/reporting/syn01/nominal_forward_driver.cpp").read_bytes()),
                                                "configure_command": [str(args.cmake), "-S", "SOURCE_ROOT", "-B", "BUILD_ROOT", "-G", args.generator,
                                                                      "-DCSL_BUILD_SYN01_REPORT=ON", "-DBUILD_TESTING=OFF", "-DCMAKE_BUILD_TYPE=Release"],
                                                "build_command": [str(args.cmake), "--build", "BUILD_ROOT", "--config", "Release", "--target",
                                                                  "csl_syn01_nominal_forward_report", "--parallel", str(args.jobs), "--verbose"]})
        errors = report.validate_record(record)
        if errors:
            raise ValueError("record validation failed: " + ", ".join(errors))
        if record["collection"]["state"] != "complete":
            raise ValueError("failed/non-oracle-passing trials are retained as collection failure evidence, not publishable report bundles")
        core = {key: value for key, value in record.items() if key != "report_id"}
        record["report_id"] = "syn01-nominal-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d") + "-" + source_commit[:8] + "-" + sha(canonical(core))[:12]
        out_root = Path(args.out_root).resolve()
        bundle = out_root / record["report_id"]
        if bundle.exists() or bundle.with_suffix(".zip").exists():
            raise ValueError("immutable report destination already exists")
        bundle.mkdir(parents=True, exist_ok=False)
        _write(bundle / "records.json", canonical(record) + b"\n")
        _write(bundle / "raw-events.jsonl", streams["driver-stdout.jsonl"])
        _write(bundle / "configure-log.txt", streams["configure-stdout.txt"] + streams["configure-stderr.txt"])
        _write(bundle / "build-log.txt", streams["build-stdout.txt"] + streams["build-stderr.txt"])
        _write(bundle / "driver-stderr.txt", streams["driver-stderr.txt"])
        _write(bundle / "trials.csv", trials_csv(trials))
        _write(bundle / "summary.csv", summary_csv(record))
        _write(bundle / "scenarios.json", canonical({"fixture_catalog": record["fixture_catalog"],
                                                       "scenario_hashes": record["scenario_hashes"]}) + b"\n")
        (bundle / "index.html").write_text(report.render_html(record), encoding="utf-8", newline="\n")
        (bundle / "latency.svg").write_text(report.render_svg(record), encoding="utf-8", newline="\n")
        (bundle / "environment.json").write_bytes(canonical(record["environment"]) + b"\n")
        (bundle / "build-provenance.json").write_bytes(canonical(record["provenance"]) + b"\n")
        (bundle / "measurement-command.txt").write_text("\n".join(command) + "\n", encoding="utf-8")
        (bundle / "profile-evidence.txt").write_text("No separate source-level profile was collected; no comparative performance claim is made. Limiter and capacity remain unknown.\n", encoding="utf-8")
        for name in ("README.md",):
            shutil.copyfile(TOOLING / name, bundle / name)
        _write(bundle / "publication-map.json", canonical(publication_map.project(record)) + b"\n")
        manifest_files = {path.name: sha(path.read_bytes()) for path in bundle.iterdir()}
        manifest = {"schema": "csl.syn01-report-manifest/1", "report_id": record["report_id"],
                    "source_commit": source_commit, "harness_commit": harness_commit, "files": manifest_files}
        (bundle / "manifest.json").write_bytes(canonical(manifest) + b"\n")
        zip_bundle(bundle, bundle.with_suffix(".zip"))
        print(json.dumps({"report_id": record["report_id"], "bundle": str(bundle),
                          "source_commit": source_commit, "harness_commit": harness_commit,
                          "state": record["collection"]["state"], "counts": record["collection"]["counts"]}, indent=2))
        return bundle
    except Exception as error:
        location = persist_failure(args.out_root, stage, source_commit, harness_commit, command, streams, error)
        raise RuntimeError(f"SYN-01 collection failed at {stage}; evidence saved at {location}: {error}") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cmake", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--harness-commit", required=True)
    parser.add_argument("--generator", default="Visual Studio 17 2022")
    parser.add_argument("--architecture", default="x64")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=3600)
    collect(parser.parse_args())


if __name__ == "__main__":
    main()
