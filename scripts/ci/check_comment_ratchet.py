"""Inventory tracked Python comments and prevent new prose in scripts/ci."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tokenize
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

SCOPE = "scripts/ci"
CommentKind = Literal["comment_only", "inline", "directive"]
ENCODING_COOKIE = re.compile(r"^#.*?coding[:=][ \t]*[-\w.]+")
DIRECTIVE = re.compile(
    r"#\s*(?:"
    r"(?i:(?:ruff:\s*)?noqa)(?:\s*:\s*[A-Z][A-Z0-9]+(?:[ ,]+[A-Z][A-Z0-9]+)*)?"
    r"|fmt:\s*(?:on|off|skip)"
    r"|(?:ruff:\s*)?isort:\s*(?:on|off|skip|skip_file|split)"
    r"|(?:type|ty|pyright):\s*ignore(?:\[[\w, -]+\])?"
    r"|SPDX-(?:FileCopyrightText|License-Identifier):\s*\S.*"
    r")"
)


@dataclass(frozen=True)
class Comment:
    path: str
    line: int
    kind: CommentKind
    text: str


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root)


def revision(root: Path, ref: str) -> str:
    return (
        git(root, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").decode().strip()
    )


def python_paths(paths: bytes) -> list[str]:
    return sorted({os.fsdecode(path) for path in paths.split(b"\0") if path.endswith(b".py")})


def comments(path: str, contents: bytes) -> list[Comment]:
    result = []
    try:
        source = io.BytesIO(contents)
        _, encoding_lines = tokenize.detect_encoding(source.readline)
        source.seek(0)
        for token in tokenize.tokenize(source.readline):
            if token.type != tokenize.COMMENT:
                continue
            line, column = token.start
            text = token.string.rstrip()
            kind: CommentKind = "inline" if token.line[:column].strip() else "comment_only"
            if (
                (line == 1 and column == 0 and text.startswith("#!"))
                or (
                    line <= len(encoding_lines)
                    and kind == "comment_only"
                    and ENCODING_COOKIE.match(text)
                )
                or DIRECTIVE.fullmatch(text)
            ):
                kind = "directive"
            result.append(Comment(path, line, kind, text))
    except (SyntaxError, tokenize.TokenError, UnicodeError) as error:
        raise ValueError(f"{path}: cannot tokenize Python source: {error}") from error
    return result


def snapshot(root: Path, commit: str, *paths: str) -> dict[str, list[Comment]]:
    tracked = python_paths(git(root, "ls-tree", "-r", "--name-only", "-z", commit, "--", *paths))
    return {path: comments(path, git(root, "show", f"{commit}:{path}")) for path in tracked}


def newly_added(root: Path, base: str) -> list[Comment]:
    previous = snapshot(root, base, SCOPE)
    violations = []
    for path in python_paths(git(root, "ls-files", "-z", "--", SCOPE)):
        file = root / path
        if file.is_symlink():
            raise ValueError(f"{path}: expected a regular Python file")
        if not file.exists():
            continue
        allowance = Counter(
            item.text for item in previous.get(path, ()) if item.kind != "directive"
        )
        for item in comments(path, file.read_bytes()):
            if item.kind == "directive":
                continue
            if allowance[item.text]:
                allowance[item.text] -= 1
            else:
                violations.append(item)
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    check = modes.add_parser(
        "check", help="compare tracked working files with an explicit Git base"
    )
    check.add_argument("--base", required=True)
    inventory = modes.add_parser("inventory", help="list Python comments at a Git revision")
    inventory.add_argument("--ref", default="HEAD")
    inventory.add_argument("paths", nargs="*", default=[SCOPE])
    args = parser.parse_args()
    try:
        root = Path(os.fsdecode(git(Path.cwd(), "rev-parse", "--show-toplevel")).rstrip("\n"))
        if args.mode == "inventory":
            commit = revision(root, args.ref)
            files = snapshot(root, commit, *args.paths)
            captured = [item for group in files.values() for item in group]
            counts = Counter(item.kind for item in captured)
            print(
                json.dumps(
                    {
                        "commit": commit,
                        "paths": args.paths,
                        "files": len(files),
                        "counts": {
                            "comment_only": counts["comment_only"],
                            "inline": counts["inline"],
                            "directives": counts["directive"],
                        },
                        "comments": [asdict(item) for item in captured],
                    },
                    indent=2,
                )
            )
            return 0
        violations = newly_added(root, revision(root, args.base))
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        parser.exit(2, f"comment ratchet: {error}\n")
    for item in violations:
        print(f"{item.path}:{item.line}: {item.text}", file=sys.stderr)
    if violations:
        print("Remove new prose comments or put the decision in an ADR.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
