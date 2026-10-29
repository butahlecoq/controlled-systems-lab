#!/usr/bin/env python3
"""Run the EXP-03 native smoke and its independent inclusion oracle."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from check_two_points_approximation import check


def main():
    if len(sys.argv) != 6:
        raise SystemExit(
            "usage: check_two_points_approximation_smoke.py DRIVER REFERENCE_BUILDER "
            "FIGURE_DATA RESULT REFERENCE_OUTPUT"
        )
    driver, builder, figure_data, result, reference_output = map(Path, sys.argv[1:])
    subprocess.run([
        sys.executable, str(builder), "--figure-data", str(figure_data),
        "--result", str(result), "--output", str(reference_output),
    ], check=True, capture_output=True, text=True)
    run = subprocess.run([str(driver), "smoke", str(reference_output)],
                         check=True, capture_output=True, text=True)
    reference = json.loads(reference_output.read_text(encoding="utf-8"))
    raw = json.loads(run.stdout)
    checked = check(reference, raw)
    if len(checked["results"]) != 10:
        raise SystemExit("Expected five exact/outer methods on both phase planes")
    if any(item["status"] != "verified" for item in checked["results"]):
        raise SystemExit("Independent inclusion oracle did not verify every method")
    print(json.dumps({
        "schema": checked["schema"],
        "case_id": checked["case_id"],
        "verified_results": len(checked["results"]),
        "methods": sorted({item["method"] for item in checked["results"]}),
        "directions": sorted({item["relation"] for item in checked["results"]}),
    }, indent=2))


if __name__ == "__main__":
    main()
