#!/usr/bin/env python3
"""Validate GEO-03 saved data, typed CSV projections, and offline bundle."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import zipfile
from pathlib import Path

SCHEMA = "csl.geo03-hv-report/1"
CONVERTER = ("csl.conversion.qhull", "1.0.0+qhull.8.0.2")
LP_BACKEND = ("csl.lp.highs", "1.0.0+highs.1.11.0")
TRIAL_FIELDS = (
    "fixture", "direction", "round", "converter_id", "converter_version",
    "lp_backend_id", "lp_backend_version", "ambient_dimension",
    "input_representation", "output_representation", "input_inequalities",
    "input_equalities", "input_vertices", "input_rays", "preparation_ns",
    "workspace_creation_ns", "run_ns", "total_ns", "output_inequalities",
    "output_equalities", "output_vertices", "output_rays", "oracle_checks",
    "oracle_passed",
)
TRIAL_INTEGER_FIELDS = (
    "round", "ambient_dimension", "input_inequalities", "input_equalities",
    "input_vertices", "input_rays", "preparation_ns", "workspace_creation_ns",
    "run_ns", "total_ns", "output_inequalities", "output_equalities",
    "output_vertices", "output_rays", "oracle_checks",
)
TIMING_FIELDS = ("preparation_ns", "workspace_creation_ns", "run_ns", "total_ns")
SUMMARY_FIELDS = (
    "fixture", "direction", "trials", "failures", "all_oracles_passed",
    *(f"{field}_{suffix}_ns" for field in TIMING_FIELDS for suffix in ("median", "min", "max", "range")),
)

# Independent contract oracle: geometry dimensions and expected conversion shapes,
# authored here so CSV validation does not trust the report's own scenario metadata.
FIXTURES = {
    "square": {"inequalities": 4, "equalities": 0, "vertices": 4, "oracle_checks": {"H-to-V": 9, "V-to-H": 24}},
    "simplex": {"inequalities": 3, "equalities": 0, "vertices": 3, "oracle_checks": {"H-to-V": 7, "V-to-H": 20}},
    "embedded-segment": {"inequalities": 2, "equalities": 1, "vertices": 2, "oracle_checks": {"H-to-V": 6, "V-to-H": 21}},
    "singleton": {"inequalities": 0, "equalities": 2, "vertices": 1, "oracle_checks": {"H-to-V": 3, "V-to-H": 12}},
}
DIRECTIONS = ("H-to-V", "V-to-H")
EXPECTED_LINEAGE_AUDIT = {
    "status": "source-level review; executable equivalence not established",
    "contract_reference": "docs/contracts/polyhedral-conversion.md#lineage-audit-a17-and-a18",
    "sources": {
        "A17": {
            "path": "Scientific Research/GeoCalcLib-master/vertexEnumeration.m",
            "sha256": "d0f4ef259c0e33a48c0b2f56480e4a1c68df42a1783baf6e8110af8078e5fd19",
            "finding": "thin wrapper delegates to external libgeocalc; its algorithm and guarantees are not established by the archived wrapper",
        },
        "A18": {
            "path": "Конференция/ICIE 2018/VertexEnumeration.m",
            "sha256": "0d70893bd42066ed311b6ab36aa203e9fdf8856863cc23d9b5e254e45a87bee6",
            "finding": "homogenization, rank completion, randomized initial basis, inverse-based ray updates, and epsilon-policy division; not the Qhull polar-facet algorithm",
        },
    },
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_shape(fixture: str, direction: str) -> tuple[dict[str, int | str], dict[str, int | str]]:
    spec = FIXTURES[fixture]
    h_to_v = direction == "H-to-V"
    input_shape = {
        "ambient_dimension": 2,
        "input_representation": "H" if h_to_v else "V",
        "output_representation": "V" if h_to_v else "H",
        "input_inequalities": spec["inequalities"] if h_to_v else 0,
        "input_equalities": spec["equalities"] if h_to_v else 0,
        "input_vertices": 0 if h_to_v else spec["vertices"],
        "input_rays": 0,
    }
    output_shape = {
        "output_inequalities": 0 if h_to_v else spec["inequalities"],
        "output_equalities": 0 if h_to_v else spec["equalities"],
        "output_vertices": spec["vertices"] if h_to_v else 0,
        "output_rays": 0,
    }
    return input_shape, output_shape


def expected_summary(trials: list[dict], repetitions: int) -> list[dict]:
    summaries = []
    for fixture in sorted(FIXTURES):
        for direction in DIRECTIONS:
            rows = [row for row in trials if (row["fixture"], row["direction"]) == (fixture, direction)]
            require(len(rows) == repetitions, f"wrong trial count for {fixture} {direction}")
            require({row["round"] for row in rows} == set(range(repetitions)), f"wrong rounds for {fixture} {direction}")
            input_shape, output_shape = expected_shape(fixture, direction)
            for row in rows:
                require(all(type(row[field]) is int and row[field] >= 0 for field in TRIAL_INTEGER_FIELDS), "trial integer field has invalid type/value")
                require(all(type(row[field]) is str for field in TRIAL_FIELDS if field not in TRIAL_INTEGER_FIELDS), "trial string field has invalid type")
                require(all(row[key] == value for key, value in input_shape.items()), f"input shape differs for {fixture} {direction}")
                require(all(row[key] == value for key, value in output_shape.items()), f"output shape differs for {fixture} {direction}")
                require(row["converter_id"] == CONVERTER[0] and row["converter_version"] == CONVERTER[1], "unexpected converter identity")
                require(row["lp_backend_id"] == LP_BACKEND[0] and row["lp_backend_version"] == LP_BACKEND[1], "unexpected LP identity")
                require(row["oracle_passed"] == "true", f"oracle failed for {fixture} {direction}")
                require(row["oracle_checks"] == FIXTURES[fixture]["oracle_checks"][direction], f"wrong oracle count for {fixture} {direction}")
                require(row["run_ns"] > 0 and row["total_ns"] >= row["run_ns"], "invalid conversion timing")

            entry = {
                "fixture": fixture,
                "direction": direction,
                "trials": repetitions,
                "failures": 0,
                "all_oracles_passed": True,
            }
            for field in TIMING_FIELDS:
                values = [row[field] for row in rows]
                entry[field] = {
                    "unit": "ns",
                    "median": int(statistics.median(values)),
                    "min": min(values),
                    "max": max(values),
                    "range": max(values) - min(values),
                }
            entry["input"] = {key: value for key, value in input_shape.items() if key != "input_representation" and key != "output_representation"}
            entry["output"] = output_shape
            entry["oracle_checks_per_trial"] = FIXTURES[fixture]["oracle_checks"][direction]
            summaries.append(entry)
    return summaries


def read_csv(path: Path, expected_fields: tuple[str, ...], label: str) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        require(tuple(reader.fieldnames or ()) == expected_fields, f"{label} CSV columns differ from schema")
        rows = list(reader)
    require(all(None not in row and None not in row.values() for row in rows), f"{label} CSV row width differs from schema")
    return rows


def csv_trial_projection(trials: list[dict]) -> list[dict[str, str]]:
    return [{field: str(trial[field]) for field in TRIAL_FIELDS} for trial in trials]


def csv_summary_projection(summaries: list[dict]) -> list[dict[str, str]]:
    projected = []
    for summary in summaries:
        row = {
            "fixture": summary["fixture"],
            "direction": summary["direction"],
            "trials": str(summary["trials"]),
            "failures": str(summary["failures"]),
            "all_oracles_passed": str(summary["all_oracles_passed"]),
        }
        for field in TIMING_FIELDS:
            for suffix in ("median", "min", "max", "range"):
                row[f"{field}_{suffix}_ns"] = str(summary[field][suffix])
        projected.append(row)
    return projected


def validate(root: Path) -> None:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    require(manifest["schema"] == "csl.geo03-report-manifest/1", "manifest schema mismatch")
    wrapper = json.loads((root / "records.json").read_text(encoding="utf-8"))
    require(manifest["report_id"] == wrapper["report_id"], "manifest/report identity mismatch")
    require(set(manifest["files"]) == {path.name for path in root.iterdir() if path.is_file()} - {"manifest.json"}, "manifest inventory mismatch")
    for name, expected in manifest["files"].items():
        path = root / name
        require(path.is_file(), f"missing manifested file {name}")
        require(digest(path) == expected, f"hash mismatch: {name}")

    require(wrapper["schema"] == SCHEMA, "report schema mismatch")
    payload = wrapper["payload"]
    require(payload["schema"] == SCHEMA, "payload schema mismatch")
    actual = hashlib.sha256(canonical(payload)).hexdigest()
    require(wrapper["payload_sha256"] == actual, "payload digest mismatch")
    expected_id = f"geo03-{payload['created_utc'][:10].replace('-', '')}-{actual[:12]}"
    require(wrapper["report_id"] == expected_id, "report id does not match payload digest")

    repetitions = payload["measurement"]["repetitions"]
    measure = payload["measurement"]
    require(type(repetitions) is int and repetitions >= 5 and type(measure["warmups"]) is int and measure["warmups"] >= 1, "insufficient warmups/repetitions")
    trials = payload["trials"]
    require(len(trials) == repetitions * len(FIXTURES) * len(DIRECTIONS), "saved trial count mismatch")
    require(measure["emitted_trials"] == len(trials) and measure["expected_trials"] == len(trials), "measurement trial count mismatch")
    require(measure["failures"] == 0 and measure["process_return_code"] == 0, "measurement contains failures")
    require(payload.get("lineage_audit") == EXPECTED_LINEAGE_AUDIT, "A17/A18 source lineage audit differs from reviewed archive evidence")
    require("A17/A18 lineage not audited" not in payload["scope_limitations"], "stale lineage limitation contradicts the audit")
    literal_scenarios = payload_scenario_literal()
    require(payload["scenarios"] == literal_scenarios, "scenario metadata differs from independent fixture definitions")
    require(json.loads((root / "scenarios.json").read_text(encoding="utf-8")) == literal_scenarios, "scenario sidecar differs from independent fixture definitions")
    require({(row["fixture"], row["direction"]) for row in trials} == {(name, direction) for name in FIXTURES for direction in DIRECTIONS}, "unexpected trial groups")
    summaries = expected_summary(trials, repetitions)
    require(payload["summary"] == summaries, "saved summary differs from independently recomputed trial summary")

    raw = [json.loads(line) for line in (root / "raw-events.jsonl").read_text(encoding="utf-8").splitlines()]
    require(raw == trials, "raw JSONL differs from saved trials")
    trial_projection = csv_trial_projection(trials)
    csv_trials = read_csv(root / "trials.csv", TRIAL_FIELDS, "trial")
    require(csv_trials == trial_projection, "trials CSV does not exactly project saved trial records")
    raw_driver = read_csv(root / "raw-driver-output.csv", TRIAL_FIELDS, "raw driver")
    require(raw_driver == trial_projection, "raw driver CSV does not exactly project saved trial records")

    csv_summaries = read_csv(root / "summary.csv", SUMMARY_FIELDS, "summary")
    require(csv_summaries == csv_summary_projection(summaries), "summary CSV does not exactly project recomputed summary")

    html = (root / "index.html").read_text(encoding="utf-8")
    require("<svg" in html and "<!doctype html>" in html.lower(), "standalone HTML/SVG missing")
    require("A17/A18 source-level lineage" in html and "Executable equivalence is not established" in html, "HTML omits bounded lineage conclusion")
    require(re.search(r'(?:href|src)=["\']https?://', html, re.I) is None, "HTML has external resource")
    require(payload["limiter_profile"]["profiled_operations"] > 0, "separate limiter profile is missing")
    require((root / "profile.txt").stat().st_size > 0, "limiter profile notes are missing")
    require("no accepted workload-size baseline" in " ".join(payload["scope_limitations"]), "workload limitation missing")

    archive = root.parent / (wrapper["report_id"] + ".zip")
    require(archive.is_file(), "offline ZIP is missing")
    with zipfile.ZipFile(archive) as zf:
        require(len(zf.namelist()) == len(set(zf.namelist())), "ZIP contains duplicate members")
        require(set(zf.namelist()) == set(manifest["files"]) | {"manifest.json"}, "ZIP inventory mismatch")
        require(zf.testzip() is None, "ZIP CRC validation failed")
        require(zf.read("manifest.json") == (root / "manifest.json").read_bytes(),
                "ZIP manifest differs from adjacent manifest.json")
        for name, expected in manifest["files"].items():
            require(hashlib.sha256(zf.read(name)).hexdigest() == expected, f"ZIP hash mismatch: {name}")
    print(f"VALID {wrapper['report_id']}: {len(trials)} trials, 8 independent-oracle groups, {len(manifest['files'])} hashed bundle files")


def payload_scenario_literal() -> dict:
    """Known analytic fixture metadata, separate from report rows and CSVs."""
    return {
        "square": {"dimension": 2, "inequalities": 4, "equalities": 0, "vertices": 4, "rays": 0, "analytic_set": "[0,1] x [0,1]", "oracle": "vertex membership plus support in five literal directions"},
        "simplex": {"dimension": 2, "inequalities": 3, "equalities": 0, "vertices": 3, "rays": 0, "analytic_set": "x>=0, y>=0, x+y<=1", "oracle": "vertex membership plus support in four literal directions"},
        "embedded-segment": {"dimension": 2, "inequalities": 2, "equalities": 1, "vertices": 2, "rays": 0, "analytic_set": "{(x,0): -1<=x<=2}", "oracle": "endpoint/interior/off-set membership plus support directions"},
        "singleton": {"dimension": 2, "inequalities": 0, "equalities": 2, "vertices": 1, "rays": 0, "analytic_set": "{(2,-3)}", "oracle": "literal singleton/nearby-point membership plus support directions"},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dir", type=Path)
    validate(parser.parse_args().report_dir)
