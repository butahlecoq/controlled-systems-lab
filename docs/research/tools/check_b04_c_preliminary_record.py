"""Independent exact-dyadic replay of the saved preliminary B04-c outputs."""
from __future__ import annotations

from fractions import Fraction as F
import json
from pathlib import Path
import sys


def replay(initial, b, controls):
    a = [[F(i == j) for j in range(4)] for i in range(4)]
    a[1][0] = F(-25, 4)
    a[3][2] = F(-25, 4)
    states = [initial]
    for control in controls:
        state = [sum(a[i][j] * states[-1][j] for j in range(4)) + b[i] * control
                 for i in range(4)]
        states.append(state)
    return states


def main(record_path: Path) -> dict:
    record = json.loads(record_path.read_text())
    data = record["input"]
    initial = [F(x) for x in data["initial"]]
    b = [F(x) for x in data["B"]]
    candidate_controls = [F.from_float(float.fromhex(x))
                          for x in record["candidate"]["controls_binary64_hex"]]
    candidate_states = replay(initial, b, candidate_controls)
    violations = []
    for stage, state in enumerate(candidate_states):
        for index, lo, hi, label in ((0, F(1176), F(1224), "x1"),
                                     (2, F(432), F(468), "x3")):
            if not lo <= state[index] <= hi:
                violations.append([stage, label])
    terminal = candidate_states[-1]
    z = [F(1200)-terminal[0], terminal[1], F(8, 3)*(F(450)-terminal[2]),
         F(8, 3)*terminal[3], terminal[1]-F(8, 3)*terminal[3]]
    squared = sum(x*x for x in z)
    if squared != F(record["candidate"]["exact_squared_objective"]):
        raise ValueError("candidate exact squared objective differs")
    if [str(x) for x in terminal] != record["candidate"]["terminal_state_exact_dyadic"]:
        raise ValueError("candidate exact terminal replay differs")
    if violations:
        raise ValueError("candidate violates the exact phase box")

    reach = record["published_point_reachability"]
    reach_controls = [F.from_float(float.fromhex(x)) for x in reach["controls_binary64_hex"]]
    reach_states = replay(initial, b, reach_controls)
    point = [F(12007,10), F(-22929,1000), F(2251,5), F(-7709,1000)]
    radii = [F(1,20), F(1,2000), F(1,20), F(1,2000)]
    reach_terminal = reach_states[-1]
    within = all(abs(reach_terminal[i]-point[i]) <= radii[i] for i in range(4))
    reach_violations = []
    for stage, state in enumerate(reach_states):
        for index, lo, hi, label in ((0, F(1176), F(1224), "x1"),
                                     (2, F(432), F(468), "x3")):
            if not lo <= state[index] <= hi:
                reach_violations.append([stage, label])
    if not within or reach_violations:
        raise ValueError("published-point reachability failed exact replay")
    if [str(x) for x in reach_terminal] != reach["terminal_state_exact_dyadic"]:
        raise ValueError("reachability terminal replay differs")

    flow = F(12)*point[0] + F(23)*point[2] - F("3095440554305551/125000000000")
    stock = F(12)*point[1] + F(23)*point[3] - F("-565554305551/1250000000")
    plane = record["published_plane_residuals_exact"]
    if flow != F(plane["flow_12x1_plus_23x3_minus_3095440554305551_over_125000000000"]):
        raise ValueError("published flow-plane residual differs")
    if stock != F(plane["stock_12x2_plus_23x4_plus_565554305551_over_1250000000"]):
        raise ValueError("published stock-plane residual differs")

    expected_bands = ["|J* - 30.899| <= 0.0005", "J* < 30.8985", "J* > 30.8995"]
    if record["pre_registered_bands_unchanged"] != expected_bands:
        raise ValueError("pre-registered bands changed")
    return {"schema": "csl.b04-c-preliminary-exact-check/1",
            "candidate_exact_phase_box": "passed",
            "candidate_exact_squared_objective": str(squared),
            "reachability_exact_phase_box": "passed",
            "reachability_exact_rounding_box": "passed",
            "published_flow_plane_residual": str(flow),
            "published_stock_plane_residual": str(stock),
            "pre_registered_bands_unchanged": True,
            "optimality_or_family_coverage_proved": False}


if __name__ == "__main__":
    result = main(Path(sys.argv[1]))
    print(json.dumps(result, sort_keys=True))
