#!/usr/bin/env python3
"""Collect versioned GEO-04 records. Collection is only valid after harness review."""
from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from geo04_catalog import CATALOG_VERSION, EXPECTED, SCENARIOS
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "reports"))
import collector_common

SCHEMA = "csl.geo04-polyhedral-report/1"
PHASES = ("intersection_ns", "prepare_ns", "workspace_ns", "conversion_run_ns", "lp_workspace_ns", "reduction_ns", "total_ns")
FIELDS = ("scenario", "repetition", "status", "detail", *PHASES, "lp_calls", "lp_results", "lp_optimal",
          "lp_bounds", "lp_supported_bounds", "reduction_status", "inequalities", "equalities", "vertices", "oracle_checks", "vertices_json", "oracle_passed")
HARNESS_PATH_ALLOWLIST = {
    "reports/algorithm-results/tooling/geo04/README.md",
    "reports/algorithm-results/tooling/geo04/geo04_catalog.py",
    "reports/algorithm-results/tooling/geo04/collect.py",
    "reports/algorithm-results/tooling/geo04/polyhedral_intersection_driver.cpp",
    "reports/algorithm-results/tooling/geo04/render.py",
    "reports/algorithm-results/tooling/geo04/test_report_tools.py",
}
GEO04_CMAKE_OPTION = 'option(CSL_BUILD_GEO04_REPORT "Build the GEO-04 intersection/reduction report driver" OFF)'
GEO04_CMAKE_TARGET = '''if(CSL_BUILD_GEO04_REPORT)
  add_executable(csl_geo04_intersection_report reports/algorithm-results/tooling/geo04/polyhedral_intersection_driver.cpp)
  target_link_libraries(csl_geo04_intersection_report PRIVATE CSL::polyhedral CSL::qhull_conversion CSL::highs_lp)
endif()'''
GEO03_CMAKE_OPTION = 'option(CSL_BUILD_GEO03_REPORT "Build the GEO-03 H/V conversion report driver" OFF)'
GEO03_CMAKE_TARGET = '''if(CSL_BUILD_GEO03_REPORT)
  add_executable(csl_geo03_conversion_report reports/algorithm-results/tooling/geo03/hv_conversion_driver.cpp)
  target_link_libraries(csl_geo03_conversion_report PRIVATE CSL::qhull_conversion CSL::highs_lp)
endif()'''


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8").strip()


def validate_source_tree_delta(changed_paths: list[str]) -> None:
    unexpected = sorted(set(changed_paths) - HARNESS_PATH_ALLOWLIST)
    if unexpected:
        raise ValueError(f"tracked source tree changed outside the report harness allowlist: {unexpected}")


def validate_cmake_delta(source_text: str, harness_text: str) -> None:
    if source_text.count(GEO03_CMAKE_OPTION) != 1 or source_text.count(GEO03_CMAKE_TARGET) != 1:
        raise ValueError("pinned CMakeLists.txt lacks the unique GEO-03 anchors")
    expected = source_text.replace(GEO03_CMAKE_OPTION, GEO03_CMAKE_OPTION + "\n" + GEO04_CMAKE_OPTION, 1)
    expected = expected.replace(GEO03_CMAKE_TARGET, GEO03_CMAKE_TARGET + "\n" + GEO04_CMAKE_TARGET, 1)
    if harness_text != expected:
        raise ValueError("CMakeLists.txt changed beyond the exact GEO-04 report-target insertion")


def vertices_match_expected(points: list, expected_points: list, tolerance: float = 1e-7) -> bool:
    if len(points) != len(expected_points):
        return False
    consumed: set[int] = set()
    for point in points:
        if len(point) != 2:
            return False
        match = next((index for index, candidate in enumerate(expected_points)
                      if index not in consumed and all(abs(float(actual)-float(wanted)) <= tolerance
                                                       for actual, wanted in zip(point, candidate))), None)
        if match is None:
            return False
        consumed.add(match)
    return len(consumed) == len(expected_points)


def redact_paths(value, source_root: Path, build: Path):
    replacements = [(str(source_root), "SOURCE_ROOT"), (str(build), "BUILD_ROOT"),
                    (str(Path.home()), "USER_HOME")]
    if isinstance(value, str):
        for actual, token in replacements:
            value = value.replace(actual, token).replace(actual.replace("\\", "/"), token)
        return value
    if isinstance(value, list):
        return [redact_paths(item, source_root, build) for item in value]
    if isinstance(value, dict):
        return {key: redact_paths(item, source_root, build) for key, item in value.items()}
    return value


def clean_tracked() -> None:
    if git("status", "--porcelain=v1", "--untracked-files=no"):
        raise ValueError("tracked source tree is dirty")


