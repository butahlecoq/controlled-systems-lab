"""Exact arithmetic for the bounded B04-C corrected-track profile.

Finite inputs are first parsed as binary64, then interpreted as the exact
dyadic values of those bits, following ADR 0003. Acceptance-band edges remain
the exact decimal rationals registered in issue #531.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
import math

F = Fraction
HORIZON = 16


def dyadic(value: str) -> F:
    """Return the exact rational represented by parsing ``value`` as double."""
    parsed = float(F(value))
    if not math.isfinite(parsed):
        raise ValueError("profile inputs must be finite binary64 values")
    return F.from_float(parsed)


def dot(lhs: tuple[F, ...] | list[F], rhs: tuple[F, ...] | list[F]) -> F:
    return sum((a * b for a, b in zip(lhs, rhs)), F(0))


@dataclass(frozen=True)
class Profile:
    initial: tuple[F, ...]
    transition: tuple[tuple[F, ...], ...]
    input_vector: tuple[F, ...]
    feature_matrix: tuple[tuple[F, ...], ...]
    feature_offset: tuple[F, ...]
    feature_weights: tuple[F, ...]
    phase_bounds: tuple[tuple[int, F, F], ...]


def profile() -> Profile:
    initial = tuple(dyadic(value) for value in (
        "1220.28265395983", "119500", "440.005764648976", "45300"))
    transition = tuple(tuple(
        F(1) if row == column else F(-25, 4) if (row, column) in ((1, 0), (3, 2)) else F(0)
        for column in range(4)) for row in range(4))
    input_vector = (dyadic("2208/110"), F(0), dyadic("-1152/110"), F(0))
    # The source criterion has separate 64/9 and 8/3 coefficients. Each is
    # converted to binary64 first, then treated as an exact dyadic input.
    cross = dyadic("8/3")
    weight = dyadic("64/9")
    feature_matrix = (
        (F(-1), F(0), F(0), F(0)),
        (F(0), F(1), F(0), F(0)),
        (F(0), F(0), F(-1), F(0)),
        (F(0), F(0), F(0), F(1)),
        (F(0), F(1), F(0), -cross),
    )
    feature_offset = (F(1200), F(0), F(450), F(0), F(0))
    feature_weights = (F(1), F(1), weight, weight, F(1))
    phases = tuple(
        (coordinate, F(lower), F(upper))
        for coordinate, lower, upper in ((0, 1176, 1224), (2, 432, 468)))
    return Profile(initial, transition, input_vector, feature_matrix,
                   feature_offset, feature_weights, phases)


def affine_states(model: Profile) -> tuple[tuple[tuple[F, ...], ...], ...]:
    """Return stage maps ``x[t] = offset[t] + matrix[t] @ controls``."""
    n = HORIZON
    offsets: list[tuple[F, ...]] = [model.initial]
    matrices: list[tuple[tuple[F, ...], ...]] = [
        tuple(tuple(F(0) for _ in range(n)) for _ in range(4))]
    for stage in range(n):
        previous_offset = offsets[-1]
        previous_matrix = matrices[-1]
        next_offset = tuple(dot(row, previous_offset) for row in model.transition)
        next_matrix = tuple(tuple(
            dot(model.transition[state], tuple(previous_matrix[k][control] for k in range(4)))
            + (model.input_vector[state] if control == stage else F(0))
            for control in range(n)) for state in range(4))
        offsets.append(next_offset)
        matrices.append(next_matrix)
    return tuple((offset, matrix) for offset, matrix in zip(offsets, matrices))


def replay(model: Profile, controls: tuple[F, ...] | list[F]) -> tuple[tuple[F, ...], ...]:
    if len(controls) != HORIZON:
        raise ValueError("B04-C requires exactly sixteen controls")
    states = [model.initial]
    for control in controls:
        states.append(tuple(
            dot(model.transition[state], states[-1]) + model.input_vector[state] * control
            for state in range(4)))
    return tuple(states)


def features(model: Profile, terminal: tuple[F, ...]) -> tuple[F, ...]:
    return tuple(dot(row, terminal) + offset
                 for row, offset in zip(model.feature_matrix, model.feature_offset))


def objective_squared(model: Profile, terminal: tuple[F, ...]) -> F:
    values = features(model, terminal)
    return sum((weight * value * value
                for weight, value in zip(model.feature_weights, values)), F(0))


def constraints(model: Profile) -> tuple[tuple[str, tuple[F, ...], F], ...]:
    """Return the control-space H rows ``a @ u <= b`` for all hard bounds."""
    state_maps = affine_states(model)
    rows: list[tuple[str, tuple[F, ...], F]] = []
    for stage in range(HORIZON):
        row = tuple(F(1) if control == stage else F(0) for control in range(HORIZON))
        rows.append((f"control/{stage}/upper", row, F(1)))
        rows.append((f"control/{stage}/lower", tuple(-v for v in row), F(1)))
    for stage, (offset, matrix) in enumerate(state_maps):
        for coordinate, lower, upper in model.phase_bounds:
            row = tuple(matrix[coordinate])
            rows.append((f"phase/{stage}/{coordinate}/upper", row, upper - offset[coordinate]))
            rows.append((f"phase/{stage}/{coordinate}/lower", tuple(-v for v in row),
                         offset[coordinate] - lower))
    return tuple(rows)


def terminal_feature_map(model: Profile) -> tuple[tuple[F, ...], tuple[tuple[F, ...], ...]]:
    offset, state_matrix = affine_states(model)[-1]
    feature_offset = tuple(dot(row, offset) + value
                           for row, value in zip(model.feature_matrix, model.feature_offset))
    feature_matrix = tuple(tuple(
        sum((model.feature_matrix[feature][state] * state_matrix[state][control]
             for state in range(4)), F(0))
        for control in range(HORIZON)) for feature in range(5))
    return feature_offset, feature_matrix


def weighted_inner(model: Profile, lhs: tuple[F, ...], rhs: tuple[F, ...]) -> F:
    return sum((weight * a * b for weight, a, b
                in zip(model.feature_weights, lhs, rhs)), F(0))


def correct_candidate(model: Profile, candidate: tuple[F, ...]) -> tuple[tuple[F, ...], tuple[int, int]]:
    """Correct two controls so the exact convex objective gradient is zero."""
    if len(candidate) != HORIZON:
        raise ValueError("candidate must contain sixteen controls")
    offset, matrix = terminal_feature_map(model)
    residual = tuple(offset[i] + dot(matrix[i], candidate) for i in range(5))
    selected: tuple[int, int] | None = None
    for left, right in combinations(range(HORIZON), 2):
        a = tuple(matrix[i][left] for i in range(5))
        b = tuple(matrix[i][right] for i in range(5))
        aa = weighted_inner(model, a, a)
        ab = weighted_inner(model, a, b)
        bb = weighted_inner(model, b, b)
        if aa * bb - ab * ab:
            selected = left, right
            break
    if selected is None:
        raise ValueError("terminal residual map has rank below two")
    left, right = selected
    a = tuple(matrix[i][left] for i in range(5))
    b = tuple(matrix[i][right] for i in range(5))
    aa = weighted_inner(model, a, a)
    ab = weighted_inner(model, a, b)
    bb = weighted_inner(model, b, b)
    rhs_a = -weighted_inner(model, a, residual)
    rhs_b = -weighted_inner(model, b, residual)
    determinant = aa * bb - ab * ab
    corrected = list(candidate)
    corrected[left] += (rhs_a * bb - rhs_b * ab) / determinant
    corrected[right] += (aa * rhs_b - ab * rhs_a) / determinant
    return tuple(corrected), selected


def gradient(model: Profile, controls: tuple[F, ...]) -> tuple[F, ...]:
    offset, matrix = terminal_feature_map(model)
    residual = tuple(offset[i] + dot(matrix[i], controls) for i in range(5))
    return tuple(weighted_inner(model, tuple(matrix[i][control] for i in range(5)), residual)
                 for control in range(HORIZON))


def band_verdict(squared: F) -> str:
    low = F("30.8985") ** 2
    high = F("30.8995") ** 2
    if low <= squared <= high:
        return "within pre-registered confirmation band"
    if squared < low:
        return "below pre-registered lower band"
    return "above pre-registered upper band"
