#!/usr/bin/env python3
"""Replace private checkout/build/capture prefixes in a saved Strategy A/B bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=pathlib.Path, required=True)
    parser.add_argument("--source-root", type=pathlib.Path, required=True)
    parser.add_argument("--build-root", type=pathlib.Path, required=True)
    parser.add_argument("--capture-root", type=pathlib.Path, required=True)
    args = parser.parse_args()

    bundle = args.bundle.resolve(strict=True)
    replacements = [
        (str(args.build_root.resolve(strict=True)), "${BUILD_ROOT}"),
        (str(args.source_root.resolve(strict=True)), "${SOURCE_ROOT}"),
        (str(args.capture_root.resolve(strict=True)), "${CAPTURE_ROOT}"),
    ]
    if any(not old.startswith("/") for old, _ in replacements):
        raise ValueError("all private path prefixes must be absolute")
    for path in bundle.rglob("*"):
        if not path.is_file() or path.name == "SHA256SUMS":
            continue
        data = path.read_bytes()
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for old, new in replacements:
            content = content.replace(old, new)
        path.write_text(content, encoding="utf-8")

    note_path = bundle / "build-note.json"
    note = json.loads(note_path.read_text(encoding="utf-8"))
    note["configured_source_checkout"] = "${SOURCE_ROOT}"
    note["executable"]["path"] = "${BUILD_ROOT}/examples/registered_synthesis_comparison"
    for name in ("cmake-compiler-metadata.cmake", "target-flags.make", "target-link.txt"):
        note["build"]["retained_cmake_files"][name] = sha256((bundle / name).read_bytes())
    note_path.write_text(json.dumps(note, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    environment_path = bundle / "strategy-ab-ts02-environment.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    environment["executable"] = "${BUILD_ROOT}/examples/registered_synthesis_comparison"
    metadata_path = environment["build"]["compiler_metadata_file"]
    if not metadata_path.startswith("${BUILD_ROOT}/"):
        metadata = pathlib.Path(metadata_path)
        environment["build"]["compiler_metadata_file"] = "${BUILD_ROOT}/" + metadata.relative_to(args.build_root.resolve()).as_posix()
    resource_path = bundle / environment["measurement"]["resource_profile"]
    environment["measurement"]["resource_profile_sha256"] = sha256(resource_path.read_bytes())
    environment["binary_build_provenance"]["build_note"]["sha256"] = sha256(note_path.read_bytes())
    environment_path.write_text(json.dumps(environment, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"bundle": str(bundle), "replacements": len(replacements),
                      "resource_profile_sha256": environment["measurement"]["resource_profile_sha256"],
                      "build_note_sha256": environment["binary_build_provenance"]["build_note"]["sha256"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
