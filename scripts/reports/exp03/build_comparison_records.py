#!/usr/bin/env python3
"""Package EXP-03 method attempts as immutable csl.comparison-record/1 data."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_two_points_approximation import checked_attempt


METHODS = (
    "exact-polytope-quickhull", "axis-box", "rotated-parallelotope",
    "directional-ellipsoid", "zonotope-axis-cover",
)
METHOD_IDS = {
    "exact-polytope-quickhull": ("csl.quickhull_2d", "unregistered", "src/geometry/hull/quickhull_2d.cpp"),
    "axis-box": ("csl.approximation.box", "1", "src/geometry/approximation/box_parallelotope.cpp"),
    "rotated-parallelotope": ("csl.approximation.parallelotope", "1", "src/geometry/approximation/box_parallelotope.cpp"),
    "directional-ellipsoid": ("csl.approximation.ellipsoid.exp03", "1", "src/geometry/approximation/ellipsoidal.cpp"),
    "zonotope-axis-cover": ("csl.geometry.zonotope.axis-cover", "1.0.0", "src/geometry/approximation/zonotope.cpp"),
}
DRIVER = "benchmarks/reporting/exp03/two_points_approximation.cpp"


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _status(raw: dict, verification: dict) -> str:
    if raw.get("status") == "completed" and verification.get("status") == "verified":
        return "completed"
    if raw.get("status") in {"unsupported", "refused", "cancelled", "timed_out", "resource_limited"}:
        return raw["status"]
    if raw.get("status") == "failed" or verification.get("status") == "verification_failed":
        return "failed"
    return "incomplete"


def build_records(reference: dict, run: dict, check: dict,
                  provenance: dict | None = None) -> list[dict]:
    if (run.get("schema") != "csl.exp03-two-points-approximation-run/1" or
            check.get("schema") != "csl.exp03-two-points-approximation-check/1" or
            check.get("status") != "verified" or
            run.get("case_id") != reference.get("case_id") or
            run.get("case_id") != check.get("case_id")):
        raise ValueError("EXP-03 inputs are not one independently checked comparison")
    source_index = reference["stage"] if "stage" in reference else len(reference["layers"]) - 1
    stage = run["stage"]
    if source_index != stage:
        raise ValueError("EXP-03 comparison stage differs from the finite reference")

    measurement_checks = check.get("measurement_call_checks", [])
    measurement_check_by_index = {index: item for index, item in enumerate(measurement_checks)}
    measurement_indices = {}
    for index, item in enumerate(run.get("measurements", [])):
        measurement_indices.setdefault((item["projection_index"], item["method"], item["phase"],
                                        item.get("repetition")), (index, item))
    records = []
    for projection_index, projection in enumerate(run["projections"]):
        manifest = {
            "schema": "csl.exp03-two-points-projected-input/1",
            "case_id": run["case_id"],
            "reference_source_figure_data_sha256": run["reference_source_figure_data_sha256"],
            "stage": stage,
            "coordinate_indices": projection["coordinate_indices"],
            "coordinate_labels": projection["coordinate_labels"],
            "binary64_projected_reference_points": projection["input_points"],
            "exact_scale_2000_lattice_states": reference["layers"][stage]["finite_states_scaled"],
            "state_scale": reference["finite_game"]["state_scale"],
            "projection_pairs": reference["projection_pairs"],
        }
        manifest_bytes = canonical(manifest).encode("utf-8")
        input_hash = sha256(manifest_bytes)
        problem_id = "csl.problem.v1.sha256:" + input_hash
        repetition_count = (run.get("measurement_policy", {}).get("measured_repetitions_per_method", 0) + 1
                            if run.get("measurements") else 1)
        method_by_id = {item["method"]: item for item in projection["methods"]}
        if set(method_by_id) != set(METHODS):
            raise ValueError("EXP-03 projection omitted or duplicated a method")
        configs = []
        for method in METHODS:
            result = method_by_id[method]["result"]
            method_id, version, implementation_path = METHOD_IDS[method]
            params = result.get("method_parameters", {})
            configuration = {
                "schema": "csl.exp03-method-configuration/1",
                "method": method_id,
                "version": version,
                "projection_index": projection_index,
                "coordinates": projection["coordinate_indices"],
                "relation": result.get("direction"),
                "size_budget": result.get("size_budget"),
                "parameters": params,
                "build_source_commit": (provenance or {}).get("source_base_commit"),
            }
            config_id = "csl.config.v1.sha256:" + sha256(canonical(configuration).encode("utf-8"))
            configs.append((method, method_id, version, implementation_path, configuration, config_id))

        request = {
            "schema": "csl.exp03-comparison-request/1",
            "case_id": run["case_id"],
            "stage": stage,
            "projection_index": projection_index,
            "coordinate_indices": projection["coordinate_indices"],
            "relation_scope": "binary64 projected reference plus separately checked exact lattice states",
            "assurance": "numerical native outputs independently checked with exact dyadic/rational predicates",
            "repetitions_including_warmup": repetition_count,
            "methods": [item[1] for item in configs],
        }
        request_digest = sha256(canonical(request).encode("utf-8"))
        spec = {
            "schema": "csl.comparison-spec/2",
            "arms": [{"configuration_id": config_id, "instrumentation": "disabled",
                      "strategy": method_id}
                     for _, method_id, _, _, _, config_id in configs],
            "input_manifest_hash": input_hash,
            "input_manifest_source": manifest["schema"],
            "problem_id": problem_id,
            "repetitions": repetition_count,
            "request_digest": request_digest,
        }
        spec_text = canonical(spec)
        spec_id = sha256(spec_text.encode("utf-8"))
        attempts = []
        for arm_index, (method, method_id, version, implementation_path,
                        configuration, config_id) in enumerate(configs):
            for repetition in range(repetition_count):
                if run.get("measurements"):
                    phase = "warmup" if repetition == 0 else "measured"
                    run_repetition = None if repetition == 0 else repetition - 1
                    pair = measurement_indices.get((projection_index, method, phase, run_repetition))
                    if pair is None:
                        raise ValueError("EXP-03 run omitted a declared method repetition")
                    capture_index, observed = pair
                    verification = measurement_check_by_index.get(capture_index, {})
                    raw = observed.get("result", {})
                    elapsed_ns = observed.get("elapsed_ns")
                else:
                    phase = "smoke"
                    capture_index = None
                    raw = method_by_id[method]["result"]
                    verification = checked_attempt(reference, stage, projection_index,
                                                   {"method": method, "result": raw})
                    elapsed_ns = None
                status = _status(raw, verification)
                run_id = f"exp03-p{projection_index}-{method}-r{repetition:02d}"
                source_hashes = (provenance or {}).get("report_code_sha256", {})
                binary_hash = (provenance or {}).get("build", {}).get("benchmark_executable_sha256")
                runtime = {
                    "architecture": (provenance or {}).get("build", {}).get("operating_system", "unrecorded"),
                    "build_type": (provenance or {}).get("build", {}).get("configuration", "unrecorded"),
                    "compiler": (provenance or {}).get("build", {}).get("compiler", "unrecorded"),
                    "compiler_version": (provenance or {}).get("build", {}).get("compiler", "unrecorded"),
                    "executable_sha256": binary_hash,
                    "implementation": method_id,
                    "language": "C++",
                    "os": (provenance or {}).get("build", {}).get("operating_system", "unrecorded"),
                    "version": version,
                }
                sources = [{"path": path, "sha256": source_hashes[path]}
                           for path in (DRIVER, implementation_path) if path in source_hashes]
                run_payload = {
                    "schema": "csl.external-method-run/1",
                    "run": run_id,
                    "problem": problem_id,
                    "request_digest": request_digest,
                    "configuration": {"id": config_id},
                    "input_manifest": {"schema": manifest["schema"], "sha256": input_hash,
                                       "content_hex": manifest_bytes.hex()},
                    "method": {"id": method_id, "version": version, "runtime": runtime,
                               "sources": sources},
                    "result": {"reported_status": status, "raw_output": raw,
                               "independent_check": verification,
                               "measurement_phase": phase, "elapsed_ns": elapsed_ns,
                               "captured_sequence": capture_index},
                    "status": status,
                }
                run_text = canonical(run_payload)
                event = {
                    "schema": "csl.external-method-event/1",
                    "method_id": method_id,
                    "instrumentation": "disabled",
                    "repetition": repetition,
                    "warmup": repetition == 0,
                    "status": {"completed": "passed", "incomplete": "incomplete"}.get(status, status),
                    "duration_ns": elapsed_ns,
                    "projection_index": projection_index,
                    "phase": phase,
                    "captured_sequence": capture_index,
                    "checker_status": verification.get("status"),
                }
                attempts.append({
                    "arm_index": arm_index,
                    "measurement_payload": canonical(event),
                    "repetition_index": repetition,
                    "reported_status": status,
                    "run": run_text,
                    "run_digest": sha256(run_text.encode("utf-8")),
                    "run_id": run_id,
                })
        run_material = {"attempts": attempts, "comparison_spec_id": spec_id,
                        "schema": "csl.comparison-record/1"}
        records.append({
            "schema": "csl.comparison-record/1",
            "comparison_run_id": sha256(canonical(run_material).encode("utf-8")),
            "comparison_spec_id": spec_id,
            "spec": spec_text,
            "attempts": attempts,
            "track": "new-comparison",
        })
    for record in records:
        validate_record(record)
    return records


def write_records(records: list[dict], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for projection_index, record in enumerate(records):
        path = output_dir / f"comparison-record-projection-{projection_index}.json"
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                        encoding="utf-8")
        paths.append(path)
    return paths


def validate_record(record: dict) -> None:
    expected_top = {"schema", "comparison_run_id", "comparison_spec_id", "spec", "attempts", "track"}
    if (set(record) != expected_top or record.get("schema") != "csl.comparison-record/1" or
            record.get("track") != "new-comparison"):
        raise ValueError("comparison-record envelope is invalid")
    spec_text = record["spec"]
    spec = json.loads(spec_text)
    if (canonical(spec) != spec_text or spec.get("schema") != "csl.comparison-spec/2" or
            set(spec) != {"schema", "arms", "input_manifest_hash", "input_manifest_source",
                          "problem_id", "repetitions", "request_digest"}):
        raise ValueError("comparison specification is invalid or noncanonical")
    spec_id = sha256(spec_text.encode("utf-8"))
    if record.get("comparison_spec_id") != spec_id:
        raise ValueError("comparison specification digest differs")
    arms, repetitions = spec["arms"], spec["repetitions"]
    attempts = record["attempts"]
    if len(attempts) != len(arms) * repetitions:
        raise ValueError("comparison record omitted a declared attempt")
    for index, item in enumerate(attempts):
        arm_index, repetition = divmod(index, repetitions)
        run_text = item["run"]
        run = json.loads(run_text)
        event_text = item["measurement_payload"]
        event = json.loads(event_text)
        if (item["arm_index"] != arm_index or item["repetition_index"] != repetition or
                item["run_id"] != run.get("run") or item["reported_status"] != run.get("status") or
                item["reported_status"] != run.get("result", {}).get("reported_status") or
                run.get("schema") != "csl.external-method-run/1" or
                canonical(run) != run_text or canonical(event) != event_text or
                sha256(run_text.encode("utf-8")) != item["run_digest"] or
                run["method"]["id"] != arms[arm_index]["strategy"] or
                run["configuration"]["id"] != arms[arm_index]["configuration_id"] or
                event["method_id"] != arms[arm_index]["strategy"] or
                event["repetition"] != repetition or event["warmup"] != (repetition == 0)):
            raise ValueError(f"comparison attempt {index} disagrees with its spec, run or event")
        attached = run["input_manifest"]
        content = bytes.fromhex(attached["content_hex"])
        manifest = json.loads(content)
        input_hash = sha256(content)
        if (canonical(manifest).encode("utf-8") != content or
                attached["schema"] != spec["input_manifest_source"] or
                attached["sha256"] != input_hash or input_hash != spec["input_manifest_hash"] or
                run["problem"] != spec["problem_id"] or
                run["problem"] != "csl.problem.v1.sha256:" + input_hash or
                run["request_digest"] != spec["request_digest"]):
            raise ValueError(f"comparison attempt {index} has invalid shared input identity")
    run_id = sha256(canonical({"attempts": attempts, "comparison_spec_id": spec_id,
                               "schema": "csl.comparison-record/1"}).encode("utf-8"))
    if record.get("comparison_run_id") != run_id:
        raise ValueError("comparison run digest differs")
