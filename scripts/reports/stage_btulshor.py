#!/usr/bin/env python3
"""Validate the immutable saved BTULSHOR comparison bundle."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile


ROOT = Path(__file__).resolve().parents[2]
REPORT_ID = "btulshor-source-faithful-20261110-v1"
SCHEMA = "csl.btulshor-source-faithful-bundle/1"
ORIGINAL_SOURCE_SHA256 = "06fa90d5977ab49174abbf866899000f511fad46eac4a1e72388bbe27090a442"
MANIFEST = "manifest.json"
SUMS = "SHA256SUMS"
ZIP_NAME = f"{REPORT_ID}.zip"
SOURCE_ALLOWLIST = {
    "include/csl/geometry/legacy_btulshor.hpp",
    "src/geometry/legacy_btulshor.cpp",
    "benchmarks/reporting/btulshor/driver.cpp",
    "scripts/reports/btulshor/render.py",
    "scripts/reports/btulshor/capture.py",
    "scripts/reports/btulshor/figures.py",
    "scripts/reports/figure_style.py",
    "docs/research/tools/check_btulshor_hulls.py",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def safe_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    require(bool(name) and not path.is_absolute() and path.as_posix() == name and
            all(part not in ("", ".", "..") for part in path.parts),
            f"unsafe bundle path: {name!r}")
    require("\\" not in name and not name.startswith("/"), f"unsafe bundle path: {name!r}")
    return path


def _read_regular(root: Path, name: str) -> bytes:
    safe_name(name)
    path = root.joinpath(*PurePosixPath(name).parts)
    require(not path.is_symlink() and path.is_file(), f"missing or unsafe bundle file: {name}")
    require(root.resolve() in path.resolve().parents, f"bundle path escapes source root: {name}")
    return path.read_bytes()


def _decode_json(data: bytes, label: str) -> dict:
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON in {label}: {exc}") from exc
    require(isinstance(value, dict), f"expected JSON object in {label}")
    return value


def _sum_list(data: bytes) -> dict[str, str]:
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("SHA256SUMS is not ASCII") from exc
    result = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        require(match is not None, "malformed SHA256SUMS line")
        value, name = match.groups()
        safe_name(name)
        require(name not in result, f"duplicate SHA256SUMS entry: {name}")
        result[name] = value
    return result


def validate(source_root: Path) -> dict:
    """Validate the bundle's manifest, checksums, source boundary, and offline ZIP."""
    source_root = Path(source_root)
    require(source_root.is_dir() and not source_root.is_symlink(), "source root must be a regular directory")
    manifest_bytes = _read_regular(source_root, MANIFEST)
    sums_bytes = _read_regular(source_root, SUMS)
    manifest = _decode_json(manifest_bytes, MANIFEST)
    require(manifest.get("schema") == SCHEMA, "unsupported BTULSHOR bundle schema")
    commit = manifest.get("capture_source_commit")
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
            "capture_source_commit must be a full 40-character lowercase commit")
    require(manifest.get("source_sha256") == ORIGINAL_SOURCE_SHA256,
            "original BTULSHOR source SHA-256 differs")
    listed = manifest.get("files")
    require(isinstance(listed, dict) and listed, "manifest files must be a nonempty path/hash mapping")
    expected = {}
    for name, value in listed.items():
        safe_name(name)
        require(name not in (MANIFEST, SUMS, ZIP_NAME), f"manifest must not list itself or archive: {name}")
        require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
                f"invalid SHA-256 in manifest: {name}")
        expected[name] = value
        if name.startswith("source/"):
            require(name.removeprefix("source/") in SOURCE_ALLOWLIST,
                    f"source snapshot contains a non-public or unapproved file: {name}")
        elif name.startswith("raw/"):
            require(name.endswith(".json"), f"raw bundle entries must be JSON: {name}")
        elif name.startswith("input/"):
            require(name.endswith(".json"), f"bundle inputs must be JSON: {name}")
        else:
            require(name in {"index.html", "point-projections.svg", "offline_check.py"},
                    f"unexpected bundle content path: {name}")
    require("index.html" in expected and "point-projections.svg" in expected,
            "bundle must include its report and 2D projection figure")
    require(b'lang="en"' in _read_regular(source_root, "index.html"),
            "saved report must be an English HTML page")
    require("offline_check.py" in expected, "bundle must include offline_check.py")
    source_names = {name.removeprefix("source/") for name in expected if name.startswith("source/")}
    require(source_names and source_names <= SOURCE_ALLOWLIST,
            "source snapshot contains a non-public or unapproved file")
    require(any(name.startswith("raw/") and name.endswith(".json") for name in expected),
            "bundle must include raw comparison evidence")
    require(any(name.startswith("input/") and name.endswith(".json") for name in expected),
            "bundle must include comparison inputs")

    actual_names = set()
    for path in source_root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"symlink in bundle refused: {path.relative_to(source_root)}")
        if path.is_file():
            relative = path.relative_to(source_root).as_posix()
            if relative != ZIP_NAME:
                actual_names.add(relative)
    require(actual_names == set(expected) | {MANIFEST, SUMS},
            "bundle file inventory differs from manifest")
    for name, value in expected.items():
        require(digest(_read_regular(source_root, name)) == value, f"manifest hash mismatch: {name}")
    sums = _sum_list(sums_bytes)
    require(set(sums) == set(expected) | {MANIFEST}, "SHA256SUMS inventory differs")
    require(sums[MANIFEST] == digest(manifest_bytes), "SHA256SUMS manifest hash mismatch")
    for name, value in expected.items():
        require(sums[name] == value, f"SHA256SUMS hash mismatch: {name}")

    archive_path = source_root / ZIP_NAME
    require(not archive_path.is_symlink() and archive_path.is_file(), f"missing or unsafe archive: {ZIP_NAME}")
    archive_expected = {f"{REPORT_ID}/{name}" for name in set(expected) | {MANIFEST, SUMS}}
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            names = [item.filename for item in members]
            require(len(names) == len(set(names)), "duplicate ZIP members")
            for name in names:
                safe_name(name)
            require(set(names) == archive_expected, "ZIP member inventory differs from bundle")
            for item in members:
                safe_name(item.filename)
                mode = item.external_attr >> 16
                require((mode & 0o170000) != 0o120000, f"ZIP symlink refused: {item.filename}")
                require(archive.read(item) == _read_regular(source_root, item.filename[len(REPORT_ID) + 1:]),
                        f"ZIP content differs from staged bundle: {item.filename}")
            bad = archive.testzip()
            require(bad is None, f"ZIP CRC failure: {bad}")
    except zipfile.BadZipFile as exc:
        raise ValueError(f"invalid offline ZIP: {exc}") from exc
    return {"manifest": manifest, "files": {name: _read_regular(source_root, name) for name in expected},
            "manifest_bytes": manifest_bytes, "sums_bytes": sums_bytes,
            "zip_bytes": archive_path.read_bytes()}

