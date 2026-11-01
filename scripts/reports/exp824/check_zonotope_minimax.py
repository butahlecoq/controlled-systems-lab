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


def determinant(matrix: list[list[Fraction]]) -> Fraction:
    if not matrix:
        return Fraction(1)
    work = [row[:] for row in matrix]
    result = Fraction(1)
    for column in range(len(work)):
        pivot = next((row for row in range(column, len(work)) if work[row][column]), None)
        if pivot is None:
            return Fraction(0)
        if pivot != column:
            work[pivot], work[column] = work[column], work[pivot]
            result = -result
        value = work[column][column]
        result *= value
        for row in range(column + 1, len(work)):
            factor = work[row][column] / value
            for index in range(column + 1, len(work)):
                work[row][index] -= factor * work[column][index]
    return result


def matrix_rank(matrix: list[list[Fraction]]) -> int:
    if not matrix:
        return 0
    work = [row[:] for row in matrix]
    rows, columns = len(work), len(work[0])
    rank = 0
    for column in range(columns):
        pivot = next((row for row in range(rank, rows) if work[row][column]), None)
        if pivot is None:
            continue
        work[pivot], work[rank] = work[rank], work[pivot]
        divisor = work[rank][column]
        for index in range(column, columns):
            work[rank][index] /= divisor
        for row in range(rows):
            if row == rank:
                continue
            factor = work[row][column]
            if factor:
                for index in range(column, columns):
                    work[row][index] -= factor * work[rank][index]
        rank += 1
        if rank == rows:
            break
    return rank


def solve_square(matrix: list[list[Fraction]], vector: list[Fraction]) -> list[Fraction]:
    work = [row[:] + [value] for row, value in zip(matrix, vector)]
    size = len(work)
    for column in range(size):
        pivot = next((row for row in range(column, size) if work[row][column]), None)
        if pivot is None:
            raise ValueError("selected zonotope basis is singular")
        work[pivot], work[column] = work[column], work[pivot]
        divisor = work[column][column]
        work[column] = [value / divisor for value in work[column]]
        for row in range(size):
            if row != column:
                factor = work[row][column]
                work[row] = [left - factor * right for left, right in zip(work[row], work[column])]
    return [row[-1] for row in work]


