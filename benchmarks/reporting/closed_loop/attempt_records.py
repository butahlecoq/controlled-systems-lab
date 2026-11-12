"""Versioned attempt storage with canonical stage records and checked references."""
from __future__ import annotations

from dataclasses import dataclass
import codecs
import hashlib
import json
import math
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
IO_STATUS = "record-io-integrity.json"
IO_SCHEMA = "csl.closed-loop.record-io/1"
IO_STATUS_SCHEMA = "csl.closed-loop.record-io-integrity/1"
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


def append_jsonl(path: Path, value: Mapping[str, Any]) -> WriteReceipt:
    started = time.perf_counter()
    encoded = (json.dumps(value, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    serialization_seconds = time.perf_counter() - started
    fsync_started = time.perf_counter()
    with path.open("ab") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return WriteReceipt(path.name, len(encoded), hashlib.sha256(encoded).hexdigest(),
                        serialization_seconds, time.perf_counter() - fsync_started)


def append_io_event(attempt_dir: Path, event: Mapping[str, Any]) -> None:
    try:
        _append_io_event(attempt_dir, event)
    except (OSError, TypeError, ValueError, OverflowError) as error:
        # The journal is diagnostic. A failure here must not undo an already
        # durable attempt or stage checkpoint.
        try:
            _mark_io_invalid(attempt_dir,
                f"{type(error).__name__}: {error}; telemetry append disabled")
        except OSError:
            pass


def _append_io_event(attempt_dir: Path, event: Mapping[str, Any]) -> None:
    if _read_io_status(attempt_dir) is not None:
        return
    recovery = _recover_io_log_tail(attempt_dir)
    if recovery is not None and recovery.get("integrity_status") == "invalid":
        return
    if recovery is not None:
        recovery_row = {"schema": IO_SCHEMA,
            "operation": "record-io-tail-recovery", **recovery}
        try:
            _validate_io_event(recovery_row, 0)
        except ValueError as error:
            _mark_io_invalid(attempt_dir, f"recovery event is invalid: {error}")
            return
        append_jsonl(attempt_dir / IO_LOG, recovery_row)
    row = dict(event)
    row["schema"] = IO_SCHEMA
    try:
        _validate_io_event(row, 0)
        append_jsonl(attempt_dir / IO_LOG, row)
    except (TypeError, ValueError, OverflowError) as error:
        _mark_io_invalid(attempt_dir, f"generated event is invalid: {type(error).__name__}: {error}",
            operation=row.get("operation"))


def _read_io_status(attempt_dir: Path) -> dict[str, Any] | None:
    path = attempt_dir / IO_STATUS
    if not path.is_file():
        return None
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"schema": IO_STATUS_SCHEMA, "integrity_status": "invalid",
            "integrity_diagnostic": "record I/O integrity sidecar is unreadable"}
    if not isinstance(status, dict) or status.get("schema") != IO_STATUS_SCHEMA or \
            status.get("integrity_status") != "invalid":
        return {"schema": IO_STATUS_SCHEMA, "integrity_status": "invalid",
            "integrity_diagnostic": "record I/O integrity sidecar has an invalid schema"}
    return status


def _mark_io_invalid(attempt_dir: Path, diagnostic: str, *, operation: Any = None,
                     recovery_evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    status = {"schema": IO_STATUS_SCHEMA, "integrity_status": "invalid",
        "metric_totals_complete": False, "metric_totals_available": False,
        "integrity_diagnostic": diagnostic,
        "recovery_evidence": recovery_evidence or []}
    if isinstance(operation, str):
        status["operation"] = operation
    atomic_json(attempt_dir / IO_STATUS, status)
    return status


class _RecordIoIntegrityError(ValueError):
    pass


def _validate_io_event(event: Any, row_number: int) -> None:
    if not isinstance(event, dict) or event.get("schema") != IO_SCHEMA:
        raise _RecordIoIntegrityError(f"invalid record I/O schema at row {row_number}")
    operation = event.get("operation")
    required: dict[str, tuple[str, ...]] = {
        "attempt-checkpoint": ("path", "bytes_written", "sha256", "serialization_seconds", "fsync_seconds"),
        "stage-checkpoint": ("update_index", "path", "bytes_written", "sha256", "serialization_seconds", "fsync_seconds"),
        "stage-reference": ("update_index", "path", "index_bytes_written", "sha256", "serialization_seconds", "fsync_seconds"),
        "native-payload": ("payload", "update_index", "path", "bytes_written", "sha256", "serialization_seconds", "fsync_seconds"),
        "native-capture-checkpoint": ("update_index", "path", "bytes_written", "sha256", "serialization_seconds", "fsync_seconds"),
        "record-artifact": ("scope", "path", "bytes_written", "sha256", "serialization_seconds", "fsync_seconds"),
        "stage-reference-hash": ("path", "bytes_read", "verification_seconds", "sha256"),
        "stage-reference-verification": ("path", "bytes_read", "verification_seconds", "sha256"),
        "native-capture-verification": ("path", "bytes_read", "verification_seconds", "sha256"),
        "native-payload-verification": ("path", "bytes_read", "verification_seconds", "sha256"),
        "stage-index-recovery-read": ("path", "bytes_read", "parse_seconds"),
        "stage-index-read": ("path", "bytes_read", "parse_seconds"),
        "stage-index-tail-verified": ("path", "bytes_read", "verification_seconds", "sha256"),
        "stage-index-tail-preserved": ("path", "bytes_written", "sha256", "serialization_seconds", "fsync_seconds"),
        "stage-index-prefix-restored": ("path", "bytes_written", "sha256", "serialization_seconds", "fsync_seconds"),
        "attempt-read": ("path", "bytes_read", "parse_seconds"),
        "stage-summary-read": ("path", "bytes_read", "parse_seconds"),
        "record-io-tail-recovery": ("path", "bytes", "sha256", "bytes_read", "verification_seconds",
            "tail_bytes_written", "prefix_repair_bytes_written", "serialization_seconds", "fsync_seconds",
            "metric_effect"),
    }
    if not isinstance(operation, str) or operation not in required:
        raise _RecordIoIntegrityError(f"unknown record I/O operation at row {row_number}")
    for key in required[operation]:
        if key not in event:
            raise _RecordIoIntegrityError(f"{operation} is missing {key} at row {row_number}")
    string_fields = {"path", "sha256", "scope", "payload", "metric_effect"}
    integer_fields = {"update_index", "bytes", "bytes_written", "bytes_read", "index_bytes_written",
        "stage_bytes", "tail_bytes_written", "prefix_repair_bytes_written"}
    number_fields = {"serialization_seconds", "fsync_seconds", "verification_seconds", "parse_seconds"}
    for key in string_fields.intersection(event):
        if not isinstance(event[key], str) or not event[key]:
            raise _RecordIoIntegrityError(f"{operation}.{key} must be a nonempty string at row {row_number}")
    for key in integer_fields.intersection(event):
        value = event[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise _RecordIoIntegrityError(f"{operation}.{key} must be a nonnegative integer at row {row_number}")
    for key in number_fields.intersection(event):
        value = event[key]
        finite = isinstance(value, int) or (isinstance(value, float) and math.isfinite(value))
        if isinstance(value, bool) or not finite or value < 0:
            raise _RecordIoIntegrityError(f"{operation}.{key} must be a finite nonnegative number at row {row_number}")


def _recover_io_log_tail(attempt_dir: Path) -> dict[str, Any] | None:
    """Preserve an unterminated telemetry row before allowing another append."""
    if _read_io_status(attempt_dir) is not None:
        return {"integrity_status": "invalid"}
    path = attempt_dir / IO_LOG
    if not path.is_file() or path.stat().st_size == 0:
        return None
    with path.open("rb") as stream:
        stream.seek(-1, os.SEEK_END)
        if stream.read(1) == b"\n":
            return None
    started = time.perf_counter()
    data = path.read_bytes()
    prefix_end = data.rfind(b"\n") + 1
    prefix, tail = data[:prefix_end], data[prefix_end:]
    recovery_evidence = []
    try:
        for row_number, raw_line in enumerate(prefix.splitlines(), start=1):
            if not raw_line.strip():
                continue
            try:
                event = json.loads(raw_line)
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise _RecordIoIntegrityError(f"malformed completed row {row_number}") from error
            _validate_io_event(event, row_number)
    except _RecordIoIntegrityError as error:
        if tail:
            evidence = _preserve_io_tail(attempt_dir, tail)
            recovery_evidence.append(evidence)
        _mark_io_invalid(attempt_dir, f"{error}; original journal bytes preserved",
            recovery_evidence=recovery_evidence)
        return {"integrity_status": "invalid"}
    digest = hashlib.sha256(tail).hexdigest()
    tail_name = f"record-io-tail-{digest}.bin"
    tail_path = attempt_dir / tail_name
    if tail_path.exists():
        existing = tail_path.read_bytes()
        if existing != tail:
            evidence = _preserve_io_tail(attempt_dir, tail, collision=True)
            _mark_io_invalid(attempt_dir, "preserved record I/O tail path has changed contents",
                recovery_evidence=[evidence])
            return {"integrity_status": "invalid"}
        tail_bytes_written = 0
        tail_receipt = None
    else:
        tail_receipt = atomic_bytes(tail_path, tail)
        tail_bytes_written = len(tail)
    prefix_receipt = atomic_bytes(path, prefix)
    return {"path": tail_name, "bytes": len(tail), "sha256": digest,
        "bytes_read": len(data), "verification_seconds": time.perf_counter() - started,
        "tail_bytes_written": tail_bytes_written,
        "prefix_repair_bytes_written": prefix_receipt.bytes_written,
        "serialization_seconds": ((tail_receipt.serialization_seconds if tail_receipt else 0.0)
            + prefix_receipt.serialization_seconds),
        "fsync_seconds": ((tail_receipt.fsync_seconds if tail_receipt else 0.0)
            + prefix_receipt.fsync_seconds),
        "metric_effect": "torn source event is unknown; only the preserved evidence write is counted"}


def _preserve_io_tail(attempt_dir: Path, tail: bytes, *, collision: bool = False) -> dict[str, Any]:
    digest = hashlib.sha256(tail).hexdigest()
    suffix = "-collision" if collision else ""
    tail_name = f"record-io-tail-{digest}{suffix}.bin"
    tail_path = attempt_dir / tail_name
    if tail_path.exists() and tail_path.read_bytes() != tail:
        raise OSError("cannot preserve record I/O tail without overwriting existing evidence")
    if tail_path.exists():
        bytes_written = 0
    else:
        receipt = atomic_bytes(tail_path, tail)
        bytes_written = receipt.bytes_written
    return {"path": tail_name, "bytes": len(tail), "sha256": digest,
        "bytes_written": bytes_written}


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
    metadata_serialization_started = time.perf_counter()
    metadata_bytes = (json.dumps(metadata, indent=2, allow_nan=False) + "\n").encode("utf-8")
    metadata_serialization_seconds = time.perf_counter() - metadata_serialization_started
    metadata_digest = hashlib.sha256(metadata_bytes).hexdigest()
    meta_path = attempt_dir / f"{stem}-{metadata_digest}.json"
    if meta_path.exists():
        if meta_path.stat().st_size != len(metadata_bytes) or file_sha256(meta_path) != metadata_digest:
            raise ValueError("content-addressed native capture metadata exists with different contents")
        receipt = WriteReceipt(meta_path.name, len(metadata_bytes), metadata_digest,
            metadata_serialization_seconds, 0.0)
    else:
        written = atomic_bytes(meta_path, metadata_bytes)
        receipt = WriteReceipt(written.path, written.bytes_written, written.sha256,
            written.serialization_seconds + metadata_serialization_seconds, written.fsync_seconds)
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


def write_record_artifact(attempt_dir: Path, path: Path, value: Any,
                          scope: str) -> WriteReceipt:
    receipt = atomic_json(path, value)
    append_io_event(attempt_dir, {"operation": "record-artifact", "scope": scope,
        "path": str(path.relative_to(attempt_dir)), "bytes_written": receipt.bytes_written,
        "sha256": receipt.sha256, "serialization_seconds": receipt.serialization_seconds,
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
    digest = _record_hash_read(attempt_dir, path, "stage-reference-hash")
    row = {"schema": STAGE_REFERENCE_SCHEMA, "update_index": update_index,
        "path": relative, "bytes": byte_count, "sha256": digest}
    index_receipt = append_jsonl(attempt_dir / STAGE_INDEX, row)
    append_io_event(attempt_dir, {"operation": "stage-reference", "update_index": update_index,
        "path": relative, "stage_bytes": byte_count, "index_bytes_written": index_receipt.bytes_written,
        "sha256": digest, "serialization_seconds": index_receipt.serialization_seconds,
        "fsync_seconds": index_receipt.fsync_seconds})
    return row


def finalize_stage(attempt_dir: Path, update_index: int, value: Mapping[str, Any]) -> dict[str, Any]:
    receipt = write_stage(attempt_dir, update_index, value)
    reference = {"schema": STAGE_REFERENCE_SCHEMA, "update_index": update_index,
        "path": receipt.path, "bytes": receipt.bytes_written, "sha256": receipt.sha256}
    index_receipt = append_jsonl(attempt_dir / STAGE_INDEX, reference)
    append_io_event(attempt_dir, {"operation": "stage-reference", **reference,
        "index_bytes_written": index_receipt.bytes_written,
        "serialization_seconds": index_receipt.serialization_seconds,
        "fsync_seconds": index_receipt.fsync_seconds})
    return reference


def _verified_index_prefix(attempt_dir: Path) -> tuple[list[dict[str, Any]], bytes, bytes]:
    """Return checked complete rows, exact prefix bytes, and any unterminated tail."""
    path = attempt_dir / STAGE_INDEX
    if not path.exists():
        return [], b"", b""
    started = time.perf_counter()
    data = path.read_bytes()
    prefix_end = data.rfind(b"\n") + 1
    prefix = data[:prefix_end]
    tail = data[prefix_end:]
    references: list[dict[str, Any]] = []
    expected = 0
    try:
        for raw_line in prefix.splitlines():
            if not raw_line.strip():
                continue
            try:
                reference = json.loads(raw_line)
            except json.JSONDecodeError as error:
                raise ValueError(f"stage reference index is malformed at row {expected}") from error
            if (not isinstance(reference, dict) or reference.get("schema") != STAGE_REFERENCE_SCHEMA
                    or reference.get("update_index") != expected):
                raise ValueError(f"stage reference index is not contiguous at row {expected}")
            _reference_path(attempt_dir, reference)
            references.append(reference)
            expected += 1
    finally:
        append_io_event(attempt_dir, {"operation": "stage-index-recovery-read",
            "path": STAGE_INDEX, "bytes_read": len(data),
            "parse_seconds": time.perf_counter() - started})
    return references, prefix, tail


def register_orphan_stages(attempt_dir: Path,
                           diagnostics: list[dict[str, Any]] | None = None) -> int:
    """Recover a verified index prefix and index stage files left after interruption.

    Only an unterminated final JSONL fragment is recoverable. Its exact bytes are
    saved under a content-addressed name before the index is atomically restored
    to the checked prefix. A malformed newline-terminated row remains fatal.
    """
    indexed, prefix, torn_tail = _verified_index_prefix(attempt_dir)
    if torn_tail:
        digest = hashlib.sha256(torn_tail).hexdigest()
        tail_name = f"stage-records-tail-{digest}.bin"
        tail_path = attempt_dir / tail_name
        if tail_path.exists():
            verify_started = time.perf_counter()
            if tail_path.stat().st_size != len(torn_tail) or file_sha256(tail_path) != digest:
                raise ValueError("preserved stage-index tail file exists with different contents")
            tail_receipt = WriteReceipt(tail_name, 0, digest, 0.0, 0.0)
            append_io_event(attempt_dir, {"operation": "stage-index-tail-verified",
                "path": tail_name, "bytes_read": len(torn_tail),
                "verification_seconds": time.perf_counter() - verify_started,
                "sha256": digest})
        else:
            tail_receipt = atomic_bytes(tail_path, torn_tail)
            append_io_event(attempt_dir, {"operation": "stage-index-tail-preserved",
                "path": tail_name, "bytes_written": tail_receipt.bytes_written,
                "sha256": tail_receipt.sha256, "serialization_seconds": tail_receipt.serialization_seconds,
                "fsync_seconds": tail_receipt.fsync_seconds})
        index_path = attempt_dir / STAGE_INDEX
        index_receipt = atomic_bytes(index_path, prefix)
        append_io_event(attempt_dir, {"operation": "stage-index-prefix-restored",
            "path": STAGE_INDEX, "bytes_written": index_receipt.bytes_written,
            "sha256": index_receipt.sha256, "serialization_seconds": index_receipt.serialization_seconds,
            "fsync_seconds": index_receipt.fsync_seconds})
        if diagnostics is not None:
            diagnostics.append({"kind": "unterminated-jsonl-tail", "path": tail_name,
                "bytes": len(torn_tail), "sha256": tail_receipt.sha256,
                "diagnostic": "preserved unterminated final stage reference and restored the verified index prefix"})
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
    if _record_hash_read(attempt_dir, path, "stage-reference-verification") != reference.get("sha256"):
        raise ValueError(f"referenced stage hash changed: {name}")
    return path


def iter_stage_references(attempt_dir: Path, *, verify_hashes: bool = True) -> Iterable[dict[str, Any]]:
    index_path = attempt_dir / STAGE_INDEX
    if not index_path.exists():
        return
    expected = 0
    parse_seconds = 0.0
    bytes_read = index_path.stat().st_size
    try:
        with index_path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                parse_started = time.perf_counter()
                try:
                    reference = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"stage reference index is malformed at row {expected}") from error
                parse_seconds += time.perf_counter() - parse_started
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
    finally:
        append_io_event(attempt_dir, {"operation": "stage-index-read", "path": STAGE_INDEX,
            "bytes_read": bytes_read, "parse_seconds": parse_seconds})


def file_sha256(path: Path) -> str:
    return _hash_file(path)[0]


def _hash_file(path: Path) -> tuple[str, int, float]:
    digest = hashlib.sha256()
    byte_count = 0
    started = time.perf_counter()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            byte_count += len(block)
    return digest.hexdigest(), byte_count, time.perf_counter() - started


def _record_hash_read(attempt_dir: Path, path: Path, operation: str) -> str:
    digest, byte_count, elapsed = _hash_file(path)
    append_io_event(attempt_dir, {"operation": operation,
        "path": str(path.relative_to(attempt_dir)), "bytes_read": byte_count,
        "verification_seconds": elapsed, "sha256": digest})
    return digest


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
    prefix = f"native-query-{index:03d}"
    versioned = isinstance(path, str) and path.startswith(prefix + "-") and path.endswith(".json")
    legacy = path == f"native-query-{index:03d}.json"
    if not isinstance(index, int) or not (versioned or legacy):
        raise ValueError("native capture reference has a noncanonical path")
    if Path(path).name != path:
        raise ValueError("native capture reference escapes the attempt directory")
    if versioned and path != f"{prefix}-{reference.get('sha256')}.json":
        raise ValueError("native capture content-addressed path differs from its checked hash")
    meta_path = attempt_dir / path
    if not meta_path.is_file() or meta_path.stat().st_size != reference.get("bytes") or \
            _record_hash_read(attempt_dir, meta_path, "native-capture-verification") != reference.get("sha256"):
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
                _record_hash_read(attempt_dir, resolved, "native-payload-verification") != payload.get("sha256"):
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
            {"status", "observed_physical", "applied_control", "observed_next_physical",
             "native_query_capture"})
        reads.append(receipt)
        capture = fields.get("native_query_capture")
        if capture is not None:
            if not isinstance(capture, dict) or capture.get("schema") != \
                    "csl.closed-loop.native-query-capture-reference/1":
                raise ValueError("v2 stage has an invalid native capture reference")
            read_native_capture_metadata(attempt_dir, capture)
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


def verify_v2_attempt(attempt_dir: Path, record: Mapping[str, Any]) -> tuple[list, list, list[IoReceipt]] | None:
    """Verify canonical stage/native evidence and match it to cached replay summaries."""
    if record.get("format_version") != 2:
        return None
    if record.get("schema") != ATTEMPT_SCHEMA_V2:
        raise ValueError("attempt format version and schema disagree")
    stage_records = record.get("stage_records")
    if not isinstance(stage_records, dict) or stage_records.get("path") != STAGE_INDEX:
        raise ValueError("v2 attempt has a noncanonical stage index reference")
    controls, states, reads = materialize_episode_summary(attempt_dir, record)
    if "controls" in record and record.get("controls") != controls:
        raise ValueError("cached attempt controls differ from checked stage records")
    if "physical_states" in record and record.get("physical_states") != states:
        raise ValueError("cached attempt states differ from checked stage records")
    if record.get("completed_holds") != len(controls):
        raise ValueError("cached completed-hold count differs from checked stage records")
    if record.get("status") == "complete":
        expected_holds = record.get("original_intervals")
        if isinstance(expected_holds, bool) or not isinstance(expected_holds, int) or \
                len(controls) != expected_holds or stage_records.get("count") != expected_holds:
            raise ValueError("complete attempt does not contain every checked stage")
    controls_digest = hashlib.sha256(json.dumps(controls, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if record.get("controls_sha256") is not None and record.get("controls_sha256") != controls_digest:
        raise ValueError("cached controls hash differs from checked stage records")
    return controls, states, reads


def _io_unavailable(status: Mapping[str, Any]) -> dict[str, Any]:
    result = {"integrity_status": status.get("integrity_status", "invalid"),
        "metric_totals_complete": False, "metric_totals_available": False,
        "integrity_diagnostic": status.get("integrity_diagnostic", "record I/O metrics are unavailable"),
        "recovery_evidence": status.get("recovery_evidence", []),
        "integrity_record": IO_STATUS,
        "scope": "record I/O aggregates withheld because the diagnostic journal is unavailable; canonical attempt/stage data is independent"}
    if isinstance(status.get("operation"), str):
        result["invalid_operation"] = status["operation"]
    return result


def summarize_io(attempt_dir: Path) -> dict[str, Any]:
    path = attempt_dir / IO_LOG
    prior_status = _read_io_status(attempt_dir)
    if prior_status is not None:
        return _io_unavailable(prior_status)
    if not path.is_file():
        return _io_unavailable({"integrity_status": "incomplete",
            "integrity_diagnostic": "record I/O log is missing", "recovery_evidence": []})
    recovery = _recover_io_log_tail(attempt_dir)
    if recovery is not None and recovery.get("integrity_status") == "invalid":
        return _io_unavailable(_read_io_status(attempt_dir) or {})
    if recovery is not None:
        recovery_row = {"schema": IO_SCHEMA, "operation": "record-io-tail-recovery", **recovery}
        try:
            _validate_io_event(recovery_row, 0)
            append_jsonl(path, recovery_row)
        except (TypeError, ValueError, OverflowError) as error:
            status = _mark_io_invalid(attempt_dir,
                f"recovery event is invalid: {type(error).__name__}: {error}",
                operation="record-io-tail-recovery")
            return _io_unavailable(status)

    totals: dict[str, Any] = {"checkpoint_writes": 0, "stage_writes": 0,
        "reference_writes": 0, "attempt_json_bytes_written": 0,
        "stage_json_bytes_written": 0, "native_payload_bytes_written": 0,
        "native_capture_checkpoint_bytes_written": 0, "reference_index_bytes_written": 0,
        "record_artifact_bytes_written": 0, "recovery_evidence_bytes_written": 0,
        "record_io_recovery_evidence_bytes_written": 0,
        "record_io_prefix_repair_bytes_written": 0,
        "index_repair_bytes_written": 0, "total_record_bytes_written": 0,
        "bytes_read": 0, "parse_seconds": 0.0, "verification_seconds": 0.0,
        "serialization_seconds": 0.0, "fsync_seconds": 0.0}
    try:
        with path.open("r", encoding="utf-8") as stream:
            for row_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as error:
                    raise _RecordIoIntegrityError(
                        f"malformed completed row {row_number}") from error
                _validate_io_event(event, row_number)
                operation = event["operation"]
                if operation == "attempt-checkpoint":
                    totals["checkpoint_writes"] += 1
                    totals["attempt_json_bytes_written"] += event["bytes_written"]
                    totals["total_record_bytes_written"] += event["bytes_written"]
                elif operation == "stage-checkpoint":
                    totals["stage_writes"] += 1
                    totals["stage_json_bytes_written"] += event["bytes_written"]
                    totals["total_record_bytes_written"] += event["bytes_written"]
                elif operation == "stage-reference":
                    totals["reference_writes"] += 1
                    index_bytes = event["index_bytes_written"]
                    totals["reference_index_bytes_written"] += index_bytes
                    totals["total_record_bytes_written"] += index_bytes
                elif operation == "native-payload":
                    totals["native_payload_bytes_written"] += event["bytes_written"]
                    totals["total_record_bytes_written"] += event["bytes_written"]
                elif operation == "native-capture-checkpoint":
                    totals["native_capture_checkpoint_bytes_written"] += event["bytes_written"]
                    totals["total_record_bytes_written"] += event["bytes_written"]
                elif operation == "record-artifact":
                    totals["record_artifact_bytes_written"] += event["bytes_written"]
                    totals["total_record_bytes_written"] += event["bytes_written"]
                elif operation == "stage-index-tail-preserved":
                    totals["recovery_evidence_bytes_written"] += event["bytes_written"]
                    totals["total_record_bytes_written"] += event["bytes_written"]
                elif operation == "stage-index-prefix-restored":
                    totals["index_repair_bytes_written"] += event["bytes_written"]
                    totals["total_record_bytes_written"] += event["bytes_written"]
                elif operation == "record-io-tail-recovery":
                    totals["record_io_recovery_evidence_bytes_written"] += event["tail_bytes_written"]
                    totals["record_io_prefix_repair_bytes_written"] += event["prefix_repair_bytes_written"]
                    totals["total_record_bytes_written"] += event["tail_bytes_written"]
                if "bytes_read" in event:
                    totals["bytes_read"] += event["bytes_read"]
                    totals["parse_seconds"] += event.get("parse_seconds", 0.0)
                    totals["verification_seconds"] += event.get("verification_seconds", 0.0)
                totals["serialization_seconds"] += event.get("serialization_seconds", 0.0)
                totals["fsync_seconds"] += event.get("fsync_seconds", 0.0)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, KeyError, OverflowError) as error:
        status = _mark_io_invalid(attempt_dir,
            f"{type(error).__name__}: {error}; metric aggregates withheld")
        return _io_unavailable(status)

    totals["scope"] = ("attempt/stage checkpoints, native payload and capture records, stage-reference index, "
        "checked reference hash reads, held-step request artifacts, torn stage/telemetry tail preservation and journal repair, "
        "and selective record reads; "
        "excludes controller query, execution process, replay/checker/render, and telemetry-log append scopes")
    evidence = []
    for tail_path in sorted(attempt_dir.glob("record-io-tail-*.bin")):
        tail_bytes = tail_path.read_bytes()
        evidence.append({"path": tail_path.name, "bytes": len(tail_bytes),
            "sha256": hashlib.sha256(tail_bytes).hexdigest()})
    totals["integrity_status"] = "incomplete" if evidence else "complete"
    totals["metric_totals_complete"] = not evidence
    totals["metric_totals_available"] = True
    totals["recovery_evidence"] = evidence
    if evidence:
        totals["metric_totals_scope"] = (
            "totals cover only verified complete telemetry rows; preserved torn bytes are excluded and "
            "missing metric values are unknown")
    return totals