def build_provenance(build: Path, exe: Path, source_commit: str, harness_commit: str) -> dict:
    clean_tracked()
    if git("rev-parse", "HEAD") != harness_commit:
        raise ValueError("harness commit does not match current checkout")
    changed_paths = git("diff", "--name-only", source_commit, harness_commit).splitlines()
    validate_source_tree_delta([path for path in changed_paths if path != "CMakeLists.txt"])
    source_cmake = subprocess.check_output(["git", "show", f"{source_commit}:CMakeLists.txt"], text=True, encoding="utf-8")
    harness_cmake = subprocess.check_output(["git", "show", f"{harness_commit}:CMakeLists.txt"], text=True, encoding="utf-8")
    validate_cmake_delta(source_cmake, harness_cmake)
    source_tree_oid = git("rev-parse", f"{source_commit}^{{tree}}")
    harness_tree_oid = git("rev-parse", f"{harness_commit}^{{tree}}")
    reply = build / ".cmake" / "api" / "v1" / "reply"
    indices = sorted(reply.glob("index-*.json"))
    if not indices:
        raise ValueError("CMake File API reply missing; query codemodel-v2 and toolchains-v1 before configuring")
    index = json.loads(indices[-1].read_text(encoding="utf-8"))
    def load(filename: str) -> dict:
        return json.loads((reply / filename).read_text(encoding="utf-8"))
    codemodel = load(index["reply"]["codemodel-v2"]["jsonFile"])
    configurations = [item for item in codemodel["configurations"] if item["name"] == "Release"]
    if len(configurations) != 1:
        raise ValueError("actual Release configuration missing from CMake File API")
    targets = {item["id"]: load(item["jsonFile"]) for item in configurations[0]["targets"]}
    roots = [key for key, target in targets.items() if target["name"] == "csl_geo04_intersection_report"]
    if len(roots) != 1:
        raise ValueError("GEO-04 report executable missing from configured Release graph")
    selected: dict[str, dict] = {}
    def visit(key: str) -> None:
        if key in selected:
            return
        target = targets[key]
        selected[key] = {field: target[field] for field in ("name", "type", "compileGroups", "link", "archive", "artifacts") if field in target}
        for dep in target.get("dependencies", []):
            visit(dep["id"])
    visit(roots[0])
    root = targets[roots[0]]
    artifacts = [build / artifact["path"] for artifact in root.get("artifacts", []) if Path(artifact["path"]).name == exe.name]
    if len(artifacts) != 1 or not artifacts[0].is_file() or not artifacts[0].samefile(exe):
        raise ValueError("provided executable is not the configured Release target artifact")
    compile_groups = [group for group in root.get("compileGroups", []) if group.get("language") == "CXX"]
    if len(compile_groups) != 1 or compile_groups[0].get("languageStandard", {}).get("standard") != "20":
        raise ValueError("report driver must have one C++20 Release compile group")
    flags = " ".join(fragment["fragment"] for fragment in compile_groups[0].get("compileCommandFragments", []))
    if "/DNDEBUG" not in flags and "-DNDEBUG" not in flags:
        raise ValueError("Release/NDEBUG flag missing from actual report driver compile group")
    toolchains = load(index["reply"]["toolchains-v1"]["jsonFile"])["toolchains"]
    cxx = [item for item in toolchains if item.get("language") == "CXX"]
    if len(cxx) != 1:
        raise ValueError("actual C++ toolchain missing")
    names = {target["name"] for target in selected.values()}
    required = {"csl_geo04_intersection_report", "csl_polyhedral", "csl_qhull_conversion", "csl_highs_lp", "highs", "csl_optimization", "csl_registry", "csl_sets", "csl_numeric"}
    if not required <= names:
        raise ValueError("report executable dependency graph is incomplete")
    source_root = Path(git("rev-parse", "--show-toplevel")).resolve()
    pin_files = [Path("cmake/HighsDependencies.cmake"), Path("cmake/QhullDependencies.cmake")]
    dependency_pins = {str(path).replace("\\", "/"): hashlib.sha256((source_root / path).read_bytes()).hexdigest()
                       for path in pin_files}
    paths = codemodel["paths"]
    if not Path(paths["source"]).samefile(source_root) or not Path(paths["build"]).samefile(build):
        raise ValueError("CMake source/build path ownership differs from this collection")
    cmake_version = index.get("cmake", {}).get("version", {})
    return {"source_commit": source_commit, "harness_commit": harness_commit, "tracked_clean": True,
            "tracked_tree_binding": {"scope": "complete tracked repository tree", "source_tree_oid": source_tree_oid,
                                     "harness_tree_oid": harness_tree_oid, "allowed_harness_delta": sorted(HARNESS_PATH_ALLOWLIST),
                                     "actual_changed_paths": changed_paths},
            "executable": {"name": exe.name, "sha256": hashlib.sha256(exe.read_bytes()).hexdigest()},
            "cmake": {"version": cmake_version, "generator": index.get("cmake", {}).get("generator", {}).get("name")},
            "configuration": "Release", "cxx_standard": "20", "compiler": cxx[0],
            "dependency_pin_file_sha256": dependency_pins,
            "driver_compile_group": compile_groups[0], "dependency_targets": sorted(names),
            "file_api_paths": paths, "targets": list(selected.values())}


