"""Canonical input descriptions for the OPT-12 measurement scenarios."""
from __future__ import annotations

import hashlib
import json


SCENARIOS = ("tiny-overhead", "small-reuse", "transfer-cost")


def fixture_descriptions() -> dict[str, dict]:
    """Return fresh, hash-sealed descriptions of the measured LP inputs."""
    fixtures = {
        "tiny-overhead": {
            "rows": 1, "columns": 1, "objective": [-1.0], "coefficient": [1.0],
            "source_rhs": 1.0, "changed_rhs": 0.5, "expected_objective": -0.5,
        },
        "small-reuse": {
            "rows": 1, "columns": 40, "objective": [-1.0] * 40,
            "coefficient": [1.0] * 40, "source_rhs": 20.0,
            "changed_rhs": 19.0, "expected_objective": -19.0,
        },
        "transfer-cost": {
            "rows": 1, "columns": 100000,
            "source_objective": {"all_columns": 1.0, "column_0": -1.0},
            "changed_objective": {"all_columns": 1.0, "column_99999": -2.0},
            "coefficient": {"all_columns": 1.0}, "source_rhs": 50000.0,
            "changed_rhs": 49999.0, "expected_objective": -99998.0,
            "objective_change": "column 99999: -1 to -2",
        },
    }
    for fixture in fixtures.values():
        canonical = json.dumps(fixture, sort_keys=True, separators=(",", ":")).encode()
        fixture["sha256"] = hashlib.sha256(canonical).hexdigest()
    return fixtures
