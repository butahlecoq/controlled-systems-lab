#!/usr/bin/env python3
"""Check deterministic, offline B08 import through the production artifact codec."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


executable = Path(sys.argv[1])
bundle = Path(sys.argv[2])
saved_bundle = Path(sys.argv[3])
source_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in bundle.iterdir() if path.is_file()}

with tempfile.TemporaryDirectory(prefix="csl-mpc03-b08-record-") as temporary:
    root = Path(temporary)
    first = root / "first.json"
    second = root / "second.json"
    subprocess.run([executable, bundle, first], check=True, capture_output=True, text=True)
    subprocess.run([executable, bundle, second], check=True, capture_output=True, text=True)
    assert first.read_bytes() == second.read_bytes(), "adapter output must be deterministic"
    archive = json.loads(first.read_text(encoding="utf-8"))
    saved_record_path = saved_bundle / "comparison-record.json"
    assert first.read_bytes() == saved_record_path.read_bytes(), "saved archive must match deterministic regeneration"
    saved_manifest = json.loads((saved_bundle / "manifest.json").read_text(encoding="utf-8"))
    assert saved_manifest["comparison_spec_id"] == archive["comparison_spec_id"]
    assert saved_manifest["comparison_run_id"] == archive["comparison_run_id"]
    assert saved_manifest["comparison_record_sha256"] == hashlib.sha256(saved_record_path.read_bytes()).hexdigest()
    for name, digest in saved_manifest["source_files"].items():
        assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == digest
    assert archive["schema"] == "csl.comparison-record/1"
    spec = json.loads(archive["spec"])
    assert spec["schema"] == "csl.comparison-spec/2"
    assert spec["input_manifest_source"] == "csl.mpc03-b08-case/1"
    assert spec["repetitions"] == 1
    assert len(spec["arms"]) == 2
    assert len(archive["attempts"]) == 2
    runs = [json.loads(attempt["run"]) for attempt in archive["attempts"]]
    events = [json.loads(attempt["measurement_payload"]) for attempt in archive["attempts"]]
    assert all(attempt["reported_status"] == "completed" for attempt in archive["attempts"])
    assert [event["mathematical_outcome"] for event in events] == ["optimal", "undetermined"]
    assert all(event["no_speed_claim"] for event in events)
    assert "relaxation_lower_bound" in events[1]
    for run in runs:
        attachments = {item["id"]: item for item in run["attachments"]}
        assert attachments["b08-case"]["schema"] == "csl.mpc03-b08-case/1"
        assert attachments["b08-disturbance-tube"]["media_type"] == "image/svg+xml"
        outcome = bytes.fromhex(attachments["b08-comparison-outcome"]["content"])
        assert json.loads(outcome)["schema"] == "csl.mpc03-b08-comparison-outcome/1"

    tampered = root / "tampered"
    shutil.copytree(bundle, tampered)
    (tampered / "solver-output.json").write_text("{}\n", encoding="utf-8")
    rejected_output = root / "must-not-exist.json"
    rejected = subprocess.run([executable, tampered, rejected_output], capture_output=True, text=True)
    assert rejected.returncode != 0
    assert not rejected_output.exists()

assert source_hashes == {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in bundle.iterdir() if path.is_file()}, "frozen bundle changed"
