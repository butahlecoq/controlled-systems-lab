#!/usr/bin/env python3
"""Reject new or edited working documentation outside its retained set.

Legacy files are migrated in verified batches, so this checks changed paths
against the PR base rather than reclassifying the entire existing corpus. The
ADR shape check is only a syntax gate; reviewers must verify that each ADR is a
real decision record and not a renamed plan or worklog.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

STANDING_DOCS = {
    "docs/agents/issue-tracker.md",
    "docs/agents/delivery.md",
    "docs/architecture/comparison-program.md",
    "docs/architecture/published-algorithm-results.md",
}
ROOT_ENTRY_DOCS = {"AGENTS.md", "README.md", "CONTRIBUTING.md"}
ISSUE_TEMPLATES = {
    ".github/ISSUE_TEMPLATE/algorithm-proposal.md",
    ".github/ISSUE_TEMPLATE/reproduction.md",
    ".github/ISSUE_TEMPLATE/scientific-correction.md",
}
ADR_PATH = re.compile(
    r"docs/architecture/decisions/(?P<number>[0-9]{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md\Z"
)
WORKING_PATH_WORD = re.compile(
    r"(?:^|[-_.])(plan|plans|spec|specs|draft|drafts|review|reviews|notes)(?:[-_.]|$)", re.I
)
MARKDOWN_SUFFIXES = {".md", ".markdown"}
DOCUMENT_SUFFIXES = MARKDOWN_SUFFIXES | {".rst", ".adoc", ".org", ".text", ".txt"}
WORKING_DOCUMENT_SUFFIXES = DOCUMENT_SUFFIXES | {".json", ".yml", ".yaml"}
FUNCTIONAL_DOC_ASSETS = {
    "docs/artifacts/schemas/": {".json"},
    "docs/catalogue/": {".json", ".sha256"},
    "docs/contracts/closed-loop/": {".json", ".sha256"},
    "docs/examples/": {".css", ".csv", ".html", ".json", ".png", ".svg"},
    "docs/research/evidence/": {
        ".c",
        ".cmake",
        ".cpp",
        ".html",
        ".json",
        ".jsonl",
        ".log",
        ".make",
        ".out",
        ".png",
        ".py",
        ".sha256",
        ".stderr",
        ".stdout",
        ".svg",
        ".txt",
        ".yml",
        ".yaml",
    },
    "docs/research/figures/": {".png", ".svg"},
    "docs/research/tools/": {".py"},
}
FUNCTIONAL_DOC_EXACT_ASSETS = {
    "docs/build/ci-cache-evidence-2026-10-19.json",
    "docs/research/archive-selected-sources.json",
    "docs/research/b04-consistency.json",
    "docs/research/b04-historical-comparison.html",
    "docs/research/b04-historical-comparison.json",
    "docs/research/ext07-hybrid-2d.json",
    "docs/research/ext07-hybrid-2d.svg",
    "docs/research/inventory.json",
    "docs/research/legacy-characterization.json",
    "docs/research/proof-audit-provenance.json",
    "docs/research/reference-b08.json",
    "docs/research/syn04-strategy-b-ts03-control-projection.svg",
    "docs/research/verification.json",
    "docs/research/works-selected-sources.json",
    "scripts/reports/geo07_dependent/review-seal.json",
    "scripts/reports/geo07_port/review-seal.json",
}
LOCAL_ONLY_WORKING_FILES = {"docs/research/exp06-423-decision-log.tsv"}
EXPLICIT_WORKING_DIRECTORIES = {"drafts", "notes", "plans", "reviews", "specs", "superpowers"}
FUNCTIONAL_REPO_ASSET_LOCATIONS = {
    "benchmarks/reporting/",
    "benchmarks/results/",
    "reports/algorithm-results/",
    "reports/closed-loop-pilot/",
}


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True, encoding="utf-8")


def is_retained_markdown(path: str, root: Path) -> bool:
    if path in ROOT_ENTRY_DOCS or path in ISSUE_TEMPLATES or path in STANDING_DOCS:
        return True
    match = ADR_PATH.fullmatch(path)
    if not match:
        return False
    try:
        lines = (root / path).read_text(encoding="utf-8").splitlines()
    except (OSError, IndexError, UnicodeDecodeError):
        return False
    first_line = lines[0] if lines else ""
    has_metadata = any(line.startswith("Date:") for line in lines[:8]) and any(
        "Status:" in line for line in lines[:8]
    )
    has_decision = any(
        re.fullmatch(r"## Decision(?: and alternatives)?", line)
        or re.fullmatch(r"## Context and decision", line)
        for line in lines
    )
    return (
        first_line.startswith(f"# ADR {match.group('number')}:") and has_metadata and has_decision
    )


def changed_paths(base: str, root: Path) -> list[str]:
    committed = git(root, "diff", "--name-only", "--diff-filter=AMRT", "-z", f"{base}...HEAD")
    working = git(root, "diff", "HEAD", "--name-only", "--diff-filter=AMRT", "-z")
    return sorted({path for raw in (committed, working) for path in raw.split("\0") if path})


def is_working_document_path(path: str) -> bool:
    if Path(path).suffix.lower() not in WORKING_DOCUMENT_SUFFIXES:
        return False
    parts = path.split("/")
    stem = Path(path).stem
    suffix = Path(path).suffix.lower()
    return (
        (stem.lower() == "readme" and suffix in DOCUMENT_SUFFIXES)
        or any(part.lower() in {"notes", "plans", "specs", "drafts", "reviews"} for part in parts)
        or bool(WORKING_PATH_WORD.search(stem))
    )


def is_functional_doc_asset(path: str) -> bool:
    if path in FUNCTIONAL_DOC_EXACT_ASSETS:
        return True
    if path.startswith("docs/research/evidence/") and Path(path).name in {
        "SHA256SUMS",
        "exit-code",
    }:
        return True
    suffix = Path(path).suffix.lower()
    return any(
        path.startswith(prefix) and suffix in suffixes
        for prefix, suffixes in FUNCTIONAL_DOC_ASSETS.items()
    )


def is_explicit_working_directory(path: str) -> bool:
    return any(part.lower() in EXPLICIT_WORKING_DIRECTORIES for part in path.split("/")[:-1])


def is_functional_repo_asset(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix not in DOCUMENT_SUFFIXES and any(
        path.startswith(prefix) for prefix in FUNCTIONAL_REPO_ASSET_LOCATIONS
    )


def is_retained_change(path: str, root: Path) -> bool:
    suffix = Path(path).suffix.lower()
    if path in LOCAL_ONLY_WORKING_FILES:
        return False
    if suffix in MARKDOWN_SUFFIXES:
        return is_retained_markdown(path, root)
    if is_explicit_working_directory(path):
        return False
    if path.startswith("docs/"):
        if is_functional_doc_asset(path):
            return True
        return False
    if path in FUNCTIONAL_DOC_EXACT_ASSETS:
        return True
    if is_functional_repo_asset(path):
        return True
    if is_working_document_path(path):
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="base commit for the change range (defaults to HEAD^)")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.repo_root.resolve()
    base = args.base or git(root, "rev-parse", "HEAD^").strip()
    bad = [path for path in changed_paths(base, root) if not is_retained_change(path, root)]
    if bad:
        print(
            "Working documents are local-only; changed paths outside the retained guide, ADR, and functional-asset set:",
            file=sys.stderr,
        )
        for path in bad:
            print(f"  {path}", file=sys.stderr)
        return 1
    print("Changed paths follow the retained documentation policy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
