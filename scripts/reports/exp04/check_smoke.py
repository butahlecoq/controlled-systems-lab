"""Run the EXP-04 public replay driver and check its literal smoke observations."""
import csv
import io
import subprocess
import sys

completed = subprocess.run([sys.argv[1], "smoke"], check=True, capture_output=True, text=True)
rows = list(csv.DictReader(io.StringIO(completed.stdout)))
expected = [("scalar-endpoint", "2", "0"), ("scalar-even", "1.5", "0"),
            ("plane-forward", "3", "1"), ("plane-reverse", "2", "1")]
assert len(rows) == len(expected)
for row, (case, x, y) in zip(rows, expected):
    assert (row["phase"], row["case"], row["calls"], row["status"],
            row["verified"], row["terminal_x"], row["terminal_y"],
            row["objective"]) == ("smoke", case, "1", "complete", "true", x, y, x)
    assert int(row["elapsed_ns"]) > 0
