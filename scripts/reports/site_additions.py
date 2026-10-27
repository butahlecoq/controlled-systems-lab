"""Prepare and apply validated additions to an existing static report site."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Callable, Mapping


@dataclass(frozen=True)
class Plan:
    site: Path
    files: tuple[tuple[PurePosixPath, bytes], ...]
    replace_existing: frozenset[PurePosixPath]
    require_absent: tuple[PurePosixPath, ...]
    fingerprints: tuple[tuple[PurePosixPath, str | None], ...]


def _relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (not value or "\\" in value or ":" in value or path.is_absolute() or
            str(path) != value or any(part in {".", ".."} for part in path.parts)):
        raise ValueError("site addition path must be a normalized relative path")
    return path


def _site_path(site: Path, relative: PurePosixPath) -> Path:
    return site.joinpath(*relative.parts)


def _check_parents(site: Path, relative: PurePosixPath) -> None:
    current = site
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ValueError("site addition parent must not be a symlink: " + str(relative))
        if current.exists() and not current.is_dir():
            raise ValueError("site addition parent is not a directory: " + str(relative))


def _fingerprint(path: Path) -> str | None:
    if path.is_symlink():
        raise ValueError("site addition destination must not be a symlink: " + str(path))
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError("site addition destination is not a file: " + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(
    site_root: Path,
    files: Mapping[str, bytes],
    *,
    replace_existing: frozenset[str] = frozenset(),
    require_absent: tuple[str, ...] = (),
) -> Plan:
    site_root = Path(site_root)
    if site_root.is_symlink() or not site_root.is_dir():
        raise ValueError("site root must be an existing, non-symlink directory")
    site = site_root.resolve(strict=True)
    additions = [(_relative(name), content) for name, content in files.items()]
    if any(not isinstance(content, bytes) for _, content in additions):
        raise ValueError("site addition contents must be bytes")
    paths = [path for path, _ in additions]
    if len(set(paths)) != len(paths) or len({str(path).casefold() for path in paths}) != len(paths):
        raise ValueError("site addition paths must be unique, including case-insensitively")
    path_keys = {tuple(part.casefold() for part in path.parts) for path in paths}
    for path in paths:
        folded = tuple(part.casefold() for part in path.parts)
        if any(folded[:index] in path_keys for index in range(1, len(path.parts))):
            raise ValueError("site addition file cannot also be a parent directory: " + str(path))
    replacements = frozenset(_relative(name) for name in replace_existing)
    if not replacements.issubset(set(paths)):
        raise ValueError("replacement policy names a path outside the addition plan")
    absent = tuple(_relative(name) for name in require_absent)
    if len(set(absent)) != len(absent):
        raise ValueError("fresh-only paths must be unique")
    for relative in absent:
        current = site
        for part in relative.parts:
            current = current / part
            if current.is_symlink() or current.exists():
                raise ValueError("site route must be fresh: " + str(relative))
    fingerprints = []
    for relative in paths:
        _check_parents(site, relative)
        current = _site_path(site, relative)
        fingerprint = _fingerprint(current)
        if fingerprint is not None and relative not in replacements:
            raise ValueError("site addition destination already exists: " + str(relative))
        fingerprints.append((relative, fingerprint))
    ordered = tuple(sorted(additions, key=lambda item: (
        2 if item[0] == PurePosixPath("index.html") else
        1 if item[0].name == "index.html" else 0, str(item[0]))))
    return Plan(site, ordered, replacements, absent, tuple(fingerprints))


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staged: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="." + path.name + ".", suffix=".tmp",
                                         dir=path.parent, delete=False) as stream:
            staged = Path(stream.name)
            stream.write(content)
            stream.flush()
        os.replace(staged, path)
    finally:
        if staged is not None:
            try:
                staged.unlink()
            except FileNotFoundError:
                pass


def commit(plan: Plan, *, writer: Callable[[Path, bytes], None] | None = None) -> None:
    """Write prepared files, with route indexes last; I/O failure may leave partial additions."""
    writer = _write if writer is None else writer
    for relative in plan.require_absent:
        current = plan.site
        for part in relative.parts:
            current = current / part
            if current.is_symlink() or current.exists():
                raise ValueError("site route changed after preparation: " + str(relative))
    for relative, fingerprint in plan.fingerprints:
        current = _site_path(plan.site, relative)
        _check_parents(plan.site, relative)
        if _fingerprint(current) != fingerprint:
            raise ValueError("site destination changed after preparation: " + str(relative))
    for relative, content in plan.files:
        writer(_site_path(plan.site, relative), content)
