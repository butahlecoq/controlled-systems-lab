"""Functional timeout and raw-capture regression for the issue #3 collector."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import collect


def main(out: Path, exe: Path) -> None:
    out.mkdir(parents=True, exist_ok=False)
    child = ("import sys,time;"
             "sys.stdout.buffer.write(b'partial-out\\n');sys.stdout.flush();"
             "sys.stderr.buffer.write(b'partial-err\\n');sys.stderr.flush();"
             "time.sleep(30)")
    stdout, stderr, code, timed_out = collect.capture(
        [sys.executable, "-c", child], out, "timeout", 1)
    assert (stdout, stderr, code, timed_out) == (
        b"partial-out\n", b"partial-err\n", 124, True)
    assert (out / "timeout.stdout").read_bytes() == stdout
    assert (out / "timeout.stderr").read_bytes() == stderr
    record = json.loads((out / "timeout.process.json").read_text(encoding="utf-8"))
    assert record["timed_out"] is True and record["return_code"] == 124
    assert record["stdout_sha256"] == hashlib.sha256(stdout).hexdigest()
    assert record["stderr_sha256"] == hashlib.sha256(stderr).hexdigest()

    stdout, stderr, code, timed_out = collect.capture(
        [sys.executable, "-c", "import sys;sys.stdout.buffer.write(b'failed\\n');sys.exit(9)"],
        out, "failure", 5)
    assert (stdout, stderr, code, timed_out) == (b"failed\n", b"", 9, False)
    assert (out / "failure.stdout").read_bytes() == stdout

    smoke = subprocess.check_output([str(exe), "--smoke"], cwd=collect.ROOT)
    smoke_rows = [json.loads(line) for line in smoke.splitlines()]
    names = ["l19", "integrator", "all_infeasible", "empty_catalogue",
             "no_scenarios", "unsupported", "cancelled", "b08_rounded"]
    by_fixture = {row["fixture"]: row for row in smoke_rows}
    rows = []
    for round_number in range(8):
        order = names if round_number % 2 == 0 else list(reversed(names))
        for name in order:
            # Parser-only fixture: these durations/counts are synthetic and
            # are never written as a measurement record.
            row = dict(by_fixture[name])
            row["round"] = round_number
            row["warmup"] = round_number == 0
            row["batch"] = 1 if name == "b08_rounded" else 10000 if name == "l19" else 5000
            row["checked_calls"] = row["batch"]
            row["elapsed_ns"] = 20_000_000
            rows.append(row)
    raw = lambda: b"".join((json.dumps(row) + "\n").encode() for row in rows)
    head = smoke_rows[0]["harness_commit"]
    fixture_hash = smoke_rows[0]["fixture_sha256"]
    assert len(collect.validate_rows(raw(), head, fixture_hash, smoke_rows)) == 64
    b08 = next(row for row in rows if row["fixture"] == "b08_rounded")
    changed = json.loads(b08["input_canonical"])
    changed["disturbance_vertices_binary64_hex"][2][0][0] = float.hex(-0.3)
    b08["input_canonical"] = json.dumps(changed, sort_keys=True, separators=(",", ":"))
    b08["input_sha256"] = hashlib.sha256(b08["input_canonical"].encode()).hexdigest()
    try:
        collect.validate_rows(raw(), head, fixture_hash, smoke_rows)
    except ValueError as error:
        assert "mathematical identity differs" in str(error)
    else:
        raise AssertionError("changed binary64 disturbance coefficient was admitted")
    print("partial timeout and failed-process bytes retained")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_capture.py BUILD_OUTPUT_DIR EXE")
    main(Path(sys.argv[1]), Path(sys.argv[2]))
