"""Versioned record semantics shared by GEO-05 collection and rendering."""
from __future__ import annotations

import hashlib
import json
import copy
from statistics import median

SCHEMA = "csl.geo05-numerical-report/1"
CATALOG_VERSION = "geo05-analytic-v1"
SCENARIOS = ("singular_a", "unreachable_equality_target",
             "integrator_predecessor", "v_projection_preserves_ray")
PHASES = ("preparation_ns", "workspace_ns", "run_ns", "verification_ns", "end_to_end_ns")
HARNESS_PATH_ALLOWLIST = {
    "CMakeLists.txt",
    "reports/algorithm-results/tooling/geo05/README.md",
    "reports/algorithm-results/tooling/geo05/projection_predecessor_driver.cpp",
    "reports/algorithm-results/tooling/geo05/report.py",
    "reports/algorithm-results/tooling/geo05/schema-v1.json",
    "reports/algorithm-results/tooling/geo05/smoke.py",
    "reports/algorithm-results/tooling/geo05/collect.py",
    "reports/algorithm-results/tooling/geo05/render.py",
    "reports/algorithm-results/tooling/geo05/test_report_tools.py",
}
GEO04_CMAKE_OPTION = 'option(CSL_BUILD_GEO04_REPORT "Build the GEO-04 intersection/reduction report driver" OFF)'
GEO05_CMAKE_OPTION = 'option(CSL_BUILD_GEO05_REPORT "Build the GEO-05 projection/predecessor report driver" OFF)'
GEO04_CMAKE_TARGET = '''if(CSL_BUILD_GEO04_REPORT)
  add_executable(csl_geo04_intersection_report reports/algorithm-results/tooling/geo04/polyhedral_intersection_driver.cpp)
  target_link_libraries(csl_geo04_intersection_report PRIVATE CSL::polyhedral CSL::qhull_conversion CSL::highs_lp)
endif()'''
GEO05_CMAKE_TARGET = '''if(CSL_BUILD_GEO05_REPORT)
  add_executable(csl_geo05_projection_predecessor_report reports/algorithm-results/tooling/geo05/projection_predecessor_driver.cpp)
  target_link_libraries(csl_geo05_projection_predecessor_report PRIVATE CSL::polyhedral)
endif()'''
# These independent literal checks are sample/fixture checks only. They do not
# establish exact set equality or validated arithmetic.
ORACLES = {
    "singular_a": {"inputs": {"X": {"kind": "universal", "dimension": 2}, "U": {"kind": "interval", "bounds": [-1, 1]}, "S": {"kind": "singleton", "point": [2, 0]}, "A": [[1, 0], [0, 0]], "B": [[1], [0]], "offset": [0, 0], "projected_coordinates": [0, 1]}, "input_rows": 4, "output_rows": 2, "result_kind": "h",
                   "sample_points": [[1, -1000], [3, 1000]], "rejected_points": [[0.5, 0]],
                   "meaning": "singular A retains the free state direction"},
    "unreachable_equality_target": {"inputs": {"X": {"kind": "universal", "dimension": 2}, "U": {"kind": "interval", "bounds": [-1, 1]}, "S": {"kind": "H", "equalities": [[0, 1]], "values": [1]}, "A": [[1, 0], [0, 0]], "B": [[1], [0]], "offset": [0, 0], "projected_coordinates": [0, 1]}, "input_rows": 3, "output_rows": 1, "result_kind": "h",
                                     "sample_points": [], "rejected_points": [[0, 0], [100, -100]],
                                     "meaning": "target equality is unreachable under singular dynamics"},
    "integrator_predecessor": {"inputs": {"X": {"kind": "interval", "bounds": [-2, 2]}, "U": {"kind": "interval", "bounds": [-1, 1]}, "S": {"kind": "interval", "bounds": [1, 3]}, "A": [[1]], "B": [[1]], "offset": [0], "projected_coordinates": [0]}, "input_rows": 6, "output_rows": 4, "result_kind": "h",
                                "sample_points": [[0], [1], [2]], "rejected_points": [[-0.125], [2.125]],
                                       "meaning": "x'=x+u, X=[-2,2], U=[-1,1], S=[1,3] gives literal predecessor samples",
                                       "expected_fm_peak_rows": 6, "expected_fm_peak_basis": "2X+2U+2S rows; eliminating u generates 2x2+2=6 before tautology removal"},
    "v_projection_preserves_ray": {"inputs": {"V": {"vertices": [[2, 3]], "rays": [[1, 0], [0, -1]]}, "projected_coordinates": [1]}, "input_rows": 3, "output_rows": 3, "result_kind": "v",
                                   "vertices": [[3]], "rays": [[0], [-1]],
                                   "meaning": "selected ray images, including zero, are retained"},
}

def sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()

def bind_fixture_identity(row: dict) -> dict:
    scenario = row.get("scenario")
    if scenario not in ORACLES:
        raise ValueError("unknown fixture scenario")
    row["input_sha256"] = sha256_json(ORACLES[scenario]["inputs"])
    row["scenario_sha256"] = sha256_json(ORACLES[scenario])
    return row


def scenario_order(round_index: int) -> tuple[str, ...]:
    return SCENARIOS if round_index % 2 == 0 else tuple(reversed(SCENARIOS))


def validate_source_tree_delta(changed_paths: list[str]) -> None:
    unexpected = sorted(set(path.replace("\\", "/") for path in changed_paths) - HARNESS_PATH_ALLOWLIST - {"CMakeLists.txt"})
    if unexpected:
        raise ValueError(f"source commit changed outside the report harness allowlist: {unexpected}")


def validate_cmake_delta(source_text: str, harness_text: str) -> None:
    if source_text.count(GEO04_CMAKE_OPTION) != 1 or source_text.count(GEO04_CMAKE_TARGET) != 1:
        raise ValueError("pinned CMakeLists.txt lacks unique GEO-04 anchors")
    expected = source_text.replace(GEO04_CMAKE_OPTION, GEO04_CMAKE_OPTION + "\n" + GEO05_CMAKE_OPTION, 1)
    expected = expected.replace(GEO04_CMAKE_TARGET, GEO04_CMAKE_TARGET + "\n" + GEO05_CMAKE_TARGET, 1)
    if harness_text != expected:
        raise ValueError("CMakeLists.txt changed beyond the exact GEO-05 report-target insertion")


def synthetic_trial(scenario: str, repetition: int) -> dict:
    """Deterministic test-only trial that cannot be confused with a measurement."""
    return {"scenario": scenario, "repetition": repetition, "status": "passed", "oracle_passed": True,
            "detail": "synthetic test fixture", "oracle_scope": "numeric_literal_samples",
            "max_rows": 128 if scenario != "v_projection_preserves_ray" else None,
            "input_rows": ORACLES[scenario]["input_rows"],
            "output_rows": ORACLES[scenario]["output_rows"],
            "result_kind": ORACLES[scenario]["result_kind"],
            "result_encoding": "h_contradiction_row" if scenario == "unreachable_equality_target" else ("v_generators" if scenario == "v_projection_preserves_ray" else "h_rows"),
            "input_sha256": sha256_json(ORACLES[scenario]["inputs"]),
            "scenario_sha256": sha256_json(ORACLES[scenario]),
            "expected_fm_peak_rows": 6 if scenario == "integrator_predecessor" else None,
            "work_observed": True,
            "durations_ns": {phase: (None if phase == "workspace_ns" and scenario != "v_projection_preserves_ray" else 1)
                             for phase in PHASES}}


