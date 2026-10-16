"""Capture a fresh Release build and finite-feedback run from one clean Git tree.

The destination is retained on every failure. Publication admission is separate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import traceback


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root)


def clean_receipt(root: Path) -> dict:
    commit = git(root, "rev-parse", "HEAD").decode().strip()
    tree = git(root, "rev-parse", "HEAD^{tree}").decode().strip()
    status = git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise ValueError("full source tree is dirty: " + status.decode(errors="replace")[:500])
    return {"schema": "csl.finite-feedback-clean-tree-receipt/1", "observed_utc": now(),
            "commit": commit, "tree": tree, "status_sha256": sha(status),
            "tracked_count": len(git(root, "ls-files", "-z").split(b"\0")) - 1,
            "git_version": git(root, "--version").decode().strip()}


def run_logged(command: list[str], cwd: Path, out: Path, stem: str) -> int:
    with (out / (stem + ".stdout.log")).open("wb") as stdout, (out / (stem + ".stderr.log")).open("wb") as stderr:
        return subprocess.run(command, cwd=cwd, stdout=stdout, stderr=stderr, check=False).returncode


def observe_host() -> dict:
    return {"schema": "csl.finite-feedback-host-observation/2", "observed_utc": now(),
            "platform": platform.platform(), "processor": platform.processor(),
            "logical_processors": os.cpu_count(),
            "concurrent_work": "Other repository work may be active; single-session timings are exploratory."}


def capture(root: Path, build: Path, out: Path, cmake: Path) -> dict:
    if build.exists() or out.exists():
        raise ValueError("fresh build and collection destinations required")
    if root not in build.parents or root not in out.parents:
        raise ValueError("build and collection must be inside the source root")
    if subprocess.run(["git", "check-ignore", "-q", str(build)], cwd=root).returncode != 0 or \
            subprocess.run(["git", "check-ignore", "-q", str(out)], cwd=root).returncode != 0:
        raise ValueError("build and collection must be Git ignored")
    out.mkdir(parents=True)
    status: dict = {"schema": "csl.finite-feedback-capture/2", "state": "started",
                    "commands": {}, "return_codes": {}, "failure": None}
    try:
        pre = clean_receipt(root)
        status["prebuild"] = pre
        save(out / "prebuild-receipt.json", pre)
        status["source_commit"] = pre["commit"]
        status["source_tree"] = pre["tree"]
        build.mkdir()
        query = build / ".cmake/api/v1/query"
        query.mkdir(parents=True)
        (query / "codemodel-v2").write_bytes(b"")
        (query / "cache-v2").write_bytes(b"")
        configure = [str(cmake), "-S", str(root), "-B", str(build), "-G", "Visual Studio 17 2022",
                     "-A", "x64", "-DCSL_BUILD_FINITE_FEEDBACK_REPORT=ON", "-DCSL_ENABLE_HIGHS=OFF",
                     "-DCSL_ENABLE_QHULL=OFF", "-DBUILD_TESTING=OFF"]
        release = [str(cmake), "--build", str(build), "--config", "Release", "--target",
                   "csl_finite_feedback_report", "--parallel", "4", "--verbose"]
        status["commands"] = {"configure": configure, "build": release,
                              "smoke": ["csl_finite_feedback_report.exe", "--smoke"],
                              "measure": ["csl_finite_feedback_report.exe", "--measure", "7"]}
        status["configure_start_utc"] = now()
        status["return_codes"]["configure"] = run_logged(configure, root, out, "configure")
        if status["return_codes"]["configure"] != 0:
            raise RuntimeError("fresh configure failed")
        status["build_start_utc"] = now()
        status["return_codes"]["build"] = run_logged(release, root, out, "release-build")
        status["build_end_utc"] = now()
        if status["return_codes"]["build"] != 0:
            raise RuntimeError("fresh Release build failed")
        exe = build / "Release/csl_finite_feedback_report.exe"
        if not exe.is_file():
            raise RuntimeError("selected executable is missing")
        status["executable_sha256_before"] = sha(exe.read_bytes())
        status["executable_size_bytes"] = exe.stat().st_size
        status["host_pre"] = observe_host()
        save(out / "host-pre.json", status["host_pre"])
        status["return_codes"]["smoke"] = run_logged([str(exe), "--smoke"], root, out, "smoke")
        if status["return_codes"]["smoke"] != 0:
            raise RuntimeError("smoke failed")
        status["measure_start_utc"] = now()
        status["return_codes"]["measure"] = run_logged([str(exe), "--measure", "7"], root, out, "measure")
        status["measure_end_utc"] = now()
        status["host_post"] = observe_host()
        save(out / "host-post.json", status["host_post"])
        status["executable_sha256_after"] = sha(exe.read_bytes())
        post = clean_receipt(root)
        status["postrun"] = post
        save(out / "postrun-receipt.json", post)
        if pre["commit"] != post["commit"] or pre["tree"] != post["tree"] or \
                status["executable_sha256_before"] != status["executable_sha256_after"]:
            raise RuntimeError("source tree or executable changed during collection")
        if status["return_codes"]["measure"] != 0:
            raise RuntimeError("measurement returned nonzero")
        status["state"] = "captured"
    except Exception as error:
        status["state"] = "rejected"
        status["failure"] = str(error)
        (out / "failure.traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
    save(out / "capture-status.json", status)
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--cmake", required=True, type=Path)
    args = parser.parse_args()
    result = capture(*(path.resolve() for path in (args.root, args.build, args.out, args.cmake)))
    print(json.dumps({"state": result["state"], "failure": result["failure"],
                      "source_commit": result.get("source_commit")}))
    if result["state"] != "captured":
        sys.exit(1)


if __name__ == "__main__":
    main()
