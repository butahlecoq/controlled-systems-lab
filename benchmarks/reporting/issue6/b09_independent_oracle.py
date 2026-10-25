"""Direct corner-history enumeration for the B09 affine source-reference case."""
from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path


ACTIONS = (1.0, 0.75, 0.5, 0.25, 0.0, -0.25, -0.5, -0.75, -1.0)
DISTURBANCES = ((-1.0, -1.0), (-1.0, 1.0), (1.0, -1.0), (1.0, 1.0))


def case(lambda_value: float) -> dict:
    k, p, inv, c1, c2, c3, c4, c5 = 2.5, 30240.0, 360.0, 0.1, -6700.0, 900.0, -15.0, -12.0
    dk = -0.03 * k
    km = k + dk
    delta = km - k
    pp = p + c2 * delta**2 + c3 * delta
    iu = inv + c4 * delta**2 + c5 * delta
    fuel_flow = pp / iu / (1.0 + km)
    initial = (fuel_flow * km, 18100.0, fuel_flow, 7150.0)
    b1 = c1*p/inv/(1+k) + c1*c3*k/inv/(1+k) - c1*p*k/inv/(1+k)**2 - c1*c5*p*k/inv**2/(1+k)
    b3 = -(c1*p/inv/(1+k)**2 + c1*c5*p/inv**2/(1+k) - c1*c3/inv/(1+k))
    b = (b1, 0.0, b3, 0.0)
    A = ((1,0,0,0), (-75,1,0,0), (0,0,1,0), (0,0,-75,1))
    W = ((0.06,0), (0,0), (0,-0.06), (0,0))

    def inside(x):
        return (57.5 <= x[0] <= 62.5 and -30 <= x[1] <= 20000 and
                23 <= x[2] <= 25 and -30 <= x[3] <= 8000)

    def cost(x):
        return ((x[0]-60)**2 + x[1]**2 + (x[2]-24)**2 + x[3]**2 +
                lambda_value*(x[1]-2.5*x[3])**2)

    best = math.inf
    winners = []
    feasible_count = 0
    for indices in itertools.product(range(len(ACTIONS)), repeat=4):
        points = [initial]
        feasible = True
        for index in indices:
            control = ACTIONS[index]
            successors = []
            for state in points:
                for disturbance in DISTURBANCES:
                    nxt = tuple(sum(A[i][j]*state[j] for j in range(4)) + b[i]*control +
                                 sum(W[i][j]*disturbance[j] for j in range(2)) for i in range(4))
                    if not inside(nxt):
                        feasible = False
                        break
                    successors.append(nxt)
                if not feasible:
                    break
            if not feasible:
                break
            points = successors
        if not feasible:
            continue
        feasible_count += 1
        worst = max(cost(point) for point in points)
        if worst < best - 1e-9:
            best, winners = worst, [indices]
        elif abs(worst-best) <= 1e-9:
            winners.append(indices)
    return {"lambda": lambda_value, "method": "direct enumeration of all action plans and disturbance-corner histories",
            "plan_count": len(ACTIONS)**4, "feasible_plan_count": feasible_count,
            "oracle_worst_squared_minimum": best, "oracle_worst_norm_minimum": math.sqrt(best),
            "winning_action_indices": [list(plan) for plan in winners], "winner_count": len(winners)}


def replay(action_indices: list[int], lambda_value: float) -> dict:
    k, p, inv, c1, c2, c3, c4, c5 = 2.5, 30240.0, 360.0, 0.1, -6700.0, 900.0, -15.0, -12.0
    dk = -0.03 * k
    km = k + dk
    delta = km - k
    pp = p + c2 * delta**2 + c3 * delta
    iu = inv + c4 * delta**2 + c5 * delta
    fuel = pp / iu / (1.0 + km)
    state = [fuel * km, 18100.0, fuel, 7150.0]
    states = [state.copy()]
    accumulated = 0.0
    for index in action_indices:
        accumulated += ACTIONS[index]
        km = k + dk + c1 * accumulated
        delta = km - k
        pp = p + c2 * delta**2 + c3 * delta
        iu = inv + c4 * delta**2 + c5 * delta
        next_fuel = pp / iu / (1.0 + km)
        state = [next_fuel * km, state[1] - 75.0 * state[0],
                 next_fuel, state[3] - 75.0 * state[2]]
        states.append(state.copy())
    terminal = states[-1]
    squared = ((terminal[0]-60)**2 + terminal[1]**2 + (terminal[2]-24)**2 + terminal[3]**2 +
               lambda_value*(terminal[1]-2.5*terminal[3])**2)
    return {"action_indices": action_indices, "terminal_state": terminal,
            "objective_squared": squared, "objective_norm": math.sqrt(squared)}


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: b09_exact_oracle.py OUTPUT.json LAMBDA0_GEOMETRY.json LAMBDA1_GEOMETRY.json")
    output = Path(sys.argv[1])
    result = [case(0.0), case(1.0)]
    for index, lambda_value in enumerate((0.0, 1.0), start=2):
        geometry = json.loads(Path(sys.argv[index]).read_text(encoding="utf-8"))
        if geometry["lambda"] != lambda_value:
            raise ValueError("geometry objective order differs")
        fixed = replay(geometry["winner_action_indices"], lambda_value)
        adaptive = replay(geometry["closed_loop_action_indices"], lambda_value)
        for name, actual in (("open_loop_replay", fixed), ("closed_loop_replay", adaptive)):
            if (not math.isclose(actual["objective_squared"], geometry[f"{name}_objective_squared"], rel_tol=0, abs_tol=1e-8) or
                    any(not math.isclose(a,b,rel_tol=0,abs_tol=1e-9)
                        for a,b in zip(actual["terminal_state"],geometry[f"{name}_terminal_state"]))):
                raise ValueError(f"independent {name} criterion/state differs")
            result[index-2][name] = actual
        if {tuple(x) for x in result[index-2]["winning_action_indices"]} != {tuple(x) for x in geometry["winner_action_sequences"]}:
            raise ValueError("solver and exhaustive open-loop minimizer families differ")
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