def summarize(trials: list[dict], complete_group: bool) -> dict:
    result = {}
    for scenario in SCENARIOS:
        group = [row for row in trials if row["scenario"] == scenario]
        passed = [row for row in group if row["status"] == "passed" and row["oracle_passed"]]
        accepted = passed if complete_group else []
        phases = {}
        for phase in PHASES:
            values = sorted(row[phase] for row in accepted)
            phases[phase] = {
                "unit": "ns", "successful_trials": len(values),
                "median": (values[(len(values)-1)//2] + values[len(values)//2]) // 2 if values else None,
                "min": min(values) if values else None, "max": max(values) if values else None,
                "range": max(values)-min(values) if values else None,
                "trials_excluded_from_summary": len(group)-len(accepted),
            }
        result[scenario] = {"attempts": len(group), "passed": len(passed),
                            "failures": len(group)-len(passed), "phases": phases}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True, help="actual configured CMake File API build tree")
    parser.add_argument("--source-commit", required=True, help="fixed algorithm-code commit being measured")
    parser.add_argument("--harness-commit", required=True, help="commit containing this collector/driver")
    parser.add_argument("--concurrent-work", type=Path, required=True, help="operator observation of unrelated work; use an explicit none/busy note")
    parser.add_argument("--profile-evidence", type=Path, required=True, help="separate untimed profile notes and observations")
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.repetitions < 7 or args.warmups < 1:
        parser.error("accepted measurements require at least 7 repetitions and 1 warmup")
    if args.out.exists():
        parser.error(f"refusing to overwrite existing collection: {args.out}")
    build = args.build_dir.resolve()
    reply = build / ".cmake" / "api" / "v1" / "reply"
    indices = sorted(reply.glob("index-*.json"))
    if not indices:
        parser.error("CMake File API query/reply missing; configure with codemodel-v2 and toolchains-v1 queries")
    index = json.loads(indices[-1].read_text(encoding="utf-8"))
    cmake = index["cmake"]["paths"]["cmake"]
    final_build_command = [cmake, "--build", str(build), "--config", "Release", "--target", "csl_geo04_intersection_report", "--parallel", "4", "--verbose"]
    final_build = subprocess.run(final_build_command, text=True, capture_output=True, check=False, timeout=1200)
    if final_build.returncode:
        args.out.mkdir(parents=True)
        (args.out / "final-build-stdout.txt").write_text(final_build.stdout, encoding="utf-8")
        (args.out / "final-build-stderr.txt").write_text(final_build.stderr, encoding="utf-8")
        raise SystemExit(f"final Release build failed ({final_build.returncode}); logs saved to {args.out}")
    provenance = build_provenance(build, args.exe.resolve(), args.source_commit, args.harness_commit)
    provenance["final_build"] = {"command": final_build_command, "return_code": final_build.returncode,
                                 "stdout_sha256": sha256_bytes(final_build.stdout.encode()),
                                 "stderr_sha256": sha256_bytes(final_build.stderr.encode())}
    out = args.out
    if out.exists():
        parser.error(f"refusing to overwrite existing collection: {out}")
    source_root = Path(git("rev-parse", "--show-toplevel")).resolve()
    safe_provenance = redact_paths(provenance, source_root, build)
    out.mkdir(parents=True)
    (out / "build-provenance.json").write_text(json.dumps(safe_provenance, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    safe_stdout = redact_paths(final_build.stdout, source_root, build)
    safe_stderr = redact_paths(final_build.stderr, source_root, build)
    (out / "build-provenance.txt").write_text(safe_stdout+"\n--- STDERR ---\n"+safe_stderr+
        "\n--- FILE API ---\n"+json.dumps(safe_provenance,indent=2,ensure_ascii=False)+"\n", encoding="utf-8")
    (out / "final-build-command.txt").write_text(redact_paths(subprocess.list2cmdline(final_build_command),source_root,build)+"\n", encoding="utf-8")
    command = [str(args.exe.resolve()), "--repetitions", str(args.repetitions), "--warmups", str(args.warmups)]
    before = collector_common.machine_snapshot()
    executable_hash = hashlib.sha256(args.exe.read_bytes()).hexdigest()
    aborted = False
    try:
        process = subprocess.run(command, text=True, capture_output=True, check=False, timeout=300)
        return_code, stdout, stderr = process.returncode, process.stdout, process.stderr
    except subprocess.TimeoutExpired as error:
        aborted = True
        return_code = None
        stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
        stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else (error.stderr or "")
    if hashlib.sha256(args.exe.read_bytes()).hexdigest() != executable_hash:
        raise SystemExit("measurement executable changed while collection was running")
    clean_tracked()
    after = collector_common.machine_snapshot()
    machine_load = collector_common.public_load(copy.deepcopy(before),copy.deepcopy(after))
    (out / "raw-driver-output.csv").write_text(stdout, encoding="utf-8")
    (out / "process-stderr.txt").write_text(stderr, encoding="utf-8")
    (out / "measurement-command.txt").write_text(redact_paths(subprocess.list2cmdline(command),source_root,build) + "\n", encoding="utf-8")
    concurrent_note = args.concurrent_work.read_text(encoding="utf-8", errors="replace").strip()
    profile_note = args.profile_evidence.read_text(encoding="utf-8", errors="replace").strip()
    if not concurrent_note or not profile_note:
        raise SystemExit("concurrent-work and separate profile evidence notes must be nonempty")
    (out / "concurrent-work.txt").write_text(concurrent_note+"\n", encoding="utf-8")
    (out / "profile-evidence.txt").write_text(profile_note+"\n", encoding="utf-8")
    trials: list[dict] = []
    parse_error = None
    try:
        reader = csv.DictReader(stdout.splitlines())
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("unexpected driver CSV header")
        for raw in reader:
            row = {key: raw[key] for key in FIELDS}
            for key in ("repetition", *PHASES, "lp_calls", "lp_results", "lp_optimal", "lp_bounds", "lp_supported_bounds",
                        "inequalities", "equalities", "vertices", "oracle_checks"):
                row[key] = int(row[key])
                if row[key] < 0:
                    raise ValueError(f"negative value in {key}")
            if row["oracle_passed"] not in ("true", "false"):
                raise ValueError("noncanonical oracle_passed boolean")
            row["oracle_passed"] = row["oracle_passed"] == "true"
            row["vertices_json"] = json.loads(row["vertices_json"])
            trials.append(row)
        expected = {(case, r) for case in SCENARIOS for r in range(args.repetitions)}
        actual = {(row["scenario"], row["repetition"]) for row in trials}
        if actual != expected or len(actual) != len(trials):
            raise ValueError("missing, duplicate, or unexpected scenario repetitions")
    except (ValueError, KeyError, csv.Error) as error:
        parse_error = str(error)
    if parse_error:
        trials = []
    for row in trials:
        expected_case = EXPECTED.get(row["scenario"])
        if expected_case is None:
            row["status"] = "unexpected_scenario"
            continue
        row["scenario_sha256"] = sha256_bytes(json.dumps(expected_case,sort_keys=True,separators=(",", ":")).encode())
        row["input_sha256"] = sha256_bytes(json.dumps(expected_case["inputs"],sort_keys=True,separators=(",", ":")).encode())
        if "vertices" in expected_case:
            points = row["vertices_json"]
            expected_points = expected_case["vertices"]
            if not vertices_match_expected(points, expected_points):
                row["status"] = "oracle_failed"
                row["oracle_passed"] = False
        if row["scenario"] == "essential_rows_highs" and not (
            row["reduction_status"]=="incomplete" and row["lp_calls"]==3 and row["lp_bounds"]==0 and
            row["lp_supported_bounds"]==0 and row["inequalities"]==3 and row["equalities"]==1
        ):
            row["status"] = "oracle_failed"
            row["oracle_passed"] = False
    all_passed = return_code == 0 and not aborted and parse_error is None and len(trials) == args.repetitions * len(SCENARIOS) and all(
        row["status"] == "passed" and row["oracle_passed"] for row in trials)
    expected_trial_count = args.repetitions * len(SCENARIOS)
    failed_trial_count = sum(not (row["status"] == "passed" and row["oracle_passed"]) for row in trials)
    total_failure_count = expected_trial_count - len(trials) + failed_trial_count
    payload = {
        "schema": SCHEMA, "report_id": None,
        "algorithm": {"id": "GEO-04", "api": "CSL public polyhedral intersection and halfspace-reduction APIs",
                      "source_commit": args.source_commit, "harness_commit": args.harness_commit},
        "inputs": {"scenario_catalog_version": CATALOG_VERSION,
                   "scenario_catalog_sha256": sha256_bytes(json.dumps(EXPECTED,sort_keys=True,separators=(",", ":")).encode()),
                   "executable_sha256": executable_hash,
                   "executable_name": args.exe.name},
        "drivers": {"converter": {"id": "csl.conversion.qhull", "version": "1.0.0+qhull.8.0.2"},
                    "lp_backend": {"id": "csl.lp.highs", "version": "1.0.0+highs.1.11.0"}},
        "collection": {"state": "complete" if all_passed else "failed", "process_return_code": return_code,
                       "aborted_or_timed_out": aborted, "parse_error": parse_error, "expected_trials": expected_trial_count,
                       "actual_trials": len(trials), "failures": total_failure_count, "measured_repetitions": args.repetitions,
                       "warmups_per_scenario": args.warmups, "order": "forward on even repetitions, reverse on odd repetitions",
                       "fresh_input_workspace_and_provider_per_trial": True,
                       "timings": "steady-clock nanoseconds; phase intervals as named in driver CSV",
                       "seed": {"value": None, "reason": "the implementations have no user-configurable random seed"}},
        "environment": {"os": platform.platform(), "architecture": platform.machine(), "cpu_model": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER"),
                        "logical_cpu_count": os.cpu_count(), "python": platform.python_version(),
                        "resources": {"total_threads": 1, "outer_workers": 1, "threads_per_worker": 1,
                                      "memory_bytes": {"value": None, "reason": "no memory limit requested"}},
                        "native_threads_requested": 1, "outer_workers": 1, "threads_per_worker": 1,
                        "native_threads_observed": {"value": None, "reason": "not sampled by the phase-1 harness"},
                        "per_trial_peak_memory": {"value": None, "reason": "not observed by the phase-1 harness"},
                        "per_trial_cpu": {"value": None, "reason": "not observed by the phase-1 harness"},
                        "machine_load": machine_load,
                        "machine_observations": {"before": {key:value for key,value in before.items() if key!="processes"},
                                                 "after": {key:value for key,value in after.items() if key!="processes"}},
                        "physical_memory_before_bytes": before.get("ram_bytes"),
                        "physical_memory_after_bytes": after.get("ram_bytes"),
                        "load_percent_before": before.get("load_percent"),
                        "load_percent_after": after.get("load_percent"),
                        "compiler_and_release_flags": "see build-provenance.json and build-provenance.txt"},
        "tolerances": {"numerical_policy": {"absolute": 1e-8, "relative": 1e-8},
                       "analytic_output_oracle": {"absolute": 1e-7, "relative": 0.0},
                       "arithmetic": "binary64"},
        "expected": EXPECTED,
        "evidence": {"scope": "numerical binary64 fixture checks; no exact validated geometry claim",
                     "limiter_profile": {"file": "profile-evidence.txt", "timing_trials_profiled": False},
                     "essential_row_result": "HiGHS currently returns no supported objective bounds; production reduction must remain incomplete and retain all rows.",
                     "fixed_bound_unit_fixture_is_benchmark_backend": False,
                     "limitations": ["small analytic fixtures only", "no competitor or speedup claim", "no application-scale or scalability claim",
                                     "LP query internal phase timings and OS-observed thread counts unavailable"]},
        "trials": trials, "summary": summarize(trials, all_passed),
    }
    raw_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    digest = hashlib.sha256(raw_payload).hexdigest()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_id = f"geo04-{stamp}-{digest[:12]}"
    payload["report_id"] = report_id
    payload["payload_sha256"] = digest
    payload["payload_hash_scope"] = "canonical JSON payload excluding report_id and payload_sha256"
    (out / "records.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    (out / "collection-status.json").write_text(json.dumps({"schema":"csl.geo04-collection-status/1",
        "state":payload["collection"]["state"],"return_code":return_code,"aborted_or_timed_out":aborted,
        "parse_error":parse_error,"expected_trials":payload["collection"]["expected_trials"],
        "actual_trials":payload["collection"]["actual_trials"],"failures":payload["collection"]["failures"]},
        indent=2,sort_keys=True)+"\n",encoding="utf-8")
    (out / "raw-events.jsonl").write_text("".join(json.dumps(row, sort_keys=True, allow_nan=False)+"\n" for row in trials), encoding="utf-8")
    (out / "scenarios.json").write_text(json.dumps(EXPECTED, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    (out / "environment.json").write_text(json.dumps(payload["environment"], indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(report_id)
    return 0 if all_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
