"""Sanitize public provenance at the saved-report export boundary."""
from __future__ import annotations

import hashlib
import json
import re

SCHEMA = "csl.report-public-provenance/1"
EVIDENCE_KEYS = {
    "configure.log": "configure_log_sha256",
    "build.log": "build_log_sha256",
    "CMakeCache.txt": "cache_sha256",
    "release-target.vcxproj": "project_sha256",
    "CMakeCXXCompiler.cmake": "compiler_config_sha256",
}
PLACEHOLDERS = {
    "SOURCE_ROOT": "Pinned clean solver checkout",
    "BUILD_ROOT": "Configured Release build directory",
    "HARNESS_ROOT": "Checkout of the separately versioned measurement harness",
    "DEPENDENCY_ROOT": "Directory holding the recorded dependency sources",
    "MEASUREMENT_ROOT": "Parent directory holding the solver and Release build",
    "VISUAL_STUDIO_ROOT": "Installed Visual Studio root; version is retained",
    "PROGRAM_FILES_ROOT": "Machine-specific program installation prefix",
}
ABSOLUTE_WINDOWS_PATH = re.compile(rb"[A-Za-z]:[\\/](?!/)")


def assert_public_bytes(data: bytes, name: str) -> None:
    if ABSOLUTE_WINDOWS_PATH.search(data):
        raise ValueError("absolute host path remains in public provenance: " + name)


def sanitizer(build):
    """Resolve the original roots from the retained configure command."""
    configure = build["configure_command"]
    source = next(x.split("=", 1)[1] for x in configure if x.startswith("-DCSL_SOURCE_ROOT="))
    binary = configure[configure.index("-B") + 1]
    runner = configure[configure.index("-S") + 1].replace("\\", "/")
    suffix = "/reports/algorithm-results/tooling/syn04_ts02/runner"
    if not runner.endswith(suffix):
        raise ValueError("unexpected measured harness root")
    dependency = build["dependencies"]["resolved_sources"]["CSL_HIGHS"]["source"].replace("\\", "/").rsplit("/", 1)[0]
    cmake = build["cmake"].replace("\\", "/")
    marker = "/Common7/"
    if marker not in cmake:
        raise ValueError("unexpected measured Visual Studio CMake installation")
    roots = {
        source: "SOURCE_ROOT", binary: "BUILD_ROOT", runner[:-len(suffix)]: "HARNESS_ROOT",
        dependency: "DEPENDENCY_ROOT", cmake.split(marker, 1)[0]: "VISUAL_STUDIO_ROOT",
        binary.replace("\\", "/").rsplit("/", 1)[0]: "MEASUREMENT_ROOT",
        cmake.split("/Microsoft Visual Studio/", 1)[0]: "PROGRAM_FILES_ROOT",
    }
    patterns = []
    for root, label in sorted(roots.items(), key=lambda item: len(item[0]), reverse=True):
        parts = root.replace("\\", "/").split("/")
        patterns.append((re.compile(r"[\\/]+".join(re.escape(p) for p in parts), re.I), label))

    def text(value):
        for pattern, label in patterns:
            value = pattern.sub(lambda _: label, value)
        return value

    def value(item):
        if isinstance(item, str):
            return text(item)
        if isinstance(item, dict):
            return {key: value(child) for key, child in item.items()}
        if isinstance(item, list):
            return [value(child) for child in item]
        return item

    return text, value


def sanitize_collection(measurement, commands, evidence):
    """Preserve original evidence hashes and bind the new sanitized file bytes."""
    raw_build = measurement["build"]
    sanitize_text, sanitize_value = sanitizer(raw_build)
    clean_measurement = sanitize_value(measurement)
    clean_commands = sanitize_value(commands)
    clean_evidence = {}
    originals = {}
    for name, data in evidence.items():
        key = EVIDENCE_KEYS[name]
        original = hashlib.sha256(data).hexdigest()
        if original != raw_build[key]:
            raise ValueError("original build evidence hash differs: " + name)
        originals[name] = original
        clean = sanitize_text(data.decode("utf-8")).encode("utf-8")
        assert_public_bytes(clean, name)
        clean_evidence[name] = clean
        clean_measurement["build"][key] = hashlib.sha256(clean).hexdigest()
    clean_measurement["build"]["sanitization"] = {
        "schema": SCHEMA,
        "policy": "Replace original absolute host roots with portable placeholders; preserve versions, flags, source identities and hashes. Published build-evidence hashes bind sanitized bytes; original hashes remain available without the private source bytes.",
        "root_placeholders": PLACEHOLDERS,
        "original_build_evidence_sha256": originals,
    }
    for name, item in (("measurement", clean_measurement), ("commands", clean_commands)):
        assert_public_bytes(json.dumps(item, ensure_ascii=False).encode("utf-8"), name)
    return clean_measurement, clean_commands, clean_evidence
