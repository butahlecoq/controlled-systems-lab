#!/usr/bin/env python3
"""Capture the host and toolchain around an EXT-04 measurement."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess


def command_version(*command: str) -> str:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode and command[0] in {"cmake", "ninja"} and shutil.which("mise"):
        result = subprocess.run(
            ["mise", "exec", "cmake@3.31.6", "ninja@1.12.1", "--", *command],
            check=True, capture_output=True, text=True)
    elif result.returncode:
        raise subprocess.CalledProcessError(result.returncode, command,
                                            output=result.stdout, stderr=result.stderr)
    return (result.stdout or result.stderr).splitlines()[0].strip()


def snapshot() -> dict:
    cpu = "unknown"
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith(("model name", "hardware")):
                cpu = line.split(":", 1)[-1].strip()
                break
    return {
        "os": platform.platform(),
        "architecture": platform.machine(),
        "cpu": cpu,
        "logical_processors": os.cpu_count(),
        "load_average": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
        "compiler": command_version("c++", "--version"),
        "cmake": command_version("cmake", "--version"),
        "ninja": command_version("ninja", "--version"),
        "build_configuration": "Release, C++20, -O3",
        "external_solvers": {"HiGHS": False, "Qhull": False},
        "provider": "phase-one LP; one sequential thread",
    }


def capture(phase: str, before_path: Path | None) -> dict:
    current = snapshot()
    if phase == "before":
        return {"before": current}
    if before_path is None:
        raise ValueError("after capture requires the before snapshot")
    before = json.loads(before_path.read_text(encoding="utf-8"))
    if set(before) != {"before"}:
        raise ValueError("before snapshot schema differs")
    return {
        **current,
        "load_average_before_measurement": before["before"]["load_average"],
        "load_average_after_measurement": current["load_average"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("before", "after"))
    parser.add_argument("--before", type=Path)
    args = parser.parse_args()
    print(json.dumps(capture(args.phase, args.before), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
