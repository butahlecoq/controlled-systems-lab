#!/usr/bin/env python3
"""Focused behavior check for the nominal surrogate's input cost."""
from __future__ import annotations

from fractions import Fraction as Q
import json

from tube_objective import SCENARIO_PATH, simulate
from check_tube_objective import run_vertex


def main() -> None:
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    scenario["nominal_plan"]["controls"] = ["1/8", "0", "0"]
    disturbances = (Q(0), Q(0), Q(0))

    built = simulate(scenario, disturbances)
    checked_actual, checked_nominal, _, _ = run_vertex(scenario, disturbances)
    assert Q(built["nominal_surrogate_cost"]) == checked_nominal
    assert checked_nominal > 0
    assert Q(built["nominal_surrogate_cost"]) == Q(9, 64)
    assert Q(built["actual_cost"]) == checked_actual
    print("nonzero nominal input cost check passed: 9/64")


if __name__ == "__main__":
    main()
