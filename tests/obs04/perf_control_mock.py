#!/usr/bin/env python3
"""Exercise the OBS-04 perf FIFO handshake without requiring perf_event access."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time


def serve(
    control_path: Path, ack_path: Path, acknowledgement: bytes | None,
    commands: list[str], fragment_ack: bool = False,
) -> None:
    control_fd = os.open(control_path, os.O_RDONLY)
    ack_fd = os.open(ack_path, os.O_WRONLY)
    try:
        pending = b""
        while True:
            chunk = os.read(control_fd, 64)
            if not chunk:
                return
            pending += chunk
            while b"\n" in pending:
                raw, pending = pending.split(b"\n", 1)
                command = raw.decode("ascii")
                commands.append(command)
                if acknowledgement is not None:
                    if fragment_ack:
                        os.write(ack_fd, acknowledgement[:2])
                        time.sleep(0.005)
                        os.write(ack_fd, acknowledgement[2:])
                    else:
                        os.write(ack_fd, acknowledgement)
                else:
                    return
    finally:
        os.close(ack_fd)
        os.close(control_fd)


def run(
    binary: Path, acknowledgement: bytes | None, fragment_ack: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    with tempfile.TemporaryDirectory(prefix="obs04-perf-mock-") as directory:
        root = Path(directory)
        control_path = root / "control"
        ack_path = root / "ack"
        os.mkfifo(control_path)
        os.mkfifo(ack_path)
        commands: list[str] = []
        server = threading.Thread(
            target=serve, args=(control_path, ack_path, acknowledgement, commands, fragment_ack), daemon=True
        )
        server.start()
        environment = os.environ.copy()
        environment["CSL_PERF_CONTROL_FIFO"] = str(control_path)
        environment["CSL_PERF_ACK_FIFO"] = str(ack_path)
        result = subprocess.run(
            [str(binary), "--profile-strategy", "reach-back", "--profile-calls", "1"],
            env=environment, capture_output=True, text=True, timeout=45,
        )
        server.join(timeout=2)
        if server.is_alive():
            raise RuntimeError("mock perf FIFO server did not stop")
        return result, commands


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: perf_control_mock.py /path/to/csl_obs04_instrumentation_comparison")
    binary = Path(sys.argv[1]).resolve(strict=True)

    malformed_arguments = [
        (["--profile-strategy", "reach-back", "--profile-calls", "8oops"],
         "complete unsigned integer"),
        (["--profile-strategy", "reach-back", "--profile-strategy", "direct-joint",
          "--profile-calls", "1"],
         "--profile-strategy may be provided only once"),
        (["--profile-strategy", "reach-back", "--profile-calls", "1", "--profile-calls", "2"],
         "--profile-calls may be provided only once"),
        (["--profile-strategy", "reach-back", "--profile-calls", "0"],
         "Profile call count must be positive"),
        (["--profile-strategy", "reach-back", "--profile-calls", "1",
          "--record", "/tmp/obs04-invalid-mixed-mode.record"],
         "Profile mode and comparison-record capture are separate modes"),
        (["--record", "/tmp/obs04-invalid-first.record",
          "--record", "/tmp/obs04-invalid-second.record"],
         "--record may be provided only once"),
    ]
    for arguments, diagnostic in malformed_arguments:
        rejected = subprocess.run(
            [str(binary), *arguments], capture_output=True, text=True, timeout=5,
            env={key: value for key, value in os.environ.items()
                 if key not in {"CSL_PERF_CONTROL_FIFO", "CSL_PERF_ACK_FIFO"}},
        )
        if rejected.returncode == 0 or rejected.stdout or diagnostic not in rejected.stderr:
            raise RuntimeError(f"malformed profile arguments were accepted or started work: {arguments}")

    passed, commands = run(binary, acknowledgement=b"ack\n")
    if passed.returncode != 0:
        raise RuntimeError(f"acknowledged mock capture failed: {passed.stderr}")
    if commands != ["enable", "disable"]:
        raise RuntimeError(f"unexpected mock command sequence: {commands}")
    events = [json.loads(line) for line in passed.stdout.splitlines() if line.startswith("{")]
    if not events or events[-1].get("sample_scope") != "acknowledged_perf_control_window":
        raise RuntimeError("driver did not identify the acknowledged profile scope")
    if events[-1].get("acknowledged_commands") != 2:
        raise RuntimeError("driver did not count both acknowledged transitions")

    nul_terminated, nul_commands = run(binary, acknowledgement=b"ack\n\0")
    if nul_terminated.returncode != 0 or nul_commands != ["enable", "disable"]:
        raise RuntimeError(f"NUL-terminated perf acknowledgements were not accepted: {nul_terminated.stderr}")
    nul_events = [json.loads(line) for line in nul_terminated.stdout.splitlines() if line.startswith("{")]
    if not nul_events or nul_events[-1].get("acknowledged_commands") != 2:
        raise RuntimeError("driver did not count both NUL-terminated acknowledgements")

    fragmented, fragmented_commands = run(
        binary, acknowledgement=b"ack\n\0", fragment_ack=True,
    )
    if fragmented.returncode != 0 or fragmented_commands != ["enable", "disable"]:
        raise RuntimeError(f"fragmented perf acknowledgements were not accepted: {fragmented.stderr}")
    fragmented_events = [json.loads(line) for line in fragmented.stdout.splitlines() if line.startswith("{")]
    if not fragmented_events or fragmented_events[-1].get("acknowledged_commands") != 2:
        raise RuntimeError("driver did not count both fragmented acknowledgements")

    missing, missing_commands = run(binary, acknowledgement=None)
    if missing.returncode == 0 or missing_commands != ["enable"]:
        raise RuntimeError("driver accepted a control command without an acknowledgement")
    if "perf" not in missing.stderr.lower() and "acknowledgement" not in missing.stderr.lower():
        raise RuntimeError(f"missing-ack failure was not reported clearly: {missing.stderr}")
    print("OBS-04 CLI checks passed: malformed/duplicate profile arguments rejected before profile setup")
    print("OBS-04 perf control mock passed: enable/disable acknowledged; missing ack rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
