#!/usr/bin/env python3
"""Build a checksummed exact cost-evaluation report from the pinned MPC-06 case."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from tube_objective import OUTPUT, ROOT, SCENARIO_PATH, analyze
from render_tube_objective import write as render


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    scenario_bytes = SCENARIO_PATH.read_bytes()
    (OUTPUT / "scenario.json").write_bytes(scenario_bytes)
    (OUTPUT / "base-scenario.json").write_bytes(
        (ROOT / "benchmarks/scenarios/mpc06-nilpotent-tube-v1.json").read_bytes())
    (OUTPUT / "base-result.json").write_bytes(
        (ROOT / "reports/algorithm-results/mpc06-nilpotent-tube-pilot-v1/result.json").read_bytes())
    result = analyze()
    (OUTPUT / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, "scripts/reports/mpc06/check_tube_objective.py"], cwd=ROOT, check=True)
    render(result)
    readme = """# MPC-06 exact tube-policy cost extension

This is a new analytic cost evaluation tied to the exact nilpotent double-integrator tube in the adjacent `mpc06-nilpotent-tube-pilot-v1` report. Exact copies of the prior scenario and result are included in this bundle as `base-scenario.json` and `base-result.json`. It defines a three-stage quadratic cost and evaluates one fixed zero nominal plan with the fixed full-state feedback gain `K=[-1,-2]` under stagewise independent disturbances in `[-1/8,1/8]`.

The nominal surrogate cost is exactly `0`; the exact worst-case actual finite-horizon cost is `3/8`. The maximizing disturbance histories are `(1/8,-1/8,1/8)` and its sign reversal. The exact checker enumerates all eight vertices, checks every resulting state and input bound, and uses convexity of the sum-of-squares objective in the complete disturbance vector to establish the same maximum for the continuous box.

This is a cost certificate for one fixed plan and one fixed ancillary policy. It does not optimize the nominal plan or gain and is not a fixed-plan minimax optimum or globally optimal causal policy result. There is no benchmark timing, no terminal invariant set, and no approximation-family comparison; #99/#100 gate approximation claims. The controller assumes the current full state is observed before each input, with disturbance entering after that input.

All calculations use exact rational arithmetic in Python's standard library. No external solver or optional dependency is used. The plotted path is a maximizing witness inside the exact RPI tube, not an optimal trajectory.

## Reproduce

```sh
python scripts/reports/mpc06/build_tube_objective.py
python scripts/reports/mpc06/check_tube_objective.py
```

The staged report is functional evidence, not a performance measurement. There are no public API, dependency, installation, or release/package changes.
"""
    (OUTPUT / "README.md").write_text(readme, encoding="utf-8")
    source_paths = (
        "benchmarks/scenarios/mpc06-tube-objective-v1.json",
        "benchmarks/scenarios/mpc06-nilpotent-tube-v1.json",
        ".github/workflows/algorithm-reports.yml",
        "reports/algorithm-results/mpc06-nilpotent-tube-pilot-v1/result.json",
        "scripts/reports/mpc06/check_tube.py",
        "scripts/reports/mpc06/tube_objective.py",
        "scripts/reports/mpc06/check_tube_objective.py",
        "scripts/reports/mpc06/test_tube_objective.py",
        "scripts/reports/mpc06/render_tube_objective.py",
        "scripts/reports/mpc06/build_tube_objective.py",
        "scripts/reports/stage_mpc06_tube_objective.py",
    )
    files = sorted(path.name for path in OUTPUT.iterdir() if path.is_file() and path.name not in {"manifest.json", "SHA256SUMS"})
    manifest = {
        "schema": "csl.mpc06-tube-objective-manifest/1",
        "report_id": OUTPUT.name,
        "source_commit": result["source_commit"],
        "source_files": {name: sha((ROOT / name).read_bytes()) for name in source_paths},
        "files": {name: sha((OUTPUT / name).read_bytes()) for name in files},
        "scope": "exact finite-horizon actual cost of one fixed nominal plan plus one fixed full-state tube feedback law; no timing or optimality claim",
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    inventory = sorted(path.name for path in OUTPUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUTPUT / "SHA256SUMS").write_text("".join(f"{sha((OUTPUT / name).read_bytes())}  {name}\n" for name in inventory), encoding="ascii")
    print(json.dumps({"report": str(OUTPUT.relative_to(ROOT)), "files": len(inventory),
                      "nominal_cost": result["objective"]["nominal_surrogate_cost"],
                      "worst_cost": result["objective"]["worst_case_actual_cost"]}, sort_keys=True))


if __name__ == "__main__":
    main()
