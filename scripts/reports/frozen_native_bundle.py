"""Read source-qualified native example bundles without changing their bytes."""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath


@dataclass(frozen=True, kw_only=True)
class FrozenNativeBundle:
    route: str
    source_commit: str
    schema: str
    manifest_sha256: str
    archive_sha256: str


def checked_file(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative)
    if (
        not relative
        or parts.is_absolute()
        or any(part in {".", ".."} for part in parts.parts)
        or parts.as_posix() != relative
        or "\\" in relative
    ):
        raise ValueError("native example asset path is unsafe")
    path = root
    if path.is_symlink():
        raise ValueError("native example root is symlinked")
    for part in parts.parts:
        path /= part
        if path.is_symlink():
            raise ValueError("native example asset is symlinked")
    if not path.is_file():
        raise ValueError("native example asset is missing: " + relative)
    return path


def read_bundle(repository_root: Path, identity: FrozenNativeBundle) -> dict[str, bytes]:
    if identity.route in {"", ".", ".."} or any(c in identity.route for c in "/\\"):
        raise ValueError("native example route must be one directory name")
    root = Path(repository_root)
    for part in ("reports", "algorithm-results", identity.route):
        root /= part
        if root.is_symlink():
            raise ValueError("native example bundle ancestor is symlinked")
    raw_manifest = checked_file(root, "manifest.json").read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest() != identity.manifest_sha256:
        raise ValueError("native example manifest differs from the frozen publication identity")
    manifest = json.loads(raw_manifest)
    if manifest["schema"] != identity.schema or manifest["source_commit"] != identity.source_commit:
        raise ValueError("native example source or schema differs")
    records = manifest["files_sha256"]
    if not isinstance(records, dict) or not records:
        raise ValueError("native example digest list is empty")
    files = {"manifest.json": raw_manifest}
    for name, digest in records.items():
        if not isinstance(name, str) or not isinstance(digest, str):
            raise ValueError("native example digest records must contain paths and SHA-256 strings")
        content = checked_file(root, name).read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("native example digest differs: " + name)
        files[name] = content
    archive_name = identity.route + ".zip"
    archive_bytes = checked_file(root, archive_name).read_bytes()
    if hashlib.sha256(archive_bytes).hexdigest() != identity.archive_sha256:
        raise ValueError("native example archive differs from frozen publication identity")
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        if (
            len(archive.namelist()) != len(files)
            or set(archive.namelist()) != set(files)
            or archive.testzip() is not None
        ):
            raise ValueError("native example archive members differ")
        for name, content in files.items():
            if archive.read(name) != content:
                raise ValueError("native example archive bytes differ: " + name)
    files[archive_name] = archive_bytes
    sidecar = checked_file(root, archive_name + ".sha256").read_bytes()
    canonical = (identity.archive_sha256 + "  " + archive_name + "\n").encode("ascii")
    if sidecar != canonical:
        raise ValueError("native example archive checksum differs")
    files[archive_name + ".sha256"] = sidecar
    paths = list(root.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise ValueError("native example bundle contains a symlinked asset")
    actual = {path.relative_to(root).as_posix() for path in paths if path.is_file()}
    if actual != set(files):
        raise ValueError("native example bundle contains unlisted files")
    return files
