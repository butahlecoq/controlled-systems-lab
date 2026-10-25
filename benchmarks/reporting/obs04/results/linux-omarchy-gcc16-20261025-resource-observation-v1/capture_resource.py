#!/usr/bin/env python3
"""Capture one OBS-04 driver run with process-level max RSS and elapsed time."""
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

if len(sys.argv) != 3:
    raise SystemExit("usage: capture_resource.py DRIVER COMPARISON_RECORD")

driver_argument, record_argument = sys.argv[1:]
driver = Path(driver_argument).resolve(strict=True)
record = Path(record_argument).resolve()
output = Path(__file__).resolve().parent
command = [driver_argument, "--record", record_argument]
start = time.perf_counter_ns()
with (output / "driver.stdout.log").open("wb") as stdout, (output / "driver.stderr.log").open("wb") as stderr:
    completed = subprocess.run(command, cwd=Path.cwd(), stdout=stdout, stderr=stderr, check=False)
elapsed_ns = time.perf_counter_ns() - start
usage = resource.getrusage(resource.RUSAGE_CHILDREN)
measurement = {
    "schema": "csl.obs04-process-resource-observation/1",
    "scope": "one driver process; includes startup, fixture/preparation, all attempts, record encoding and file output",
    "working_directory": ".",
    "command": command,
    "exit_code": completed.returncode,
    "elapsed_wall_ns": elapsed_ns,
    "user_cpu_seconds": usage.ru_utime,
    "system_cpu_seconds": usage.ru_stime,
    "max_rss_kib": usage.ru_maxrss,
    "binary_sha256": hashlib.sha256(driver.read_bytes()).hexdigest(),
    "record_path": record_argument,
    "record_bytes": record.stat().st_size if record.is_file() else None,
    "stdout_bytes": (output / "driver.stdout.log").stat().st_size,
    "stderr_bytes": (output / "driver.stderr.log").stat().st_size,
    "platform": sys.platform,
    "python_version": sys.version,
    "clock_ticks_per_second": os.sysconf("SC_CLK_TCK"),
}
(output / "resource-observation.json").write_text(
    json.dumps(measurement, sort_keys=True, indent=2) + "\n", encoding="utf-8"
)
if completed.returncode != 0:
    raise SystemExit(completed.returncode)
