from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import re
import subprocess


def source_hashes_match_commit(root: Path, commit: str, expected: dict[str, str]) -> bool:
    if (not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit) or
            not isinstance(expected, dict) or not expected):
        return False
    commit_type = subprocess.run(["git", "-C", str(root), "cat-file", "-t", commit],
        check=False, capture_output=True)
    if commit_type.returncode != 0 or commit_type.stdout.strip() != b"commit":
        return False
    for name, expected_hash in expected.items():
        path = PurePosixPath(name)
        if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
            return False
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            return False
        tree_entry = subprocess.run(["git", "-C", str(root), "ls-tree", "-rz", commit,
            "--", f":(literal){path.as_posix()}"], check=False, capture_output=True)
        if tree_entry.returncode != 0:
            return False
        matching = []
        for entry in tree_entry.stdout.split(b"\0"):
            if not entry:
                continue
            metadata, separator, entry_path = entry.partition(b"\t")
            fields = metadata.split()
            if separator and entry_path == path.as_posix().encode() and len(fields) == 3:
                matching.append(fields)
        if len(matching) != 1:
            return False
        mode, object_type, object_id = matching[0]
        if mode not in (b"100644", b"100755") or object_type != b"blob":
            return False
        completed = subprocess.run(["git", "-C", str(root), "cat-file", "blob", object_id.decode("ascii")],
            check=False, capture_output=True)
        if completed.returncode != 0:
            return False
        if hashlib.sha256(completed.stdout).hexdigest() != expected_hash:
            return False
    return True


def source_hashes_match_commit_or_checkout(root: Path, commit: str, expected: dict[str, str]) -> bool:
    """Verify captured files against the pinned commit, or its exact checkout contents.

    A squash merge can discard the captured commit object even though the archived
    report's source files are unchanged on the target branch. In that case the
    checkout itself is the only available source of provenance, so accept it only
    when every captured relative path is a regular, non-symlink file under root and
    every SHA-256 digest matches. If the commit object exists, keep the stricter
    commit-tree check and never fall back after a mismatch.
    """
    if (not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit) or
            not isinstance(expected, dict) or not expected):
        return False
    commit_type = subprocess.run(["git", "-C", str(root), "cat-file", "-t", commit],
        check=False, capture_output=True)
    if commit_type.returncode == 0:
        return source_hashes_match_commit(root, commit, expected)

    resolved_root = root.resolve()
    for name, expected_hash in expected.items():
        path = PurePosixPath(name)
        if (path.is_absolute() or not path.parts or
                any(part in ("", ".", "..") for part in path.parts) or
                "\\" in name or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)):
            return False
        candidate = root.joinpath(*path.parts)
        ancestors = [candidate, *candidate.parents]
        if any(item.is_symlink() for item in ancestors if item != root) or not candidate.is_file():
            return False
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(resolved_root)
        except (OSError, ValueError):
            return False
        if not resolved.is_file() or hashlib.sha256(resolved.read_bytes()).hexdigest() != expected_hash:
            return False
    return True