def summarize(trials: list[dict], measured_repetitions: int, warmups: int,
              warmup_trials: list[dict] | None = None,
              process_return_code: int = 0, parse_errors: int = 0, timed_out: bool = False) -> dict:
    warmup_trials = warmup_trials or []
    statuses = {name: 0 for name in ("passed", "failed", "unsupported", "cancelled", "missing")}
    for row in [*warmup_trials, *trials]:
        status = row.get("status")
        statuses[status if status in statuses else "failed"] += 1
    expected = len(SCENARIOS) * measured_repetitions
    statuses["missing"] += max(0, expected - len(trials))
    expected_warmups = len(SCENARIOS) * warmups
    statuses["missing"] += max(0, expected_warmups - len(warmup_trials))
    valid = (statuses["failed"] == statuses["unsupported"] == statuses["cancelled"] == statuses["missing"] == 0
             and process_return_code == 0 and parse_errors == 0 and not timed_out)
    phases = {}
    for phase in PHASES:
        values = [row["durations_ns"][phase] for row in trials if row.get("status") == "passed"
                  and row.get("oracle_passed") is True and isinstance(row.get("durations_ns"), dict)
                  and isinstance(row["durations_ns"].get(phase), int) and not isinstance(row["durations_ns"][phase], bool)]
        phases[phase] = {"median_ns": median(values) if valid and values else None,
                         "min_ns": min(values) if valid and values else None,
                         "max_ns": max(values) if valid and values else None,
                         "successful_trials": len(values), "unavailable_trials": len(trials)-len(values),
                         "trials_excluded": 0 if valid else len(values)}
    by_scenario = {}
    for scenario in SCENARIOS:
        group = [row for row in trials if row.get("scenario") == scenario]
        phase_stats = {}
        for phase in PHASES:
            values = [row.get("durations_ns", {}).get(phase) for row in group
                      if row.get("status") == "passed" and row.get("oracle_passed") is True
                      and isinstance(row.get("durations_ns", {}).get(phase), int)
                      and not isinstance(row.get("durations_ns", {}).get(phase), bool)]
            phase_stats[phase] = {"median_ns": median(values) if valid and values else None,
                                  "min_ns": min(values) if valid and values else None,
                                  "max_ns": max(values) if valid and values else None,
                                  "successful_trials": len(values), "unavailable_trials": len(group)-len(values),
                                  "trials_excluded": 0 if valid else len(values)}
        by_scenario[scenario] = {"attempts": len(group), "phases": phase_stats}
    return {"measured_repetitions": measured_repetitions, "warmups_per_scenario": warmups,
            "expected_trials": expected, "counts": statuses, "valid_success_summary": valid,
            "expected_warmup_trials": expected_warmups, "actual_warmup_trials": len(warmup_trials),
            "process_return_code": process_return_code, "parse_errors": parse_errors, "timed_out": timed_out,
            "phases": phases, "by_scenario": by_scenario}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def strict_json_loads(source: str):
    def object_pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def reject_constant(value: str):
        raise ValueError(f"nonfinite JSON number: {value}")
    return json.loads(source, object_pairs_hook=object_pairs, parse_constant=reject_constant)


def resign_record(record: dict) -> None:
    unsigned = {k: v for k, v in record.items() if k not in ("report_id", "payload_sha256")}
    digest = hashlib.sha256(_canonical(unsigned)).hexdigest()
    record["payload_sha256"] = digest
    record["report_id"] = f"geo05-{digest[:16]}"


def make_record(trials: list[dict], purpose: str, provenance: dict,
                measured_repetitions: int | None = None, warmups: int | None = None,
                warmup_trials: list[dict] | None = None,
                process_return_code: int = 0, parse_errors: int = 0, timed_out: bool = False) -> dict:
    repetitions = measured_repetitions if measured_repetitions is not None else 1
    warmup_count = warmups if warmups is not None else 0
    record = {"schema": SCHEMA, "purpose": purpose, "algorithm": {"id": "GEO-05", **provenance},
              "catalog": {"version": CATALOG_VERSION, "scenarios": list(SCENARIOS), "oracles": copy.deepcopy(ORACLES)},
              "collection": summarize(trials, repetitions, warmup_count, warmup_trials,
                                       process_return_code, parse_errors, timed_out),
              "trials": trials, "warmup_trials": warmup_trials or [],
              "evidence_limits": ["numeric sample checks only", "H relation support Unestablished",
                                  "no exact set equality or validated arithmetic claim"]}
    resign_record(record)
    validate_record(record)
    return record


