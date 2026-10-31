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
    for stem in ("fuel-four-state", "nonfuel-integrator"):
        source_path = ROOT / f"benchmarks/reporting/stage-projection/examples/{stem}.json"
        source_bytes = source_path.read_bytes()
        source = json.loads(source_bytes)
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        with tempfile.TemporaryDirectory(prefix="stage-projection-route-") as directory:
            output = Path(directory) / "native-batch.json"
            subprocess.run([str(executable), str(source_path), source_hash, str(output)], check=True)
            raw = output.read_bytes()
            evidence = json.loads(Path(f"{output}.evidence.json").read_text(encoding="utf-8"))
        serialized = raw.decode("utf-8") + json.dumps(evidence, ensure_ascii=False)
        if "fuel-control-" in serialized or "fuel-stage-v-" in serialized:
            raise SystemExit(f"generic nominal-forward route leaked fuel-specific IDs for {stem}")
        batch = json.loads(raw)
        digest = batch.pop("content_sha256")
        canonical = json.dumps(batch, ensure_ascii=False, allow_nan=False, sort_keys=True,
                               separators=(",", ":")).encode("utf-8")
        if hashlib.sha256(canonical).hexdigest() != digest:
            raise SystemExit(f"native route batch content hash mismatch for {stem}")
        evidence_digest = evidence.pop("content_sha256", None)
        evidence_canonical = json.dumps(evidence, ensure_ascii=False, allow_nan=False,
                                        sort_keys=True, separators=(",", ":")).encode("utf-8")
        if evidence_digest is not None and hashlib.sha256(evidence_canonical).hexdigest() != evidence_digest:
            raise SystemExit(f"native route evidence content hash mismatch for {stem}")
        provenance = batch["provenance"]
        if (batch["schema"] != "csl.stage-projection-batch/1"
                or provenance["run_id"] != source["run_id"]
                or batch["request_id"] != source["request_id"]
                or batch["route_id"] != source["route_id"]
                or provenance["record_schema"] != source["record_schema"]
                or provenance["source_sha256"] != source_hash):
            raise SystemExit(f"native route batch source identity mismatch for {stem}")
        if (evidence["schema"] != "csl.nominal-forward-stage-evidence/1"
                or evidence["run_id"] != source["run_id"]
                or evidence["problem_id"] != batch["problem_id"]
                or evidence["request_id"] != source["request_id"]
                or evidence["route_id"] != source["route_id"]
                or evidence["source_sha256"] != source_hash
                or len(evidence["stage_sources"]) != 2
                or not all("marginal_evidence" in stage and "capture_source_evidence" in stage
                           and "marginal_representation" in stage
                           and stage["providers"] for stage in evidence["stage_sources"])):
            raise SystemExit(f"native route evidence sidecar is incomplete or mismatched for {stem}")
        if any("h_to_v" in stage for stage in evidence["stage_sources"]):
            raise SystemExit(f"native route materialized a full-dimensional stage marginal for {stem}")
        statuses = {(record["pair_index"], record["stage"]): record["outcome"]["status"]
                    for record in batch["records"]}
        pairs = len(source["coordinate_pairs"])
        expected = {(pair, stage): ("success" if stage < 2 else "unavailable")
                    for pair in range(pairs) for stage in range(source["dynamics"]["horizon"] + 1)}
        if statuses != expected:
            raise SystemExit(f"stage outcomes differ for {stem}: {statuses}")
        marginal_ids = {stage["stage"]: stage["marginal_set_id"]
                        for stage in evidence["stage_sources"]}
        if any(stage["capture_source_evidence"]["reference"]["ideal_output"] !=
               stage["marginal_set_id"] for stage in evidence["stage_sources"]):
            raise SystemExit(f"capture source evidence is not bound to the original marginal for {stem}")
        if any(tuple(record["source_set_ids"]) != (marginal_ids[record["stage"]],)
               for record in batch["records"] if record["outcome"]["status"] == "success"):
            raise SystemExit(f"capture did not project original marginal sets directly for {stem}")
        for record in batch["records"]:
            if record["outcome"]["status"] != "success":
                continue
            evidence_chain = record["outcome"]["evidence"]
            components = record["outcome"]["components"]
            if len(evidence_chain) != 2 or len(components) != 1:
                raise SystemExit(f"projected H set and 2D V materialization were not both retained for {stem}")
            projection_evidence, materialization_evidence = evidence_chain
            if (projection_evidence["input_set_ids"] != [marginal_ids[record["stage"]]]
                    or materialization_evidence["input_set_ids"] != [projection_evidence["ideal_output_id"]]
                    or materialization_evidence["ideal_output_id"] != components[0]["component_id"]
                    or not materialization_evidence.get("provider", {}).get("id")
                    or not materialization_evidence["provider"].get("version")):
                raise SystemExit(f"2D materialization evidence is not linked to the source projection for {stem}")
        failure_details = [record["outcome"].get("explanation", "") for record in batch["records"]
                           if record["stage"] == 2]
        later_details = [record["outcome"].get("explanation", "") for record in batch["records"]
                         if record["stage"] > 2]
        if not failure_details or not all("affine_rank" in detail for detail in failure_details):
            raise SystemExit(f"the native provider's R2 failure is not preserved for {stem}")
        if not later_details or not all("stopped at R2" in detail for detail in later_details):
            raise SystemExit(f"later stage gaps do not identify the stop for {stem}")
        print(f"native nominal_forward batch hash, source identity, successful prefix, and explicit gaps verified for {stem}")


if __name__ == "__main__":
    main()
