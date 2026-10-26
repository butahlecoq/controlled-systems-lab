"""Strict offline reader for csl.stage-projection-batch/1 documents."""

from __future__ import annotations

import json
import hashlib
from fractions import Fraction
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "docs/artifacts/schemas/stage-projection-batch-v1.schema.json"
SCHEMA_ID = "csl.stage-projection-batch/1"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
jsonschema.Draft202012Validator.check_schema(SCHEMA)
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


class ProjectionBatchError(ValueError):
    """The saved batch is malformed or does not match its source identity."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ProjectionBatchError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def loads_stage_projection_batch(
    raw: bytes | str,
    *,
    expected_run_id: str,
    expected_problem_id: str,
    expected_request_id: str,
    expected_route_id: str,
    expected_source_sha256: str,
) -> dict[str, Any]:
    """Parse and validate one batch, including exact source-record binding."""
    try:
        document = json.loads(raw, object_pairs_hook=_unique_object,
                              parse_constant=lambda value: (_ for _ in ()).throw(
                                  ProjectionBatchError(f"non-finite JSON number: {value}")))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ProjectionBatchError(f"invalid JSON: {error}") from error
    errors = sorted(VALIDATOR.iter_errors(document), key=lambda error: list(error.absolute_path))
    if errors:
        first = errors[0]
        path = ".".join(map(str, first.absolute_path)) or "$"
        raise ProjectionBatchError(f"{path}: {first.message}")
    provenance = document["provenance"]
    expected = {
        "run_id": expected_run_id,
        "problem_id": expected_problem_id,
        "request_id": expected_request_id,
        "route_id": expected_route_id,
        "source_sha256": expected_source_sha256,
    }
    actual = {
        "run_id": provenance["run_id"],
        "problem_id": document["problem_id"],
        "request_id": document["request_id"],
        "route_id": document["route_id"],
        "source_sha256": provenance["source_sha256"],
    }
    if actual != expected:
        raise ProjectionBatchError(f"source identity mismatch: expected {expected}, got {actual}")
    content = {key: value for key, value in document.items() if key != "content_sha256"}
    canonical = json.dumps(content, ensure_ascii=False, allow_nan=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != document["content_sha256"]:
        raise ProjectionBatchError("content_sha256 does not match the saved batch")

    pair_count = len(document["requested_pairs"])
    stage_points = document["stage_axis"]["points"]
    if not stage_points:
        raise ProjectionBatchError("stage_axis.points must not be empty")
    if any(right <= left for left, right in zip(stage_points, stage_points[1:])):
        raise ProjectionBatchError("stage_axis.points must be strictly increasing")
    seen_pairs: set[tuple[int, int]] = set()
    for i, pair in enumerate(document["requested_pairs"]):
        normalized = tuple(pair)
        if pair[0] == pair[1] or max(pair) >= len(document["coordinates"]):
            raise ProjectionBatchError(f"requested_pairs[{i}] references invalid coordinates")
        if normalized in seen_pairs:
            raise ProjectionBatchError(f"requested_pairs[{i}] duplicates an earlier ordered pair")
        seen_pairs.add(normalized)
    if len(stage_points) != len(set(stage_points)):
        raise ProjectionBatchError("stage_axis.points must be unique")
    if document["stage_axis"]["kind"] == "stage" and stage_points != list(range(len(stage_points))):
        raise ProjectionBatchError("stage axis must be the contiguous R0-based stage sequence")

    expected_grid = [(stage, pair) for stage in range(len(stage_points)) for pair in range(pair_count)]
    actual_grid = [(row["stage"], row["pair_index"]) for row in document["records"]]
    if actual_grid != expected_grid:
        raise ProjectionBatchError("records must contain the complete stage-major ordered pair grid")
    for i, row in enumerate(document["records"]):
        time = row["physical_time"]
        if (document["stage_axis"]["kind"] == "physical_time" and
                (time is None or time != stage_points[row["stage"]])):
            raise ProjectionBatchError(f"records[{i}] time does not match its stage axis")
        outcome = row["outcome"]
        if outcome.get("status") == "success":
            evidence_ids = []
            for item in outcome["evidence"]:
                for source_id in item["input_set_ids"]:
                    if source_id not in evidence_ids:
                        evidence_ids.append(source_id)
            if evidence_ids != row["source_set_ids"]:
                raise ProjectionBatchError(f"records[{i}] source set IDs do not match projection evidence")
            ids = [component["component_id"] for component in outcome["components"]]
            if len(ids) != len(set(ids)):
                raise ProjectionBatchError(f"records[{i}] has duplicate geometry component identities")
            for component in outcome["components"]:
                kind, vertices, rays = component["kind"], component.get("vertices", []), component.get("rays", [])
                if kind != "empty" and not vertices:
                    raise ProjectionBatchError(f"records[{i}] nonempty geometry must include vertices")
                if kind in {"point", "segment", "polygon"} and rays:
                    raise ProjectionBatchError(f"records[{i}] bounded geometry cannot include recession rays")
                if kind == "empty" and (vertices or rays):
                    raise ProjectionBatchError(f"records[{i}] empty geometry cannot include vertices or rays")
                if kind in {"point", "segment", "polygon"}:
                    unique = list(dict.fromkeys(tuple(point) for point in vertices))
                    if kind == "point" and len(unique) != 1:
                        raise ProjectionBatchError(f"records[{i}] point vertices must all represent one point")
                    if kind == "segment" and len(unique) < 2:
                        raise ProjectionBatchError(f"records[{i}] segment vertices must include two distinct points")
                    if kind == "polygon" and len(unique) < 3:
                        raise ProjectionBatchError(f"records[{i}] polygon vertices must include three distinct points")
                    if kind != "point" and len(unique) >= 2:
                        x0, y0 = (Fraction.from_float(float(value)) for value in unique[0])
                        x1, y1 = (Fraction.from_float(float(value)) for value in unique[1])
                        area = any((x1 - x0) * (Fraction.from_float(float(y)) - y0) !=
                                   (y1 - y0) * (Fraction.from_float(float(x)) - x0)
                                   for x, y in unique[2:])
                        if (kind == "segment") == area:
                            raise ProjectionBatchError(f"records[{i}] geometry kind does not match its exact vertex affine dimension")
                if kind == "unbounded" and not rays:
                    raise ProjectionBatchError(f"records[{i}] unbounded geometry must include a ray")
                if kind == "unbounded" and not any(any(value != 0 for value in ray) for ray in rays):
                    raise ProjectionBatchError(f"records[{i}] unbounded geometry must include a nonzero ray")
        if outcome.get("kind") == "stopped" and outcome.get("status") in {"unavailable", "failure"}:
            if not outcome.get("stop_reason") or "stop_diagnostics" not in outcome:
                raise ProjectionBatchError(f"records[{i}] stopped outcome must retain its stop reason and diagnostics")
    coordinate_ids = [coordinate["id"] for coordinate in document["coordinates"]]
    for i, trajectory in enumerate(document["trajectory_series"]):
        if trajectory["source_run_id"] != expected_run_id:
            raise ProjectionBatchError(f"trajectory_series[{i}] source run does not match batch run")
        if any(identifier not in coordinate_ids for identifier in trajectory["coordinate_ids"]):
            raise ProjectionBatchError(f"trajectory_series[{i}] references an unknown coordinate")
        if trajectory["coordinate_ids"][0] == trajectory["coordinate_ids"][1]:
            raise ProjectionBatchError(f"trajectory_series[{i}] repeats a coordinate")
        if len(trajectory["points"]) != len(stage_points):
            raise ProjectionBatchError(f"trajectory_series[{i}] does not align with the stage axis")
    return document


def read_stage_projection_batch(path: Path, **expected_identity: str) -> dict[str, Any]:
    """Read a batch only after verifying its current bytes and source binding."""
    return loads_stage_projection_batch(path.read_bytes(), **expected_identity)


def dumps_stage_projection_batch(document: dict[str, Any], **expected_identity: str) -> bytes:
    """Serialize a batch only after applying the same checks as the offline reader."""
    document = {key: value for key, value in document.items() if key != "content_sha256"}
    canonical = json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    document["content_sha256"] = hashlib.sha256(canonical).hexdigest()
    raw = (json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")) + "\n").encode("utf-8")
    loads_stage_projection_batch(raw, **expected_identity)
    return raw
