#!/usr/bin/env python3
"""Cross-check a saved B06 numerical capture against its integer exhaustive oracle."""
import json
import hashlib
import math
import statistics
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile

import scenario_contract


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_capture.py RESULT_DIRECTORY")
    root = Path(sys.argv[1])
    repo = Path(__file__).resolve().parents[3]
    fixture = (root / "scenario.json").read_bytes()
    oracle = json.loads((root / "exact-oracle.json").read_text())
    rows = [json.loads(line) for line in (root / "raw-runs.jsonl").read_text().splitlines()]
    if len(rows) != 8 or [r["batch"] for r in rows] != list(range(8)):
        raise SystemExit("expected one excluded warmup and seven ordered measured calls")
    if oracle["plan_count"] != 3125 or oracle["disturbance_histories_per_plan"] != 1024:
        raise SystemExit("exact oracle did not exhaust the declared domain")
    if oracle["source_commit"] != rows[0]["source_commit"] or oracle["fixture_sha256"] != rows[0]["fixture_sha256"]:
        raise SystemExit("exact oracle source or input identity differs from solver capture")
    if len(oracle["oracle_sha256"]) != 64 or len(rows[0]["driver_sha256"]) != 64:
        raise SystemExit("missing executable source hashes")
    if hashlib.sha256(fixture).hexdigest() != rows[0]["fixture_sha256"]:
        raise SystemExit("captured scenario differs from the compiled fixture identity")
    def source_at_capture(relative_path):
        result = subprocess.run(["git", "-C", str(repo), "show",
            f"{rows[0]['source_commit']}:{relative_path}"], capture_output=True, check=False)
        if result.returncode != 0:
            raise SystemExit(f"measured source commit does not contain {relative_path}")
        return result.stdout
    driver = source_at_capture("benchmarks/reporting/issue6/b06_finite_minimax.cpp")
    oracle_source = source_at_capture("benchmarks/reporting/issue6/b06_exact_oracle.cpp")
    if hashlib.sha256(driver).hexdigest() != rows[0]["driver_sha256"]:
        raise SystemExit("measured-commit benchmark driver differs from the compiled source identity")
    if hashlib.sha256(oracle_source).hexdigest() != oracle["oracle_sha256"]:
        raise SystemExit("captured exact oracle source hash differs")
    canonical_path = repo / "benchmarks/scenarios/b06-owner-confirmed-disturbance-v1.json"
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    scenario_contract.validate(canonical)
    captured = json.loads(fixture)
    legacy_a = captured.get("model", {}).get("A_row_major")
    corrected_a = canonical["model"]["A_row_major"]
    if len(legacy_a) != 15 or len(corrected_a) != 16 or legacy_a != corrected_a[:13] + corrected_a[14:]:
        raise SystemExit("saved manifest defect does not match the reviewed single-zero B06 correction")
    corrected_capture = deepcopy(canonical)
    corrected_capture["model"]["A_row_major"] = legacy_a.copy()
    for name in ("offset", "control_catalogue_rows", "disturbance_box_per_stage"):
        corrected_capture["model"].pop(name)
    corrected_capture["objective"].pop("quadratic_terminal")
    if captured != corrected_capture:
        raise SystemExit("immutable capture scenario differs beyond the documented A matrix entry")
    if oracle["evaluated_pairs"] != 3_200_000:
        raise SystemExit("exact oracle pair count mismatch")
    if oracle["minimizing_plan_indices"] != [1936] or oracle["printed_l09_plan_index"] != 1936:
        raise SystemExit("exact minimax plan mismatch")
    exact_value = oracle["minimum_objective_squared_numerator"] / oracle["objective_numerator_denominator"]
    for row in rows:
        if row["status"] != "numerical_optimal" or row["assurance"] != "numerical":
            raise SystemExit(f"batch {row['batch']} did not complete with numerical assurance")
        if row["source_commit"] != rows[0]["source_commit"] or row["fixture_sha256"] != rows[0]["fixture_sha256"]:
            raise SystemExit("source or input identity changed during capture")
        if row["plan_count"] != 3125 or row["evaluated_terminal_vertices"] != 3_200_000:
            raise SystemExit(f"batch {row['batch']} did not evaluate all plans and vertices")
        if row["minimizing_plan_indices"] != oracle["minimizing_plan_indices"]:
            raise SystemExit(f"batch {row['batch']} minimizer differs from exact oracle")
        if not math.isclose(row["objective_squared"], exact_value, rel_tol=0, abs_tol=1e-10):
            raise SystemExit(f"batch {row['batch']} objective differs from exact oracle")
        if row["printed_plan_index"] != oracle["printed_l09_plan_index"]:
            raise SystemExit("reported L09 plan index mismatch")
        if not math.isclose(row["printed_plan_worst_squared"], exact_value, rel_tol=0, abs_tol=1e-10):
            raise SystemExit("reported L09 plan did not attain the exact reference optimum")
        if row["driver_sha256"] != rows[0]["driver_sha256"]:
            raise SystemExit("runner source identity changed during capture")
        if row["elapsed_ns"] <= 0:
            raise SystemExit(f"batch {row['batch']} has a nonpositive interval")
    geometry = json.loads((root / "geometry.json").read_text())
    if geometry["source_commit"] != rows[0]["source_commit"] or len(geometry["winner_terminal_vertices"]) != 1024:
        raise SystemExit("geometry capture source or vertex count mismatch")
    if geometry["winner_terminal_vertices"] != geometry["printed_terminal_vertices"]:
        raise SystemExit("printed L09 plan and minimizing plan terminal sets differ")
    clean_tree = json.loads((root / "clean-source-tree.json").read_text())
    if not clean_tree["clean"] or clean_tree["commit"] != rows[0]["source_commit"]:
        raise SystemExit("measurement source worktree was not clean at the captured commit")
    if (root / "stderr.txt").read_bytes() or (root / "exit-code").read_text().strip() != "0":
        raise SystemExit("measurement process failed or wrote stderr")
    capture = json.loads((root / "capture.json").read_text())
    elapsed = [row["elapsed_ns"] for row in rows[1:]]
    if (capture["timing"]["median_ns"] != statistics.median(elapsed) or
            capture["timing"]["min_ns"] != min(elapsed) or
            capture["timing"]["max_ns"] != max(elapsed) or
            capture["resources"]["process_peak_rss_kib"] != max(r["process_peak_rss_kib"] for r in rows)):
        raise SystemExit("capture summary differs from raw rows")
    file_manifest = json.loads((root / "manifest.json").read_text())
    expected_files = set(file_manifest["files"]) | {"manifest.json"}
    actual_files = {path.name for path in root.iterdir() if path.is_file()}
    if actual_files != expected_files:
        raise SystemExit("saved bundle inventory differs from its manifest")
    for name, digest in file_manifest["files"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise SystemExit(f"saved bundle hash mismatch: {name}")
    claimed_manifest = (root.parent / (root.name + ".manifest.sha256")).read_text().split()[0]
    if hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest() != claimed_manifest:
        raise SystemExit("manifest checksum differs")
    archive = root.parent / (root.name + ".zip")
    with ZipFile(archive) as zipped:
        if zipped.testzip() is not None:
            raise SystemExit("offline ZIP CRC check failed")
        members = set(zipped.namelist())
        expected = {f"{root.name}/{name}" for name in file_manifest["files"]}
        expected.add(f"{root.name}/manifest.json")
        if members != expected:
            raise SystemExit("offline ZIP inventory differs from the saved bundle")
        for name in file_manifest["files"]:
            if zipped.read(f"{root.name}/{name}") != (root / name).read_bytes():
                raise SystemExit(f"offline ZIP payload differs: {name}")
    print(json.dumps({"status": "passed", "measured_batches": 7,
        "warmup_batches": 1, "plan_count": 3125,
        "evaluated_pairs": oracle["evaluated_pairs"],
        "minimizing_plan_indices": oracle["minimizing_plan_indices"],
        "exact_objective_norm": oracle["objective_norm"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
