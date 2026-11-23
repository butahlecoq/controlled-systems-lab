from __future__ import annotations

import hashlib
import io
import re
import subprocess
import zipfile
from typing import NamedTuple


class SourceLocation(NamedTuple):
    path: str
    member: str | None = None


FIXED_SCHEMA = "csl.mpc07.capture/1"
JOINT_SCHEMA = "csl.mpc07.joint-filter.capture/1"
NATIVE_SOURCE_NAMES = frozenset(("native-affine_bridge.cpp", "native-CMakeLists.txt"))

COMMON_LOCATIONS = {
    "capture.py": (SourceLocation("benchmarks/reporting/mpc07/capture.py"),),
    "policy.py": (SourceLocation("benchmarks/reporting/mpc07/policy.py"),),
    "report.py": (SourceLocation("benchmarks/reporting/mpc07/report.py"),),
    "source_inventory.py": (
        SourceLocation("benchmarks/reporting/mpc07/source_inventory.py"),
    ),
    "native-build-receipt.json": (
        SourceLocation("benchmarks/reporting/mpc07/native-build-receipt.json"),
    ),
    "test_mpc07_policy.py": (SourceLocation("tests/reporting/test_mpc07_policy.py"),),
    "native-affine_bridge.cpp": (
        SourceLocation("benchmarks/reporting/mpc11/affine_bridge.cpp"),
    ),
    "native-CMakeLists.txt": (SourceLocation("benchmarks/reporting/mpc11/CMakeLists.txt"),),
}

FIXED_LOCATIONS = {
    **COMMON_LOCATIONS,
    "README.md": (
        SourceLocation(
            "benchmarks/reporting/mpc07/evidence/bounded-policy-0e821c2a/offline.zip",
            "mpc07-report/RAW/source/README.md",
        ),
        SourceLocation("benchmarks/reporting/mpc07/README.md"),
        SourceLocation("benchmarks/reporting/mpc07/evidence/bounded-policy-0e821c2a/README.md"),
    ),
    "PLAN.md": (
        SourceLocation("benchmarks/reporting/mpc07/evidence/bounded-policy-0e821c2a/PLAN.md"),
        SourceLocation("benchmarks/reporting/mpc07/PLAN.md"),
        SourceLocation(
            "benchmarks/reporting/mpc07/evidence/bounded-policy-0e821c2a/offline.zip",
            "mpc07-report/RAW/source/PLAN.md",
        ),
    ),
}

JOINT_LOCATIONS = {
    **COMMON_LOCATIONS,
    "README.md": (
        SourceLocation(
            "benchmarks/reporting/mpc07/evidence/joint-filter-04369201/offline.zip",
            "mpc07-joint-report/RAW/source/README.md",
        ),
        SourceLocation("benchmarks/reporting/mpc07/README.md"),
        SourceLocation(
            "benchmarks/reporting/mpc07/evidence/bounded-policy-0e821c2a/offline.zip",
            "mpc07-report/RAW/source/README.md",
        ),
        SourceLocation("benchmarks/reporting/mpc07/evidence/joint-filter-04369201/README.md"),
        SourceLocation(
            "benchmarks/reporting/mpc07/evidence/joint-filter-04369201-recheck-v2/README.md"
        ),
    ),
    "PLAN.md": (
        SourceLocation(
            "benchmarks/reporting/mpc07/evidence/joint-filter-04369201/offline.zip",
            "mpc07-joint-report/RAW/source/PLAN.md",
        ),
        SourceLocation("benchmarks/reporting/mpc07/PLAN.md"),
        SourceLocation("benchmarks/reporting/mpc07/evidence/bounded-policy-0e821c2a/PLAN.md"),
        SourceLocation(
            "benchmarks/reporting/mpc07/evidence/bounded-policy-0e821c2a/offline.zip",
            "mpc07-report/RAW/source/PLAN.md",
        ),
        SourceLocation("benchmarks/reporting/mpc07/evidence/joint-filter-04369201/PLAN.md"),
    ),
    "JOINT-FILTER.md": (
        SourceLocation(
            "benchmarks/reporting/mpc07/evidence/joint-filter-04369201-recheck-v2/JOINT-FILTER.md"
        ),
        SourceLocation("benchmarks/reporting/mpc07/JOINT-FILTER.md"),
        SourceLocation(
            "benchmarks/reporting/mpc07/evidence/joint-filter-04369201/JOINT-FILTER.md"
        ),
    ),
    "joint_filter.py": (SourceLocation("benchmarks/reporting/mpc07/joint_filter.py"),),
    "joint_capture.py": (SourceLocation("benchmarks/reporting/mpc07/joint_capture.py"),),
    "test_mpc07_joint_filter.py": (
        SourceLocation("tests/reporting/test_mpc07_joint_filter.py"),
    ),
    "joint-gain-fixture.json": (
        SourceLocation("tests/reporting/fixtures/mpc07-joint-gain-t08.json"),
    ),
    "figure_style.py": (SourceLocation("scripts/reports/figure_style.py"),),
}


