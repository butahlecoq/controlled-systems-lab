from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import re
import subprocess


def source_hashes_match_commit(root: Path, commit: str, expected: dict[str, str]) -> bool:
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
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
        object_name = f"{commit}:{path.as_posix()}"
        object_type = subprocess.run(["git", "-C", str(root), "cat-file", "-t", object_name],
            check=False, capture_output=True)
        if object_type.returncode != 0 or object_type.stdout.strip() != b"blob":
            return False
        completed = subprocess.run(["git", "-C", str(root), "cat-file", "blob", object_name],
            check=False, capture_output=True)
        if completed.returncode != 0:
            return False
        if hashlib.sha256(completed.stdout).hexdigest() != expected_hash:
            return False
    return True
