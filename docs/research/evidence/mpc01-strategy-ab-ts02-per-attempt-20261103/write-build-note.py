#!/usr/bin/env python3
"""Retain CMake and object-file evidence connecting a Strategy A/B binary to its source."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--build-dir", type=pathlib.Path, required=True)
    parser.add_argument("--binary", type=pathlib.Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve(strict=True)
    build = args.build_dir.resolve(strict=True)
    binary = args.binary.resolve(strict=True)
    output = args.output_dir.resolve(strict=True)
    cache = {}
    for line in (build / "CMakeCache.txt").read_text().splitlines():
        if line and not line.startswith("#") and ":" in line and "=" in line:
            key, value = line.split(":", 1)
            cache[key] = value.split("=", 1)[1]
    configured_root = pathlib.Path(cache["CMAKE_HOME_DIRECTORY"]).resolve(strict=True)
    if configured_root != root:
        raise ValueError("CMake build directory was configured from a different source checkout")
    source = subprocess.run(["git", "show", f"{args.source_commit}:examples/registered_synthesis_comparison.cpp"],
                            cwd=root, check=True, capture_output=True).stdout
    source_archive = subprocess.run(["git", "archive", "--format=tar", args.source_commit],
                                    cwd=root, check=True, capture_output=True).stdout
    current_source = (root / "examples/registered_synthesis_comparison.cpp").read_bytes()
    if source != current_source:
        raise ValueError("configured source checkout does not match the declared binary source commit")

    compiler_files = sorted(build.glob("CMakeFiles/*/CMakeCXXCompiler.cmake"))
    if len(compiler_files) != 1:
        raise ValueError("expected one configured CMake C++ compiler metadata file")
    compiler_file = compiler_files[0]
    compiler_text = compiler_file.read_bytes()
    compiler_values = {}
    for name in ("CMAKE_CXX_COMPILER_ID", "CMAKE_CXX_COMPILER_VERSION"):
        match = re.search(rf'^set\({name} "([^"]*)"\)$', compiler_text.decode(), re.MULTILINE)
        if not match:
            raise ValueError(f"CMake compiler metadata is missing {name}")
        compiler_values[name] = match.group(1)

    target_dir = build / "examples/CMakeFiles/registered_synthesis_comparison.dir"
    artifacts = {
        "cmake-compiler-metadata.cmake": compiler_text,
        "target-flags.make": (target_dir / "flags.make").read_bytes(),
        "target-link.txt": (target_dir / "link.txt").read_bytes(),
    }
    for filename, content in artifacts.items():
        (output / filename).write_bytes(content)
    object_file = target_dir / "registered_synthesis_comparison.cpp.o"
    note = {
        "schema": "csl.mpc01-binary-build-note/1",
        "source": {"revision": args.source_commit,
                   "file": "examples/registered_synthesis_comparison.cpp",
                   "file_sha256": sha256(source), "tree_sha256": sha256(source_archive)},
        "configured_source_checkout": str(configured_root),
        "build": {"type": cache.get("CMAKE_BUILD_TYPE", "unknown"),
                  "generator": cache.get("CMAKE_GENERATOR", "unknown"),
                  "compiler": {"id": compiler_values["CMAKE_CXX_COMPILER_ID"],
                               "version": compiler_values["CMAKE_CXX_COMPILER_VERSION"],
                               "path": cache.get("CMAKE_CXX_COMPILER", "unknown")},
                  "release_flags": cache.get("CMAKE_CXX_FLAGS_RELEASE", ""),
                  "retained_cmake_files": {name: sha256(content) for name, content in artifacts.items()},
                  "object_file": {"path": "examples/CMakeFiles/registered_synthesis_comparison.dir/registered_synthesis_comparison.cpp.o",
                                  "sha256": sha256(object_file.read_bytes())}},
        "executable": {"path": str(binary), "sha256": sha256(binary.read_bytes())},
        "interpretation": "This note records the configured source revision, generated CMake compile/link metadata, object-file digest, and final executable digest from the retained build tree. It is build provenance evidence, not a signed attestation.",
    }
    note_path = output / "build-note.json"
    note_path.write_text(json.dumps(note, indent=2, sort_keys=True) + "\n")
    environment_path = output / "environment.json"
    if environment_path.is_file():
        environment = json.loads(environment_path.read_text())
        environment["binary_build_provenance"] = {
            "schema": "csl.binary-build-provenance/2",
            "source_revision": args.source_commit,
            "source_tree_sha256": note["source"]["tree_sha256"],
            "executable_sha256": note["executable"]["sha256"],
            "build_note": {"path": "build-note.json", "sha256": sha256(note_path.read_bytes())},
        }
        environment_path.write_text(json.dumps(environment, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"build_note": str(note_path), "binary_sha256": note["executable"]["sha256"],
                      "compiler": f"{compiler_values['CMAKE_CXX_COMPILER_ID']} {compiler_values['CMAKE_CXX_COMPILER_VERSION']}"},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