def locations_for(schema: str) -> dict[str, tuple[SourceLocation, ...]]:
    if schema == FIXED_SCHEMA:
        return dict(FIXED_LOCATIONS)
    if schema == JOINT_SCHEMA:
        return dict(JOINT_LOCATIONS)
    raise ValueError("unsupported MPC07 source inventory schema")


def primary_paths(schema: str) -> dict[str, str]:
    return {name: candidates[0].path for name, candidates in locations_for(schema).items()}


def locations_for_capture(schema: str, names: set[str]) -> dict[str, tuple[SourceLocation, ...]]:
    inventory = locations_for(schema)
    if names == set(inventory):
        return inventory
    legacy_names = set(inventory) - {"source_inventory.py"}
    if names == legacy_names:
        return {name: candidates for name, candidates in inventory.items() if name in names}
    raise ValueError("mandatory source inventory differs")


def revision_for(name: str, source_revision: str, native_revision: str) -> str:
    return native_revision if name in NATIVE_SOURCE_NAMES else source_revision


def git_blob(repository, revision: str, path: str) -> bytes:
    return subprocess.check_output(
        ["git", "show", "--end-of-options", f"{revision}:{path}"],
        cwd=repository,
        stderr=subprocess.DEVNULL,
    )


def read_location(repository, revision: str, location: SourceLocation) -> bytes:
    data = git_blob(repository, revision, location.path)
    if location.member is None:
        return data
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = [item for item in archive.infolist() if item.filename == location.member]
        if (
            len(members) != 1
            or members[0].is_dir()
            or members[0].file_size > 100_000
            or members[0].flag_bits & 1
            or members[0].compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
        ):
            raise ValueError("captured source archive member inventory differs")
        return archive.read(members[0])


def available_location(repository, revision: str, locations: tuple[SourceLocation, ...]):
    for location in locations:
        try:
            return location, read_location(repository, revision, location)
        except (
            OSError,
            ValueError,
            KeyError,
            RuntimeError,
            EOFError,
            subprocess.CalledProcessError,
            zipfile.BadZipFile,
        ):
            continue
    raise ValueError("no authorized source path is available in the recorded commit")


def authenticate(
    schema: str,
    source_sha256: dict[str, str],
    captured_sources: dict[str, bytes],
    source_revision: str,
    native_revision: str,
    repository,
) -> dict[str, SourceLocation]:
    if not re.fullmatch(r"[0-9a-f]{40}", source_revision) or not re.fullmatch(
        r"[0-9a-f]{40}", native_revision
    ):
        raise ValueError("source revisions must be full pinned hexadecimal commits")
    inventory = locations_for_capture(schema, set(source_sha256))
    if set(captured_sources) != set(inventory):
        raise ValueError("mandatory captured source files differ")

    selected = {}
    for name, candidates in inventory.items():
        expected_hash = source_sha256[name]
        captured = captured_sources[name]
        if hashlib.sha256(captured).hexdigest() != expected_hash:
            raise ValueError("source snapshot hash differs: " + name)
        revision = revision_for(name, source_revision, native_revision)
        for location in candidates:
            try:
                recorded = read_location(repository, revision, location)
            except (
                OSError,
                ValueError,
                KeyError,
                RuntimeError,
                EOFError,
                subprocess.CalledProcessError,
                zipfile.BadZipFile,
            ):
                continue
            if hashlib.sha256(recorded).hexdigest() == expected_hash and recorded == captured:
                selected[name] = location
                break
        else:
            raise ValueError("source snapshot differs from recorded Git commit or archive: " + name)
    return selected


def capture_sources(schema: str, source_revision: str, native_revision: str, repository):
    if not re.fullmatch(r"[0-9a-f]{40}", source_revision) or not re.fullmatch(
        r"[0-9a-f]{40}", native_revision
    ):
        raise ValueError("source revisions must be full pinned hexadecimal commits")
    result = {}
    selected = {}
    for name, candidates in locations_for(schema).items():
        revision = revision_for(name, source_revision, native_revision)
        location, content = available_location(repository, revision, candidates)
        selected[name] = location
        result[name] = content
    return result, selected
