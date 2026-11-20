"""Classify the matched catalogue stops that have a short independent witness."""
from fractions import Fraction
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
bikes = json.loads((root / "9.json").read_bytes(), parse_float=Fraction)
assert bikes["A"]["values"][:3] == [1, 0, 0]
assert bikes["B"]["values"][:2] == [-1, 0]
assert bikes["G"]["values"][:3] == [1, 0, 0]
assert not any(bikes["offset"])
assert [stage[0][0] for stage in bikes["constraints"]["control"]] == [0] * 3
assert bikes["constraints"]["state"][3][0][0] == 0
upper = bikes["initial"][0] + sum(row[0] for row in bikes["external"])
assert upper == -3
power = json.loads((root / "30.json").read_bytes())
audit = json.loads((root / "independent-audit.json").read_bytes())
checked = audit["rows"][29]
assert checked["number"] == 30 and checked["open_loop"]["status"] == "complete"
assert checked["closed_loop"]["holds"] == 1
assert power["open_loop"]["controls"][0] == power["closed_loop"]["controls"][0]
assert power["open_loop"]["states"][1] == power["closed_loop"]["states"][1]
assert "optimality.withheld" in power["closed_loop"]["decisions"][1]["raw_diagnostics"]
report = {
    "model_9": {
        "status": "infeasible-in-the-pinned-continuous-relaxation",
        "coordinate": "x1",
        "terminal_upper_bound": int(upper),
        "terminal_minimum": 0,
    },
    "model_30": {
        "status": "feedback-suffix-has-an-independently-checked-feasible-witness",
        "feedback_holds": 1,
        "witness": "suffix of complete open-loop trajectory from the identical observation",
        "witness_holds": 2,
    },
}
(root / "stops-audit.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
