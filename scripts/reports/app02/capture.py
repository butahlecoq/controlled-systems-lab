"""Capture APP-02 results from a clean, exact frozen source checkout."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess

SOURCE = "8fecba49e34c37e5e01c40218a8f014a179818fd"
TREE = "7754b4c088566225b007c58531a74aae0024d5a1"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def git(source: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=source, text=True).strip()


def receipt(source: Path, phase: str) -> dict:
    value = {"schema": "csl.app02-source-receipt/1", "phase": phase,
             "observed_utc": utc(), "commit": git(source, "rev-parse", "HEAD"),
             "tree": git(source, "rev-parse", "HEAD^{tree}"),
             "status": git(source, "status", "--porcelain=v1", "--untracked-files=all").splitlines(),
             "tracked_count": len(git(source, "ls-files").splitlines())}
    if value["commit"] != SOURCE or value["tree"] != TREE or value["status"]:
        raise ValueError("Source checkout differs from the clean frozen commit")
    return value


def command(args: list[str], cwd: Path, output: Path, env: dict[str, str]) -> None:
    run = subprocess.run(args, cwd=cwd, env=env, capture_output=True)
    output.write_bytes(run.stdout + run.stderr)
    if run.returncode:
        raise RuntimeError(f"Command failed ({run.returncode}): {args}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    capture = args.capture.resolve()
    if capture.exists():
        raise ValueError("Capture directory must be fresh")
    capture.mkdir(parents=True)
    write(capture / "prebuild.json", receipt(source, "prebuild"))
    build = capture / "measure-build"
    env = dict(os.environ, VSLANG="1033", DOTNET_CLI_UI_LANGUAGE="en-US",
               PreferredUILang="en-US")
    command(["python", "-m", "cmake", "-S", str(source), "-B", str(build),
             "-DBUILD_TESTING=OFF", "-DCSL_ENABLE_HIGHS=OFF",
             "-DCSL_ENABLE_QHULL=OFF", "-DCSL_BUILD_APP02_REPORT=ON"],
            source, capture / "configure.log", env)
    command(["python", "-m", "cmake", "--build", str(build), "--config", "Release",
             "--target", "csl_app02_approximation_report", "--parallel", "4", "--",
             "/p:PreferredUILang=en-US", "/clp:ErrorsOnly"],
            source, capture / "build.log", env)
    executable = build / "Release/csl_app02_approximation_report.exe"
    if not executable.is_file():
        raise FileNotFoundError(executable)
    for name, phase in (("smoke", "smoke"), ("measure", "measure")):
        run = subprocess.run([str(executable), phase], cwd=source, env=env,
                             capture_output=True)
        (capture / f"{name}.csv").write_bytes(run.stdout)
        (capture / f"{name}.stderr.txt").write_bytes(run.stderr)
        if run.returncode:
            raise RuntimeError(f"APP-02 {phase} driver failed ({run.returncode})")
    post = receipt(source, "postrun")
    post["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    write(capture / "postrun.json", post)
    write(capture / "host.json", {"source_commit": SOURCE, "source_tree": TREE,
         "source_status": [], "collected_utc": utc(),
         "host": platform.node(), "os": platform.platform(),
         "processor": platform.processor(), "architecture": platform.machine(),
         "python": platform.python_version(), "logical_processors": os.cpu_count()})
    print(capture)


if __name__ == "__main__":
    main()
