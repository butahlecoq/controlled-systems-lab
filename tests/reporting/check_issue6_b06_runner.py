#!/usr/bin/env python3
"""Check the configured B06 request and reject runtime fixture drift without solving."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

runner = Path(sys.argv[1])
scenario_path = Path(sys.argv[2])
scenario_bytes = scenario_path.read_bytes()
scenario = json.loads(scenario_bytes)
valid = subprocess.run([runner, "--validate-only", scenario_path], capture_output=True, text=True)
if valid.returncode:
    raise SystemExit(valid.stderr)
result = json.loads(valid.stdout)
if result.get("status") != "scenario_validated" or result.get("fixture_sha256") is None:
    raise SystemExit("configured B06 validation did not report its fixture identity")

scenario["model"]["A_row_major"][13] = "1"
with tempfile.TemporaryDirectory() as temporary:
    changed = Path(temporary) / "changed-scenario.json"
    changed.write_text(json.dumps(scenario), encoding="utf-8")
    run = subprocess.run([runner, "--validate-only", changed], capture_output=True, text=True)
    if run.returncode != 2 or "differ from the configured canonical fixture" not in run.stderr:
        raise SystemExit("runner accepted scenario bytes different from the configured fixture")
