#!/usr/bin/env python3
"""Package registered Strategy A/B captures as canonical comparison records.

This packages saved attempts; it does not execute strategies or certify their
timing profile. Every warmup, measured attempt, status, witness, and diagnostic
remains in the record payload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


STRATEGIES = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")
MANIFEST_SCHEMA = "csl.mpc01-strategy-ab-input/1"
EVENT_STATUS_BY_TERMINATION = {
    "completed": "passed",
    "refused": "refused",
    "unsupported": "unsupported",
    "failed": "failed",
    "timed_out": "timed_out",
    "resource_limited": "resource_limited",
    "cancelled": "cancelled",
    "incomplete": "incomplete",
}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line:
            row = json.loads(line)
            row["_source_line"] = line
            rows.append(row)
    return rows


def build_record(events_path: Path, scenario_path: Path, environment_path: Path,
                 codec_environment_path: Path) -> dict[str, Any]:
    events = read_jsonl(events_path)
    environment_text = environment_path.read_text(encoding="utf-8")
    environment = json.loads(environment_text)
    resource_profile_text = None
    resource_profile_name = environment.get("measurement", {}).get("resource_profile")
    if resource_profile_name is not None:
        resource_profile_path = environment_path.parent / resource_profile_name
        resource_profile_text = resource_profile_path.read_text(encoding="utf-8")
        if sha256(resource_profile_text.encode("utf-8")) != environment["measurement"].get("resource_profile_sha256"):
            raise ValueError("capture environment resource-profile digest mismatch")
        if json.loads(resource_profile_text).get("schema") != "csl.mpc01-resource-profile/1":
            raise ValueError("unsupported MPC-01 resource-profile schema")
    codec_environment_text = codec_environment_path.read_text(encoding="utf-8")
    codec_environment = json.loads(codec_environment_text)
    if codec_environment.get("schema") != "csl.obs04-environment/1":
        raise ValueError("codec environment must use csl.obs04-environment/1")
    build_provenance = environment.get("binary_build_provenance")
    if build_provenance is not None:
        if build_provenance.get("schema") == "csl.binary-build-provenance/2":
            if (build_provenance.get("source_revision") != environment.get("source_commit") or
                    build_provenance.get("executable_sha256") != environment.get("executable_sha256") or
                    build_provenance.get("source_tree_sha256") != codec_environment["build"].get("source_tree_sha256")):
                raise ValueError("binary build note does not bind the capture source and executable")
            relative = Path(build_provenance["build_note"]["path"])
            bundle_root = environment_path.parent.resolve()
            note_path = (bundle_root / relative).resolve()
            if (relative.is_absolute() or ".." in relative.parts or not note_path.is_relative_to(bundle_root) or
                    note_path.is_symlink() or sha256(note_path.read_bytes()) != build_provenance["build_note"]["sha256"]):
                raise ValueError("binary build note path or digest is invalid")
            note = json.loads(note_path.read_text(encoding="utf-8"))
            if (note.get("schema") != "csl.mpc01-binary-build-note/1" or
                    note.get("source", {}).get("revision") != build_provenance["source_revision"] or
                    note.get("source", {}).get("tree_sha256") != build_provenance["source_tree_sha256"] or
                    note.get("executable", {}).get("sha256") != build_provenance["executable_sha256"]):
                raise ValueError("binary build note contents do not bind the pinned source and executable")
        else:
            if (build_provenance.get("schema") != "csl.binary-build-provenance/1" or
                    build_provenance.get("source_revision") != environment.get("source_commit") or
                    build_provenance.get("executable_sha256") != environment.get("executable_sha256") or
                    build_provenance.get("source_tree_sha256") != codec_environment["build"].get("source_tree_sha256")):
                raise ValueError("binary build provenance does not bind the capture source and executable")
            repository_root = Path(__file__).resolve().parents[3]
            provenance_files: dict[str, Path] = {}
            for key in ("build_note", "process_record", "checksum_manifest", "dynamic_dependencies"):
                relative = Path(build_provenance[key]["path"])
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("binary build provenance path must stay within the repository")
                resolved = (repository_root / relative).resolve()
                if not resolved.is_relative_to(repository_root):
                    raise ValueError("binary build provenance path escapes the repository")
                if sha256(resolved.read_bytes()) != build_provenance[key]["sha256"]:
                    raise ValueError(f"binary build provenance digest mismatch: {key}")
                provenance_files[key] = resolved
            build_note = provenance_files["build_note"].read_text(encoding="utf-8")
            process_record = json.loads(provenance_files["process_record"].read_text(encoding="utf-8"))
            checksum_rows = {}
            for line in provenance_files["checksum_manifest"].read_text(encoding="utf-8").splitlines():
                expected, path = line.split(maxsplit=1)
                checksum_rows[path.strip()] = expected
            if (build_provenance["source_revision"] not in build_note or
                    build_provenance["executable_sha256"] not in build_note or
                    process_record.get("executable_sha256") != build_provenance["executable_sha256"] or
                    checksum_rows.get(build_provenance["build_note"]["checksum_key"]) != build_provenance["build_note"]["sha256"] or
                    checksum_rows.get(build_provenance["process_record"]["checksum_key"]) != build_provenance["process_record"]["sha256"]):
                raise ValueError("archived build note/process record do not attest the pinned executable and source")
            dynamic_dependencies = provenance_files["dynamic_dependencies"].read_text(encoding="utf-8").lower()
            if any(name in dynamic_dependencies for name in ("libcsl", "libhighs", "libqhull")):
                raise ValueError("capture executable unexpectedly loads a project/backend shared library")
    scenario_bytes = scenario_path.read_bytes()
    scenario_hash = sha256(scenario_bytes)
    events_hash = sha256(events_path.read_bytes())
    environment_hash = sha256(environment_text.encode("utf-8"))
    header = next((row for row in events if row.get("event") == "header"), None)
    attempts = [row for row in events if row.get("event") == "trial"]
    if header is None or not attempts:
        raise ValueError("event file must contain one header and strategy trials")
    if (codec_environment["build"]["source_revision"] != environment["source_commit"] or
            codec_environment["build"]["source_dirty"] is not False or
            codec_environment["runtime"]["binary_sha256"].get("value") != environment["executable_sha256"] or
            codec_environment["execution"]["warmup_repetitions"] != environment["measurement"]["warmup_pairs_excluded"] or
            codec_environment["execution"]["tolerances"]["absolute"] != float(header["absolute_tolerance"]) or
            codec_environment["execution"]["tolerances"]["relative"] != float(header["relative_tolerance"])):
        raise ValueError("codec environment does not match saved capture provenance")
    if header.get("schema") not in {
        "csl.synthesis.paired-ts01-event/1", "csl.synthesis.paired-family-event/1"
    }:
        raise ValueError("unsupported Strategy A/B event schema")
    if header.get("scenario_sha256") != scenario_hash or environment.get("scenario_sha256") != scenario_hash:
        raise ValueError("event/environment scenario digest differs from the supplied scenario")
    if environment.get("source_dirty_before_run") is not False:
        raise ValueError("source must have been clean for a canonical comparison record")
    if set(row.get("strategy") for row in attempts) != set(STRATEGIES):
        raise ValueError("capture must include both registered Strategy A and Strategy B")
    if any(row.get("schema") != header["schema"] or
           row.get("status") != EVENT_STATUS_BY_TERMINATION.get(row.get("termination"))
           for row in attempts):
        raise ValueError("trial rows do not match the declared event schema/status vocabulary")

    paired: dict[int, dict[str, dict[str, Any]]] = {}
    for row in attempts:
        pair = paired.setdefault(int(row["repetition"]), {})
        strategy = row["strategy"]
        if strategy in pair:
            raise ValueError(f"duplicate strategy row for repetition {row['repetition']}")
        pair[strategy] = row
    if any(set(pair) != set(STRATEGIES) for pair in paired.values()):
        raise ValueError("a repetition is missing one member of its A/B pair")
    repetitions = sorted(paired)
    if repetitions != list(range(len(repetitions))):
        raise ValueError("repetition indices must be contiguous from zero")
    measured_pairs = int(environment["measurement"]["measured_alternating_pairs"])
    warmup_pairs = int(environment["measurement"]["warmup_pairs_excluded"])
    if warmup_pairs != 1 or measured_pairs < 1:
        raise ValueError("capture must declare one excluded warmup pair and at least one measured pair")
    declared_repetitions = measured_pairs + warmup_pairs
    if len(repetitions) != declared_repetitions:
        raise ValueError("event rows disagree with the environment's declared pair count")
    if any(bool(paired[repetition][strategy]["warmup"]) != (repetition == 0)
           for repetition in repetitions for strategy in STRATEGIES):
        raise ValueError("warmup flag must identify the excluded first pair")

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "scenario_path": environment["scenario"],
        "scenario_sha256": scenario_hash,
        "scenario_content_hex": scenario_bytes.hex(),
        "resolved_problem_id": header["problem"],
        "profile": header["profile"],
        "target": header["target"],
        "representation": header["representation"],
        "assurance": header["assurance"],
        "absolute_tolerance": header["absolute_tolerance"],
        "relative_tolerance": header["relative_tolerance"],
        "resource_policy": header["resource_policy"],
        "event_header_json": header["_source_line"],
        "events_file_sha256": events_hash,
        "environment_file_sha256": environment_hash,
    }
    manifest_bytes = canonical(manifest).encode("utf-8")
    input_hash = sha256(manifest_bytes)
    problem_id = "csl.problem.v1.sha256:" + input_hash
    source_commit = environment["source_commit"]
    build = environment["build"]
    host = environment["host"]
    source_hash = environment["source_file_sha256"]

    configs: list[tuple[str, str, str]] = []
    for strategy in STRATEGIES:
        first = paired[0][strategy]
        config = {
            "schema": "csl.mpc01-strategy-configuration/1",
            "strategy": strategy,
            "strategy_version": first["strategy_version"],
            "strategy_provenance": first["strategy_provenance"],
            "selector_provenance": first["selector_provenance"],
            "membership_provenance": first["membership_provenance"],
            "profile": header["profile"],
            "target": header["target"],
            "assurance": header["assurance"],
            "representation": header["representation"],
            "source_commit": source_commit,
            "driver_sha256": source_hash,
        }
        config_id = "csl.config.v1.sha256:" + sha256(canonical(config).encode("utf-8"))
        configs.append((strategy, canonical(config), config_id))

    request = {
        "schema": "csl.mpc01-strategy-ab-request/1",
        "profile": header["profile"],
        "target": header["target"],
        "assurance": header["assurance"],
        "representation": header["representation"],
        "absolute_tolerance": header["absolute_tolerance"],
        "relative_tolerance": header["relative_tolerance"],
        "strategy_ids": list(STRATEGIES),
        "repetitions_including_warmup": len(repetitions),
        "measurement_scope": header["per_strategy_scope"],
    }
    request_digest = sha256(canonical(request).encode("utf-8"))
    spec = {
        "schema": "csl.comparison-spec/3",
        "arms": [{"configuration_id": config_id, "instrumentation": "disabled", "strategy": strategy}
                 for strategy, _, config_id in configs],
        "input_manifest_hash": input_hash,
        "input_manifest_source": MANIFEST_SCHEMA,
        "problem_id": problem_id,
        "repetitions": len(repetitions),
        "request_digest": request_digest,
        "environment": codec_environment,
    }
    spec_text = canonical(spec)
    spec_id = sha256(spec_text.encode("utf-8"))

    runtime = {
        "language": "C++",
        "implementation": "registered-synthesis-strategy",
        "version": build["compiler"],
        "executable_sha256": environment["executable_sha256"],
        "os": host["os"],
        "architecture": host["cpu"],
        "compiler": build["compiler"],
        "compiler_version": build["compiler"].split()[-1],
        "build_type": build["type"],
    }
    source_ref = [{"path": environment["source_file"], "sha256": source_hash}]
    output_attempts = []
    for arm_index, (strategy, config_text, config_id) in enumerate(configs):
        for repetition in repetitions:
            row = paired[repetition][strategy]
            reported_status = ("completed" if row["termination"] == "completed"
                               else row["termination"])
            run_id = f"mpc01-strategy-ab-{header['profile']}-arm-{arm_index}-r-{repetition:02d}"
            result = {
                "schema": "csl.mpc01-strategy-ab-attempt/1",
                "event_json": row["_source_line"],
                "capture_environment_json": environment_text,
                "resource_profile_json": resource_profile_text,
                "request_json": canonical(request),
                "configuration_json": config_text,
            }
            run = {
                "schema": "csl.external-method-run/1",
                "run": run_id,
                "problem": problem_id,
                "request_digest": request_digest,
                "configuration": {"id": config_id},
                "input_manifest": {"schema": MANIFEST_SCHEMA, "sha256": input_hash,
                                   "content_hex": manifest_bytes.hex()},
                "method": {"id": strategy, "version": row["strategy_version"],
                           "runtime": runtime, "sources": source_ref,
                           "deviations_sha256": None},
                "result": {"reported_status": reported_status, "raw_output": result,
                           "independent_check_json": canonical(row["verification_summary"]),
                           "measurement_phase": "warmup" if row["warmup"] else "measured",
                           "elapsed_ns": (row["timings_ns"]["end_to_end_strategy"].get("value")
                                          if row["timings_ns"]["end_to_end_strategy"].get("available")
                                          else None),
                           "captured_sequence": row["order_position"]},
                "status": reported_status,
                "recorded_state": "unverified_recorded_data",
            }
            run_text = canonical(run)
            event = {
                "schema": "csl.external-method-event/1",
                "method_id": strategy,
                "instrumentation": "disabled",
                "repetition": repetition,
                "warmup": bool(row["warmup"]),
                "status": "passed" if reported_status == "completed" else reported_status,
                "duration_ns": (row["timings_ns"]["end_to_end_strategy"].get("value")
                                if row["timings_ns"]["end_to_end_strategy"].get("available")
                                else None),
                "order_position": row["order_position"],
            }
            output_attempts.append({
                "arm_index": arm_index,
                "measurement_payload": canonical(event),
                "repetition_index": repetition,
                "reported_status": reported_status,
                "run": run_text,
                "run_digest": sha256(run_text.encode("utf-8")),
                "run_id": run_id,
            })
    record_material = {"attempts": output_attempts, "comparison_spec_id": spec_id,
                       "schema": "csl.comparison-record/1"}
    record = {
        "schema": "csl.comparison-record/1",
        "comparison_run_id": sha256(canonical(record_material).encode("utf-8")),
        "comparison_spec_id": spec_id,
        "spec": spec_text,
        "attempts": output_attempts,
        "track": "new-comparison",
    }
    validate_record(record)
    return record


def validate_record(record: dict[str, Any]) -> None:
    spec_text = record["spec"]
    spec = json.loads(spec_text)
    if canonical(spec) != spec_text or spec["schema"] != "csl.comparison-spec/3" or \
            spec.get("environment", {}).get("schema") != "csl.obs04-environment/1":
        raise ValueError("comparison specification is not canonical")
    spec_id = sha256(spec_text.encode("utf-8"))
    if record["comparison_spec_id"] != spec_id:
        raise ValueError("comparison specification digest mismatch")
    arms, repetitions = spec["arms"], spec["repetitions"]
    if len(record["attempts"]) != len(arms) * repetitions:
        raise ValueError("record does not retain every declared attempt")
    for index, attempt in enumerate(record["attempts"]):
        arm, repetition = divmod(index, repetitions)
        run_text = attempt["run"]
        run = json.loads(run_text)
        event_text = attempt["measurement_payload"]
        event = json.loads(event_text)
        raw_output = run["result"]["raw_output"]
        capture_environment = json.loads(raw_output["capture_environment_json"])
        resource_profile_text = raw_output["resource_profile_json"]
        if resource_profile_text is None:
            if "resource_profile" in capture_environment.get("measurement", {}):
                raise ValueError(f"attempt {index} omits its declared resource profile")
        elif (sha256(resource_profile_text.encode("utf-8")) !=
              capture_environment["measurement"].get("resource_profile_sha256")):
            raise ValueError(f"attempt {index} resource-profile binding mismatch")
        if (attempt["arm_index"] != arm or attempt["repetition_index"] != repetition or
                attempt["reported_status"] != run["status"] or attempt["run_id"] != run["run"] or
                sha256(run_text.encode("utf-8")) != attempt["run_digest"] or
                canonical(run) != run_text or canonical(event) != event_text or
                run["method"]["id"] != arms[arm]["strategy"] or
                run["configuration"]["id"] != arms[arm]["configuration_id"] or
                event["method_id"] != arms[arm]["strategy"] or
                event["repetition"] != repetition or event["warmup"] != (repetition == 0)):
            raise ValueError(f"attempt {index} disagrees with its specification")
        manifest = bytes.fromhex(run["input_manifest"]["content_hex"])
        if (sha256(manifest) != spec["input_manifest_hash"] or
                run["input_manifest"]["sha256"] != spec["input_manifest_hash"] or
                run["problem"] != spec["problem_id"] or
                run["request_digest"] != spec["request_digest"]):
            raise ValueError(f"attempt {index} input binding mismatch")
    expected_run_id = sha256(canonical({"attempts": record["attempts"],
        "comparison_spec_id": spec_id, "schema": "csl.comparison-record/1"}).encode("utf-8"))
    if record["comparison_run_id"] != expected_run_id:
        raise ValueError("comparison run digest mismatch")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--environment", required=True, type=Path)
    parser.add_argument("--codec-environment", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    record = build_record(args.events, args.scenario, args.environment, args.codec_environment)
    payload = canonical(record)
    if args.output.exists() and args.output.read_text(encoding="utf-8") != payload:
        raise SystemExit(f"output exists with different content: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    main()
