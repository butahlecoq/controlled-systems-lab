"""Admit a frozen finite-feedback driver run into saved, versioned records.

This command reads an already completed collection. It never runs the driver.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import statistics
import subprocess

SOURCE = "6602f0f88a8ef2071edefbbd913f7c4bbb6201df"
SCHEMA = "csl.finite-feedback-records/1"
FIELDS = ("purpose", "scenario", "repetition", "status", "initial_winning",
          "initial_actions", "branch_actions", "elapsed_ns", "provider_id",
          "provider_version", "detail")
CASES = {
    "clipping": ("0", "", ""),
    "branching": ("1", "0", "1:0|2:1"),
    "empty-action": ("0", "", ""),
    "nominal": ("1", "0", ""),
}
RAW = ("measure.stdout.csv", "measure.stderr.txt", "smoke.stdout.csv",
       "smoke.stderr.txt", "host-pre.json", "host-post.json", "process-capture.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    require(isinstance(value, dict), "JSON object required: " + path.name)
    return value


def rows(content: bytes, purpose: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
    require(reader.fieldnames == list(FIELDS), "driver CSV header differs")
    result = list(reader)
    count = 4 if purpose == "smoke" else 32
    require(len(result) == count, "driver emitted incomplete row count")
    expected = [("smoke", case, 0) for case in CASES] if purpose == "smoke" else (
        [("warmup", case, 0) for case in CASES] +
        [("trial", list(CASES)[(index + repetition) % 4], repetition)
         for repetition in range(7) for index in range(4)])
    for row, (phase, case, repetition) in zip(result, expected):
        require(None not in row and (row["purpose"], row["scenario"], row["repetition"]) ==
                (phase, case, str(repetition)), "driver order or row differs")
        require(row["status"] == "passed" and row["detail"] == "" and
                (row["initial_winning"], row["initial_actions"], row["branch_actions"]) == CASES[case] and
                row["provider_id"] == "csl.reachability.finite-feedback-table" and
                row["provider_version"] == "1.0.0" and
                re.fullmatch(r"\d+", row["elapsed_ns"]) is not None,
                "literal output, registered identity, status, or timing differs")
    return result


def summarize(measured: list[dict]) -> list[dict]:
    return [{"scenario": case, "attempts": 7, "matches": 7, "failures": 0,
             "median_ns": statistics.median([int(row["elapsed_ns"]) for row in measured
                                           if row["scenario"] == case]),
             "min_ns": min(int(row["elapsed_ns"]) for row in measured if row["scenario"] == case),
             "max_ns": max(int(row["elapsed_ns"]) for row in measured if row["scenario"] == case)}
            for case in CASES]


def frozen_file(root: Path, relative: str) -> bytes:
    result = subprocess.run(["git", "show", f"{SOURCE}:{relative}"], cwd=root,
                            capture_output=True, check=True)
    data = result.stdout
    require((root / relative).read_bytes() == data, "frozen source differs: " + relative)
    return data


def graph(build: Path) -> dict:
    reply = build / ".cmake/api/v1/reply"
    indexes = list(reply.glob("index-*.json"))
    require(len(indexes) == 1, "single CMake File API index required")
    index = read_json(indexes[0])
    model = read_json(reply / index["reply"]["codemodel-v2"]["jsonFile"])
    config = next(item for item in model["configurations"] if item["name"] == "Release")
    targets = {item["name"]: read_json(reply / item["jsonFile"]) for item in config["targets"]}
    require("csl_finite_feedback_report" in targets, "report target missing from graph")
    names = sorted(targets)
    selected = {}
    for name in names:
        if name.startswith("csl_") or name == "ZERO_CHECK":
            target = targets[name]
            selected[name] = {
                "type": target["type"],
                "dependencies": sorted(dep["id"].split("::", 1)[0] for dep in target.get("dependencies", [])),
                "compile_groups": [{"language": group.get("language"),
                                    "standard": group.get("languageStandard", {}).get("standard"),
                                    "fragments": [fragment["fragment"] for fragment in group.get("compileCommandFragments", [])],
                                    "defines": [value["define"] for value in group.get("defines", [])]}
                                   for group in target.get("compileGroups", [])],
                "artifacts": [Path(item["path"]).name for item in target.get("artifacts", [])],
            }
    report = selected["csl_finite_feedback_report"]
    groups = report["compile_groups"]
    require(any(group["language"] == "CXX" and group["standard"] == "20" and
                "NDEBUG" in group["defines"] and
                any("/O2" in fragment for fragment in group["fragments"])
                for group in groups), "Release C++20/NDEBUG/O2 graph required")
    require("csl_finite_feedback_port" in report["dependencies"] and
            "csl_finite_feedback" in report["dependencies"] and
            "csl_finite_feedback_report.exe" in report["artifacts"],
            "registered report dependency graph differs")
    return {"schema": "csl.finite-feedback-build-graph/1",
            "generator": {"source": "SOURCE_ROOT", "build": "BUILD_ROOT"},
            "configuration": "Release", "targets": selected}


def collect(root: Path, build: Path, collection: Path, out: Path) -> Path:
    require(not out.exists(), "refusing to overwrite a saved bundle")
    require(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip() == SOURCE,
            "collection worktree has different HEAD")
    # Reporting scripts may be added later. The built source/harness bytes stay fixed.
    checked = {name: sha(frozen_file(root, name)) for name in (
        "benchmarks/reporting/finite_feedback/driver.cpp",
        "src/reachability/finite_feedback.cpp",
        "src/reachability/finite_feedback_port.cpp",
        "include/csl/reachability/finite_feedback_port.hpp",
        "cmake/OptionalReports.cmake")}
    capture = read_json(collection / "process-capture.json")
    require(capture["source_commit"] == SOURCE and capture["smoke_exit"] == 0 and
            capture["measure_exit"] == 0 and capture["driver_sha256"] ==
            checked["benchmarks/reporting/finite_feedback/driver.cpp"],
            "capture exit or source identity differs")
    executable = build / "Release/csl_finite_feedback_report.exe"
    require(sha(executable.read_bytes()) == capture["executable_sha256"],
            "measured executable differs")
    require(all((collection / name).is_file() for name in RAW), "raw collection incomplete")
    require((collection / "smoke.stderr.txt").read_bytes() == b"" and
            (collection / "measure.stderr.txt").read_bytes() == b"", "driver stderr nonempty")
    smoke = rows((collection / "smoke.stdout.csv").read_bytes(), "smoke")
    attempts = rows((collection / "measure.stdout.csv").read_bytes(), "measure")
    require(Counter(row["scenario"] for row in attempts if row["purpose"] == "trial") ==
            {case: 7 for case in CASES}, "measured fixture count differs")
    build_graph = graph(build)
    cache = (build / "CMakeCache.txt").read_text(encoding="utf-8", errors="replace")
    for token in ("BUILD_TESTING:BOOL=OFF", "CSL_BUILD_FINITE_FEEDBACK_REPORT:BOOL=ON",
                  "CSL_ENABLE_HIGHS:BOOL=OFF", "CSL_ENABLE_QHULL:BOOL=OFF",
                  "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022"):
        require(token in cache, "build setting differs: " + token)
    build_log = (build / "release-build.raw.log").read_text(encoding="utf-8", errors="replace")
    require("0" in build_log and "/std:c++20" in build_log and "/D NDEBUG" in build_log and
            "csl_finite_feedback_report.exe" in build_log, "verbose Release build evidence incomplete")
    # Keep raw host/process observations and sanitized build evidence. Do not copy private paths.
    source_path = str(root).replace("\\", "/")
    build_path = str(build).replace("\\", "/")
    sanitized = build_log.replace(str(root), "SOURCE_ROOT").replace(str(build), "BUILD_ROOT")
    sanitized = sanitized.replace(source_path, "SOURCE_ROOT").replace(build_path, "BUILD_ROOT")
    pre, post = (read_json(collection / name) for name in ("host-pre.json", "host-post.json"))
    require(pre["observed_utc"] <= capture["measure_start_utc"] <=
            capture["measure_end_utc"] <= post["observed_utc"], "host time order differs")
    record = {"schema": SCHEMA, "source_commit": SOURCE, "harness_commit": SOURCE,
              "source_sha256": checked, "executable_sha256": capture["executable_sha256"],
              "build_graph_sha256": sha(encoded(build_graph)),
              "raw_csv_sha256": sha((collection / "measure.stdout.csv").read_bytes()),
              "collection_start_utc": capture["measure_start_utc"],
              "collection_end_utc": capture["measure_end_utc"],
              "environment": {"host_pre": pre, "host_post": post,
                              "compiler": "MSVC 19.44.35215.0", "configuration": "Release",
                              "requested_outer_workers": 1, "actual_outer_workers": 1,
                              "requested_native_threads": 1, "observed_native_threads": None,
                              "native_thread_unavailable_reason": "driver does not observe OS native thread count",
                              "arithmetic": "finite integer table indices and Boolean policy; steady-clock nanoseconds",
                              "reuse": "one process; fresh registry, prepared plan, and workspace per call",
                              "warmup": "one excluded call per fixture; process/cache state may be warm",
                              "order": "seven round-robin repetitions with rotating first fixture"},
              "timing": {"interval": "before registry construction through registered execution, full-policy reference comparison, and literal oracle; excludes fixture construction, destruction, CSV serialization, and process startup",
                         "clock": "std::chrono::steady_clock", "unit": "ns",
                         "warmups": 4, "measured_repetitions_per_fixture": 7,
                         "internal_phases": None, "native_only_time": None,
                         "unavailable_reason": "frozen public driver exposes only the whole verified call interval"},
              "fixture_oracle": {name: {"initial_winning": result[0],
                                        "initial_actions": result[1], "branch_actions": result[2]}
                                 for name, result in CASES.items()},
              "work": {"smoke_calls": len(smoke), "warmup_calls": 4,
                       "measured_registered_calls": 28, "matched": 28,
                       "failed": 0, "unsupported": 0, "cancelled": 0, "missing": 0},
              "trials": attempts, "summary": summarize([row for row in attempts
                                                         if row["purpose"] == "trial"]),
              "interpretation": "Inconclusive exploratory single-adapter timings; no competitor, speedup, source-mapped limiter, continuous-state or physical-model claim."}
    record["payload_sha256"] = sha(encoded(record))
    record["report_id"] = "finite-feedback-" + record["payload_sha256"][:16]
    out.mkdir(parents=True)
    for name in RAW:
        shutil.copyfile(collection / name, out / name)
    (out / "build-graph.json").write_bytes(encoded(build_graph))
    (out / "release-build.log").write_text(sanitized, encoding="utf-8")
    (out / "records.json").write_bytes(encoded(record))
    (out / "trials.jsonl").write_bytes(b"".join(encoded(row) for row in attempts))
    (out / "manifest.json").write_bytes(encoded({
        "schema": "csl.finite-feedback-source-manifest/1", "report_id": record["report_id"],
        "files": {path.name: sha(path.read_bytes()) for path in sorted(out.iterdir())}}))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--collection", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(collect(*(path.resolve() for path in (args.root, args.build, args.collection, args.out))))


if __name__ == "__main__":
    main()
