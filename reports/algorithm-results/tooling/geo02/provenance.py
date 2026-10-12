"""Verify that GEO-02 timings came from the reviewed clean Release target."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

HARNESS_PATHS = {
    "CMakeLists.txt",
    "reports/algorithm-results/tooling/geo02/README.md",
    "reports/algorithm-results/tooling/geo02/affine_sum_driver.cpp",
    "reports/algorithm-results/tooling/geo02/collect.py",
    "reports/algorithm-results/tooling/geo02/provenance.py",
    "reports/algorithm-results/tooling/geo02/render.py",
    "reports/algorithm-results/tooling/geo02/test_report_tools.py",
    "scripts/reports/geo02_registered_reports.py",
    "scripts/reports/report_data.py",
    "scripts/reports/site.py",
    "tests/reporting/test_geo02_publication.py",
}

CMAKE_CONFLICT = """<<<<<<< HEAD
install(FILES include/csl/geometry/polyhedral_intersection.hpp DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/csl/geometry)
install(FILES docs/contracts/hull-reduction.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)
install(FILES docs/contracts/polyhedral-intersection.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)
=======
install(FILES include/csl/geometry/affine_sum.hpp DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/csl/geometry)
install(FILES docs/contracts/hull-reduction.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)
install(FILES docs/contracts/affine-sum-operations.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)
>>>>>>> e4d6c1e (feat(geometry): implement affine images and Minkowski sums)"""
CMAKE_RESOLVED = """install(FILES include/csl/geometry/polyhedral_intersection.hpp DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/csl/geometry)
install(FILES docs/contracts/polyhedral-intersection.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)
install(FILES include/csl/geometry/affine_sum.hpp DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/csl/geometry)
install(FILES docs/contracts/hull-reduction.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)
install(FILES docs/contracts/affine-sum-operations.md DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/CSL/contracts)"""
GEO04_OPTION = 'option(CSL_BUILD_GEO04_REPORT "Build the GEO-04 intersection/reduction report driver" OFF)'
GEO02_OPTION = 'option(CSL_BUILD_GEO02_REPORT "Build the GEO-02 affine/sum report driver" OFF)'
GEO04_TARGET = """if(CSL_BUILD_GEO04_REPORT)
  add_executable(csl_geo04_intersection_report reports/algorithm-results/tooling/geo04/polyhedral_intersection_driver.cpp)
  target_link_libraries(csl_geo04_intersection_report PRIVATE CSL::polyhedral CSL::qhull_conversion CSL::highs_lp)
endif()"""
GEO02_TARGET = """if(CSL_BUILD_GEO02_REPORT)
  add_executable(csl_geo02_affine_sum_report reports/algorithm-results/tooling/geo02/affine_sum_driver.cpp)
  target_compile_features(csl_geo02_affine_sum_report PRIVATE cxx_std_20)
  target_link_libraries(csl_geo02_affine_sum_report PRIVATE CSL::affine_sum CSL::hull CSL::highs_lp CSL::qhull_conversion CSL::phase_one)
