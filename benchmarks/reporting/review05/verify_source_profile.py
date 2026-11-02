#!/usr/bin/env python3
"""Recheck every retained output and gprof file in a source-profile bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from check_horizon_ladder import check_attempt


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    args = parser.parse_args()
    bundle = args.bundle.resolve(strict=True)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    attempts = read_jsonl(bundle / "attempts.jsonl")
    processes = read_jsonl(bundle / "processes.jsonl")
    captured_checks = read_jsonl(bundle / "checks.jsonl")
    scenario = bundle / "horizon01-t08.json"
    if sha256(scenario) != manifest.get("scenario_sha256"):
        parser.error("pinned T=8 scenario hash mismatch")

    by_process = {str(item["process_id"]): item for item in processes}
    if len(by_process) != len(processes):
        parser.error("duplicate process identities")
    for process in processes:
        expected_strategy = ("csl.synthesis.reach-back" if process["group"] % 2 == process["order_position"]
                             else "csl.synthesis.strategy-b")
        if process.get("strategy") != expected_strategy:
            parser.error(f"non-alternating process order: {process.get('process_id')}")
    output_cache: dict[str, list[dict[str, object]]] = {}
    checks = []
    for process_id, process in by_process.items():
        if process.get("process_status") != "completed" or process.get("return_code") != 0:
            parser.error(f"unsuccessful process retained: {process_id}")
        stdout = bundle / str(process.get("stdout_path"))
        stderr = bundle / str(process.get("stderr_path"))
        if sha256(stdout) != process.get("stdout_sha256") or sha256(stderr) != process.get("stderr_sha256"):
            parser.error(f"raw stdout/stderr hash mismatch: {process_id}")
        if process.get("observed_results") != process.get("expected_results"):
            parser.error(f"wrong result count: {process_id}")
        profile = bundle / str(process.get("gmon_path"))
        if not profile.is_file() or sha256(profile) != process.get("gmon_sha256"):
            parser.error(f"gprof file missing or hash mismatch: {process_id}")
        try:
            output_cache[process_id] = [json.loads(line) for line in stdout.read_text(encoding="utf-8").splitlines()]
        except json.JSONDecodeError as error:
            parser.error(f"invalid output in {process_id}: {error}")

    for attempt in attempts:
        process_id = str(attempt.get("process_id"))
        output_index = attempt.get("output_line")
        if process_id not in output_cache or not isinstance(output_index, int):
            parser.error(f"attempt has no retained process/output: {attempt.get('attempt_id')}")
        lines = output_cache[process_id]
        if output_index < 0 or output_index >= len(lines):
            parser.error(f"attempt output index is invalid: {attempt.get('attempt_id')}")
        result = lines[output_index]
        if result.get("scenario_sha256") != manifest.get("scenario_sha256"):
            parser.error(f"result scenario identity mismatch: {attempt.get('attempt_id')}")
        status, reasons = check_attempt(
            {"process_status": attempt.get("process_status"), "result": result,
             "horizon": attempt.get("horizon"), "strategy": attempt.get("strategy")},
            str(manifest["scenario_sha256"]))
        checks.append({"attempt_id": attempt.get("attempt_id"), "process_id": process_id,
                       "strategy": attempt.get("strategy"), "status": status, "reasons": reasons})

    expected = int(manifest["repetitions_per_strategy"]) * 2
    if len(attempts) != expected or len(checks) != expected:
        parser.error(f"attempt count {len(attempts)} differs from expected {expected}")
    captured_by_id = {str(check.get("attempt_id")): check for check in captured_checks}
    if len(captured_by_id) != len(captured_checks):
        parser.error("duplicate capture-check identities")
    for check in checks:
        captured = captured_by_id.get(str(check["attempt_id"]))
        if not captured or captured.get("status") != check["status"]:
            parser.error(f"captured and offline verdict differ: {check['attempt_id']}")
        check["profile_present"] = True
    if any(check["status"] != "verified" for check in checks):
        for check in checks:
            if check["status"] != "verified":
                print(json.dumps(check, sort_keys=True))
        return 1
    checks_path = bundle / "checks.jsonl"
    with checks_path.open("w", encoding="utf-8") as stream:
        for check in checks:
            stream.write(json.dumps(check, separators=(",", ":")) + "\n")
    print(json.dumps({"processes": len(processes), "attempts": len(checks),
                      "verified": len(checks), "offline_checks": str(checks_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
