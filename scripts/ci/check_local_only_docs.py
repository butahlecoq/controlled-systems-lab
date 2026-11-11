#!/usr/bin/env python3
"""Reject new or edited working Markdown under docs/ outside its retained set.

Legacy files are migrated in verified batches, so this checks changed paths
against the PR base rather than reclassifying the entire existing corpus.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

STANDING_DOCS = {
    "docs/agents/issue-tracker.md",
    "docs/agents/delivery.md",
    "docs/architecture/comparison-program.md",
    "docs/architecture/published-algorithm-results.md",
}
ADR_PATH = re.compile(r"docs/architecture/decisions/(?P<number>[0-9]{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md\Z")


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True, encoding="utf-8")


def is_retained(path: str, root: Path) -> bool:
    if path in STANDING_DOCS:
        return True
    match = ADR_PATH.fullmatch(path)
    if not match:
        return False
    try:
        first_line = (root / path).read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError, UnicodeDecodeError):
        return False
    return first_line.startswith(f"# ADR {match.group('number')}:")


def changed_markdown(base: str, root: Path) -> list[str]:
    committed = git(root, "diff", "--name-only", "--diff-filter=AMRT", "-z", f"{base}...HEAD", "--", "docs/")
    working = git(root, "diff", "HEAD", "--name-only", "--diff-filter=AMRT", "-z", "--", "docs/")
    return sorted({path for raw in (committed, working) for path in raw.split("\0")
                   if path.endswith(".md")})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="base commit for the change range (defaults to HEAD^)")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.repo_root.resolve()
    base = args.base or git(root, "rev-parse", "HEAD^").strip()
    bad = [path for path in changed_markdown(base, root) if not is_retained(path, root)]
    if bad:
        print("Working Markdown under docs/ is local-only; changed paths outside the retained document set:", file=sys.stderr)
        for path in bad:
            print(f"  {path}", file=sys.stderr)
        return 1
    print("Changed docs/ Markdown follows the retained document policy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
