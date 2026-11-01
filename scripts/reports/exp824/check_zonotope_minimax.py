#!/usr/bin/env python3
"""Independently check the finite-catalog zonotope selector record."""
from __future__ import annotations

from fractions import Fraction
from itertools import product
import json
import math
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mpc05"))
import reference as two_points_reference
import check_two_points_box

SCALE = two_points_reference.SCALE
ACTION_CODES = two_points_reference.ACTION_CODES
DISTURBANCES = two_points_reference.DISTURBANCES


def close(left: float, right: float, tolerance: float = 5e-10) -> bool:
    return abs(left - right) <= tolerance * max(1.0, abs(left), abs(right))


def exact_states(action_indices: tuple[int, ...]) -> list[set[tuple[int, ...]]]:
    states = [{(9000, 0, 0, 0)}]
    for stage, action_index in enumerate(action_indices):
        next_states = {two_points_reference.step(state, ACTION_CODES[action_index], disturbance)
                       for state in states[-1] for disturbance in DISTURBANCES}
        states.append(next_states)
    return states


def trace_stage_contains_coordinates(stage: dict, states: set[tuple[int, ...]], scale: int) -> None:
    center = [Fraction.from_float(value) for value in stage["center"]]
    matrix = stage["generators"]
    generators = matrix["cols"]
    if (len(center) != matrix["rows"] or len(stage["factors"]) != generators or
            len(matrix["values"]) != matrix["rows"] * generators):
        raise ValueError("zonotope stage dimensions differ")
    values = [Fraction.from_float(value) for value in matrix["values"]]
    for state in states:
        for row, coordinate in enumerate(state):
            radius = sum((abs(values[row * generators + column])
                          for column in range(generators)), Fraction(0))
            point = Fraction(coordinate, scale)
            if not center[row] - radius <= point <= center[row] + radius:
                raise ValueError("an exact state coordinate falls outside its zonotope coordinate bounds")


def check_parallelotope_trace(method: dict, actions: tuple[int, ...]) -> None:
    trace=method["stages"]
    expected_frame=[[1,1,0,0],[0,1,1,0],[0,0,1,1],[0,0,0,1]]
    frame=trace["frame"]
    if frame["rows"]!=4 or frame["cols"]!=4 or frame["values"]!=[x for row in expected_frame for x in row]:
        raise ValueError("parallelotope frame differs from the declared fixed shear")
    inverse=[[1,-1,1,-1],[0,1,-1,1],[0,0,1,-1],[0,0,0,1]]
    stages=trace["stages"]
    state_layers=exact_states(actions)
    if len(stages)!=len(state_layers):
        raise ValueError("parallelotope trace omits a stage")
    for stage,states in zip(stages,state_layers):
        lower=[Fraction.from_float(x) for x in stage["lower"]]
        upper=[Fraction.from_float(x) for x in stage["upper"]]
        if len(lower)!=4 or len(upper)!=4:
            raise ValueError("parallelotope coordinate dimension differs from four")
        for state in states:
            for row in range(4):
                y=sum((inverse[row][col]*Fraction(coordinate,SCALE)
                       for col,coordinate in enumerate(state)),Fraction(0))
                if not lower[row]<=y<=upper[row]:
                    raise ValueError("an exact finite-history state is outside the 4D parallelotope")


def factor_corner_score(stage: dict, objective) -> tuple[float, int]:
    center = stage["center"]
    matrix = stage["generators"]
    count = matrix["cols"]
    maximum = -math.inf
    for signs in product((-1.0, 1.0), repeat=count):
        point = list(center)
        for column, sign in enumerate(signs):
            for row in range(matrix["rows"]):
                point[row] += sign * matrix["values"][row * count + column]
        maximum = max(maximum, objective(point))
    return maximum, 1 << count


def checked_planar_inclusion(example: dict) -> None:
    if example.get("dynamics") != "x_next = x + (u, w)":
        raise ValueError("planar example does not identify its dynamics")
    if example.get("candidate_search_coverage") != "complete" or len(example.get("plans", [])) != 3:
        raise ValueError("planar candidate table is incomplete")
    expected_controls = (-1.0, 0.0, 1.0)
    expected_points = example.get("terminal_catalogue_by_control")
    if len(expected_points) != 3:
        raise ValueError("planar exact terminal catalogues are missing")
    for index, (plan, control, points) in enumerate(zip(example["plans"], expected_controls, expected_points)):
        if plan["action_indices"] != [index] or plan["control"] != control:
            raise ValueError("planar control ordering changed")
        trace = plan["stages"]
        if len(trace) != 2:
            raise ValueError("planar selector trace must contain both state stages")
        stage = trace[-1]
        center = [Fraction.from_float(value) for value in stage["center"]]
        matrix = stage["generators"]
        count = matrix["cols"]
        values = [Fraction.from_float(value) for value in matrix["values"]]
        for column in range(count):
            if values[column] != 0 and values[count + column] != 0:
                raise ValueError("planar selector generators are not axis aligned")
        radii = [sum((abs(values[row * count + column]) for column in range(count)), Fraction(0))
                 for row in range(2)]
        for point in points:
            exact = [Fraction.from_float(value) for value in point]
            if any(not center[row] - radii[row] <= exact[row] <= center[row] + radii[row]
                   for row in range(2)):
                raise ValueError("an exact planar terminal vertex is outside its complete axis-aligned zonotope")
        value, corners = factor_corner_score(stage, lambda point: point[0] ** 2 + point[1] ** 2)
        if plan["factor_corners_evaluated"] != corners or not close(plan["candidate_score"], value):
            raise ValueError("planar candidate score does not match exhaustive factor-corner evaluation")
    if example["selected_candidate_attempt_index"] != 1 or example["selected_action_indices"] != [1]:
        raise ValueError("planar selector did not choose the zero-control plan")
    if not close(example["selected_replay_value"], 1.0) or not close(example["exact_finite_minimax_value"], 1.0):
        raise ValueError("planar selected replay differs from the exact finite minimax value")


