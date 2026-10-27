import json
import subprocess
import sys


result = subprocess.run([sys.argv[1], "--smoke"], check=True, capture_output=True, text=True)
report = json.loads(result.stdout)
assert report["schema"] == "csl.mpc03-open-loop-pilot/1"
assert report["history_count"] == 4
assert report["finite_reference"]["value"] == 2.25
assert report["finite_reference"]["plan_count"] == 9
assert report["finite_reference"]["minimizing_plan_indices"] == [4, 5, 7, 8]
assert report["extensive_form_milp"]["objective"] == 2.25
assert report["extensive_form_milp"]["best_bound"] == 2.25
assert report["extensive_form_milp"]["gap"] == 0
assert report["convex_action_relaxation"]["lower_bound"] == 2.0
assert report["convex_action_relaxation"]["lower_bound"] <= report["finite_upper_bound"]