endif()"""


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8").strip()


def require_clean_tracked_tree() -> None:
    if git("status", "--porcelain=v1", "--untracked-files=no"):
        raise ValueError("tracked source tree is dirty")


def validate_harness_paths(changed_paths: list[str]) -> None:
    unexpected = sorted(set(changed_paths) - HARNESS_PATHS)
    if unexpected:
        raise ValueError(f"source-to-harness changes exceed the report-tooling allowlist: {unexpected}")


def validate_source_delta(source_commit: str, harness_commit: str) -> list[str]:
    if git("rev-parse", "HEAD") != harness_commit:
        raise ValueError("harness commit does not match checked out HEAD")
    subprocess.run(["git", "merge-base", "--is-ancestor", source_commit, harness_commit], check=True)
    changed = git("diff", "--name-only", source_commit, harness_commit).splitlines()
    validate_harness_paths(changed)
    return changed


def expected_harness_cmake(source_text: str) -> str:
    if source_text.count(CMAKE_CONFLICT) != 1 or source_text.count(GEO04_OPTION) != 1 or source_text.count(GEO04_TARGET) != 1:
        raise ValueError("source CMake file lacks unique GEO-02 merge-resolution anchors")
    expected = source_text.replace(CMAKE_CONFLICT, CMAKE_RESOLVED, 1)
    expected = expected.replace(GEO04_OPTION, GEO04_OPTION + "\n" + GEO02_OPTION, 1)
    expected = expected.replace(GEO04_TARGET, GEO04_TARGET + "\n" + GEO02_TARGET, 1)
    return expected


def validate_harness_cmake(source_text: str, harness_text: str) -> None:
    if harness_text != expected_harness_cmake(source_text):
        raise ValueError("CMakeLists.txt differs beyond exact merge resolution and GEO-02 report target insertion")


def validate_cmake_delta(source_commit: str, harness_commit: str) -> None:
    source = subprocess.check_output(["git", "show", f"{source_commit}:CMakeLists.txt"], text=True, encoding="utf-8")
    harness = subprocess.check_output(["git", "show", f"{harness_commit}:CMakeLists.txt"], text=True, encoding="utf-8")
    validate_harness_cmake(source, harness)


def redact(value, source_root: Path, build_root: Path):
    replacements = [(str(source_root), "SOURCE_ROOT"), (str(build_root), "BUILD_ROOT"), (str(Path.home()), "USER_HOME")]
    if isinstance(value, str):
        for actual, token in replacements:
            value = value.replace(actual, token).replace(actual.replace("\\", "/"), token)
        return value
    if isinstance(value, list):
        return [redact(item, source_root, build_root) for item in value]
    if isinstance(value, dict):
        return {key: redact(item, source_root, build_root) for key, item in value.items()}
    return value


def _file_api(build: Path) -> tuple[dict, dict, dict, dict]:
    reply = build / ".cmake" / "api" / "v1" / "reply"
    indices = sorted(reply.glob("index-*.json"))
    if not indices:
        raise ValueError("CMake File API reply missing; query codemodel-v2 and toolchains-v1 before configuring")
    index = json.loads(indices[-1].read_text(encoding="utf-8"))

    def load(filename: str) -> dict:
        return json.loads((reply / filename).read_text(encoding="utf-8"))

    codemodel = load(index["reply"]["codemodel-v2"]["jsonFile"])
    toolchains = load(index["reply"]["toolchains-v1"]["jsonFile"])
    configurations = [row for row in codemodel["configurations"] if row["name"] == "Release"]
    if len(configurations) != 1:
        raise ValueError("actual Release configuration missing from CMake File API")
    targets = {row["id"]: load(row["jsonFile"]) for row in configurations[0]["targets"]}
    return index, codemodel, targets, toolchains


def _verified_build_graph(build: Path, exe: Path, source_commit: str, harness_commit: str) -> dict:
    source_root = Path(git("rev-parse", "--show-toplevel")).resolve()
    source_tree = git("rev-parse", f"{source_commit}^{{tree}}")
    harness_tree = git("rev-parse", f"{harness_commit}^{{tree}}")
    changed_paths = validate_source_delta(source_commit, harness_commit)
    validate_cmake_delta(source_commit, harness_commit)

    index, codemodel, targets, toolchains = _file_api(build)
    paths = codemodel["paths"]
    if not Path(paths["source"]).samefile(source_root) or not Path(paths["build"]).samefile(build):
        raise ValueError("CMake File API source/build paths do not match this collection")
    roots = [key for key, target in targets.items() if target.get("name") == "csl_geo02_affine_sum_report"]
    if len(roots) != 1:
        raise ValueError("GEO-02 report target missing from Release codemodel")
    selected: dict[str, dict] = {}

    def visit(key: str) -> None:
        if key in selected:
            return
        target = targets[key]
        selected[key] = {field: target[field] for field in ("name", "type", "compileGroups", "link", "archive", "artifacts") if field in target}
        for dependency in target.get("dependencies", []):
            visit(dependency["id"])

    visit(roots[0])
    root = targets[roots[0]]
    artifacts = [build / row["path"] for row in root.get("artifacts", []) if Path(row["path"]).name == exe.name]
    if len(artifacts) != 1 or not artifacts[0].is_file() or not artifacts[0].samefile(exe):
        raise ValueError("provided executable is not the configured GEO-02 Release target artifact")
    groups = [row for row in root.get("compileGroups", []) if row.get("language") == "CXX"]
    if len(groups) != 1 or groups[0].get("languageStandard", {}).get("standard") != "20":
        raise ValueError("GEO-02 driver must have exactly one C++20 Release compile group")
    group = groups[0]
    flags = " ".join(row.get("fragment", "") for row in group.get("compileCommandFragments", []))
    definitions = " ".join(row.get("define", "") for row in group.get("defines", []))
    if not any(token in (flags + " " + definitions) for token in ("/DNDEBUG", "-DNDEBUG", "NDEBUG")):
        raise ValueError("Release/NDEBUG definition missing from actual report driver compile group")
    cxx = [row for row in toolchains["toolchains"] if row.get("language") == "CXX"]
    if len(cxx) != 1:
        raise ValueError("C++ compiler identity missing from CMake File API")
    names = {row["name"] for row in selected.values()}
    required = {"csl_geo02_affine_sum_report", "csl_affine_sum", "csl_hull", "csl_highs_lp", "csl_qhull_conversion", "csl_phase_one"}
    if not required <= names:
        raise ValueError("Release report target dependency graph is incomplete")
    pin_paths = ("cmake/HighsDependencies.cmake", "cmake/QhullDependencies.cmake")
    dependency_pins = {name: hashlib.sha256((source_root / name).read_bytes()).hexdigest() for name in pin_paths}
    cmake = index.get("cmake", {})
    return {
        "source_commit": source_commit, "harness_commit": harness_commit, "tracked_clean": True,
        "tracked_tree_binding": {"source_tree_oid": source_tree, "harness_tree_oid": harness_tree,
                                  "scope": "complete tracked repository tree", "allowed_harness_paths": sorted(HARNESS_PATHS),
                                  "actual_changed_paths": changed_paths},
        "configuration": "Release", "cxx_standard": "20", "release_ndebug_verified": True,
        "cmake": {"version": cmake.get("version", {}), "generator": cmake.get("generator", {}).get("name")},
        "compiler": cxx[0], "driver_compile_group": group, "dependency_targets": sorted(names),
        "dependency_pin_file_sha256": dependency_pins, "file_api_paths": paths,
        "executable": {"path": str(exe), "sha256": hashlib.sha256(exe.read_bytes()).hexdigest()},
        "targets": list(selected.values()),
    }


def final_build_provenance(build: Path, exe: Path, source_commit: str, harness_commit: str) -> tuple[dict, str, str, str]:
    require_clean_tracked_tree()
    changed_paths = validate_source_delta(source_commit, harness_commit)
    validate_cmake_delta(source_commit, harness_commit)
    index, _, _, _ = _file_api(build)
    cmake = index["cmake"]["paths"]["cmake"]
    command = [cmake, "--build", str(build), "--config", "Release", "--target", "csl_geo02_affine_sum_report", "--parallel", "4", "--verbose"]
    process = subprocess.run(command, text=True, capture_output=True, check=False, timeout=1200)
    if process.returncode:
        raise RuntimeError(f"final Release build failed ({process.returncode})\n{process.stderr[-4000:]}")
    require_clean_tracked_tree()
    graph = _verified_build_graph(build, exe, source_commit, harness_commit)
    graph["tracked_tree_binding"]["actual_changed_paths"] = changed_paths
    graph["final_build"] = {"command": command, "return_code": process.returncode,
                            "stdout_sha256": hashlib.sha256(process.stdout.encode()).hexdigest(),
                            "stderr_sha256": hashlib.sha256(process.stderr.encode()).hexdigest()}
    source_root = Path(git("rev-parse", "--show-toplevel")).resolve()
    safe = redact(graph, source_root, build)
    text = json.dumps(safe, sort_keys=True, indent=2, ensure_ascii=False) + "\n--- FINAL RELEASE BUILD STDOUT ---\n" + redact(process.stdout, source_root, build) + "\n--- FINAL RELEASE BUILD STDERR ---\n" + redact(process.stderr, source_root, build)
    return safe, text, process.stdout, process.stderr
