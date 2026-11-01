from __future__ import annotations

import json
import math
import subprocess
import sys


def main() -> None:
    completed = subprocess.run([sys.argv[1]], check=True, capture_output=True, text=True)
    result = json.loads(completed.stdout)
    if result.get("schema") != "csl.issue824-two-points-zonotope-minimax/1":
        raise ValueError("unexpected zonotope minimax report schema")
    method = result["zonotope_minimax_method"]
    attempts = method["plan_attempts"]
    if method.get("candidate_search_coverage") != "complete" or len(attempts) != 27:
        raise ValueError("TwoPoints candidate search did not score all 27 fixed plans")
    scored = [attempt for attempt in attempts if attempt.get("status") == "scored"]
    if len(scored) != 27:
        raise ValueError("a TwoPoints fixed-plan attempt did not receive a score")
    for attempt in scored:
        count = attempt["terminal_generators"]
        if attempt["factor_corners_evaluated"] != 1 << count:
            raise ValueError("factor-corner score did not cover its complete sign cube")
        if not math.isfinite(attempt["candidate_score"]):
            raise ValueError("candidate score is not finite")
    selected_index = method["selected_candidate_attempt_index"]
    if attempts[selected_index]["action_indices"] != method["selected_action_indices"]:
        raise ValueError("selected plan index and action sequence differ")
    replay = method["selected_replay"]
    if not math.isfinite(replay["worst_value"]) or len(replay["path"]) != 4:
        raise ValueError("selected finite-catalogue replay is incomplete")
    planar = result["planar_selector_example"]
    if planar.get("candidate_search_coverage") != "complete" or len(planar["plans"]) != 3:
        raise ValueError("planar selector fixture did not score each control")
    if planar["selected_replay_value"] != planar["exact_finite_minimax_value"]:
        raise ValueError("planar selected replay differs from the exhaustive finite optimum")
    timing = result["timing"]
    if (timing.get("measurement_repetitions_per_method") != 7 or
            timing.get("warmup_runs_per_method") != 1 or len(timing.get("samples", [])) != 21):
        raise ValueError("report driver did not collect the declared raw timing samples")
    if any(sample.get("status") != "completed" or sample.get("elapsed_ns", 0) <= 0
           for sample in timing["samples"]):
        raise ValueError("report driver recorded a failed or empty timing sample")


if __name__ == "__main__":
    main()
