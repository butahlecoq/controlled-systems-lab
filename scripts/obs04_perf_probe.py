#!/usr/bin/env python3
"""Run a bounded acknowledged perf capture and always save a capability result."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile


def write_result(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sanitize(text: str, binary: Path) -> str:
    workspace = os.environ.get("GITHUB_WORKSPACE", "")
    if workspace:
        text = text.replace(workspace, "<workspace>")
    return text.replace(str(binary), "<OBS04_BINARY>")


def count_cycles_samples(sample_output: str) -> int:
    return sum(
        1 for line in sample_output.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "cycles" in line
    )


def permission_failure(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in (
        "operation not permitted", "permission denied", "no permission", "not supported",
        "failed to open perf event", "perf_event_paranoid", "access to performance monitoring",
        "unknown option '--control'", "unrecognized option '--control'",
    ))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--strategy", choices=("reach-back", "direct-joint"), default="reach-back")
    parser.add_argument("--calls", type=int, default=8)
    parser.add_argument("--frequency-hz", type=int, default=4999)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args()
    if not 1 <= args.calls <= 32:
        parser.error("--calls must be between 1 and 32")
    if not 100 <= args.frequency_hz <= 9999:
        parser.error("--frequency-hz must be between 100 and 9999")
    if not 15 <= args.timeout_seconds <= 300:
        parser.error("--timeout-seconds must be between 15 and 300")

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result_path = output / "capability.json"
    stdout_path = output / "driver.stdout.log"
    stderr_path = output / "perf.stderr.log"
    capture_path = output / "acknowledged.perf.data"
    perf = shutil.which("perf")
    args.binary = args.binary.resolve(strict=True)
    if not args.binary.is_file():
        parser.error("--binary must name an executable file")
    repository = Path(__file__).resolve().parents[1]
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, capture_output=True, text=True, check=True,
    ).stdout.strip()
    try:
        perf_event_paranoid = Path("/proc/sys/kernel/perf_event_paranoid").read_text(encoding="ascii").strip()
    except OSError:
        perf_event_paranoid = None
    result = {
        "schema": "csl.obs04-perf-probe/1",
        "status": "unavailable",
        "protocol": "linux-perf-record-ack-fifo",
        "strategy": ("csl.synthesis.reach-back" if args.strategy == "reach-back"
            else "csl.synthesis.strategy-b"),
        "calls_requested": args.calls,
        "timeout_seconds": args.timeout_seconds,
        "source_commit": source_commit,
        "binary_name": args.binary.name,
        "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest(),
        "host": {"platform": platform.platform(), "kernel_release": platform.release(),
            "perf_event_paranoid": perf_event_paranoid},
        "profile": {
            "event": "cycles:u",
            "requested_frequency_hz": args.frequency_hz,
            "effective_frequency_hz": None,
            "effective_frequency_status": "not_reported_by_this_probe",
            "max_bytes": 32 * 1024 * 1024,
        },
    }
    if perf is None:
        result["reason"] = "perf executable is not installed"
        write_result(result_path, result)
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text("perf executable is not installed\n", encoding="utf-8")
        print(f"perf capability: unavailable ({result['reason']})")
        return 0

    result["perf_executable"] = Path(perf).name
    version = subprocess.run([perf, "--version"], capture_output=True, text=True, timeout=5)
    result["perf_version"] = (version.stdout or version.stderr).strip()
    if version.returncode != 0:
        result["reason"] = "perf --version failed"
        write_result(result_path, result)
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(version.stderr, encoding="utf-8")
        print(f"perf capability: unavailable ({result['reason']})")
        return 0

    with tempfile.TemporaryDirectory(prefix="csl-obs04-perf-") as temp:
        temp_path = Path(temp)
        control = temp_path / "control"
        ack = temp_path / "ack"
        os.mkfifo(control)
        os.mkfifo(ack)
        environment = os.environ.copy()
        environment["CSL_PERF_CONTROL_FIFO"] = str(control)
        environment["CSL_PERF_ACK_FIFO"] = str(ack)
        driver = subprocess.Popen(
            [str(args.binary), "--profile-strategy", args.strategy, "--profile-calls", str(args.calls)],
            env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        command = [
            perf, "record", "--delay=-1", "-F", str(args.frequency_hz), "-e", "cycles:u", "-g", "--sample-cpu",
            "--max-size=32M", "--control=fifo:" + str(control) + "," + str(ack),
            "-o", str(capture_path), "-p", str(driver.pid),
        ]
        result["command"] = [
            "perf", "record", "--delay=-1", "-F", str(args.frequency_hz), "-e", "cycles:u", "-g", "--sample-cpu",
            "--max-size=32M", "--control=fifo:<control>,<ack>", "-o", "<capture>", "-p", "<driver pid>",
        ]
        perf_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            driver_stdout, driver_stderr = driver.communicate(timeout=args.timeout_seconds)
            perf_stdout, perf_stderr = perf_process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            result["status"] = "failed"
            result["reason"] = "bounded perf capture timed out"
            for process in (driver, perf_process):
                if process.poll() is None:
                    process.send_signal(signal.SIGTERM)
            for process in (driver, perf_process):
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
            driver_stdout, driver_stderr = driver.communicate()
            perf_stdout, perf_stderr = perf_process.communicate()
        stdout_path.write_text(sanitize(driver_stdout or "", args.binary), encoding="utf-8")
        stderr_path.write_text(sanitize(perf_stderr or "", args.binary), encoding="utf-8")
        result["driver_exit_code"] = driver.returncode
        result["perf_exit_code"] = perf_process.returncode
        result["driver_stderr"] = sanitize((driver_stderr or "").strip(), args.binary)
        result["perf_stdout"] = sanitize((perf_stdout or "").strip(), args.binary)
        combined_errors = sanitize((driver_stderr or "") + "\n" + (perf_stderr or ""), args.binary)
        if result.get("status") == "failed":
            if permission_failure(combined_errors):
                result["status"] = "unavailable"
                result["reason"] = (combined_errors.strip() or "runner denied perf event access")[-4000:]
        elif driver.returncode != 0 or perf_process.returncode != 0:
            result["status"] = "unavailable" if permission_failure(combined_errors) else "failed"
            result["reason"] = (combined_errors.strip() or "driver or perf exited unsuccessfully")[-4000:]
        else:
            events = [
                json.loads(line) for line in (driver_stdout or "").splitlines()
                if line.startswith("{")
            ]
            event = events[-1] if events else {}
            result["calls_passed"] = event.get("passed")
            result["acknowledged_commands"] = event.get("acknowledged_commands")
            result["sample_scope"] = event.get("sample_scope")
            if (event.get("passed") != args.calls or
                    event.get("acknowledged_commands") != 2 * args.calls or
                    event.get("sample_scope") != "acknowledged_perf_control_transitions"):
                result["status"] = "failed"
                result["reason"] = "driver did not report one acknowledged enable/disable pair per call"
            elif not capture_path.is_file() or capture_path.stat().st_size == 0:
                result["status"] = "failed"
                result["reason"] = "perf exited successfully without a non-empty perf.data file"
            else:
                sample_report = subprocess.run(
                    [perf, "script", "--input", str(capture_path), "-F",
                        "comm,pid,tid,cpu,time,event,ip,sym"],
                    capture_output=True, text=True, timeout=15,
                )
                if sample_report.returncode != 0:
                    result["status"] = "failed"
                    result["reason"] = sanitize(
                        (sample_report.stderr or "perf script could not read the recorded profile").strip(), args.binary
                    )[-4000:]
                else:
                    sample_count = count_cycles_samples(sample_report.stdout)
                    result["sample_count"] = sample_count
                    result["lost_event_count"] = None
                    result["loss_status"] = "not_counted_by_this_capability_probe"
                    result["capture_file"] = capture_path.name
                    result["capture_bytes"] = capture_path.stat().st_size
                    result["capture_sha256"] = hashlib.sha256(capture_path.read_bytes()).hexdigest()
                    if sample_count == 0:
                        result["status"] = "no_samples"
                        result["reason"] = "perf.data has no decoded cycles samples; this does not establish a usable profile"
                    else:
                        result["status"] = "available"
                        result["reason"] = "bounded profile contains decoded cycles samples with acknowledged enable/disable commands"
        write_result(result_path, result)
        print(f"perf capability: {result['status']} ({result.get('reason', '')})")
        return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
