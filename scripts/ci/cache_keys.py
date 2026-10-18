"""Emit cache compatibility keys and an explicit read/write trust decision."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re


INPUTS = (
    "cmake/Dependencies.cmake", "cmake/DependencyArchive.cmake",
    "cmake/HighsDependencies.cmake", "cmake/QhullDependencies.cmake",
    "cmake/JsonDependencies.cmake", "cmake/ObjectivesDependencies.cmake",
    "cmake/ApplyPinnedHighsPatch.cmake", "probes/core-01/CMakeLists.txt",
    "tests/cmake/pinned_highs_patch_contract.cmake", "CMakePresets.json",
    "CMakeLists.txt", ".github/workflows/native.yml", "scripts/ci/cache_keys.py",
    ".github/actions/native-cache-setup/action.yml",
    ".github/actions/native-cache-finish/action.yml",
)
CONTEXT_FIELDS = {"os", "arch", "compiler", "cmake", "ccache", "generator",
                  "configuration", "options", "lane"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def cache_keys(root, context, event, ref, revision):
    if set(context) != CONTEXT_FIELDS or any(not isinstance(v, str) or not v for v in context.values()):
        raise ValueError("cache context must supply every nonempty compatibility field")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision):
        raise ValueError("GITHUB_SHA must identify the exact source revision")
    inputs = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in INPUTS}
    inputs_sha256 = digest(inputs)
    # PRs may read trusted main snapshots but never save. Manual development
    # runs may save only in a branch-specific namespace, also scoped by GitHub.
    scope = "main"
    save = event in {"push", "workflow_dispatch"} and ref == "refs/heads/main"
    if event == "workflow_dispatch" and ref.startswith("refs/heads/") and ref != "refs/heads/main":
        scope = "branch-" + hashlib.sha256(ref.encode()).hexdigest()[:16]
        save = True
    elif event != "pull_request" and ref != "refs/heads/main":
        scope = "readonly-" + hashlib.sha256(ref.encode()).hexdigest()[:16]
    # Each lane owns its immutable snapshots. A faster core lane must not save
    # a partial archive set under the full/probe lane's key.
    compatibility_id = digest({"context": context, "inputs": inputs_sha256})
    compiler_prefix = f"csl-objects-v1-{scope}-{compatibility_id}-"
    return {"archive_key": f"csl-archives-v1-{scope}-{compatibility_id}",
            "compiler_prefix": compiler_prefix, "compiler_key": compiler_prefix + revision,
            "save_allowed": str(save).lower(), "scope": scope,
            "inputs_sha256": inputs_sha256}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--context", type=Path, required=True)
    args = parser.parse_args()
    keys = cache_keys(args.root, json.loads(args.context.read_text(encoding="utf-8")),
                      os.environ["GITHUB_EVENT_NAME"], os.environ["GITHUB_REF"],
                      os.environ["GITHUB_SHA"])
    print(json.dumps(keys, indent=2))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write("".join(f"{key}={value}\n" for key, value in keys.items()))


if __name__ == "__main__":
    main()