def main(path: Path) -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("schema") != "csl.issue824-two-points-zonotope-minimax/1":
        raise ValueError("unexpected issue824 zonotope minimax schema")
    legacy = dict(result)
    legacy["schema"] = "csl.issue824-two-points-box-minimax/2"
    with tempfile.TemporaryDirectory() as directory:
        baseline_path = Path(directory) / "baseline.json"
        baseline_path.write_text(json.dumps(legacy), encoding="utf-8")
        baseline_check = check_two_points_box.main(baseline_path, check_planar_example=False)

    method = result["zonotope_minimax_method"]
    attempts = method["plan_attempts"]
    expected_plans = list(product(range(3), repeat=3))
    if method.get("candidate_search_coverage") != "complete" or len(attempts) != len(expected_plans):
        raise ValueError("TwoPoints zonotope selector omitted fixed-plan candidate scores")
    exact_reference = result["exact_reference"]["finite_minimax_value"]
    _, _, _, exact_value = two_points_reference.reference()
    if not close(exact_reference, float(exact_value)) or not close(
            baseline_check["exact_finite_minimax_value"], float(exact_value)):
        raise ValueError("exact TwoPoints reference differs from the independent rational value")

    scores: list[float] = []
    for attempt, actions in zip(attempts, expected_plans):
        if attempt.get("status") != "scored" or attempt.get("action_indices") != list(actions):
            raise ValueError("TwoPoints zonotope candidate attempts are incomplete or reordered")
        stages = attempt.get("stages", [])
        if len(stages) != 4:
            raise ValueError("each TwoPoints zonotope candidate needs four stages")
        state_layers = exact_states(actions)
        for stage_index, (stage, states) in enumerate(zip(stages, state_layers)):
            if stage["generators"]["rows"] != 4:
                raise ValueError("TwoPoints candidate changed the four-state dimension")
            trace_stage_contains_coordinates(stage, states, SCALE)
        terminal = stages[-1]
        candidate, corner_count = factor_corner_score(terminal, lambda point: (point[0] - point[2]) ** 2)
        if (attempt["terminal_generators"] != terminal["generators"]["cols"] or
                attempt["factor_corners_evaluated"] != corner_count or
                not close(attempt["candidate_score"], candidate)):
            raise ValueError("TwoPoints candidate score differs from exhaustive factor-corner evaluation")
        scores.append(attempt["candidate_score"])

    selected_index = method["selected_candidate_attempt_index"]
    if not 0 <= selected_index < len(attempts):
        raise ValueError("selected candidate index is out of range")
    if selected_index != min(range(len(scores)), key=scores.__getitem__):
        raise ValueError("selected plan is not the stable first minimum candidate score")
    selected_attempt = attempts[selected_index]
    if selected_attempt["action_indices"] != method["selected_action_indices"]:
        raise ValueError("selected plan indices differ from the scored candidate row")
    parallelotope=result["parallelotope_method"]
    if parallelotope.get("relation")!="outer" or parallelotope.get("status")!="numerical outer fixed-frame parallelotope recurrence":
        raise ValueError("parallelotope relation/status metadata changed")
    check_parallelotope_trace(parallelotope,tuple(method["selected_action_indices"]))

    replay = method["selected_replay"]
    action_indices = tuple(method["selected_action_indices"])
    disturbances = replay["disturbance_indices"]
    disturbance_values = replay["disturbances"]
    if len(action_indices) != 3 or len(disturbances) != 3 or len(disturbance_values) != 3:
        raise ValueError("selected replay does not include every stage")
    if any(index not in range(3) for index in disturbances):
        raise ValueError("selected replay disturbance index is outside its catalogue")
    expected_disturbances = [DISTURBANCES[index] for index in disturbances]
    if disturbance_values != [[float(value)] for value in expected_disturbances]:
        raise ValueError("selected replay disturbance values differ from their catalogue indices")
    state = (9000, 0, 0, 0)
    path = [state]
    for action_index, disturbance in zip(action_indices, expected_disturbances):
        state = two_points_reference.step(state, ACTION_CODES[action_index], disturbance)
        path.append(state)
    expected_path = [[coordinate / SCALE for coordinate in row] for row in path]
    if len(replay["path"]) != len(expected_path) or any(
            not close(actual, expected)
            for actual_row, expected_row in zip(replay["path"], expected_path)
            for actual, expected in zip(actual_row, expected_row)):
        raise ValueError("selected replay path differs from the exact rational transition")
    replay_value = Fraction((state[0] - state[2]) ** 2, SCALE ** 2)
    if not close(replay["worst_value"], float(replay_value)):
        raise ValueError("selected replay objective differs from its exact terminal state")
    worst = Fraction(-1)
    for history in product(DISTURBANCES, repeat=3):
        terminal = (9000, 0, 0, 0)
        for action_index, disturbance in zip(action_indices, history):
            terminal = two_points_reference.step(terminal, ACTION_CODES[action_index], disturbance)
        worst = max(worst, Fraction((terminal[0] - terminal[2]) ** 2, SCALE ** 2))
    if replay_value != worst:
        raise ValueError("selected witness is not worst case over the full disturbance catalog")
    if replay_value < exact_value:
        raise ValueError("selected finite plan has a value below the exhaustive minimax reference")

    planar = result["planar_selector_example"]
    checked_planar_inclusion(planar)
    timing = result["timing"]
    method_names = ("exact_finite_minimax", "outer_box_selector", "zonotope_selector")
    expected_values = {
        method_names[0]: result["exact_reference"]["finite_minimax_value"],
        method_names[1]: result["box_method"]["full_catalogue_replay_value"],
        method_names[2]: replay["worst_value"],
    }
    repetitions = timing.get("measurement_repetitions_per_method")
    if (timing.get("schema") != "csl.issue824-zonotope-minimax-timing/1" or
            timing.get("warmup_runs_per_method") != 1 or repetitions != 7):
        raise ValueError("timing record does not have the declared warmup and repetition profile")
    samples = timing.get("samples", [])
    if len(samples) != repetitions * len(method_names):
        raise ValueError("timing record omits a method/repetition sample")
    durations = {method: [] for method in method_names}
    for sample in samples:
        repetition = sample["repetition"]
        offset = sample["order_in_repetition"]
        expected_method = method_names[(repetition + offset) % len(method_names)]
        method = sample["method"]
        if (method != expected_method or sample.get("status") != "completed" or
                sample.get("elapsed_ns", 0) <= 0 or
                not close(sample["returned_value"], expected_values[method])):
            raise ValueError("timed method order, work status or returned value is invalid")
        durations[method].append(sample["elapsed_ns"])
    summaries = {row["method"]: row for row in timing.get("summaries", [])}
    if set(summaries) != set(method_names):
        raise ValueError("timing summaries omit or duplicate a method")
    for method, values in durations.items():
        ordered = sorted(values)
        summary = summaries[method]
        if (len(values) != repetitions or summary.get("repetitions") != repetitions or
                summary.get("failures") != 0 or summary.get("minimum_ns") != ordered[0] or
                summary.get("median_ns") != ordered[len(ordered) // 2] or
                summary.get("maximum_ns") != ordered[-1]):
            raise ValueError("timing summary differs from its raw samples")
    return {
        "schema": "csl.issue824-two-points-zonotope-minimax-check/1",
        "status": "verified",
        "scope": "stored binary64 adaptation and declared finite catalogs",
        "exact_minimax_value": float(exact_value),
        "selected_plan_replay_value": float(replay_value),
        "exact_reference_state_path": baseline_check["exact_reference_state_path"],
        "selected_plan_state_path": baseline_check["selected_plan_state_path"],
        "candidate_search": "all 27 plans received a complete numerical factor-corner score",
        "candidate_score_evidence": "independently recomputed on every stored terminal factor corner; not a validated objective bound",
        "selected_plan_replay": "exact rational transition and every disturbance history checked",
        "stage_zonotope_relation": "all exact state coordinates checked against dyadic center +/- sum(abs(generators)); not full four-dimensional membership",
        "stage_parallelotope_relation": "all exact finite-history states independently transformed into the fixed frame and checked in four-dimensional coordinate bounds",
        "planar_zonotope_inclusion": "all finite terminal points checked inside axis-aligned zonotopes for all three plans; complete finite-set inclusion in this 2D fixture",
        "planar_exact_minimax_value": planar["exact_finite_minimax_value"],
        "timing_status": "21 completed raw samples across three methods; returned values match independently checked outcomes",
        "performance_claim": "descriptive timings only; no winner or speedup claim",
    }


if __name__ == "__main__":
    try:
        checked = main(Path(sys.argv[1]))
        print(json.dumps(checked, indent=2, sort_keys=True))
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(f"Issue 824 zonotope minimax check failed: {error}") from error
