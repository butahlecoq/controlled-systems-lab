"""Check the bounded APP-02 public-path report driver."""
import csv
import io
import subprocess
import sys

expected = ["interval-box", "diamond-axis-outer", "diamond-rotated-outer",
            "diamond-axis-inner", "square-rotated-inner"]
run = subprocess.run([sys.argv[1], "smoke"], capture_output=True, text=True, check=True)
assert run.stderr == ""
reader = csv.DictReader(io.StringIO(run.stdout), strict=True)
assert reader.fieldnames == ["phase", "case", "repetition", "calls", "status",
                             "verified", "elapsed_ns", "basis", "output_primitives"]
rows = list(reader)
assert [row["case"] for row in rows] == expected
for row in rows:
    assert row["phase"] == "smoke" and row["repetition"] == "0"
    assert row["calls"] == "1" and row["status"] == "enclosed"
    assert row["verified"] == "true" and int(row["elapsed_ns"]) > 0
    assert row["basis"] in {"v_h", "h_v"}
    assert int(row["output_primitives"]) in {2, 4}
