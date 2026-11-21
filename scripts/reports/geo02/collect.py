"""GEO-02 collection and canonical saved-record validation."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

import provenance

SCHEMA = "csl.geo02-affine-sum-report/2"
HASH_SCOPE = "canonical JSON payload excluding report_id, payload_sha256, and payload_hash_scope"
PHASES = ("setup_ns", "operation_ns", "oracle_ns", "total_ns")
TIMING_SCOPES = {
    "setup_ns": "Registry/provider construction, operation selection/preparation, and workspace creation; starts after fixture construction.",
    "operation_ns": "Elapsed time inside the prepared geometry workspace run call.",
    "oracle_ns": "Literal expected-point and support-value checks; excludes output extraction and serialization.",
    "total_ns": "End-to-end driver time from fixture construction through output extraction, serialization, and oracle checks; includes the named phases plus intervening harness work.",
}


class Scenario(TypedDict):
    inputs: dict[str, list[float] | list[list[float]]]
    candidate_count: int
    outputs: list[list[float]]
    directions: list[list[float]]
    support: list[float]


class Trial(TypedDict):
    scenario: str
    repetition: int
    status: str
    detail: str
    setup_ns: int
    operation_ns: int
    oracle_ns: int
    total_ns: int
    generated_candidate_count: int
    materialized_output_point_count: int
    reduction_status: str
    output_points: list[list[float]]
    support_checks: int
    support_values: list[float]
    oracle_passed: bool
    input_sha256: str


SCENARIOS: dict[str, Scenario] = {
    "scalar_interval_affine_image": {
        "inputs": {"vertices": [[-1.0], [1.0]], "A": [[2.0]], "b": [0.0]},
        "candidate_count": 2,
        "outputs": [[-2.0], [2.0]],
        "directions": [[1.0], [-1.0]],
        "support": [2.0, 2.0],
    },
    "rectangular_projection_box": {
        "inputs": {"vertices": [[0, 0], [0, 1], [1, 0], [1, 1]], "A": [[1.0, 1.0]], "b": [0.0]},
        "candidate_count": 4,
        "outputs": [[0.0], [2.0]],
        "directions": [[1.0], [-1.0]],
        "support": [2.0, 0.0],
    },
    "singular_map_box_segment": {
        "inputs": {
            "vertices": [[0, 0], [0, 1], [1, 0], [1, 1]],
            "A": [[1.0, 1.0], [2.0, 2.0]],
            "b": [0.0, 0.0],
        },
        "candidate_count": 4,
        "outputs": [[0, 0], [2, 4]],
        "directions": [[1.0, 0.0], [-1.0, 0.0], [0.0, 1.0], [0.0, -1.0]],
        "support": [2.0, 0.0, 4.0, 0.0],
    },
    "minkowski_interval_sum": {
        "inputs": {"left_vertices": [[-1.0], [1.0]], "right_vertices": [[2.0], [3.0]]},
        "candidate_count": 4,
        "outputs": [[1.0], [4.0]],
        "directions": [[1.0], [-1.0]],
        "support": [4.0, -1.0],
    },
    "redundant_interval_candidates": {
        "inputs": {"vertices": [[0.0], [0.0], [0.5], [1.0], [1.0]], "A": [[1.0]], "b": [0.0]},
        "candidate_count": 5,
        "outputs": [[0.0], [1.0]],
        "directions": [[1.0], [-1.0]],
        "support": [1.0, 0.0],
    },
}
FIELDS = (
    "scenario",
    "repetition",
    "status",
    "detail",
    "setup_ns",
    "operation_ns",
    "oracle_ns",
    "total_ns",
    "generated_candidate_count",
    "materialized_output_point_count",
    "reduction_status",
    "output_points",
    "support_checks",
    "support_values",
    "oracle_passed",
)


def canonical(v):
    return json.dumps(
        v, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def sha(v):
    return hashlib.sha256(v).hexdigest()


def summarize(trials, complete=True):
    result = {}
    for name in SCENARIOS:
        rows = [t for t in trials if t.get("scenario") == name]
        accepted = bool(
            complete
            and rows
            and all(t.get("status") == "passed" and t.get("oracle_passed") is True for t in rows)
        )
        phases = {}
        for phase in PHASES:
            vals = sorted(t[phase] for t in rows) if accepted else []
            phases[phase] = {
                "unit": "ns",
                "successful_trials": len(vals),
                "median": (vals[(len(vals) - 1) // 2] + vals[len(vals) // 2]) // 2
                if vals
                else None,
                "min": min(vals) if vals else None,
                "max": max(vals) if vals else None,
                "range": max(vals) - min(vals) if vals else None,
                "trials_excluded_from_summary": len(rows) - len(vals),
            }
        passed = sum(t.get("status") == "passed" and t.get("oracle_passed") is True for t in rows)
        result[name] = {
            "attempts": len(rows),
            "passed": passed,
            "failures": len(rows) - passed,
            "phases": phases,
        }
    return result


def finalize(payload, stamp="manual"):
    payload.pop("payload_sha256", None)
    payload.pop("payload_hash_scope", None)
    payload["payload_hash_scope"] = HASH_SCOPE
    payload["payload_sha256"] = sha(
        canonical(
            {
                k: v
                for k, v in payload.items()
                if k not in ("report_id", "payload_sha256", "payload_hash_scope")
            }
        )
    )
    payload["report_id"] = "geo02-" + stamp + "-" + payload["payload_sha256"][:12]
    return payload


def fixture_payload(stamp="manual"):
    trials = []
    observed = {
        "scalar_interval_affine_image": [[-2.0], [2.0]],
        "rectangular_projection_box": [[0.0], [2.0]],
        "singular_map_box_segment": [[0, 0], [2, 4]],
        "minkowski_interval_sum": [[1.0], [2.0], [3.0], [4.0]],
        "redundant_interval_candidates": [[0.0], [1.0]],
    }
    for s, c in SCENARIOS.items():
        for r in range(7):
            points = observed[s]
            out_count = len(points)
            candidate_count = c["candidate_count"]
            trials.append(
                {
                    "scenario": s,
                    "repetition": r,
                    "status": "passed",
                    "detail": "",
                    "setup_ns": 1,
                    "operation_ns": 2,
                    "oracle_ns": 3,
                    "total_ns": 6,
                    "generated_candidate_count": candidate_count,
                    "materialized_output_point_count": out_count,
                    "reduction_status": "reduced" if out_count < candidate_count else "preserved",
                    "input_sha256": sha(canonical(c["inputs"])),
                    "output_points": points,
                    "support_checks": len(c["directions"]),
                    "support_values": c["support"],
                    "oracle_passed": True,
                }
            )
    warmups = [
        {
            "scenario": s,
            "repetition": 0,
            "status": "passed",
            "detail": "",
            "generated_candidate_count": c["candidate_count"],
            "materialized_output_point_count": len(observed[s]),
            "reduction_status": "reduced"
            if len(observed[s]) < c["candidate_count"]
            else "preserved",
            "output_points": observed[s],
            "support_checks": len(c["directions"]),
            "support_values": c["support"],
            "oracle_passed": True,
        }
        for s, c in SCENARIOS.items()
    ]
    trial_count = 7 * len(SCENARIOS)
    payload = {
        "schema": SCHEMA,
        "report_id": None,
        "algorithm": {"id": "GEO-02", "source_commit": "0" * 40, "harness_commit": "0" * 40},
        "collection": {
            "state": "complete",
            "expected_trials": trial_count,
            "actual_trials": trial_count,
            "failures": 0,
            "measured_repetitions": 7,
            "warmups_per_scenario": 1,
            "warmup_results": warmups,
            "warmup_failures": 0,
            "warmup_parse_error": None,
            "process_return_code": 0,
            "aborted_or_timed_out": False,
            "parse_error": None,
        },
        "timing_scopes": TIMING_SCOPES,
        "expected": SCENARIOS,
        "inputs": {"scenario_catalog_sha256": sha(canonical(SCENARIOS))},
        "summary": summarize(trials),
        "trials": trials,
        "evidence": {
            "arithmetic": "IEEE 754 binary64 candidates with exact dyadic deletion certificates",
            "limiter_profile": "not collected",
            "limitations": [
                "five tiny deterministic analytic fixtures",
                "no competitor, speedup, application-scale, or scalability claim",
                "affine/sum generation and geometry outputs retain numerical assurance only",
                "exact deletion proves equality of the generated binary64 candidate hull, not validated geometry of the source model",
            ],
        },
    }
    return finalize(payload, stamp)


def require_driver_geometry(points: object, support: object) -> None:
    limit = sys.float_info.max

    def finite_vector(value: object) -> bool:
        return isinstance(value, list) and all(
            type(coordinate) in (int, float) and -limit <= coordinate <= limit
            for coordinate in value
        )

    if not isinstance(points, list) or not all(finite_vector(point) for point in points):
        raise ValueError("output_points must be a list of finite numerical coordinate vectors")
    if not finite_vector(support):
        raise ValueError("support_values must be a list of finite numbers")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--exe", type=Path, required=True)
    p.add_argument("--build-dir", type=Path, required=True)
    p.add_argument("--source-commit", required=True)
    p.add_argument("--harness-commit", required=True)
    p.add_argument("--concurrent-work", type=Path, required=True)
    p.add_argument("--profile-evidence", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--repetitions", type=int, default=7)
    p.add_argument("--warmups", type=int, default=1)
    p.add_argument(
        "--reviewed",
        action="store_true",
        help="required acknowledgement that fixed source and harness commits passed independent review",
    )
    a = p.parse_args()
    if not a.reviewed:
        p.error("accepted timing collection requires --reviewed after independent review")
    if a.repetitions < 7 or a.warmups < 1:
        p.error("need at least seven measured repetitions and one warmup")
    if a.out.exists():
        p.error("refusing to overwrite existing collection")
    import re

    if not re.fullmatch(r"[0-9a-f]{40}", a.source_commit) or not re.fullmatch(
        r"[0-9a-f]{40}", a.harness_commit
    ):
        p.error("source and harness commits must be full lowercase 40-character Git SHAs")
    for commit in (a.source_commit, a.harness_commit):
        try:
            provenance.git("cat-file", "-e", commit + "^{commit}")
        except subprocess.CalledProcessError:
            p.error(f"unknown Git commit: {commit}")
    try:
        concurrent_note = a.concurrent_work.read_text(encoding="utf8").strip()
        profile_note = a.profile_evidence.read_text(encoding="utf8").strip()
    except (OSError, UnicodeError) as error:
        p.error(f"cannot read operator evidence note: {error}")
    if not concurrent_note or not profile_note:
        p.error("concurrent-work and profile-evidence notes must be nonempty")
    exe = a.exe.resolve()
    build = a.build_dir.resolve()
    try:
        provenance_record, build_text, _, _ = provenance.final_build_provenance(
            build, exe, a.source_commit, a.harness_commit
        )
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        p.error(str(error))
    out = a.out.resolve()
    out.mkdir(parents=True)
    before = sha(exe.read_bytes())
    command = [str(exe), "--repetitions", str(a.repetitions), "--warmups", str(a.warmups)]
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, timeout=600, check=False, cwd=build
        )
        code = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
        aborted = False
    except subprocess.TimeoutExpired as error:
        code = None
        stdout = (
            error.stdout.decode(errors="replace")
            if isinstance(error.stdout, bytes)
            else (error.stdout or "")
        )
        stderr = (
            error.stderr.decode(errors="replace")
            if isinstance(error.stderr, bytes)
            else (error.stderr or "")
        )
        aborted = True
    if sha(exe.read_bytes()) != before:
        raise SystemExit("executable changed during collection")
    try:
        provenance.require_clean_tracked_tree()
    except ValueError as error:
        raise SystemExit(str(error)) from error
    (out / "raw-driver-output.csv").write_text(stdout, encoding="utf8")
    (out / "process-stderr.txt").write_text(stderr, encoding="utf8")
    source_root = Path(provenance.git("rev-parse", "--show-toplevel")).resolve()
    safe_command = provenance.redact(subprocess.list2cmdline(command), source_root, build)
    (out / "measurement-command.txt").write_text(
        "cwd=BUILD_ROOT\n" + safe_command + "\n", encoding="utf8"
    )
    (out / "build-provenance.txt").write_text(
        json.dumps(provenance_record, indent=2, ensure_ascii=False)
        + "\n--- VERIFIED FINAL RELEASE BUILD LOG ---\n"
        + build_text,
        encoding="utf8",
    )
    (out / "concurrent-work.txt").write_text(concurrent_note + "\n", encoding="utf8")
    (out / "profile-evidence.txt").write_text(profile_note + "\n", encoding="utf8")
    (out / "scenarios.json").write_text(
        json.dumps(SCENARIOS, indent=2, ensure_ascii=False) + "\n", encoding="utf8"
    )
    if TYPE_CHECKING:
        from scripts.reports.geo02 import render
    else:
        import render

    warmups = []
    try:
        for line in stderr.splitlines():
            if line.startswith("geo02_warmup="):
                warmups.append(json.loads(line[len("geo02_warmup=") :]))
        warmup_keys = {(row["scenario"], row["repetition"]) for row in warmups}
        expected_warmups = {
            (scenario, repetition) for scenario in SCENARIOS for repetition in range(a.warmups)
        }
        if len(warmup_keys) != len(warmups) or warmup_keys != expected_warmups:
            raise ValueError("missing/duplicate warmup outcomes")
        for row in warmups:
            require_driver_geometry(row["output_points"], row["support_values"])
            if row["status"] == "passed" and (
                not row["oracle_passed"]
                or not render.check_candidate_reduction(row["scenario"], row)
                or not render.check_oracle(row["scenario"], row["output_points"])
                or not render.check_supports(row["scenario"], row["support_values"])
            ):
                row["status"] = "oracle_failed"
                row["oracle_passed"] = False
        warmup_failures = sum(
            row["status"] != "passed" or row["oracle_passed"] is not True for row in warmups
        )
    except Exception as error:
        warmups = []
        warmup_failures = a.warmups * len(SCENARIOS)
        warmup_parse_error = str(error)
    else:
        warmup_parse_error = None
    trials: list[Trial] = []
    try:
        reader = csv.DictReader(stdout.splitlines())
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("unexpected driver CSV header")
        for row in reader:
            repetition = int(row["repetition"])
            durations = {phase: int(row[phase]) for phase in PHASES}
            if any(duration < 0 for duration in durations.values()) or durations["total_ns"] < sum(
                durations[phase] for phase in PHASES[:-1]
            ):
                raise ValueError("invalid or non-covering phase durations")
            candidate_count = int(row["generated_candidate_count"])
            materialized_count = int(row["materialized_output_point_count"])
            output_points = json.loads(row["output_points"])
            support_values = json.loads(row["support_values"])
            support_checks = int(row["support_checks"])
            if row["oracle_passed"] not in ("true", "false"):
                raise ValueError("invalid boolean")
            require_driver_geometry(output_points, support_values)
            scenario = row["scenario"]
            trial: Trial = {
                "scenario": scenario,
                "repetition": repetition,
                "status": row["status"],
                "detail": row["detail"],
                "setup_ns": durations["setup_ns"],
                "operation_ns": durations["operation_ns"],
                "oracle_ns": durations["oracle_ns"],
                "total_ns": durations["total_ns"],
                "generated_candidate_count": candidate_count,
                "materialized_output_point_count": materialized_count,
                "reduction_status": row["reduction_status"],
                "output_points": output_points,
                "support_checks": support_checks,
                "support_values": support_values,
                "oracle_passed": row["oracle_passed"] == "true",
                "input_sha256": sha(canonical(SCENARIOS[scenario]["inputs"])),
            }
            trials.append(trial)
        expected = {
            (scenario, repetition) for scenario in SCENARIOS for repetition in range(a.repetitions)
        }
        if {(x["scenario"], x["repetition"]) for x in trials} != expected or len(trials) != len(
            expected
        ):
            raise ValueError("missing/duplicate trial rows")
        parse_error = None
    except Exception as error:
        parse_error = str(error)
    for trial in trials:
        case = SCENARIOS[trial["scenario"]]
        if (
            not render.check_candidate_reduction(trial["scenario"], trial)
            or not render.check_oracle(trial["scenario"], trial["output_points"])
            or trial["support_checks"] != len(case["directions"])
            or not render.check_supports(trial["scenario"], trial["support_values"])
        ):
            trial["status"] = "oracle_failed"
            trial["oracle_passed"] = False
    passed = (
        code == 0
        and not aborted
        and parse_error is None
        and warmup_parse_error is None
        and warmup_failures == 0
        and len(trials) == a.repetitions * len(SCENARIOS)
        and all(trial["status"] == "passed" and trial["oracle_passed"] for trial in trials)
    )
    payload = {
        "schema": SCHEMA,
        "report_id": None,
        "payload_hash_scope": HASH_SCOPE,
        "algorithm": {
            "id": "GEO-02",
            "source_commit": a.source_commit,
            "harness_commit": a.harness_commit,
            "api": "csl.geometry.affine-sum",
        },
        "collection": {
            "state": "complete" if passed else "failed",
            "expected_trials": a.repetitions * len(SCENARIOS),
            "actual_trials": len(trials),
            "failures": a.repetitions * len(SCENARIOS)
            - sum(trial["status"] == "passed" and trial["oracle_passed"] for trial in trials),
            "measured_repetitions": a.repetitions,
            "warmups_per_scenario": a.warmups,
            "warmup_results": warmups,
            "warmup_failures": warmup_failures,
            "warmup_parse_error": warmup_parse_error,
            "process_return_code": code,
            "aborted_or_timed_out": aborted,
            "parse_error": parse_error,
            "order": "forward scenario order each repetition",
            "timing_unit": "steady-clock nanoseconds",
        },
        "timing_scopes": TIMING_SCOPES,
        "expected": SCENARIOS,
        "inputs": {
            "scenario_catalog_sha256": sha(canonical(SCENARIOS)),
            "executable_sha256": before,
            "build_provenance_sha256": sha((out / "build-provenance.txt").read_bytes()),
            "concurrent_work_sha256": sha((out / "concurrent-work.txt").read_bytes()),
            "profile_evidence_sha256": sha((out / "profile-evidence.txt").read_bytes()),
        },
        "summary": summarize(trials, passed),
        "trials": trials,
        "evidence": {
            "arithmetic": "IEEE 754 binary64 candidates with exact dyadic deletion certificates",
            "scope": "five tiny deterministic analytic fixtures; descriptive measurements",
            "limiter_profile": "not collected; no OS limiter/CPU sampling available",
            "unavailable_counters": [
                "per-trial CPU time",
                "native thread count",
                "peak memory",
                "OS limiter profiling",
                "internal LP timings",
            ],
            "limitations": [
                "tiny fixtures only",
                "no competitor, speedup, application-scale, or scalability claim",
                "affine/sum generation and geometry outputs retain numerical assurance only",
                "exact deletion proves equality of the generated binary64 candidate hull, not validated geometry of the source model",
            ],
        },
    }
    finalize(payload, dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    (out / "records.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf8"
    )
    (out / "raw-events.jsonl").write_text(
        "".join(json.dumps(trial, sort_keys=True, allow_nan=False) + "\n" for trial in trials),
        encoding="utf8",
    )
    (out / "environment.json").write_text(
        json.dumps(
            {
                "os": platform.platform(),
                "architecture": platform.machine(),
                "cpu_model": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER"),
                "logical_cpu_count": os.cpu_count(),
                "python": platform.python_version(),
                "native_threads_requested": 1,
                "native_threads_observed": None,
                "per_trial_cpu": None,
                "per_trial_peak_memory": None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf8",
    )
    (out / "collection-status.json").write_text(
        json.dumps(
            {
                key: payload["collection"][key]
                for key in (
                    "state",
                    "expected_trials",
                    "actual_trials",
                    "failures",
                    "warmups_per_scenario",
                    "warmup_results",
                    "warmup_failures",
                    "warmup_parse_error",
                    "process_return_code",
                    "aborted_or_timed_out",
                    "parse_error",
                )
            },
            indent=2,
        )
        + "\n",
        encoding="utf8",
    )
    with (out / "summary.csv").open("w", newline="", encoding="utf8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "scenario",
                "phase",
                "unit",
                "median",
                "min",
                "max",
                "range",
                "successful_trials",
                "trials_excluded_from_summary",
            ]
        )
        for scenario, group in payload["summary"].items():
            for phase, stats in group["phases"].items():
                writer.writerow(
                    [
                        scenario,
                        phase,
                        stats["unit"],
                        stats["median"],
                        stats["min"],
                        stats["max"],
                        stats["range"],
                        stats["successful_trials"],
                        stats["trials_excluded_from_summary"],
                    ]
                )
    print(payload["report_id"])
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
