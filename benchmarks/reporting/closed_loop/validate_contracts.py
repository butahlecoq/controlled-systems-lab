#!/usr/bin/env python3
"""Check canonical hashes and source bindings without numerical dependencies."""
import json

from contracts import load_task, manifest_sha256
from task_models import validate_source_binding


def main() -> int:
    report = []
    for name in ("syn-nl-lv-01", "earth-orbit", "syn-nl-fuel-01"):
        task = load_task(name)
        validate_source_binding(task)
        report.append({"task_id": task["task_id"], "task_sha256": manifest_sha256(task),
                       "source_sha256": task["source"]["sha256"], "status": "source-bound"})
    print(json.dumps({"status": "pass", "tasks": report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
