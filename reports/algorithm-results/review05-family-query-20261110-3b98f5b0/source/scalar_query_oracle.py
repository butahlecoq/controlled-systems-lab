"""Literal exact-dyadic oracle for the authored scalar query fixtures."""
from fractions import Fraction
import math


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("history values must be finite numbers")
    return Fraction(value)


def verify_history(states, controls, reported_objective, horizon, terminal_coefficient):
    if horizon not in (2, 4, 8) or terminal_coefficient not in (0, 1):
        raise ValueError("unsupported literal query fixture")
    if len(states) != horizon + 1 or len(controls) != horizon:
        raise ValueError("history length mismatch")
    if any(not isinstance(row, list) or len(row) != 1 for row in states + controls):
        raise ValueError("scalar history coordinates required")
    x = [number(row[0]) for row in states]
    u = [number(row[0]) for row in controls]
    if x[0] != 0:
        raise ValueError("initial state must be zero")
    for k in range(horizon):
        if not 0 <= u[k] <= 1 or x[k+1] != x[k] + u[k]:
            raise ValueError("literal dynamics or control bounds violated")
    objective = terminal_coefficient * x[-1]
    if number(reported_objective) != objective:
        raise ValueError("reported objective differs from original fixture objective")
    if objective != 0:
        raise ValueError("history is feasible but not optimal for the literal fixture")
    return True
