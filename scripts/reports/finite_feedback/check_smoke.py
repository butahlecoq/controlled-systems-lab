"""Check the finite feedback report executable against independent literal rows."""

import csv
import io
import subprocess
import sys


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_smoke.py DRIVER")
    completed = subprocess.run(
        [sys.argv[1], "--smoke"], capture_output=True, text=True, timeout=30, check=False
    )
    if completed.returncode or completed.stderr:
        raise AssertionError((completed.returncode, completed.stderr))
    rows = list(csv.DictReader(io.StringIO(completed.stdout)))
    expected = [
        ("clipping", "0", "", ""),
        ("branching", "1", "0", "1:0|2:1"),
        ("empty-action", "0", "", ""),
        ("nominal", "1", "0", ""),
    ]
    assert len(rows) == len(expected), rows
    for row, (scenario, winning, actions, branches) in zip(rows, expected):
        assert row["purpose"] == "smoke", row
        assert row["scenario"] == scenario, row
        assert row["repetition"] == "0", row
        assert row["status"] == "passed", row
        assert row["initial_winning"] == winning, row
        assert row["initial_actions"] == actions, row
        assert row["branch_actions"] == branches, row
        assert row["provider_id"] == "csl.reachability.finite-feedback-table", row
        assert row["provider_version"] == "1.0.0", row
        assert row["detail"] == "", row
        assert row["elapsed_ns"].isdigit(), row

    measured = subprocess.run(
        [sys.argv[1], "--measure", "5"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if measured.returncode or measured.stderr:
        raise AssertionError((measured.returncode, measured.stderr))
    measured_rows = list(csv.DictReader(io.StringIO(measured.stdout)))
    assert len(measured_rows) == 24, measured_rows
    assert [row["scenario"] for row in measured_rows[:4]] == [
        item[0] for item in expected
    ]
    for index, row in enumerate(measured_rows):
        assert row["purpose"] == ("warmup" if index < 4 else "trial"), row
        assert row["status"] == "passed", row
        assert row["detail"] == "", row
        assert row["elapsed_ns"].isdigit(), row
    assert sorted((row["scenario"], row["repetition"]) for row in measured_rows[4:]) == sorted(
        (scenario, str(repetition))
        for scenario, *_ in expected
        for repetition in range(5)
    )
    invalid = subprocess.run(
        [sys.argv[1], "--measure", "4"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert invalid.returncode == 2 and not invalid.stdout, invalid
    print("registered smoke and unsaved measurement-protocol rows matched literals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
