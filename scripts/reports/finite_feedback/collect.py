"""Admit a captured finite-feedback Release run; never execute numerical work."""
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

NUMERICAL_SOURCE = "6602f0f88a8ef2071edefbbd913f7c4bbb6201df"
SCHEMA = "csl.finite-feedback-records/2"
FIELDS = ("purpose", "scenario", "repetition", "status", "initial_winning",
          "initial_actions", "branch_actions", "elapsed_ns", "provider_id",
          "provider_version", "detail")
CASES = {
    "clipping": ("0", "", ""),
    "branching": ("1", "0", "1:0|2:1"),
    "empty-action": ("0", "", ""),
    "nominal": ("1", "0", ""),
}
RAW = ("capture-status.json", "prebuild-receipt.json", "postrun-receipt.json",
       "configure.stdout.log", "configure.stderr.log", "release-build.stdout.log",
       "release-build.stderr.log", "smoke.stdout.log", "smoke.stderr.log",
       "measure.stdout.log", "measure.stderr.log", "host-pre.json", "host-post.json")
EMPTY_SHA = hashlib.sha256(b"").hexdigest()


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
                "checked witness cells, registered identity, status, or timing differs")
    return result


def summarize(measured: list[dict]) -> list[dict]:
    return [{"scenario": case, "attempts": 7, "matches": 7, "failures": 0,
             "median_ns": statistics.median([int(row["elapsed_ns"]) for row in measured
                                           if row["scenario"] == case]),
             "min_ns": min(int(row["elapsed_ns"]) for row in measured if row["scenario"] == case),
             "max_ns": max(int(row["elapsed_ns"]) for row in measured if row["scenario"] == case)}
            for case in CASES]


def clean_receipts(collection: Path, capture: dict) -> tuple[dict, dict]:
    pre = read_json(collection / "prebuild-receipt.json")
    post = read_json(collection / "postrun-receipt.json")
    require(capture["state"] == "captured" and capture["failure"] is None and
            capture["return_codes"] == {"configure": 0, "build": 0, "smoke": 0, "measure": 0},
            "capture did not complete cleanly")
    require(pre == capture["prebuild"] and post == capture["postrun"] and
            pre["schema"] == post["schema"] == "csl.finite-feedback-clean-tree-receipt/1" and
            pre["status_sha256"] == post["status_sha256"] == EMPTY_SHA and
            pre["commit"] == post["commit"] == capture["source_commit"] and
            pre["tree"] == post["tree"] == capture["source_tree"] and
            pre["tracked_count"] == post["tracked_count"] and
            pre["observed_utc"] <= capture["configure_start_utc"] <= capture["build_start_utc"] <=
            capture["build_end_utc"] <= capture["measure_start_utc"] <=
            capture["measure_end_utc"] <= post["observed_utc"],
            "prebuild/postrun full-tree receipt differs")
    return pre, post


