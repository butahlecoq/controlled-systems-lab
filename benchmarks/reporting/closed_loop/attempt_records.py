"""Versioned attempt storage with canonical stage records and checked references."""
from __future__ import annotations

from dataclasses import dataclass
import codecs
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import time
from typing import Any, Iterable, Mapping


ATTEMPT_SCHEMA_V2 = "csl.closed-loop.attempt/2"
STAGE_REFERENCE_SCHEMA = "csl.closed-loop.stage-reference/1"
STAGE_INDEX = "stage-records.jsonl"
IO_LOG = "record-io.jsonl"
_JSON_NUMBER = re.compile(rb"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")
_JSON_CONTROL = re.compile(rb"[\x00-\x1f]")


@dataclass(frozen=True)
class IoReceipt:
    path: str
    bytes_read: int
    parse_seconds: float


@dataclass(frozen=True)
class WriteReceipt:
    path: str
    bytes_written: int
    sha256: str
    serialization_seconds: float
    fsync_seconds: float


class _HashingWriter:
    def __init__(self, stream) -> None:
        self.stream = stream
        self.digest = hashlib.sha256()
        self.bytes_written = 0

    def write(self, value: str) -> int:
        encoded = value.encode("utf-8")
        self.digest.update(encoded)
        self.bytes_written += len(encoded)
        return self.stream.write(value)


