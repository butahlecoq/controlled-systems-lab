#!/usr/bin/env python3
"""Check the finite fixed-plan comparison result and its embedded archive."""

import hashlib
import json
import subprocess
import sys


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def main() -> int:
    result = json.loads(subprocess.check_output([sys.argv[1]], text=True))
    assert result["schema"] == "csl.exp05-fixed-plan-comparison-observation/1"
    assert result["comparison_claim"] == "supported"
    manifest = result["input_manifest"]
    digest = hashlib.sha256(canonical(manifest)).hexdigest()
    assert result["input_manifest_sha256"] == digest
    oracle = result["independent_oracle"]
    assert oracle["status"] == "verified"
    assert len(oracle["plans"]) == 2
    assert oracle["global_minimax_value"] == min(plan["worst_cost"] for plan in oracle["plans"])
    assert [len(summary["samples_ns"]) for summary in result["timing_summary"]] == [7, 7]
    assert result["warmups"] == 1
    assert result["measured_repetitions_per_method"] == 7

    archive = result["comparison_record"]
    assert archive["schema"] == "csl.comparison-record/1"
    spec = json.loads(archive["spec"])
    assert spec["schema"] == "csl.comparison-spec/2"
    assert spec["input_manifest_hash"] == digest
    assert spec["problem_id"] == "csl.problem.v1.sha256:" + digest
    assert spec["repetitions"] == 7
    assert len(archive["attempts"]) == 14
    for arm in range(2):
        attempts = [item for item in archive["attempts"] if item["arm_index"] == arm]
        assert len(attempts) == 7
        assert [item["repetition_index"] for item in attempts] == list(range(7))
        assert all(item["reported_status"] == "completed" for item in attempts)
        for item in attempts:
            run = json.loads(item["run"])
            assert run["schema"] == "csl.run-statistics/7"
            assert run["final"]["kind"] == "finite_minimax"
            expected_assurance = "numerical" if arm == 0 else "validated"
            assert run["final"]["value"]["assurance"] == expected_assurance
            assert run["configuration"]["value"]["output"]["assurance"] == expected_assurance
            assert any(attachment["schema"] == "csl.exp05-minimax-outcome/1" for attachment in run["attachments"])
            event = json.loads(item["measurement_payload"])
            assert event["status"] == "passed"
            assert event["repetition"] == item["repetition_index"]
    print("issue422 finite minimax comparison archive smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
