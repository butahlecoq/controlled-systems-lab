"""Canonical input descriptions for the OPT-12 measurement scenarios."""
from __future__ import annotations

import hashlib
import json


SCENARIOS = ("tiny-overhead", "small-reuse", "transfer-cost")


def fixture_descriptions() -> dict[str, dict]:
    """Return fresh, hash-sealed descriptions of the measured LP inputs."""
    fixtures = {
        "tiny-overhead": {
            "rows": 1, "columns": 1,
            "source_objective": [-1.0], "changed_objective": [-1.0], "coefficient": [1.0],
            "variable_bounds": {"lower": 0.0, "upper": None}, "row_sense": "upper",
            "source_rhs": 1.0, "changed_rhs": 0.5, "expected_objective": -0.5,
        },
        "small-reuse": {
            "rows": 1, "columns": 40,
            "source_objective": [-1.0] * 40, "changed_objective": [-1.0] * 40,
            "coefficient": [1.0] * 40,
            "variable_bounds": {"lower": 0.0, "upper": None}, "row_sense": "upper",
            "source_rhs": 20.0,
            "changed_rhs": 19.0, "expected_objective": -19.0,
        },
        "transfer-cost": {
            "rows": 1, "columns": 100000,
            "source_objective": {"all_columns": 1.0, "column_0": -1.0},
            "changed_objective": {"all_columns": 1.0, "column_99999": -2.0},
            "coefficient": {"all_columns": 1.0},
            "variable_bounds": {"lower": 0.0, "upper": None}, "row_sense": "upper",
            "source_rhs": 50000.0,
            "changed_rhs": 49999.0, "expected_objective": -99998.0,
            "objective_change": "column 0: -1 to 1; column 99999: 1 to -2",
        },
    }
    for fixture in fixtures.values():
        canonical = json.dumps(fixture, sort_keys=True, separators=(",", ":")).encode()
        fixture["sha256"] = hashlib.sha256(canonical).hexdigest()
    return fixtures


def validate_driver_fixture_events(events: list[dict]) -> None:
    """Require fixture events emitted after the driver's LPs are constructed."""
    observed = {}
    for event in events:
        if not isinstance(event, dict) or event.get("schema") != "csl.opt12-fixture/1":
            continue
        scenario = event.get("scenario")
        if scenario in observed:
            raise ValueError(f"driver emitted a duplicate fixture identity: {scenario}")
        fixture = event.get("fixture")
        if _contains_boolean(fixture):
            raise ValueError(f"driver fixture identity contains a boolean value: {scenario}")
        observed[scenario] = fixture
    expected = {
        name: {key: value for key, value in fixture.items() if key != "sha256"}
        for name, fixture in fixture_descriptions().items()
    }
    if observed != expected:
        raise ValueError("driver fixture identities differ from the canonical measured inputs")


def _contains_boolean(value) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, dict):
        return any(_contains_boolean(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_boolean(item) for item in value)
    return False
