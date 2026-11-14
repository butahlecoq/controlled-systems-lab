"""Capture a source-pinned native 2D history-membership solve."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import TypedDict

import stage_history_membership_2d as report


class CompilerIdentity(TypedDict):
    executable: str
    id: str
    version: str


class BuildIdentity(TypedDict):
    schema: str
    source_root_matches_checkout: bool
    source_commit: str
    build_type: str
    generator: str
    casadi_enabled: bool
    casadi_version: str
    example_enabled: bool
    cmake_version: str
    compiler: CompilerIdentity


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cache_values(text: str) -> dict[str, str]:
    values = {}
    for line in text.splitlines():
        if line and not line.startswith("//") and "=" in line:
            key, value = line.split("=", 1)
            values[key.split(":", 1)[0]] = value
    return values


def _validate_build_identity(
    source_root: Path, build_root: Path, cache_text: str, compiler_text: str, source_commit: str
) -> BuildIdentity:
    values = _cache_values(cache_text)
    try:
        cache_source = Path(values["CMAKE_HOME_DIRECTORY"]).resolve(strict=True)
        compiler = Path(values["CMAKE_CXX_COMPILER"]).resolve(strict=True)
    except (KeyError, OSError) as error:
        raise RuntimeError("CMake cache has no valid source/compiler path") from error
    if cache_source != source_root or not cache_source.is_dir():
        raise RuntimeError("CMake cache source root differs from the captured source")
    if not Path(build_root).is_dir():
        raise RuntimeError("CMake build root is missing")
    if values.get("CSL_HISTORY_MEMBERSHIP_SOURCE_COMMIT") != source_commit:
        raise RuntimeError("CMake cache was configured for a different source commit")
    if values.get("CSL_ENABLE_CASADI") != "ON":
        raise RuntimeError("CMake cache did not enable the CasADi backend")
    if values.get("CSL_BUILD_HISTORY_MEMBERSHIP_2D_EXAMPLE") != "ON":
        raise RuntimeError("CMake cache did not enable the history membership example")
    if values.get("CMAKE_BUILD_TYPE") != "Release":
        raise RuntimeError("CMake cache does not describe the qualified Release build")
    if not compiler.is_file():
        raise RuntimeError("CMake cache compiler path is missing")
    compiler_id = re.search(
        r'^set\(CMAKE_CXX_COMPILER_ID "([^"]+)"\)$', compiler_text, re.MULTILINE
    )
    compiler_version = re.search(
        r'^set\(CMAKE_CXX_COMPILER_VERSION "([^"]+)"\)$', compiler_text, re.MULTILINE
    )
    if compiler_id is None or compiler_version is None:
        raise RuntimeError("CMake compiler receipt lacks compiler ID or version")
    compiler_id_value = compiler_id.group(1)
    compiler_version_value = compiler_version.group(1)
    identity = compiler_id_value + "-" + compiler_version_value
    if values.get("CSL_HISTORY_MEMBERSHIP_COMPILER") != identity:
        raise RuntimeError("CMake cache compiler identity differs from its compiler receipt")
    casadi_version = values.get("CSL_HISTORY_MEMBERSHIP_CASADI_VERSION", "")
    if not casadi_version or not re.fullmatch(r"[0-9A-Za-z.+_-]+", casadi_version):
        raise RuntimeError("CMake cache lacks a valid CasADi version")
    try:
        cmake = Path(values.get("CMAKE_COMMAND", "")).resolve(strict=True)
    except (KeyError, OSError) as error:
        raise RuntimeError("CMake cache command path is missing") from error
    if not cmake.is_file():
        raise RuntimeError("CMake cache command path is missing")
    cmake_version = subprocess.run(
        [str(cmake), "--version"], check=True, stdout=subprocess.PIPE, text=True
    ).stdout.splitlines()[0]
    expected_cmake_version = "cmake version " + ".".join(
        values.get(key, "")
        for key in (
            "CMAKE_CACHE_MAJOR_VERSION",
            "CMAKE_CACHE_MINOR_VERSION",
            "CMAKE_CACHE_PATCH_VERSION",
        )
    )
    if cmake_version != expected_cmake_version:
        raise RuntimeError("CMake cache version differs from the configured CMake executable")
    return {
        "schema": "csl.history-membership-build-identity/1",
        "source_root_matches_checkout": True,
        "source_commit": source_commit,
        "build_type": values["CMAKE_BUILD_TYPE"],
        "generator": values.get("CMAKE_GENERATOR", ""),
        "casadi_enabled": True,
        "casadi_version": casadi_version,
        "example_enabled": True,
        "cmake_version": cmake_version.removeprefix("cmake version "),
        "compiler": {
            "executable": compiler.name,
            "id": compiler_id_value,
            "version": compiler_version_value,
        },
    }


def _native_output(
    stdout: bytes, source_commit: str, compiler: str, casadi_version: str
) -> re.Match[str]:
    line = stdout.decode("utf-8").strip()
    match = re.fullmatch(
        r"source_commit=([0-9a-f]{40}); compiler=([^;]+); casadi_version=([^;]+); "
        r"provider=([^;]+); "
        r"source_J=([^;]+); u0=([^;]+); u1=([^;]+); "
        r"x1=([^,;]+),([^;]+); x2=([^,;]+),([^;]+); membership_lambda=([^;]+); "
        r"supplied_start_readback=([^;]+); max_H_violation=([^;]+); diagnostics=(.+)",
        line,
    )
    if match is None:
        raise RuntimeError("native stdout differs from the history-membership result contract")
    if match.group(1) != source_commit:
        raise RuntimeError("native executable was compiled from a different source commit")
    if match.group(2) != compiler:
        raise RuntimeError("native executable compiler differs from the CMake build receipt")
    if match.group(3) != casadi_version:
        raise RuntimeError("native executable CasADi version differs from the CMake build receipt")
    if match.group(4) != "csl.nlp.casadi-ipopt.history-cost@1":
        raise RuntimeError("history membership provider identity differs")
    return match


def _record_native_html(content: bytes) -> bytes:
    """Adjust native output links for its archived records/ location."""
    return content.replace(b'src="history.svg"', b'src="../history.svg"').replace(
        b'href="history.csv"', b'href="../history.csv"'
    )


def capture(source_root: Path, build_root: Path, output_root: Path, build_log: Path) -> dict:
    source_root = source_root.resolve(strict=True)
    build_root = build_root.resolve(strict=True)
    binary = build_root / "history_membership_2d_example"
    cache = build_root / "CMakeCache.txt"
    for path in (binary, cache, build_log):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("missing or symlinked native provenance input: " + str(path))
    output_root = output_root.resolve()
    try:
        output_relative = output_root.relative_to(source_root).as_posix()
    except ValueError as error:
        raise RuntimeError("capture output must stay inside the source checkout") from error
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=source_root,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout
    unexpected = [
        line
        for line in status.splitlines()
        if not (line.startswith("?? ") and line[3:].startswith(output_relative + "/"))
    ]
    if unexpected:
        raise RuntimeError("capture requires committed source and a clean source tree")
    source = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", source) is None:
        raise RuntimeError("git did not return a pinned source commit")
    cache_text = cache.read_text(encoding="utf-8", errors="replace")
    compiler_receipts = sorted(build_root.glob("CMakeFiles/*/CMakeCXXCompiler.cmake"))
    if len(compiler_receipts) != 1 or compiler_receipts[0].is_symlink():
        raise RuntimeError("expected exactly one CMake compiler identity receipt")
    compiler_text = compiler_receipts[0].read_text(encoding="utf-8", errors="replace")
    build_identity = _validate_build_identity(
        source_root, build_root, cache_text, compiler_text, source
    )
    source_files = {}
    for relative in report.SOURCE_PATHS:
        committed = subprocess.run(
            ["git", "show", f"{source}:{relative}"],
            cwd=source_root,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        working = (source_root / relative).read_bytes()
        if committed != working:
            raise RuntimeError("working source differs from committed Git bytes: " + relative)
        source_files[relative] = _sha256(committed)
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("refusing to overwrite existing membership evidence")
    output_root.mkdir(parents=True, exist_ok=True)
    native_output = output_root / "native-output"
    completed = subprocess.run(
        [str(binary), str(native_output)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    (output_root / "records").mkdir()
    records = output_root / "records"
    (records / "stdout.txt").write_bytes(completed.stdout)
    if completed.stderr:
        (records / "stderr.txt").write_bytes(completed.stderr)
    build_log_text = build_log.read_text(encoding="utf-8", errors="replace")
    for local_path in sorted(
        (str(source_root), str(build_root), str(Path.home())), key=len, reverse=True
    ):
        if local_path:
            build_log_text = build_log_text.replace(local_path, "<local-path>")
    (records / "build.log").write_text(
        "\n".join(
            (
                "Normalized source-matched build record",
                "source_commit=" + source,
                "compiler="
                + build_identity["compiler"]["id"]
                + "-"
                + build_identity["compiler"]["version"],
                "casadi_version=" + build_identity["casadi_version"],
                "cmake=" + build_identity["cmake_version"],
                "configuration=" + build_identity["build_type"],
                "generator=" + build_identity["generator"],
                "target=history_membership_2d_example",
                "configure=cmake -S . -B build/history-membership-2d -DCSL_ENABLE_CASADI=ON -DCSL_BUILD_HISTORY_MEMBERSHIP_2D_EXAMPLE=ON -DCMAKE_BUILD_TYPE=Release",
                "command=cmake --build build/history-membership-2d --target history_membership_2d_example -j1",
                "input_build_log_sha256=" + _sha256(build_log_text.encode("utf-8")),
                "status=source commit and configured target identity verified by capture",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (records / "build-configuration.json").write_text(
        json.dumps(build_identity, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if completed.returncode != 0:
        raise RuntimeError("membership example failed; see preserved stdout/stderr")
    compiler = build_identity["compiler"]["id"] + "-" + build_identity["compiler"]["version"]
    match = _native_output(completed.stdout, source, compiler, build_identity["casadi_version"])
    values = list(map(float, match.group(5, 6, 7, 8, 9, 10, 11, 12, 14)))
    objective, u0, u1, x1, y1, x2, y2, coefficient, violation = values
    expected_u1 = 1.0 - 0.4 / (3.0**0.5)
    expected_objective = 1.0 + 0.2 * (3.0**0.5 - 1.0)
    if (
        abs(u0 - 0.6) > 1e-5
        or abs(u1 - expected_u1) > 1e-5
        or abs(objective - expected_objective) > 1e-5
        or abs(x1 - 0.6) > 1e-5
        or abs(y1) > 1e-6
        or abs(x2 - 0.6) > 1e-5
        or abs(y2 - expected_u1) > 1e-5
        or abs(coefficient - 1.0) > 1e-5
        or match.group(13) != "1"
        or violation > 1e-7
    ):
        raise RuntimeError("native result missed analytic answer or independent readback limits")
    for name in ("history.csv", "history.svg", "index.html"):
        source_file = native_output / name
        if source_file.is_symlink() or not source_file.is_file():
            raise RuntimeError("native tool did not write " + name)
        shutil.copyfile(source_file, output_root / name)
    (records / "native-output.html").write_bytes(
        _record_native_html((native_output / "index.html").read_bytes())
    )
    shutil.rmtree(native_output)
    receipt = {
        "schema": report.SCHEMA,
        "source_commit": source,
        "source_files": source_files,
        "binary_sha256": _sha256(binary.read_bytes()),
        "provider": match.group(4),
        "build_identity": build_identity,
        "source_objective": "||x2-(1,1)||_2 + 0.5(|u0|+|u1|)",
        "selected_membership": {
            "stage": 1,
            "family": "zonotope",
            "center": [0.4, 0.0],
            "generator_matrix_rows": [[0.2], [0.0]],
            "coefficient_bounds": [-1.0, 1.0],
            "source_geometry_identity": "source-stage-1-zonotope",
        },
        "initialization": {
            "start_mode": "supplied_start",
            "primal_readback_matches": match.group(13) == "1",
            "membership_witness": [0.0],
        },
        "result": {
            "source_J": objective,
            "u0": u0,
            "u1": u1,
            "x1": [x1, y1],
            "x2": [x2, y2],
            "membership_coefficients": [coefficient],
            "maximum_history_violation": violation,
            "diagnostics": match.group(15),
        },
        "analytic_reference": {
            "u0": 0.6,
            "u1": expected_u1,
            "source_J": expected_objective,
            "derivation": "The zonotope forces u0 in [0.2,0.6]. For a=1-u0 and b=1-u1, J=1+sqrt(a^2+b^2)-(a+b)/2; its minimum has a=0.4 and b=a/sqrt(3).",
        },
        "reproduction_command": "\n".join(
            (
                "cmake -S . -B build/history-membership-2d -DCSL_ENABLE_CASADI=ON -DCSL_BUILD_HISTORY_MEMBERSHIP_2D_EXAMPLE=ON -DCMAKE_BUILD_TYPE=Release",
                "cmake --build build/history-membership-2d --target history_membership_2d_example -j1",
                "build/history-membership-2d/history_membership_2d_example build/history-membership-2d/output",
            )
        ),
        "artifacts": {
            name: _sha256((output_root / name).read_bytes())
            for name in (
                "history.csv",
                "history.svg",
                "records/stdout.txt",
                "records/build.log",
                "records/build-configuration.json",
                "records/native-output.html",
            )
        },
    }
    (records / "receipt.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    report.finalize_capture(output_root)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    capture(args.source, args.build, args.output, args.build_log)


if __name__ == "__main__":
    main()
