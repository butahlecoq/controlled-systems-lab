"""Strict parser for opt-in pinned HiGHS diagnostic clock events."""

from __future__ import annotations

import json
import math


PREFIX = b"CSL_HIGHS_CLOCK/1 "
SCHEMA = "csl.highs-clock-group/1"


def validate_group(group: object) -> dict[str, object]:
    if not isinstance(group, dict) or group.get("schema") != SCHEMA:
        raise ValueError("unexpected HiGHS clock event schema")
    index = group.get("provider_call_index")
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValueError("provider_call_index must be a nonnegative integer")
    if group.get("capture_status") not in {"captured", "unavailable"}:
        raise ValueError("invalid clock capture status")
    if not isinstance(group.get("highs_version"), str) or not group["highs_version"]:
        raise ValueError("missing HiGHS version provenance")
    expected_provenance = {
        "highs_archive_sha256": "2b44b074cf41439325ce4d0bbdac2d51379f56faf17ba15320a410d3c1f07275",
        "clock_patch_sha256": "9e6849f8933e3e434c5964f78f2c7229537a9398f1d6ded35a2cd2c5d1839501",
    }
    for key, expected in expected_provenance.items():
        if group.get(key) != expected:
            raise ValueError(f"unexpected pinned {key}")
    status = group.get("native_call_status")
    if isinstance(status, bool) or not isinstance(status, int):
        raise ValueError("native_call_status must be an integer")
    clocks = group.get("clocks")
    if not isinstance(clocks, list):
        raise ValueError("clocks must be an array")
    if group["capture_status"] == "captured" and not clocks:
        raise ValueError("captured clock registry must not be empty")
    if group["capture_status"] == "unavailable" and clocks:
        raise ValueError("unavailable capture must not claim clock samples")
    ids: set[int] = set()
    for clock in clocks:
        if not isinstance(clock, dict):
            raise ValueError("clock sample must be an object")
        clock_id, name, calls, seconds, clock_status = (
            clock.get("id"), clock.get("name"), clock.get("calls"),
            clock.get("elapsed_seconds"), clock.get("status"))
        if isinstance(clock_id, bool) or not isinstance(clock_id, int) or clock_id < 0 or clock_id in ids:
            raise ValueError("clock IDs must be unique nonnegative integers")
        ids.add(clock_id)
        if not isinstance(name, str) or not name:
            raise ValueError("clock name must be nonempty")
        if calls is not None and (isinstance(calls, bool) or not isinstance(calls, int) or calls < 0):
            raise ValueError("clock calls must be a nonnegative integer or null")
        if seconds is not None and (isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0):
            raise ValueError("elapsed_seconds must be nonnegative or null")
        if clock_status not in {"observed", "uncalled", "unavailable"}:
            raise ValueError("invalid clock sample status")
        if clock_status == "observed" and (calls is None or calls == 0 or seconds is None):
            raise ValueError("observed clocks require positive calls and elapsed seconds")
        if clock_status == "uncalled" and (calls != 0 or seconds is None):
            raise ValueError("uncalled clocks require zero calls and an elapsed reading")
        if clock_status == "unavailable" and (calls is not None or seconds is not None):
            raise ValueError("unavailable clocks must not claim numeric samples")
    return group


def parse_stderr(data: bytes, enabled: bool) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    for line in data.splitlines():
        if not line.startswith(PREFIX):
            continue
        try:
            group = json.loads(line[len(PREFIX):].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"malformed HiGHS clock event: {error}") from error
        groups.append(validate_group(group))
    if not enabled and groups:
        raise ValueError("clock events appeared in an uninstrumented attempt")
    indices = [group["provider_call_index"] for group in groups]
    if indices != list(range(len(indices))):
        raise ValueError("provider call indices must be unique and contiguous from zero")
    return groups


def parse_result_stdout(data: bytes, diagnostic: bool) -> dict[str, object]:
    text = data.decode("utf-8")
    if diagnostic:
        lines = [line for line in text.splitlines()
                 if line.startswith('{"schema":"csl.review05.horizon-attempt/1"')]
        if len(lines) != 1:
            raise ValueError("diagnostic stdout requires exactly one versioned result line")
        result = json.loads(lines[0])
    else:
        result = json.loads(text)
    if not isinstance(result, dict) or result.get("schema") != "csl.review05.horizon-attempt/1":
        raise ValueError("unexpected stdout result schema")
    return result
