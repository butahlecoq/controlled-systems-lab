#!/usr/bin/env python3
"""Verify native nominal-forward capture preserves its successful prefix and gaps."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route-executable", type=Path, required=True)
    args = parser.parse_args()
    executable = args.route_executable.resolve(strict=True)
    source_path = ROOT / "benchmarks/reporting/stage-projection/examples/fuel-four-state.json"
    source_bytes = source_path.read_bytes()
    source = json.loads(source_bytes)
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    with tempfile.TemporaryDirectory(prefix="stage-projection-route-") as directory:
        output = Path(directory) / "native-batch.json"
        subprocess.run([str(executable), str(source_path), source_hash, str(output)], check=True)
        raw = output.read_bytes()
    batch = json.loads(raw)
    digest = batch.pop("content_sha256")
    canonical = json.dumps(batch, ensure_ascii=False, allow_nan=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != digest:
        raise SystemExit("native route batch content hash mismatch")
    provenance = batch["provenance"]
    if (batch["schema"] != "csl.stage-projection-batch/1"
            or provenance["run_id"] != source["run_id"]
            or batch["request_id"] != source["request_id"]
            or batch["route_id"] != "reachability.nominal_forward"
            or provenance["record_schema"] != source["record_schema"]
            or provenance["source_sha256"] != source_hash):
        raise SystemExit("native route batch source identity mismatch")
    statuses = {(record["pair_index"], record["stage"]): record["outcome"]["status"]
                for record in batch["records"]}
    pairs = len(source["coordinate_pairs"])
    expected = {(pair, stage): ("success" if stage < 2 else "unavailable")
                for pair in range(pairs) for stage in range(source["dynamics"]["horizon"] + 1)}
    if statuses != expected:
        raise SystemExit(f"stage outcomes differ: {statuses}")
    failure_details = [record["outcome"].get("explanation", "") for record in batch["records"]
                       if record["stage"] == 2]
    later_details = [record["outcome"].get("explanation", "") for record in batch["records"]
                     if record["stage"] > 2]
    if not failure_details or not all("affine_rank" in detail for detail in failure_details):
        raise SystemExit("the native provider's R2 failure is not preserved")
    if not later_details or not all("stopped at R2" in detail for detail in later_details):
        raise SystemExit("later stage gaps do not identify the native route stopping point")
    print("native nominal_forward batch hash, source identity, successful prefix, and explicit gaps verified")


if __name__ == "__main__":
    main()
