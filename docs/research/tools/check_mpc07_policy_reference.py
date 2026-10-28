#!/usr/bin/env python3
"""Check the exact two-step policy example in mpc07-source-audit.md."""

from fractions import Fraction as F
from itertools import product
import json


def main() -> None:
    disturbance = tuple(product((F(-1), F(1)), repeat=2))
    fixed_states = []
    feedback_states = []
    fixed_costs = []
    feedback_costs = []

    for w0, w1 in disturbance:
        stage_one = (F(0), w0)
        fixed = (w0, w0 + w1)
        feedback = (w0 / 2, w1)
        assert all(-2 <= coordinate <= 2 for coordinate in stage_one)
        fixed_states.append(fixed)
        feedback_states.append(feedback)
        fixed_costs.append(fixed[1] ** 2)
        feedback_costs.append(feedback[1] ** 2)

    assert len(disturbance) == 4
    assert all(-2 <= coordinate <= 2 for state in fixed_states + feedback_states for coordinate in state)
    assert all(F(-1) <= state[0] <= F(1) for state in fixed_states + feedback_states)
    assert all(F(-1) <= w0 <= F(1) for w0, _ in disturbance)  # |u_1|=|-w_0|.
    assert max(fixed_costs) == 4
    assert max(feedback_costs) == 1

    print(json.dumps({
        "schema": "csl.mpc07-policy-reference-check/1",
        "disturbance_vertices": len(disturbance),
        "fixed_plan_worst_terminal_cost": str(max(fixed_costs)),
        "causal_affine_worst_terminal_cost": str(max(feedback_costs)),
        "fixed_plan_terminal_state_bounds": [["-1", "1"], ["-2", "2"]],
        "feedback_terminal_state_bounds": [["-1/2", "1/2"], ["-1", "1"]],
        "state_and_control_containment": "pass",
    }, indent=2))


if __name__ == "__main__":
    main()
