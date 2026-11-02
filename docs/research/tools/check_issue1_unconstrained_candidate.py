"""Independently replay the ignored Unconstrained MATLAB candidate for issue #1.

This transcribes the local candidate's finite affine game and nonlinear replay.
It does not execute MATLAB, establish that these bytes generated L04, or repair
the published terminal row.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any


SOURCE_FILES = {
    "Minmaxopenloop.m": {
        "bytes": 3244,
        "sha256": "bc45e3956992183ca10fef0b878116539c6888be2ccec4fe888d7e6d25bf26d6",
    },
    "program.m": {
        "bytes": 1388,
        "sha256": "835d8908a8b1422aa783d15a3a66245a67c5b6f1ef3a6b7b810628155b820d8b",
    },
}

INITIAL_LINEAR = (1194.0, 119520.0, 453.19, 45280.0)
TARGET = (1200.0, 0.0, 450.0, 0.0)
PUBLISHED_NONLINEAR = (1200.139, -2.294, 450.406, -16.254)
PUBLISHED_COST = 14.048
CONTROL_CATALOGUE = (1.0, 0.8, 0.0, -0.8, -1.0)
DISTURBANCE_CATALOGUE = ((-1.0, -1.0), (-1.0, 1.0), (1.0, -1.0), (1.0, 1.0))
STAGES = 4
STEPS_PER_STAGE = 2500
NONLINEAR_STEP_COUNT = STAGES * STEPS_PER_STAGE
ROUNDING_HALF_WIDTH = 0.0005


def norm_to_target(state: tuple[float, ...]) -> float:
    return math.sqrt(sum((value - target) ** 2 for value, target in zip(state, TARGET)))


def advance_linear(
    state: tuple[float, float, float, float],
    control: float,
    disturbance: tuple[float, float],
) -> tuple[float, float, float, float]:
    x1, x2, x3, x4 = state
    w1, w2 = disturbance
    return (
        x1 + 20.073 * control + 0.2 * w1,
        -25.0 * x1 + x2,
        x3 - 10.473 * control - 0.07 * w2,
        -25.0 * x3 + x4,
    )


def exact_finite_game() -> dict[str, Any]:
    plans = tuple(itertools.product(CONTROL_CATALOGUE, repeat=STAGES))
    histories = tuple(itertools.product(DISTURBANCE_CATALOGUE, repeat=STAGES))
    best_value = math.inf
    best_plans: list[tuple[float, ...]] = []
    best_witness: tuple[tuple[float, float], ...] | None = None
    best_terminal: tuple[float, ...] | None = None

    for plan in plans:
        worst_value = -math.inf
        worst_history = None
        worst_terminal = None
        for history in histories:
            state = INITIAL_LINEAR
            for control, disturbance in zip(plan, history):
                state = advance_linear(state, control, disturbance)
            value = norm_to_target(state)
            if value > worst_value:
                worst_value = value
                worst_history = history
                worst_terminal = state
        if worst_value < best_value - 1e-12:
            best_value = worst_value
            best_plans = [plan]
            best_witness = worst_history
            best_terminal = worst_terminal
        elif abs(worst_value - best_value) <= 1e-12:
            best_plans.append(plan)

    assert best_witness is not None and best_terminal is not None
    return {
        "plan_count": len(plans),
        "disturbance_histories_per_plan": len(histories),
        "minimax_value": best_value,
        "minimax_plans": best_plans,
        "selected_plan": best_plans[0],
        "worst_disturbance_history": best_witness,
        "worst_terminal_state": best_terminal,
    }


def nonlinear_flow(control_sum: float) -> tuple[float, float]:
    k = 8.0 / 3.0
    pressure = 528000.0
    inertia = 320.0
    c1, c2, c3, c4, c5 = 8.0 / 75.0, -6700.0, 9000.0, -15.0, -12.0
    delta_k = -4.0 / 125.0
    effective_k = k + delta_k + c1 * control_sum
    delta = effective_k - k
    adjusted_pressure = pressure + c2 * delta**2 + c3 * delta
    adjusted_inertia = inertia + c4 * delta**2 + c5 * delta
    fuel_flow = adjusted_pressure / adjusted_inertia / (1.0 + effective_k)
    oxidizer_flow = fuel_flow * effective_k
    return oxidizer_flow, fuel_flow


def nonlinear_replay(plan: tuple[float, ...]) -> tuple[float, float, float, float]:
    oxidizer_mass, fuel_mass = 119520.0, 45280.0
    control_sum = 0.0
    oxidizer_flow, fuel_flow = nonlinear_flow(control_sum)
    # Mirror program.m's t=2..10001 loop, including the final control change:
    # that change updates terminal flow but has no following stock integration.
    for t in range(2, NONLINEAR_STEP_COUNT + 2):
        if (t - 1) % STEPS_PER_STAGE == 0:
            stage = (t - 1) // STEPS_PER_STAGE
            control_sum += plan[stage - 1]
        next_oxidizer_flow, next_fuel_flow = nonlinear_flow(control_sum)
        oxidizer_mass -= oxidizer_flow / 100.0
        fuel_mass -= fuel_flow / 100.0
        oxidizer_flow, fuel_flow = next_oxidizer_flow, next_fuel_flow
    return oxidizer_flow, oxidizer_mass, fuel_flow, fuel_mass


def candidate_replays(selected_plan: tuple[float, ...]) -> dict[str, Any]:
    plans = tuple(itertools.product(CONTROL_CATALOGUE, repeat=STAGES))
    replayed = [(plan, nonlinear_replay(plan)) for plan in plans]
    distances = [
        math.sqrt(sum((value - target) ** 2 for value, target in zip(state, PUBLISHED_NONLINEAR)))
        for _, state in replayed
    ]
    nearest_distance = min(distances)
    nearest = [
        {"plan": plan, "terminal_state": state, "state_l2_error": distance}
        for (plan, state), distance in zip(replayed, distances)
        if abs(distance - nearest_distance) <= 1e-12
    ]
    selected_state = nonlinear_replay(selected_plan)
    within_rounding_box = [
        {"plan": plan, "terminal_state": state}
        for plan, state in replayed
        if all(abs(value - target) <= ROUNDING_HALF_WIDTH
               for value, target in zip(state, PUBLISHED_NONLINEAR))
    ]
    return {
        "plan_count": len(plans),
        "nonlinear_steps_per_plan": NONLINEAR_STEP_COUNT,
        "selected_minimax_plan_terminal_state": selected_state,
        "selected_minimax_plan_euclidean_cost": norm_to_target(selected_state),
        "nearest_published_state_replays": nearest,
        "within_published_three_decimal_rounding_box": within_rounding_box,
        "published_state_euclidean_cost": norm_to_target(PUBLISHED_NONLINEAR),
        "published_reported_cost": PUBLISHED_COST,
    }


def build_record() -> dict[str, Any]:
    linear_minimax = exact_finite_game()
    return {
        "schema": "csl.issue1-unconstrained-candidate-replay/1",
        "scope": "Independent binary64 transcription of a local ignored MATLAB candidate; not an L04 historical reproduction.",
        "source_candidate": {
            "local_path": "papers/Minimax/Unconstrained",
            "files": SOURCE_FILES,
            "execution": "MATLAB/Octave source not executed",
        },
        "linear_minimax": linear_minimax,
        "nonlinear_replay": candidate_replays(linear_minimax["selected_plan"]),
        "limitations": [
            "The source files are private ignored inputs and are identified by local hashes, not included here.",
            "The candidate's input and action catalogues differ from L04's published discrete fixture.",
            "The exhaustive transcription cannot establish which source version generated the printed paper row.",
        ],
    }


def verify_source_files(source_dir: Path) -> None:
    for name, expected in SOURCE_FILES.items():
        path = source_dir / name
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if len(raw) != expected["bytes"] or digest != expected["sha256"]:
            raise SystemExit(f"source identity mismatch: {path}")
    print("Issue #1 local MATLAB candidate source hashes verified")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-record", type=Path)
    parser.add_argument("--verify-record", type=Path)
    parser.add_argument("--source-dir", type=Path)
    args = parser.parse_args()
    if args.write_record and args.verify_record:
        parser.error("choose --write-record or --verify-record")
    if args.source_dir:
        verify_source_files(args.source_dir)
    record = build_record()
    encoded = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if args.verify_record:
        existing = args.verify_record.read_text(encoding="utf-8")
        if existing != encoded:
            raise SystemExit("candidate replay record differs from independent recomputation")
        print("Issue #1 candidate replay record verified")
    elif args.write_record:
        args.write_record.write_text(encoded, encoding="utf-8")
        print(f"Wrote {args.write_record}")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