def validate_record(record: dict) -> None:
    if record.get("schema") != SCHEMA:
        raise ValueError("unsupported GEO-05 report schema")
    digest = record.get("payload_sha256")
    unsigned = {k: v for k, v in record.items() if k not in ("report_id", "payload_sha256")}
    actual = hashlib.sha256(_canonical(unsigned)).hexdigest()
    if digest != actual or record.get("report_id") != f"geo05-{actual[:16]}":
        raise ValueError("payload digest mismatch")
    catalog = record.get("catalog", {})
    if catalog.get("version") != CATALOG_VERSION or tuple(catalog.get("scenarios", ())) != SCENARIOS or catalog.get("oracles") != ORACLES:
        raise ValueError("scenario catalog differs from pinned catalog")
    collection = record.get("collection", {})
    trials = record.get("trials")
    if not isinstance(trials, list):
        raise ValueError("trial matrix must be a list")
    purpose = record.get("purpose")
    repetitions = collection.get("measured_repetitions")
    warmup_trials = record.get("warmup_trials", [])
    if not isinstance(warmup_trials, list):
        raise ValueError("warmup matrix must be a list")
    if purpose == "test":
        allowed_rounds = {0}
        expected_warmup_pairs = set()
    elif purpose == "measurement" and isinstance(repetitions, int) and repetitions >= 7 and collection.get("warmups_per_scenario") == 1:
        allowed_rounds = set(range(repetitions))
        expected_warmup_pairs = {(name, 0) for name in SCENARIOS}
    else:
        raise ValueError("invalid purpose or measurement repetitions")
    pairs = [(row.get("scenario"), row.get("repetition")) for row in trials]
    expected = {(name, rep) for name in SCENARIOS for rep in allowed_rounds}
    if len(pairs) != len(set(pairs)) or not set(pairs) <= expected or (purpose == "test" and set(pairs) != expected):
        raise ValueError("trial matrix is duplicated, out of range, or incomplete for test data")
    warmup_pairs = [(row.get("scenario"), row.get("repetition")) for row in warmup_trials]
    if len(warmup_pairs) != len(set(warmup_pairs)) or not set(warmup_pairs) <= expected_warmup_pairs:
        raise ValueError("warmup matrix is duplicated or out of range")
    if purpose == "test" and set(warmup_pairs) != expected_warmup_pairs:
        raise ValueError("test data has an unexpected warmup matrix")
    if any(row.get("purpose") not in ("warmup", None) for row in warmup_trials):
        raise ValueError("warmup row has incorrect purpose")
    if any(row.get("purpose") not in ("measurement", None) for row in trials):
        raise ValueError("measured trial has incorrect purpose")
    for row in [*warmup_trials, *trials]:
        if not isinstance(row.get("repetition"), int) or isinstance(row.get("repetition"), bool):
            raise ValueError("trial repetition must be an integer")
        if row.get("oracle_scope") != "numeric_literal_samples":
            raise ValueError("oracle evidence must be labeled as numeric literal samples")
        if row.get("status") == "passed" and (row.get("oracle_passed") is not True or row.get("work_observed") is not True):
            raise ValueError("passed trial lacks independent check or work evidence")
        expected_limit = None if row.get("scenario") == "v_projection_preserves_ray" else 128
        if row.get("max_rows") != expected_limit:
            raise ValueError("driver max_rows does not match the pinned scenario provider")
        expected_case = ORACLES[row["scenario"]]
        if row.get("input_sha256") != sha256_json(expected_case["inputs"]) or row.get("scenario_sha256") != sha256_json(expected_case):
            raise ValueError("trial input/scenario identity digest differs from pinned fixture")
        if row.get("status") == "passed":
            if row.get("result_kind") != expected_case["result_kind"]:
                raise ValueError("observed result representation kind differs from pinned fixture")
            expected_encoding = ("h_contradiction_row" if row["scenario"] == "unreachable_equality_target"
                                 else "v_generators" if row["scenario"] == "v_projection_preserves_ray" else "h_rows")
            if row.get("result_encoding") != expected_encoding:
                raise ValueError("observed result encoding differs from pinned fixture")
            if row.get("input_rows") != expected_case["input_rows"] or row.get("output_rows") != expected_case["output_rows"]:
                raise ValueError("observed input/output row counts differ from the pinned fixture")
        elif row.get("result_kind") not in (None, "") or row.get("result_encoding") not in (None, ""):
            raise ValueError("failed attempt must mark unobserved result representation as null")
        expected_peak = expected_case.get("expected_fm_peak_rows")
        if row.get("expected_fm_peak_rows") != expected_peak:
            raise ValueError("expected Fourier-Motzkin row peak differs from the pinned derivation")
        durations = row.get("durations_ns", {})
        if row.get("status") == "passed":
            for name in PHASES:
                value = durations.get(name)
                if value is None and name == "workspace_ns" and row["scenario"] != "v_projection_preserves_ray":
                    continue
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError("successful trial has invalid duration scopes")
    computed = summarize(trials, collection.get("measured_repetitions", 1),
                         collection.get("warmups_per_scenario", 0), warmup_trials,
                         collection.get("process_return_code", 0), collection.get("parse_errors", 0), collection.get("timed_out", False))
    if collection != computed:
        raise ValueError("saved summary differs from trial matrix")
