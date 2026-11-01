#!/usr/bin/env python3
"""Run and independently verify the native nominal report fixture."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_nominal

run = subprocess.run([sys.argv[1]], check=True, capture_output=True, text=True)
result = check_nominal.check(json.loads(run.stdout))
measurement_run = subprocess.run([sys.argv[1], "--measure"], check=True,
    capture_output=True, text=True)
measurement = json.loads(measurement_run.stdout)
assert measurement["schema"] == "csl.issue824-nominal-measurement/1"
assert measurement["warmup_calls"] == 1
assert measurement["completed_calls"] == 70 and measurement["failures"] == 0
assert len(measurement["batches"]) == 7
assert all(batch["calls"] == 10 and batch["api_duration_ns"] > 0 and batch["failures"] == 0
           for batch in measurement["batches"])
assert measurement["completed_tracks_consumed"] == 355
print(f"issue824 nominal independent check passed: {result['nominal_tracks_checked']} tracks, "
      f"{result['nominal_action_plans_checked_per_track']} plans per track, "
      f"{result['finite_minimax_plans_checked']}x{result['finite_minimax_disturbance_histories_per_plan']} minimax cases; "
      f"measurement passed {measurement['completed_calls']} calls")
