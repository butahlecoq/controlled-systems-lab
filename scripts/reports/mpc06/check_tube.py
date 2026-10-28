#!/usr/bin/env python3
"""Independently check the dyadic nilpotent tube-MPC feasibility pilot."""
from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from fractions import Fraction as Q
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCENARIO = ROOT / "benchmarks/scenarios/mpc06-nilpotent-tube-v1.json"


def check_record(record: dict) -> dict:
    scenario_bytes = SCENARIO.read_bytes()
    scenario = json.loads(scenario_bytes)
    assert scenario["schema"] == "csl.mpc06-tube-input/1"
    assert scenario["scenario_id"] == record["case_id"]
    assert scenario["dynamics"]["A"] == [[1, 1], [0, 1]]
    assert scenario["dynamics"]["B"] == [[0], [1]]
    assert scenario["dynamics"]["E"] == [[0], [1]]
    assert scenario["feedback"]["K"] == [[-1, -2]]
    assert scenario["constraints"]["state_box"] == [[-1, 1], [-1, 1]]
    assert scenario["constraints"]["input_interval"] == [-1, 1]
    assert scenario["nominal_plan"]["controls"] == [0, 0, 0]
    assert record.get("scenario_sha256") == hashlib.sha256(scenario_bytes).hexdigest()
    assert record["schema"] == "csl.mpc06-nilpotent-tube-pilot/1"
    assert record["case_id"] == "double-integrator-nilpotent-tube-v1"
    build = record["build"]
    assert build["compiler_id"] and build["compiler_version"] and build["configuration"]
    measurement = record["measurement"]
    assert measurement["runs"] == 1 and measurement["warmups"] == 0
    assert measurement["requested_workers"] == measurement["actual_workers"] == 1
    assert measurement["requested_native_threads"] == measurement["actual_native_threads"] == 1
    assert measurement["parallelism"] == "single-threaded synchronous execution"
    assert measurement["errors"] == 0 and measurement["work_completed"]
    assert type(measurement["elapsed_ns"]) is int and measurement["elapsed_ns"] > 0
    assert measurement["performance_assessment"].startswith("inconclusive;")
    q = Q
    radius = q(1, 8)
    a = ((q(1), q(1)), (q(0), q(1)))
    b = (q(0), q(1))
    e = (q(0), q(1))
    k = (q(-1), q(-2))
    f = tuple(tuple(a[i][j] + b[i] * k[j] for j in range(2)) for i in range(2))
    f2 = tuple(tuple(sum(f[i][m] * f[m][j] for m in range(2))
                     for j in range(2)) for i in range(2))
    assert f == ((q(1), q(1)), (q(-1), q(-1))) and f2 == ((q(0), q(0)), (q(0), q(0)))
    assert record["feedback_matrix_matches_A_plus_BK"]
    assert record["nilpotent_index_2_verified"]

    # Z = D + FD for D = E[-1/8,1/8]. Set addition commutes, and F²=0.
    generators = ((q(0), q(1)), (q(1), q(-1)))
    supports = tuple(radius * sum(abs(g[i]) for g in generators) for i in range(2))
    input_support = radius * sum(abs(sum(k[i] * g[i] for i in range(2)))
                                 for g in generators)
    assert supports == (q(1, 8), q(1, 4)) and input_support == q(3, 8)
    assert tuple(map(q, record["state_tightening_support"])) == supports
    assert q(record["input_tightening_support"]) == input_support
    assert record["rpi_inclusion_exactly_verified"]
    assert record["initial_tube_membership"]
    assert record["nominal_plan_tightened_feasible"]
    assert record["empty_tightening_edge_case"]["empty_verified_by_support"]

    # Enumerate all disturbance vertices under the same fixed zero nominal plan.
    worst_state = q(0)
    worst_input = q(0)
    path_count = 0
    for mask in range(1 << record["horizon"]):
        state = (q(0), q(0))
        for stage in range(record["horizon"]):
            disturbance = radius if mask & (1 << stage) else -radius
            control = sum(k[i] * state[i] for i in range(2))
            next_state = (state[0] + state[1], state[1] + control + disturbance)
            assert max(abs(next_state[0]), abs(next_state[1])) <= 1
            assert abs(control) <= 1
            worst_state = max(worst_state, abs(next_state[0]), abs(next_state[1]))
            worst_input = max(worst_input, abs(control))
            state = next_state
        path_count += 1
    ref = record["matched_reference"]
    assert ref["disturbance_paths_checked"] == path_count == 8
    assert ref["all_paths_safe"]
    assert q(ref["worst_state_coordinate_abs"]) == worst_state == q(1, 4)
    assert q(ref["worst_feedback_input_abs"]) == worst_input == q(3, 8)

    error = (q(1, 8), q(-1, 4))
    unsafe_u = q(3, 4) + sum(k[i] * error[i] for i in range(2))
    unsafe = record["unsafe_nominal_plan_edge_case"]
    assert unsafe_u == q(9, 8) > 1
    assert q(unsafe["actual_input"]) == unsafe_u
    assert unsafe["rejected_by_tightened_bound_and_exact_input_bound"]
    assert record["objective"]["kind"] == "not evaluated"
    assert record["objective"]["nominal optimum"] == "not claimed"
    assert record["objective"]["minimax cost"] == "not claimed"
    return record


def check(executable: Path) -> dict:
    record = json.loads(subprocess.check_output([str(executable.resolve())], text=True))
    check_record(record)
    print("verified exact dyadic RPI identity, tightenings, 8 matched disturbance paths, and unsafe-plan witness")
    return record


if __name__ == "__main__":
    check(Path(sys.argv[1]))