def is_exact_finite_binary64(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        return False
    return math.isfinite(converted) and (not isinstance(value, int) or int(converted) == value)


def prepare_exact_zonotope_membership(stage: dict):
    """Prepare exact dyadic facet inequalities once for a stage's zonotope."""
    from itertools import combinations

    if not isinstance(stage, dict) or not isinstance(stage.get("center"), list):
        raise ValueError("zonotope stage center is missing or malformed")
    matrix = stage.get("generators")
    if not isinstance(matrix, dict):
        raise ValueError("zonotope generator matrix is missing or malformed")
    rows, count = matrix.get("rows"), matrix.get("cols")
    values = matrix.get("values")
    factors = stage.get("factors")
    if (not isinstance(rows, int) or isinstance(rows, bool) or rows < 0 or
            not isinstance(count, int) or isinstance(count, bool) or count < 0 or
            len(stage["center"]) != rows or not isinstance(values, list) or
            len(values) != rows * count or not isinstance(factors, list) or
            len(factors) != count):
        raise ValueError("zonotope center, factors, and generator matrix dimensions differ")
    center_values = stage["center"]
    if any(not is_exact_finite_binary64(value) for value in center_values + values):
        raise ValueError("zonotope center and generators must be exact finite binary64 values")
    center = [Fraction.from_float(float(value)) for value in center_values]
    count = matrix["cols"]
    generators = [[Fraction.from_float(float(values[row * count + column]))
                   for column in range(count)] for row in range(matrix["rows"])]
    basis_columns: list[int] = []
    current_rank = 0
    for column in range(count):
        candidate = basis_columns + [column]
        candidate_matrix = [[generators[row][index] for index in candidate]
                            for row in range(matrix["rows"])]
        rank_now = matrix_rank(candidate_matrix)
        if rank_now > current_rank:
            basis_columns.append(column)
            current_rank = rank_now
    rank = current_rank
    if rank == 0:
        return lambda point: list(point) == center

    basis = [[generators[row][column] for column in basis_columns]
             for row in range(matrix["rows"])]
    pivot_rows = next((rows for rows in combinations(range(matrix["rows"]), rank)
                       if determinant([[basis[row][column] for column in range(rank)]
                                       for row in rows]) != 0), None)
    if pivot_rows is None:
        raise ValueError("could not select independent zonotope coordinates")
    basis_square = [[basis[row][column] for column in range(rank)] for row in pivot_rows]

    def coordinates(vector: list[Fraction]) -> list[Fraction] | None:
        values = solve_square(basis_square, [vector[row] for row in pivot_rows])
        if any(sum((basis[row][column] * values[column] for column in range(rank)), Fraction(0))
               != vector[row] for row in range(matrix["rows"])):
            return None
        return values

    reduced_generators = [coordinates([generators[row][column]
                                       for row in range(matrix["rows"])])
                          for column in range(count)]
    if any(value is None for value in reduced_generators):
        raise ValueError("zonotope generator escaped its exact span")
    reduced = [value for value in reduced_generators if value is not None]

    # Every facet normal is orthogonal to r-1 independent generators in the
    # exact affine span. These inequalities characterize the zonotope.
    facets: list[tuple[list[Fraction], Fraction]] = []
    for selected in combinations(range(count), rank - 1):
        columns = [reduced[index] for index in selected]
        normal = []
        for row in range(rank):
            minor = [[columns[column][other] for column in range(rank - 1)]
                     for other in range(rank) if other != row]
            normal.append(((-1) ** row) * determinant(minor))
        if all(value == 0 for value in normal):
            continue
        support = sum((abs(sum((normal[row] * reduced[column][row]
                               for row in range(rank)), Fraction(0)))
                       for column in range(count)), Fraction(0))
        facets.append((normal, support))

    def contains(point: list[Fraction]) -> bool:
        if len(point) != rows:
            raise ValueError("point dimension differs from the zonotope")
        displacement = [value - origin for value, origin in zip(point, center)]
        target = coordinates(displacement)
        if target is None:
            return False
        return all(abs(sum((normal[row] * target[row] for row in range(rank)), Fraction(0))) <= support
                   for normal, support in facets)

    return contains


def trace_stage_contains_exact_zonotope(stage: dict, states: set[tuple[int, ...]], scale: int) -> None:
    contains = prepare_exact_zonotope_membership(stage)
    for state in states:
        point = [Fraction(coordinate, scale) for coordinate in state]
        if not contains(point):
            raise ValueError("an exact finite-history state is outside the full zonotope")


def check_membership_fixtures() -> None:
    sheared = {
        "center": [0.0, 0.0, 0.0, 0.0],
        "factors": [0.0, 0.0],
        "generators": {"rows": 4, "cols": 2, "values": [1.0, 1.0, 0.0, 1.0,
                                                              0.0, 0.0, 0.0, 0.0]},
    }
    contains_sheared = prepare_exact_zonotope_membership(sheared)
    if not contains_sheared([Fraction(1, 2), Fraction(1, 2), Fraction(0), Fraction(0)]):
        raise ValueError("exact zonotope checker rejected an interior point in a rank-two zonotope")
    if contains_sheared([Fraction(-1), Fraction(1), Fraction(0), Fraction(0)]):
        raise ValueError("exact zonotope checker accepted a point inside the bounding box but outside the zonotope")
    if contains_sheared([Fraction(0), Fraction(0), Fraction(0), Fraction(1)]):
        raise ValueError("exact zonotope checker ignored the lower-dimensional affine span")

    segment = {"center": [0.0, 0.0],
               "factors": [0.0],
               "generators": {"rows": 2, "cols": 1, "values": [1.0, 0.0]}}
    contains_segment = prepare_exact_zonotope_membership(segment)
    if not contains_segment([Fraction(1, 2), Fraction(0)]) or contains_segment(
            [Fraction(1, 2), Fraction(1, 100)]):
        raise ValueError("exact zonotope checker mishandled a rank-one set")

    point = {"center": [0.25, -0.5],
             "factors": [],
             "generators": {"rows": 2, "cols": 0, "values": []}}
    contains_point = prepare_exact_zonotope_membership(point)
    if not contains_point([Fraction(1, 4), Fraction(-1, 2)]) or contains_point(
            [Fraction(1, 4), Fraction(-1, 2) + Fraction(1, 1000)]):
        raise ValueError("exact zonotope checker mishandled a singleton")

    malformed = dict(sheared, factors=[0.0])
    try:
        prepare_exact_zonotope_membership(malformed)
    except ValueError:
        pass
    else:
        raise ValueError("exact zonotope checker accepted a factor/generator dimension mismatch")

    for invalid_center in ([9007199254740993], [10 ** 309]):
        invalid = {"center": invalid_center, "factors": [],
                   "generators": {"rows": 1, "cols": 0, "values": []}}
        try:
            prepare_exact_zonotope_membership(invalid)
        except ValueError:
            pass
        else:
            raise ValueError("exact zonotope checker accepted an integer altered by binary64 conversion")


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


def parallelotope_corner_score(trace: dict) -> tuple[float, int]:
    frame = trace["frame"]
    if frame["rows"] != 4 or frame["cols"] != 4:
        raise ValueError("parallelotope candidate frame is not four dimensional")
    q = frame["values"]
    terminal = trace["stages"][-1]
    maximum = -math.inf
    for mask in range(16):
        y = [terminal["upper"][i] if mask & (1 << i) else terminal["lower"][i] for i in range(4)]
        x = [sum(q[row * 4 + col] * y[col] for col in range(4)) for row in range(4)]
        maximum = max(maximum, (x[0] - x[2]) ** 2)
    return maximum, 16


def check_exact_replay(replay: dict, actions: tuple[int, ...]) -> Fraction:
    history_indices = replay["disturbance_indices"]
    if len(actions) != 3 or len(history_indices) != 3 or any(i not in range(3) for i in history_indices):
        raise ValueError("selected replay omits a stage or uses an invalid disturbance")
    state = (9000, 0, 0, 0)
    path = [state]
    for action, disturbance_index in zip(actions, history_indices):
        state = two_points_reference.step(state, ACTION_CODES[action], DISTURBANCES[disturbance_index])
        path.append(state)
    expected_path = [[coordinate / SCALE for coordinate in row] for row in path]
    if len(replay["path"]) != len(expected_path) or any(
            not close(actual, expected) for actual_row, expected_row in zip(replay["path"], expected_path)
            for actual, expected in zip(actual_row, expected_row)):
        raise ValueError("selected replay path differs from the exact rational transition")
    value = Fraction((state[0] - state[2]) ** 2, SCALE ** 2)
    if not close(replay["worst_value"], float(value)):
        raise ValueError("selected replay objective differs from its exact terminal state")
    worst = Fraction(-1)
    for history in product(DISTURBANCES, repeat=3):
        terminal = (9000, 0, 0, 0)
        for action, disturbance in zip(actions, history):
            terminal = two_points_reference.step(terminal, ACTION_CODES[action], disturbance)
        worst = max(worst, Fraction((terminal[0] - terminal[2]) ** 2, SCALE ** 2))
    if value != worst:
        raise ValueError("selected witness is not worst case over all disturbance histories")
    return value


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
    check_membership_fixtures()
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
            trace_stage_contains_exact_zonotope(stage, states, SCALE)
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
    parallel_method=result["parallelotope_minimax_method"]
    parallel_attempts=parallel_method["plan_attempts"]
    if parallel_method.get("candidate_search_coverage")!="complete" or len(parallel_attempts)!=len(expected_plans):
        raise ValueError("parallelotope candidate search omitted fixed plans")
    parallel_scores=[]
    for attempt,actions in zip(parallel_attempts,expected_plans):
        if attempt.get("status")!="scored" or attempt.get("action_indices")!=list(actions):
            raise ValueError("parallelotope attempts are incomplete or reordered")
        trace=attempt["stages"]
        check_parallelotope_trace({"stages":trace},actions)
        score,corners=parallelotope_corner_score(trace)
        if attempt.get("corners_evaluated")!=corners or not close(attempt["candidate_score"],score):
            raise ValueError("parallelotope score differs from exhaustive frame-box corner evaluation")
        parallel_scores.append(score)
    parallel_index=parallel_method["selected_candidate_attempt_index"]
    if not 0<=parallel_index<len(parallel_attempts) or parallel_index!=min(
            range(len(parallel_scores)),key=parallel_scores.__getitem__):
        raise ValueError("parallelotope selector did not choose the stable first minimum candidate")
    parallel_actions=tuple(parallel_method["selected_action_indices"])
    if parallel_attempts[parallel_index]["action_indices"]!=list(parallel_actions):
        raise ValueError("parallelotope selected index and action sequence differ")
    if parallelotope.get("plan_source")!="parallelotope-selected fixed open-loop plan":
        raise ValueError("parallelotope trace does not show the selector's selected plan")
    check_parallelotope_trace(parallelotope,parallel_actions)
    parallel_replay_value=check_exact_replay(parallel_method["selected_replay"],parallel_actions)

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
    method_names = ("exact_finite_minimax", "outer_box_selector", "zonotope_selector", "parallelotope_selector")
    expected_values = {
        method_names[0]: result["exact_reference"]["finite_minimax_value"],
        method_names[1]: result["box_method"]["full_catalogue_replay_value"],
        method_names[2]: replay["worst_value"],
        method_names[3]: float(parallel_replay_value),
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
        "stage_zonotope_relation": "all exact finite-history states checked against every exact facet inequality in each stored dyadic zonotope, including its affine span",
        "stage_parallelotope_relation": "all exact finite-history states independently transformed into the fixed frame and checked in four-dimensional coordinate bounds",
        "planar_zonotope_inclusion": "all finite terminal points checked inside axis-aligned zonotopes for all three plans; complete finite-set inclusion in this 2D fixture",
        "planar_exact_minimax_value": planar["exact_finite_minimax_value"],
        "parallelotope_candidate_score_evidence": "all 27 scores independently recomputed on all 16 frame-box corners; not a validated objective bound",
        "parallelotope_selected_plan_replay": "exact rational transition and every disturbance history checked",
        "timing_status": "28 completed raw samples across four methods; returned values match independently checked outcomes",
        "performance_claim": "descriptive timings only; no winner or speedup claim",
    }


if __name__ == "__main__":
    try:
        checked = main(Path(sys.argv[1]))
        print(json.dumps(checked, indent=2, sort_keys=True))
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(f"Issue 824 zonotope minimax check failed: {error}") from error
