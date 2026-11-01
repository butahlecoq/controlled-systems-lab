from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import re
import subprocess


def source_hashes_match_commit(root: Path, commit: str, expected: dict[str, str]) -> bool:
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
        return False
    for name, expected_hash in expected.items():
        path = PurePosixPath(name)
        if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
            return False
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            return False
        completed = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{path.as_posix()}"],
            check=False, capture_output=True)
        if completed.returncode != 0:
            return False
        if hashlib.sha256(completed.stdout).hexdigest() != expected_hash:
            return False
    return True
