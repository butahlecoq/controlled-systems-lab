#!/usr/bin/env python3
"""Run the EXP-824 driver and independently validate its finite-game result."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_two_points_box


def main() -> None:
    completed = subprocess.run([sys.argv[1]], check=True, capture_output=True, text=True)
    with tempfile.TemporaryDirectory(prefix="csl-issue824-smoke-") as temporary:
        record = Path(temporary) / "result.json"
        result = json.loads(completed.stdout)
        record.write_text(json.dumps(result), encoding="utf-8")
        checked = check_two_points_box.main(record)
        if checked["status"] != "verified":
            raise SystemExit("EXP-824 independent finite-game check did not pass")
    print("EXP-824 box minimax finite-game replay and stage enclosure passed")


if __name__ == "__main__":
    main()
