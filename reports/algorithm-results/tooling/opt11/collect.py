"""Source-bound OPT-11 collector. `measure` runs only after fixed-code review."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

if __package__:
    from .oracle import FIXTURES, fixture_digest, require
    from .validate import validate_stream
else:
    from oracle import FIXTURES, fixture_digest, require
    from validate import validate_stream

HERE = Path(__file__).resolve().parent
SOURCE_PATHS = (
    "src/adapters/highs_session.hpp", "src/adapters/lp/highs.cpp",
    "src/geometry/hull/recursive_reducer.cpp", "src/geometry/hull_reducer.cpp",
    "src/geometry/exact_convex_combination.hpp", "include/csl/geometry/hull_reducer.hpp",
    "reports/algorithm-results/tooling/opt11/CMakeLists.txt",
    "reports/algorithm-results/tooling/opt11/recursive_hull_driver.cpp",
    "reports/algorithm-results/tooling/opt11/oracle.py",
    "reports/algorithm-results/tooling/opt11/validate.py",
    "reports/algorithm-results/tooling/opt11/collect.py",
    "reports/algorithm-results/tooling/opt11/build_bundle.py",
)
HARNESS = "reports/algorithm-results/tooling/opt11/recursive_hull_driver.cpp"
TIMING_TRANSLATION_UNITS = (
    "src/geometry/hull/recursive_reducer.cpp",
    "src/geometry/hull_reducer.cpp",
    "src/adapters/lp/highs.cpp",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    return digest(path.read_bytes())


def sanitized_log(raw: str, roots: dict[str, Path]) -> str:
    clean = raw
    for label, path in sorted(roots.items(), key=lambda pair: len(str(pair[1])), reverse=True):
        normalized = str(path).rstrip("\\/").replace("\\", "/")
        pattern = r"[\\/]".join(re.escape(part) for part in normalized.split("/"))
        clean = re.sub(pattern + r"(?=$|[\\/]|[^A-Za-z0-9_.-])", label, clean,
                       flags=re.IGNORECASE)
    require(not re.search(r"(?<![A-Za-z0-9_$])[A-Za-z]:[\\/]", clean),
            "unrecognized absolute path remains in Release log")
    require(not re.search(r'''(?<![A-Za-z0-9_:$])[\\/]{2}[^\\/\s"']+[\\/][^\\/\s"']+''', clean),
            "unrecognized UNC path remains in Release log")
    return clean


def cmd(*args: str) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def source_hashes(root: Path) -> dict:
    return {name: file_hash(root / name) for name in SOURCE_PATHS}


def compiler_identity(build_root: Path, roots: dict[str, Path]) -> tuple[str, str, str, bytes, str]:
    candidates = sorted((build_root / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    identities = []
    for source in candidates:
        raw = source.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        compiler_id = re.search(r'^set\(CMAKE_CXX_COMPILER_ID "([^"]+)"\)', text, re.MULTILINE)
        version = re.search(r'^set\(CMAKE_CXX_COMPILER_VERSION "([^"]+)"\)', text, re.MULTILINE)
        compiler_path = re.search(r'^set\(CMAKE_CXX_COMPILER "([^"]+)"\)', text, re.MULTILINE)
        if compiler_id and version and compiler_path:
            identities.append((compiler_id.group(1), version.group(1), compiler_path.group(1), raw, source))
    require(bool(identities), "generated CMake C++ compiler identity is missing")
    require(len({(item[0], item[1], item[2]) for item in identities}) == 1,
            "generated CMake compiler identity files disagree")
    compiler_id, version, compiler_path, raw, source = identities[0]
    sanitized = sanitized_log(raw.decode("utf-8", errors="replace"), roots).encode("utf-8")
    return compiler_id, version, compiler_path, sanitized, source.relative_to(build_root).as_posix()


def write_utf8_lf(path: Path, text: str) -> bytes:
    """Persist UTF-8 bytes exactly, without Windows text-mode newline conversion."""
    encoded = text.encode("utf-8")
    path.write_bytes(encoded)
    return encoded


def validate_release_build_evidence(raw_log: str, root: Path, build_root: Path,
                                    exe: Path, commit: str, harness_sha256: str) -> None:
    """Require a clean-first compile and link of all timing-relevant sources."""
    lines = raw_log.splitlines()
    clean_positions = [index for index, line in enumerate(lines)
                       if "run clean command:" in line.casefold() and "/t:clean" in line.casefold()]
    require(bool(clean_positions),
            "verbose Release log lacks explicit clean-first MSBuild command evidence")

    def normalized(path: Path) -> str:
        return str(path.resolve()).replace("/", "\\").casefold()

    def is_release_compile(line: str, source: Path) -> bool:
        folded = line.casefold()
        return (
            "cl.exe" in folded and normalized(source) in folded and
            re.search(r"(?:^|\s)/o2(?:\s|$)", line, re.IGNORECASE) is not None and
            re.search(r"(?:^|\s)/std:c\+\+20(?:\s|$)", line, re.IGNORECASE) is not None and
            re.search(r"(?:^|\s)/d\s+ndebug(?:\s|$)", line, re.IGNORECASE) is not None and
            re.search(r'cmake_intdir=.*release', line, re.IGNORECASE) is not None
        )

    for relative in TIMING_TRANSLATION_UNITS:
        source = root / relative
        compile_positions = [index for index, line in enumerate(lines)
                             if is_release_compile(line, source)]
        require(any(clean_index < compile_index for clean_index in clean_positions
                    for compile_index in compile_positions),
                f"clean-first Release compiler evidence missing for {relative}")

    harness_source = root / HARNESS
    harness_commands = [line for index, line in enumerate(lines)
                        if is_release_compile(line, harness_source) and
                        any(clean_index < index for clean_index in clean_positions)]
    require(any(commit in line and harness_sha256 in line for line in harness_commands),
            "Release harness compile does not bind the requested source commit and harness hash")

    expected_exe = normalized(exe)
    link_commands = [line for line in lines
                     if "link.exe" in line.casefold() and expected_exe in line.casefold()]

    def resolved_link_library(argument: str) -> tuple[str, str] | None:
        value = argument.strip('"')
        library_name = Path(value.replace("\\", "/")).name.casefold()
        if library_name not in {"csl_hull.lib", "csl_highs_lp.lib"}:
            return None
        normalized_argument = value.replace("/", "\\")
        if re.match(r"^[A-Za-z]:\\", normalized_argument) or normalized_argument.startswith("\\\\"):
            resolved = normalized_argument.casefold()
        else:
            resolved = normalized(build_root / Path(value.replace("\\", os.sep)))
        return library_name, resolved

    def has_exact_link_inputs(line: str) -> bool:
        arguments = [quoted or unquoted for quoted, unquoted in
                     re.findall(r'"([^"]*)"|(\S+)', line)]
        actual: dict[str, set[str]] = {}
        for argument in arguments:
            library = resolved_link_library(argument)
            if library is not None:
                name, path = library
                actual.setdefault(name, set()).add(path)
        expected = {
            "csl_hull.lib": {normalized(build_root / "csl" / "Release" / "csl_hull.lib")},
            "csl_highs_lp.lib": {normalized(build_root / "csl" / "Release" / "csl_highs_lp.lib")},
        }
        return actual == expected

    require(any(has_exact_link_inputs(line) for line in link_commands),
            "Release link arguments do not resolve to both expected libraries under the verified build root")
    require(any(expected_exe in line.casefold() and "csl_opt11_measure.exe" in line.casefold()
                for line in lines),
            "verbose Release log lacks expected executable build output")


def preflight(exe: Path, root: Path, commit: str, build_log: Path,
              concurrent_note: Path) -> dict:
    root, exe = root.resolve(strict=True), exe.resolve(strict=True)
    build_log, concurrent_note = build_log.resolve(strict=True), concurrent_note.resolve(strict=True)
    require(cmd("git", "-C", str(root), "rev-parse", "HEAD") == commit,
            "checkout HEAD does not match requested full source commit")
    require(not cmd("git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"),
            "source checkout must be clean, including untracked files")
    require(exe.name == "csl_opt11_measure.exe" and exe.parent.name == "Release",
            "expected Release csl_opt11_measure.exe")
    build_root = exe.parent.parent
    cache_path = build_root / "CMakeCache.txt"
    cache = {}
    for line in cache_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" in line and "=" in line and not line.startswith(("#", "//")):
            key, value = line.split(":", 1)[0], line.split("=", 1)[1]
            cache[key] = value
    require(Path(cache.get("CMAKE_HOME_DIRECTORY", "")).resolve() == HERE and
            Path(cache.get("CSL_ROOT", "")).resolve() == root and
            cache.get("CMAKE_GENERATOR") == "Visual Studio 17 2022",
            "build tree does not belong to this source and harness")
    project_root = ET.parse(build_root / "csl_opt11_measure.vcxproj").getroot()
    ns = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
    release_groups = [group for group in project_root.findall("m:ItemDefinitionGroup", ns)
                      if "Release|x64" in group.attrib.get("Condition", "")]
    require(len(release_groups) == 1, "Release x64 project configuration is ambiguous")
    compiler_node = release_groups[0].find("m:ClCompile", ns)
    require(compiler_node is not None, "Release project compiler settings are missing")
    project_flags = {node.tag.rsplit("}", 1)[-1]: node.text for node in compiler_node}
    require(project_flags.get("LanguageStandard") == "stdcpp20" and
            project_flags.get("Optimization") == "MaxSpeed" and
            "NDEBUG" in (project_flags.get("PreprocessorDefinitions") or ""),
            "Release project does not enable C++20, MaxSpeed and NDEBUG")
    description = json.loads(cmd(str(exe), "describe"))
    hashes = source_hashes(root)
    require(description.get("kind") == "describe" and
            description.get("source_commit") == commit and
            description.get("harness_sha256") == hashes[HARNESS] and
            description.get("configuration") == "Release" and description.get("ndebug") is True and
            description.get("cxx_standard", 0) >= 202002 and
            description.get("warmups_per_fixture") == 1 and
            description.get("measured_pairs_per_fixture") == 6,
            "executable identity, Release mode or protocol differs")
    backend_runtime = description.get("backend")
    require(isinstance(backend_runtime, dict) and backend_runtime.get("method") == "csl.lp.highs" and
            backend_runtime.get("version") == "1.0.0+highs.1.11.0",
            "runtime registered HiGHS identity/version differs from the reviewed provider")
    log = build_log.read_text(encoding="utf-8", errors="replace")
    validate_release_build_evidence(log, root, build_root, exe, commit, hashes[HARNESS])
    note = concurrent_note.read_text(encoding="utf-8").strip()
    require(bool(note), "concurrent-work/load note is required")
    release_log = sanitized_log(build_log.read_text(encoding="utf-8", errors="replace"), {
        "$SOURCE_ROOT": root, "$BUILD_ROOT": build_root, "$TEMP_ROOT": Path(tempfile.gettempdir()),
        "$USER_ROOT": Path.home(),
        **{label: Path(value) for label, value in (("$PROGRAM_FILES_X86", os.environ.get("ProgramFiles(x86)")),
                                                   ("$PROGRAM_FILES", os.environ.get("ProgramFiles")),
                                                   ("$WINDOWS_ROOT", os.environ.get("SystemRoot"))) if value},
    })
    compiler_id, compiler_version, compiler_path, compiler_source, compiler_file = compiler_identity(
        build_root, {"$SOURCE_ROOT": root, "$BUILD_ROOT": build_root,
                    "$TEMP_ROOT": Path(tempfile.gettempdir()), "$USER_ROOT": Path.home(),
                    **{label: Path(value) for label, value in (("$PROGRAM_FILES_X86", os.environ.get("ProgramFiles(x86)")),
                                                               ("$PROGRAM_FILES", os.environ.get("ProgramFiles")),
                                                               ("$WINDOWS_ROOT", os.environ.get("SystemRoot"))) if value}})
    return {
        "source_commit": commit, "source_sha256": hashes,
        "fixture_sha256": fixture_digest(), "harness_sha256": hashes[HARNESS],
        "algorithm": {"baseline": {"method": "csl.hull.lp-membership", "version": "1.0.0"},
                      "recursive": {"method": "csl.hull.recursive-split-merge", "version": "1.0.0"}},
        "backend": {"method": backend_runtime["method"],
                    "version": backend_runtime["version"],
                    "adapter_version": backend_runtime["version"].split("+", 1)[0],
                    "native_version": backend_runtime["version"].split("+highs.", 1)[1],
                    "simplex_iteration_limit": None, "configured_threads": 1,
                    "presolve": "off", "parallel": "off",
                    "observed_native_threads": None},
        "executable_sha256": file_hash(exe), "build_log_sha256": file_hash(build_log),
        "sanitized_build_log": release_log,
        "sanitized_build_log_sha256": digest(release_log.encode("utf-8")),
        "compiler_identification_sha256": digest(compiler_source),
        "compiler_identification_source_sha256": digest((build_root / compiler_file).read_bytes()),
        "sanitized_compiler_identification": compiler_source.decode("utf-8"),
        "cmake_cache_sha256": file_hash(cache_path),
        "release_project_sha256": file_hash(build_root / "csl_opt11_measure.vcxproj"),
        "release_project": {"generator": cache.get("CMAKE_GENERATOR"), "configuration": "Release",
                            "language_standard": project_flags["LanguageStandard"],
                            "optimization": project_flags["Optimization"],
                            "preprocessor_definitions": project_flags.get("PreprocessorDefinitions"),
                            "compiler_id": compiler_id,
                            "compiler_version": compiler_version,
                            "compiler_path": compiler_path,
                            "compiler_identification_file": compiler_file,
                            "ndebug": True},
        "description": description,
        "environment": {"os": platform.platform(), "machine": platform.machine(),
                        "logical_processors": os.cpu_count(), "python": sys.version.split()[0],
                        "concurrent_work_note": note, "observed_native_threads": None},
        "protocol": {"warmups_per_fixture": 1, "measured_pairs_per_fixture": 6,
                     "alternation": "recursive-first iff (round + fixture index) is odd",
                     "workspace_policy": "baseline reducer and LP workspace are prepared before each timed call; recursive public run creates its registered child LP workspaces during the timed call; reducer workspace and injected LP workspace are created before timing",
                     "timing_scope": "steady_clock around one public BoundWorkspace<HullReducerPort>::run_with call; excludes fixture parsing, reducer and injected LP workspace creation, independent validation, serialization and rendering; includes recursive child workspace creation and root async scheduling",
                     "recursive_parallel_policy": "ResourcePolicy requests two outer workers and one thread per worker in measurement; smoke does not request parallel execution",
                     "numerical_policy": {"absolute_tolerance": 1e-8, "relative_tolerance": 1e-8},
                     "cancellation": "not requested", "deadline": "not requested",
                     "unavailable": ["LP simplex iterations/internal phase times", "observed native thread count",
                                     "per-node wall times", "CPU time", "peak memory", "source-mapped limiter"],
                     "performance_interpretation": "paired descriptive comparison only; no speedup claim until independent review"},
    }


def collect(args) -> Path:
    metadata = preflight(args.exe, args.source_root, args.source_commit,
                         args.build_log, args.concurrent_work_file)
    output = args.out.resolve()
    require(not output.exists(), "collection output already exists")
    output.mkdir(parents=True)
    reports_path = str(args.source_root.resolve() / "scripts" / "reports")
    if reports_path not in sys.path:
        sys.path.insert(0, reports_path)
    import collector_common as common

    before = common.machine_snapshot()
    timed_out = False
    try:
        proc = subprocess.run([str(args.exe.resolve()), "run", "measurement"],
                              capture_output=True, timeout=args.timeout_seconds)
        raw_out, raw_err, return_code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as error:
        timed_out = True
        raw_out = error.output or b""
        raw_err = error.stderr or b""
        return_code = None
    after = common.machine_snapshot()
    metadata["environment"]["machine_load"] = common.public_load(before, after)
    (output / "raw-stdout.jsonl").write_bytes(raw_out)
    (output / "raw-stderr.txt").write_bytes(raw_err)
    validation = None
    validation_error = None
    try:
        (output / "raw-stdout.jsonl").read_text(encoding="utf-8")
        validation = validate_stream(output / "raw-stdout.jsonl", "measurement")
    except Exception as error:  # Preserve evidence and mark the attempt rejected.
        validation_error = f"{type(error).__name__}: {error}"
    (output / "functional-validation.json").write_text(
        json.dumps(validation or {"status": "rejected", "error": validation_error},
                   sort_keys=True, indent=2) + "\n", encoding="utf-8")
    metadata.update({"purpose": "measurement", "process_exit_code": return_code,
                     "process_outcome": "timed_out" if timed_out else ("completed" if return_code == 0 else "failed"),
                     "timeout_seconds": args.timeout_seconds,
                     "raw_stdout_sha256": digest(raw_out), "raw_stderr_sha256": digest(raw_err),
                     "validation": validation, "validation_error": validation_error})
    write_utf8_lf(output / "release-build-log-sanitized.txt", metadata.pop("sanitized_build_log"))
    write_utf8_lf(output / "compiler-identification.cmake",
                  metadata.pop("sanitized_compiler_identification"))
    (output / "collection.json").write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n",
                                             encoding="utf-8")
    if return_code != 0 or timed_out or validation_error:
        raise RuntimeError(f"collection retained but rejected at {output}: {validation_error or metadata['process_outcome']}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("preflight", "measure"):
        p = sub.add_parser(action)
        p.add_argument("--exe", type=Path, required=True)
        p.add_argument("--source-root", type=Path, required=True)
        p.add_argument("--source-commit", required=True)
        p.add_argument("--build-log", type=Path, required=True)
        p.add_argument("--concurrent-work-file", type=Path, required=True)
        if action == "measure":
            p.add_argument("--out", type=Path, required=True)
            p.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.action == "preflight":
        result = preflight(args.exe, args.source_root, args.source_commit,
                           args.build_log, args.concurrent_work_file)
        print(json.dumps({"source_commit": result["source_commit"], "ready": True}, sort_keys=True))
    else:
        print(json.dumps({"collection": str(collect(args)), "status": "complete"}, sort_keys=True))


if __name__ == "__main__":
    main()