def graph(build: Path, root: Path, tracked: set[str]) -> dict:
    reply = build / ".cmake/api/v1/reply"
    indexes = list(reply.glob("index-*.json"))
    require(len(indexes) == 1, "one File API index required")
    index = read_json(indexes[0])
    model_path = reply / index["reply"]["codemodel-v2"]["jsonFile"]
    model = read_json(model_path)
    require(Path(model["paths"]["source"]).resolve() == root and
            Path(model["paths"]["build"]).resolve() == build,
            "File API graph belongs to another source/build directory")
    config = next(item for item in model["configurations"] if item["name"] == "Release")
    entries = {item["id"]: item for item in config["targets"]}
    report_entries = [item for item in entries.values() if item["name"] == "csl_finite_feedback_report"]
    require(len(report_entries) == 1, "unique registered report target required")
    selected: dict[str, dict] = {}
    raw_hashes = {"index": sha(indexes[0].read_bytes()), "codemodel": sha(model_path.read_bytes())}

    def visit(identifier: str) -> None:
        entry = entries[identifier]
        name = entry["name"]
        if name in selected:
            return
        target_path = reply / entry["jsonFile"]
        target = read_json(target_path)
        raw_hashes[name] = sha(target_path.read_bytes())
        sources = [item["path"].replace("\\", "/") for item in target.get("sources", [])]
        generated = {}
        build_prefix = build.relative_to(root).as_posix() + "/"
        for source in sources:
            require(not Path(source).is_absolute() and ".." not in Path(source).parts,
                    "unsafe linked target source: " + source)
            path = root / source
            if source in tracked:
                require(path.is_file(), "tracked linked source missing: " + source)
            else:
                require(source.startswith(build_prefix) and path.is_file(),
                        "linked target source is outside clean tracked tree/build: " + source)
                generated[source.removeprefix(build_prefix)] = sha(path.read_bytes())
        dependencies = [entries[item["id"]]["name"] for item in target.get("dependencies", [])]
        selected[name] = {
            "type": target["type"], "sources": sources, "generated_source_sha256": generated,
            "dependencies": sorted(dependencies),
            "artifacts": [item["path"].replace("\\", "/") for item in target.get("artifacts", [])],
            "compile_groups": [{"language": group.get("language"),
                                "standard": group.get("languageStandard", {}).get("standard"),
                                "fragments": [fragment["fragment"] for fragment in group.get("compileCommandFragments", [])],
                                "defines": [value["define"] for value in group.get("defines", [])]}
                               for group in target.get("compileGroups", [])],
            "link": [fragment["fragment"] for fragment in target.get("link", {}).get("commandFragments", [])],
            "archive": [fragment["fragment"] for fragment in target.get("archive", {}).get("commandFragments", [])],
        }
        for dependency in target.get("dependencies", []):
            visit(dependency["id"])

    visit(report_entries[0]["id"])
    report = selected["csl_finite_feedback_report"]
    require(report["artifacts"] and report["artifacts"][0] == "Release/csl_finite_feedback_report.exe" and
            report["sources"] == ["benchmarks/reporting/finite_feedback/driver.cpp"] and
            {"csl_finite_feedback", "csl_finite_feedback_port"} <= set(selected),
            "selected executable or linked ownership differs")
    for name, target in selected.items():
        if name == "ZERO_CHECK":
            continue
        require(all(group["language"] == "CXX" and group["standard"] == "20" and
                    ("NDEBUG" in group["defines"] or
                     any("NDEBUG" in fragment for fragment in group["fragments"])) and
                    any("/O2" in fragment for fragment in group["fragments"])
                    for group in target["compile_groups"]),
                "linked target is not Release C++20/NDEBUG/O2: " + name)
    compiler_files = list((build / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    require(len(compiler_files) == 1, "unique compiler owner file required")
    compiler_text = compiler_files[0].read_text(encoding="utf-8", errors="replace")
    version = re.search(r'set\(CMAKE_CXX_COMPILER_VERSION "([^"]+)"\)', compiler_text)
    compiler = re.search(r'set\(CMAKE_CXX_COMPILER "([^"]+)"\)', compiler_text)
    require(version is not None and compiler is not None and
            Path(compiler.group(1)).is_file(), "compiler identity unavailable")
    return {"schema": "csl.finite-feedback-build-graph/2", "source_root": "SOURCE_ROOT",
            "build_root": "BUILD_ROOT", "configuration": "Release",
            "selected_artifact": report["artifacts"][0], "targets": selected,
            "file_api_sha256": raw_hashes,
            "compiler": {"id": "MSVC", "version": version.group(1),
                         "binary": Path(compiler.group(1)).name,
                         "binary_sha256": sha(Path(compiler.group(1)).read_bytes()),
                         "owner_file_sha256": sha(compiler_files[0].read_bytes())}}


def sanitize(content: bytes, root: Path, build: Path) -> bytes:
    value = content.decode("utf-8", errors="replace")
    for original, replacement in ((str(build), "BUILD_ROOT"), (str(root), "SOURCE_ROOT"),
                                  (build.as_posix(), "BUILD_ROOT"), (root.as_posix(), "SOURCE_ROOT")):
        value = value.replace(original, replacement)
    return value.encode()


def collect(root: Path, build: Path, collection: Path, out: Path) -> Path:
    require(not out.exists(), "refusing to overwrite a saved bundle")
    require(all((collection / name).is_file() for name in RAW), "raw collection incomplete")
    capture = read_json(collection / "capture-status.json")
    pre, post = clean_receipts(collection, capture)
    source = capture["source_commit"]
    tree = capture["source_tree"]
    require(re.fullmatch(r"[0-9a-f]{40}", source) is not None and
            subprocess.check_output(["git", "rev-parse", source + "^{tree}"], cwd=root).decode().strip() == tree,
            "source commit/tree mismatch")
    inventory = subprocess.check_output(["git", "ls-tree", "-r", source], cwd=root)
    tracked = {line.split(b"\t", 1)[1].decode() for line in inventory.splitlines()}
    require(len(tracked) == pre["tracked_count"], "tracked source inventory differs")
    require(subprocess.check_output(["git", "show", f"{NUMERICAL_SOURCE}:benchmarks/reporting/finite_feedback/driver.cpp"], cwd=root) ==
            subprocess.check_output(["git", "show", f"{source}:benchmarks/reporting/finite_feedback/driver.cpp"], cwd=root),
            "frozen driver changed")
    executable = build / "Release/csl_finite_feedback_report.exe"
    exe_hash = sha(executable.read_bytes())
    require(capture["executable_sha256_before"] == capture["executable_sha256_after"] == exe_hash,
            "measured executable differs")
    smoke = rows((collection / "smoke.stdout.log").read_bytes(), "smoke")
    attempts = rows((collection / "measure.stdout.log").read_bytes(), "measure")
    require(all((collection / name).read_bytes() == b"" for name in
                ("smoke.stderr.log", "measure.stderr.log")), "driver stderr nonempty")
    require(Counter(row["scenario"] for row in attempts if row["purpose"] == "trial") ==
            {case: 7 for case in CASES}, "measured fixture count differs")
    build_graph = graph(build, root, tracked)
    cache = (build / "CMakeCache.txt").read_text(encoding="utf-8", errors="replace")
    for token in ("BUILD_TESTING:BOOL=OFF", "CSL_BUILD_FINITE_FEEDBACK_REPORT:BOOL=ON",
                  "CSL_ENABLE_HIGHS:BOOL=OFF", "CSL_ENABLE_QHULL:BOOL=OFF",
                  "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022"):
        require(token in cache, "build setting differs: " + token)
    build_log = (collection / "release-build.stdout.log").read_text(encoding="utf-8", errors="replace")
    require("/std:c++20" in build_log and "/D NDEBUG" in build_log and
            "csl_finite_feedback_report.exe" in build_log, "verbose Release build evidence incomplete")
    command = capture["commands"]
    require(command["configure"][1:] == ["-S", str(root), "-B", str(build), "-G",
                                             "Visual Studio 17 2022", "-A", "x64",
                                             "-DCSL_BUILD_FINITE_FEEDBACK_REPORT=ON",
                                             "-DCSL_ENABLE_HIGHS=OFF", "-DCSL_ENABLE_QHULL=OFF",
                                             "-DBUILD_TESTING=OFF"] and
            command["build"][0] == command["configure"][0] and
            command["build"][1:3] == ["--build", str(build)],
            "configure/build command identity differs")
    require(command["measure"] == ["csl_finite_feedback_report.exe", "--measure", "7"] and
            command["smoke"] == ["csl_finite_feedback_report.exe", "--smoke"] and
            command["build"][-7:] == ["--config", "Release", "--target", "csl_finite_feedback_report",
                                       "--parallel", "4", "--verbose"],
            "capture command profile differs")
    record = {"schema": SCHEMA, "source_commit": source, "source_tree": tree,
              "numerical_source_commit": NUMERICAL_SOURCE, "harness_commit": NUMERICAL_SOURCE,
              "prebuild_receipt_sha256": sha((collection / "prebuild-receipt.json").read_bytes()),
              "postrun_receipt_sha256": sha((collection / "postrun-receipt.json").read_bytes()),
              "source_inventory_sha256": sha(inventory), "build_graph_sha256": sha(encoded(build_graph)),
              "executable_sha256": exe_hash, "raw_csv_sha256": sha((collection / "measure.stdout.log").read_bytes()),
              "collection_start_utc": capture["measure_start_utc"],
              "collection_end_utc": capture["measure_end_utc"],
              "environment": {"host_pre": capture["host_pre"], "host_post": capture["host_post"],
                              "compiler": build_graph["compiler"], "configuration": "Release",
                              "requested_outer_workers": 1, "actual_outer_workers": 1,
                              "requested_native_threads": None, "observed_native_threads": None,
                              "native_thread_unavailable_reason": "finite-table adapter has no native solver thread setting; driver does not observe OS thread count",
                              "reuse": "one process; fresh registry, prepared plan, and workspace per call",
                              "warmup": "one excluded call per fixture; process/cache state may be warm",
                              "order": "seven round-robin repetitions with rotating first fixture"},
              "timing": {"interval": "before registry construction through registered execution, all winning flags and selected action-cell checks; excludes fixture construction, destruction, CSV serialization, and process startup",
                         "clock": "std::chrono::steady_clock", "unit": "ns", "warmups": 4,
                         "measured_repetitions_per_fixture": 7, "internal_phases": None,
                         "native_only_time": None,
                         "unavailable_reason": "frozen driver exposes only the whole verified call interval"},
              "oracle_scope": {"winning_flags": "all stage/state entries per fixture",
                               "action_cells": {"clipping": ["stage 0 state 0"],
                                                "branching": ["stage 0 state 0", "stage 1 state 1", "stage 1 state 2"],
                                                "empty-action": ["stage 0 state 0"],
                                                "nominal": ["stage 0 state 0"]},
                               "unchecked": "other admissible-action table entries are not checked by this driver"},
              "fixture_oracle": {name: {"initial_winning": value[0],
                                        "initial_actions": value[1], "branch_actions": value[2]}
                                 for name, value in CASES.items()},
              "work": {"smoke_calls": len(smoke), "warmup_calls": 4,
                       "measured_registered_calls": 28, "matched": 28,
                       "failed": 0, "unsupported": 0, "cancelled": 0, "missing": 0},
              "trials": attempts, "summary": summarize([row for row in attempts
                                                         if row["purpose"] == "trial"]),
              "interpretation": "Inconclusive exploratory single-adapter timings; checked witness cells do not certify the complete action tensor. No comparator, speedup, or source-mapped limiter claim."}
    record["payload_sha256"] = sha(encoded(record))
    record["report_id"] = "finite-feedback-" + record["payload_sha256"][:16]
    out.mkdir(parents=True)
    for name in RAW:
        data = (collection / name).read_bytes()
        if name.endswith(".log") or name == "capture-status.json":
            data = sanitize(data, root, build)
        (out / name).write_bytes(data)
    (out / "source-tree.txt").write_bytes(inventory)
    (out / "build-graph.json").write_bytes(encoded(build_graph))
    (out / "records.json").write_bytes(encoded(record))
    (out / "trials.jsonl").write_bytes(b"".join(encoded(row) for row in attempts))
    (out / "manifest.json").write_bytes(encoded({
        "schema": "csl.finite-feedback-source-manifest/2", "report_id": record["report_id"],
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