def _json_default(value: Any) -> Any:
    try:
        import numpy as np
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
    except ImportError:
        pass
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def atomic_json(path: Path, value: Any) -> WriteReceipt:
    """Stream one JSON value to a replacement file and report exact output bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    writer = None
    started = time.perf_counter()
    try:
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = _HashingWriter(stream)
            json.dump(value, writer, indent=2, allow_nan=False, default=_json_default)
            writer.write("\n")
            serialization_seconds = time.perf_counter() - started
            fsync_started = time.perf_counter()
            stream.flush()
            os.fsync(stream.fileno())
            fsync_seconds = time.perf_counter() - fsync_started
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    assert writer is not None
    return WriteReceipt(path.name, writer.bytes_written, writer.digest.hexdigest(),
                        serialization_seconds, fsync_seconds)


def append_jsonl(path: Path, value: Mapping[str, Any]) -> int:
    encoded = (json.dumps(value, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    with path.open("ab") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return len(encoded)


def append_io_event(attempt_dir: Path, event: Mapping[str, Any]) -> None:
    append_jsonl(attempt_dir / IO_LOG, {"schema": "csl.closed-loop.record-io/1", **event})


def atomic_bytes(path: Path, value: bytes) -> WriteReceipt:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    started = time.perf_counter()
    digest = hashlib.sha256(value).hexdigest()
    try:
        with temporary.open("wb") as stream:
            stream.write(value)
            serialization_seconds = time.perf_counter() - started
            fsync_started = time.perf_counter()
            stream.flush()
            os.fsync(stream.fileno())
            fsync_seconds = time.perf_counter() - fsync_started
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return WriteReceipt(path.name, len(value), digest, serialization_seconds, fsync_seconds)


def atomic_text(path: Path, value: str) -> WriteReceipt:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    digest = hashlib.sha256()
    byte_count = 0
    encoder = codecs.getincrementalencoder("utf-8")()
    started = time.perf_counter()
    try:
        with temporary.open("wb") as stream:
            for offset in range(0, len(value), 1024 * 1024):
                block = encoder.encode(value[offset:offset + 1024 * 1024])
                digest.update(block)
                byte_count += len(block)
                stream.write(block)
            block = encoder.encode("", final=True)
            digest.update(block)
            byte_count += len(block)
            stream.write(block)
            serialization_seconds = time.perf_counter() - started
            fsync_started = time.perf_counter()
            stream.flush()
            os.fsync(stream.fileno())
            fsync_seconds = time.perf_counter() - fsync_started
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return WriteReceipt(path.name, byte_count, digest.hexdigest(), serialization_seconds, fsync_seconds)


def persist_native_capture(attempt_dir: Path, update_index: int, capture: dict,
                           saved: dict[str, Any]) -> dict[str, Any]:
    """Persist raw protocol payloads once and checkpoint only their checked references."""
    if not isinstance(capture, dict):
        raise ValueError("native query capture must be a mapping")
    stem = f"native-query-{update_index:03d}"
    request_value = capture.get("bridge_request_raw")
    if isinstance(request_value, str) and "request" not in saved:
        receipt = atomic_text(attempt_dir / f"{stem}-request.jsonl", request_value)
        saved["request"] = {"path": receipt.path, "bytes": receipt.bytes_written, "sha256": receipt.sha256}
        append_io_event(attempt_dir, {"operation": "native-payload", "payload": "request",
            "update_index": update_index, "path": receipt.path, "bytes_written": receipt.bytes_written,
            "sha256": receipt.sha256, "serialization_seconds": receipt.serialization_seconds,
            "fsync_seconds": receipt.fsync_seconds})
    response_value = capture.get("bridge_response_raw")
    if isinstance(response_value, str) and "response" not in saved:
        receipt = atomic_text(attempt_dir / f"{stem}-response.jsonl", response_value)
        saved["response"] = {"path": receipt.path, "bytes": receipt.bytes_written, "sha256": receipt.sha256}
        append_io_event(attempt_dir, {"operation": "native-payload", "payload": "response",
            "update_index": update_index, "path": receipt.path, "bytes_written": receipt.bytes_written,
            "sha256": receipt.sha256, "serialization_seconds": receipt.serialization_seconds,
            "fsync_seconds": receipt.fsync_seconds})
    if capture.get("capture_kind") == "adapter-preflight" and "request" not in saved:
        request = capture.get("request")
        if request is not None:
            encoded = (json.dumps(request, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
            receipt = atomic_bytes(attempt_dir / f"{stem}-request.json", encoded)
            saved["request"] = {"path": receipt.path, "bytes": receipt.bytes_written,
                "sha256": receipt.sha256, "encoding": "adapter-preflight-json"}
            append_io_event(attempt_dir, {"operation": "native-payload", "payload": "request",
                "update_index": update_index, "path": receipt.path, "bytes_written": receipt.bytes_written,
                "sha256": receipt.sha256, "serialization_seconds": receipt.serialization_seconds,
                "fsync_seconds": receipt.fsync_seconds})
    if capture.get("capture_kind") == "adapter-preflight" and capture.get("adapter_response") is not None and "response" not in saved:
        encoded = (json.dumps(capture["adapter_response"], separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
        receipt = atomic_bytes(attempt_dir / f"{stem}-response.json", encoded)
        saved["response"] = {"path": receipt.path, "bytes": receipt.bytes_written,
            "sha256": receipt.sha256, "encoding": "adapter-response-json"}
        append_io_event(attempt_dir, {"operation": "native-payload", "payload": "response",
            "update_index": update_index, "path": receipt.path, "bytes_written": receipt.bytes_written,
            "sha256": receipt.sha256, "serialization_seconds": receipt.serialization_seconds,
            "fsync_seconds": receipt.fsync_seconds})
    metadata = {"schema": "csl.closed-loop.native-query-capture/3", "update_index": update_index,
        "capture_kind": capture.get("capture_kind"),
        "bridge_request_sent": capture.get("bridge_request_sent"),
        "bridge_request_transmission_status": capture.get("bridge_request_transmission_status"),
        "request_sha256": capture.get("request_sha256"), "request": saved.get("request"),
        "bridge_response_sha256": capture.get("bridge_response_sha256"),
        "response_parse_status": capture.get("response_parse_status"),
        "response": saved.get("response")}
    meta_path = attempt_dir / f"{stem}.json"
    receipt = atomic_json(meta_path, metadata)
    append_io_event(attempt_dir, {"operation": "native-capture-checkpoint", "update_index": update_index,
        "path": receipt.path, "bytes_written": receipt.bytes_written, "sha256": receipt.sha256,
        "serialization_seconds": receipt.serialization_seconds, "fsync_seconds": receipt.fsync_seconds})
    for field in ("request", "request_json", "bridge_request_raw", "parsed_response",
                  "bridge_response_raw", "adapter_response"):
        capture.pop(field, None)
    return {"schema": "csl.closed-loop.native-query-capture-reference/1", "update_index": update_index,
        "path": meta_path.name,
        "bytes": receipt.bytes_written, "sha256": receipt.sha256}


def write_attempt(attempt_dir: Path, value: Mapping[str, Any]) -> WriteReceipt:
    receipt = atomic_json(attempt_dir / "attempt.json", value)
    append_io_event(attempt_dir, {"operation": "attempt-checkpoint", "path": receipt.path,
        "bytes_written": receipt.bytes_written, "sha256": receipt.sha256,
        "serialization_seconds": receipt.serialization_seconds,
        "fsync_seconds": receipt.fsync_seconds})
    return receipt


def write_stage(attempt_dir: Path, update_index: int, value: Mapping[str, Any]) -> WriteReceipt:
    path = f"stage-{update_index:03d}.json"
    receipt = atomic_json(attempt_dir / path, value)
    append_io_event(attempt_dir, {"operation": "stage-checkpoint", "update_index": update_index,
        "path": receipt.path, "bytes_written": receipt.bytes_written, "sha256": receipt.sha256,
        "serialization_seconds": receipt.serialization_seconds,
        "fsync_seconds": receipt.fsync_seconds})
    return receipt


def _append_reference(attempt_dir: Path, update_index: int, path: Path) -> dict[str, Any]:
    relative = path.name
    if relative != f"stage-{update_index:03d}.json":
        raise ValueError("stage record path does not match its update index")
    byte_count = path.stat().st_size
    digest = file_sha256(path)
    row = {"schema": STAGE_REFERENCE_SCHEMA, "update_index": update_index,
        "path": relative, "bytes": byte_count, "sha256": digest}
    index_bytes = append_jsonl(attempt_dir / STAGE_INDEX, row)
    append_io_event(attempt_dir, {"operation": "stage-reference", "update_index": update_index,
        "path": relative, "stage_bytes": byte_count, "index_bytes_written": index_bytes,
        "sha256": digest})
    return row


def finalize_stage(attempt_dir: Path, update_index: int, value: Mapping[str, Any]) -> dict[str, Any]:
    receipt = write_stage(attempt_dir, update_index, value)
    reference = {"schema": STAGE_REFERENCE_SCHEMA, "update_index": update_index,
        "path": receipt.path, "bytes": receipt.bytes_written, "sha256": receipt.sha256}
    index_bytes = append_jsonl(attempt_dir / STAGE_INDEX, reference)
    append_io_event(attempt_dir, {"operation": "stage-reference", **reference,
        "index_bytes_written": index_bytes})
    return reference


def register_orphan_stages(attempt_dir: Path) -> int:
    """Index finalized or interrupted stage files left after the worker exits."""
    indexed = list(iter_stage_references(attempt_dir, verify_hashes=False))
    next_index = len(indexed)
    recovered = 0
    while True:
        path = attempt_dir / f"stage-{next_index:03d}.json"
        if not path.is_file():
            break
        _append_reference(attempt_dir, next_index, path)
        next_index += 1
        recovered += 1
    return recovered


def _reference_path(attempt_dir: Path, reference: Mapping[str, Any]) -> Path:
    index = reference.get("update_index")
    name = reference.get("path")
    if not isinstance(index, int) or index < 0 or name != f"stage-{index:03d}.json":
        raise ValueError("stage reference has an invalid index or canonical path")
    if Path(name).name != name:
        raise ValueError("stage reference path escapes the attempt directory")
    path = attempt_dir / name
    if not path.is_file():
        raise ValueError(f"referenced stage record is missing: {name}")
    if path.stat().st_size != reference.get("bytes"):
        raise ValueError(f"referenced stage byte count changed: {name}")
    if file_sha256(path) != reference.get("sha256"):
        raise ValueError(f"referenced stage hash changed: {name}")
    return path


def iter_stage_references(attempt_dir: Path, *, verify_hashes: bool = True) -> Iterable[dict[str, Any]]:
    index_path = attempt_dir / STAGE_INDEX
    if not index_path.exists():
        return
    expected = 0
    with index_path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                reference = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"stage reference index is malformed at row {expected}") from error
            if (not isinstance(reference, dict) or reference.get("schema") != STAGE_REFERENCE_SCHEMA
                    or reference.get("update_index") != expected):
                raise ValueError(f"stage reference index is not contiguous at row {expected}")
            if verify_hashes:
                _reference_path(attempt_dir, reference)
            else:
                name = reference.get("path")
                if not isinstance(name, str) or Path(name).name != name:
                    raise ValueError("stage reference path escapes the attempt directory")
            yield reference
            expected += 1


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _skip_whitespace(data: mmap.mmap, position: int) -> int:
    while position < len(data) and data[position] in (32, 9, 10, 13):
        position += 1
    return position


def _string_end(data: mmap.mmap, start: int) -> int:
    position = start + 1
    while True:
        quote = data.find(b'"', position)
        slash = data.find(b"\\", position)
        if quote < 0:
            raise ValueError("JSON string is truncated")
        if slash < 0 or quote < slash:
            if _JSON_CONTROL.search(data, position, quote) is not None:
                raise ValueError("JSON string contains an unescaped control character")
            return quote + 1
        if _JSON_CONTROL.search(data, position, slash) is not None:
            raise ValueError("JSON string contains an unescaped control character")
        if slash + 1 >= len(data):
            raise ValueError("JSON string ends after an escape")
        escaped = data[slash + 1]
        if escaped in b'"\\/bfnrt':
            position = slash + 2
        elif escaped == ord("u"):
            if slash + 6 > len(data) or any(byte not in b"0123456789abcdefABCDEF"
                    for byte in data[slash + 2:slash + 6]):
                raise ValueError("JSON string has an invalid unicode escape")
            position = slash + 6
        else:
            raise ValueError("JSON string has an invalid escape")


def _parse_json_value(data: mmap.mmap, start: int) -> int:
    position = _skip_whitespace(data, start)
    if position >= len(data):
        raise ValueError("JSON value is missing")
    first = data[position]
    if first == 34:
        return _string_end(data, position)
    if first == 91:
        position = _skip_whitespace(data, position + 1)
        if data[position:position + 1] == b"]":
            return position + 1
        while True:
            position = _parse_json_value(data, position)
            position = _skip_whitespace(data, position)
            delimiter = data[position:position + 1]
            if delimiter == b"]":
                return position + 1
            if delimiter != b",":
                raise ValueError("JSON array has an invalid delimiter")
            position = _skip_whitespace(data, position + 1)
            if data[position:position + 1] == b"]":
                raise ValueError("JSON array has a trailing comma")
    if first == 123:
        position = _skip_whitespace(data, position + 1)
        if data[position:position + 1] == b"}":
            return position + 1
        while True:
            if data[position:position + 1] != b'"':
                raise ValueError("JSON object key is not a string")
            position = _skip_whitespace(data, _string_end(data, position))
            if data[position:position + 1] != b":":
                raise ValueError("JSON object key is missing a colon")
            position = _parse_json_value(data, position + 1)
            position = _skip_whitespace(data, position)
            delimiter = data[position:position + 1]
            if delimiter == b"}":
                return position + 1
            if delimiter != b",":
                raise ValueError("JSON object has an invalid delimiter")
            position = _skip_whitespace(data, position + 1)
            if data[position:position + 1] == b"}":
                raise ValueError("JSON object has a trailing comma")
    if data[position:position + 4] == b"true":
        return position + 4
    if data[position:position + 5] == b"false":
        return position + 5
    if data[position:position + 4] == b"null":
        return position + 4
    end = position
    while end < len(data) and data[end] not in (32, 9, 10, 13, 44, 93, 125):
        end += 1
    if not _JSON_NUMBER.fullmatch(data[position:end]):
        raise ValueError("JSON value is not a valid number or literal")
    return end


def read_object_fields(path: Path, *, selected: set[str] | None = None,
                       omitted: set[str] | None = None) -> tuple[dict[str, Any], IoReceipt]:
    """Read selected top-level JSON fields without allocating omitted values."""
    started = time.perf_counter()
    result: dict[str, Any] = {}
    omitted = omitted or set()
    with path.open("rb") as stream:
        if path.stat().st_size == 0:
            raise ValueError(f"JSON record is empty: {path}")
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            for offset in range(0, len(data), 64 * 1024):
                decoder.decode(data[offset:offset + 64 * 1024], final=False)
            decoder.decode(b"", final=True)
            position = _skip_whitespace(data, 0)
            if data[position:position + 1] != b"{":
                raise ValueError(f"JSON record must be an object: {path}")
            position += 1
            after_comma = False
            while True:
                position = _skip_whitespace(data, position)
                if data[position:position + 1] == b"}":
                    if after_comma:
                        raise ValueError("JSON object has a trailing comma")
                    position += 1
                    break
                key_start = position
                key_end = _string_end(data, key_start)
                key = json.loads(data[key_start:key_end])
                position = _skip_whitespace(data, key_end)
                if data[position:position + 1] != b":":
                    raise ValueError(f"JSON object is missing a colon after {key!r}")
                value_start = _skip_whitespace(data, position + 1)
                value_end = _parse_json_value(data, value_start)
                _capture_value(data, result, key, value_start, value_end, selected, omitted)
                position = _skip_whitespace(data, value_end)
                delimiter = data[position:position + 1]
                if delimiter == b",":
                    position += 1
                    after_comma = True
                elif delimiter == b"}":
                    position += 1
                    after_comma = False
                    break
                else:
                    raise ValueError(f"JSON object has an invalid delimiter after {key!r}")
            if _skip_whitespace(data, position) != len(data):
                raise ValueError("JSON record has trailing content")
    return result, IoReceipt(path.name, path.stat().st_size, time.perf_counter() - started)


def _capture_value(data: mmap.mmap, result: dict[str, Any], key: str,
                   start: int | None, end: int, selected: set[str] | None,
                   omitted: set[str]) -> None:
    if key in omitted or selected is not None and key not in selected:
        return
    if start is None:
        raise ValueError(f"JSON field has no value: {key}")
    raw = data[start:end].strip()
    try:
        result[key] = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON field is malformed: {key}") from error


def read_attempt(path: Path, *, selected: set[str] | None = None,
                 include_embedded_stages: bool = False) -> tuple[dict[str, Any], IoReceipt]:
    """Read an attempt while skipping the duplicated v1 stage array."""
    omitted = set() if include_embedded_stages else {"stages"}
    return read_object_fields(path, selected=selected, omitted=omitted)


def read_stage_fields(attempt_dir: Path, reference: Mapping[str, Any],
                      selected: set[str]) -> tuple[dict[str, Any], IoReceipt]:
    path = _reference_path(attempt_dir, reference)
    fields, receipt = read_object_fields(path, selected=selected)
    return fields, receipt


def read_native_capture_metadata(attempt_dir: Path, reference: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Path]]:
    index = reference.get("update_index")
    path = reference.get("path")
    if not isinstance(index, int) or path != f"native-query-{index:03d}.json":
        raise ValueError("native capture reference has a noncanonical path")
    if Path(path).name != path:
        raise ValueError("native capture reference escapes the attempt directory")
    meta_path = attempt_dir / path
    if not meta_path.is_file() or meta_path.stat().st_size != reference.get("bytes") or \
            file_sha256(meta_path) != reference.get("sha256"):
        raise ValueError("native capture metadata reference is missing or changed")
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    if metadata.get("schema") != "csl.closed-loop.native-query-capture/3" or \
            metadata.get("update_index") != index:
        raise ValueError("native capture metadata identity differs from its reference")
    payload_paths = {}
    for name in ("request", "response"):
        payload = metadata.get(name)
        if payload is None:
            continue
        payload_path = payload.get("path")
        expected_prefix = f"native-query-{index:03d}-"
        if not isinstance(payload_path, str) or not payload_path.startswith(expected_prefix) or \
                Path(payload_path).name != payload_path:
            raise ValueError(f"native {name} payload path escapes the attempt directory")
        resolved = attempt_dir / payload_path
        if not resolved.is_file() or resolved.stat().st_size != payload.get("bytes") or \
                file_sha256(resolved) != payload.get("sha256"):
            raise ValueError(f"native {name} payload reference is missing or changed")
        payload_paths[name] = resolved
    return metadata, payload_paths


def materialize_episode_summary(attempt_dir: Path, record: Mapping[str, Any]) -> tuple[list, list, list[IoReceipt]]:
    """Build replay summaries from checked stage references, retaining no rich stage rows."""
    controls: list = []
    states: list = []
    reads: list[IoReceipt] = []
    initial = record.get("selected_initial_state_physical")
    if isinstance(initial, list):
        states.append(initial)
    count = 0
    for reference in iter_stage_references(attempt_dir):
        count += 1
        fields, receipt = read_stage_fields(attempt_dir, reference,
            {"status", "observed_physical", "applied_control", "observed_next_physical"})
        reads.append(receipt)
        if not states and isinstance(fields.get("observed_physical"), list):
            states.append(fields["observed_physical"])
        if fields.get("status") == "applied-and-observed":
            action = fields.get("applied_control")
            next_state = fields.get("observed_next_physical")
            if not isinstance(action, list) or not isinstance(next_state, list):
                raise ValueError("applied stage record lacks its control or observed next state")
            controls.append(action)
            states.append(next_state)
    expected = record.get("stage_records", {}).get("count")
    if expected is not None and expected != count:
        raise ValueError("attempt stage-reference count differs from its index")
    return controls, states, reads


def summarize_io(attempt_dir: Path) -> dict[str, Any]:
    path = attempt_dir / IO_LOG
    totals: dict[str, Any] = {"checkpoint_writes": 0, "stage_writes": 0,
        "reference_writes": 0, "attempt_json_bytes_written": 0,
        "stage_json_bytes_written": 0, "native_payload_bytes_written": 0,
        "native_capture_checkpoint_bytes_written": 0, "reference_index_bytes_written": 0,
        "bytes_read": 0, "parse_seconds": 0.0,
        "serialization_seconds": 0.0, "fsync_seconds": 0.0}
    if not path.is_file():
        return totals
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            event = json.loads(line)
            operation = event.get("operation")
            if operation == "attempt-checkpoint":
                totals["checkpoint_writes"] += 1
                totals["attempt_json_bytes_written"] += event["bytes_written"]
            elif operation == "stage-checkpoint":
                totals["stage_writes"] += 1
                totals["stage_json_bytes_written"] += event["bytes_written"]
            elif operation == "stage-reference":
                totals["reference_writes"] += 1
                totals["reference_index_bytes_written"] += event.get("index_bytes_written", 0)
            elif operation == "native-payload":
                totals["native_payload_bytes_written"] += event["bytes_written"]
            elif operation == "native-capture-checkpoint":
                totals["native_capture_checkpoint_bytes_written"] += event["bytes_written"]
            if "bytes_read" in event:
                totals["bytes_read"] += event["bytes_read"]
                totals["parse_seconds"] += event.get("parse_seconds", 0.0)
            totals["serialization_seconds"] += event.get("serialization_seconds", 0.0)
            totals["fsync_seconds"] += event.get("fsync_seconds", 0.0)
    totals["scope"] = "attempt and stage JSON serialization plus fsync; excludes controller, execution, reference-index append, replay, rendering, and telemetry-log writes"
    return totals
