"""Capture APP-04 public adapter observations from one clean frozen commit."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def git(source: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=source, text=True).strip()


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def receipt(source: Path, commit: str, phase: str) -> dict:
    value = {"schema": "csl.app04-source-receipt/1", "phase": phase,
             "observed_utc": utc(), "commit": git(source, "rev-parse", "HEAD"),
             "tree": git(source, "rev-parse", "HEAD^{tree}"),
             "status": git(source, "status", "--porcelain=v1", "--untracked-files=all").splitlines(),
             "tracked_count": len(git(source, "ls-files").splitlines())}
    if value["commit"] != commit or value["status"]:
        raise ValueError("Source checkout is not the clean frozen commit")
    return value


def command(arguments: list[str], source: Path, log: Path, env: dict[str, str]) -> None:
    run = subprocess.run(arguments, cwd=source, env=env, capture_output=True)
    log.write_bytes(run.stdout + run.stderr)
    if run.returncode:
        raise RuntimeError(f"Command failed ({run.returncode}): {arguments}")


def capture(source: Path, destination: Path, commit: str, cmake: str) -> None:
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Capture directory must be fresh")
    before = receipt(source, commit, "prebuild")
    destination.mkdir(parents=True)
    write(destination / "prebuild.json", before)
    build = destination / "measure-build"
    env = dict(os.environ, VSLANG="1033", PreferredUILang="en-US",
               DOTNET_CLI_UI_LANGUAGE="en-US")
    command([cmake, "-S", str(source), "-B", str(build), "-DBUILD_TESTING=OFF",
             "-DCSL_ENABLE_HIGHS=OFF", "-DCSL_ENABLE_QHULL=OFF",
             "-DCSL_BUILD_APP04_REPORT=ON"], source,
            destination / "configure.log", env)
    command([cmake, "--build", str(build), "--config", "Release", "--target",
             "csl_app04_ellipsoid_report", "--parallel", "4", "--",
             "/p:PreferredUILang=en-US", "/clp:ErrorsOnly"], source,
            destination / "build.log", env)
    executable = build / "Release/csl_app04_ellipsoid_report.exe"
    if not executable.is_file():
        raise FileNotFoundError(executable)
    for phase in ("smoke", "measure"):
        run = subprocess.run([str(executable), phase], cwd=source, env=env,
                             capture_output=True)
        (destination / f"{phase}.csv").write_bytes(run.stdout)
        (destination / f"{phase}.stderr.txt").write_bytes(run.stderr)
        if run.returncode:
            raise RuntimeError(f"APP-04 {phase} run failed ({run.returncode})")
    after = receipt(source, commit, "postrun")
    after["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    write(destination / "postrun.json", after)
    write(destination / "host.json", {"source_commit": commit,
        "source_tree": before["tree"], "source_status": [],
        "collected_utc": utc(), "host": platform.node(),
        "os": platform.platform(), "processor": platform.processor(),
        "architecture": platform.machine(), "python": platform.python_version(),
        "logical_processors": os.cpu_count()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--cmake", default="cmake")
    args = parser.parse_args()
    capture(args.source, args.capture, args.commit, args.cmake)
