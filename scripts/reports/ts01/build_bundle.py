"""Build the immutable T-S01 report bundle from its authored exact record."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[3] / "reports" / "algorithm-results"

def _load_tool(name):
    spec = importlib.util.spec_from_file_location("csl_ts01_" + name, Path(__file__).with_name(name + ".py"))
    if spec is None or spec.loader is None:
        raise RuntimeError("T-S01 report tooling is unavailable: " + name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

report = _load_tool("report")
publication_map = _load_tool("publication_map")

REPORT_ID = "syn07-ts01-20261014-e22d9c2aeb05"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def write_json(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8"))


def build(out=None, measurement_dir=None):
    if measurement_dir is None:
        raise ValueError("--measurement-dir is required for this measured T-S01 result bundle")
    points = [
        ("s=0", [0, 0, 1, 0, 1], True, "Closed-segment endpoint; exact equations and bounds hold."),
        ("s=1/4", [0, 0.25, 1, 0.25, 0.75], True, "Interior dyadic parameter; exact equations and bounds hold."),
        ("s=1", [0, 1, 1, 1, 0], True, "Closed-segment endpoint; exact equations and bounds hold."),
        ("s=1-2^-53", [0, 1.0-2**-53, 1, 1.0-2**-53, 2**-53], True, "Adjacent representable dyadic coordinates sum to exactly one."),
        ("feasible_nonoptimal_zero", [0, 0, 0, 0, 0], False, "Feasible controls, but x2 is not one and objective is one."),
        ("feasible_nonoptimal_endpoint", [0, 1, 2, 1, 1], False, "Feasible controls, but x2 is two and objective is one."),
        ("off_relation_dyadic_perturbation", [0, 1, 1, 1, 2**-1074], False, "Exact binary64 sum is greater than one; no tolerance is applied."),
    ]
    examples = [{"id": name, "point": point, "expected_member": expected, "actual_member": report.contains(point), "reason": reason} for name, point, expected, reason in points]
    record = {
        "schema": report.SCHEMA,
        "report_id": REPORT_ID,
        "source_commit": report.SOURCE_COMMIT,
        "algorithm": {"strategy_id": "csl.synthesis.ts01-analytic", "strategy_version": "1", "profile_id": "ts01_exact_integrator"},
        "coordinates": report.COORDINATES,
        "scenario": {"value": {"assumptions": [
            "Discrete-time, two-step scalar system with times (0,1,2).",
            "Known initial state x0=0; unrestricted one-dimensional state at every stage.",
            "Both transitions are exactly x[t+1]=x[t]+u[t], with zero offsets and no external channels.",
            "Independent closed control intervals u0,u1 in [0,1].",
            "Nominal open-loop information; no observations, temporal constraints, or other constraints.",
            "Terminal quadratic objective has Q=2, linear coefficient -2, and offset 1: J(x2)=x2^2-2*x2+1.",
            "Requested target is exact_optimal_relation, representation csl.polyhedron.h, numerical assurance, no materialization limit, and empty transformation lineage.",
        ], "expected_objective_minimum": 0}},
        "input": {"value": {"times": [0,1,2], "initial_state": [0], "transitions": [{"A": [[1]], "B": [[1]], "offset": [0]}, {"A": [[1]], "B": [[1]], "offset": [0]}], "controls": [{"lower": [0], "upper": [1]}, {"lower": [0], "upper": [1]}], "terminal_objective": {"Q": [[2]], "linear": [-2], "offset": 1}, "request": {"profile": "ts01_exact_integrator", "target": "exact_optimal_relation", "representation": "csl.polyhedron.h", "assurance": "numerical"}}},
        "assumptions": [
            "Discrete-time, two-step scalar system with times (0,1,2).",
            "Known initial state x0=0; unrestricted one-dimensional state at every stage.",
            "Both transitions are exactly x[t+1]=x[t]+u[t], with zero offsets and no external channels.",
            "Independent closed control intervals u0,u1 in [0,1].",
            "Nominal open-loop information; no observations, temporal constraints, or other constraints.",
            "Terminal quadratic objective has Q=2, linear coefficient -2, and offset 1: J(x2)=x2^2-2*x2+1.",
            "Requested target is exact_optimal_relation, representation csl.polyhedron.h, numerical assurance, no materialization limit, and empty transformation lineage.",
        ],
        "canonical_relation": {
            "representation": "csl.polyhedron.h",
            "dimension": 5,
            "equalities": [[1,0,0,0,0],[0,1,0,-1,0],[0,0,1,0,0],[0,0,0,1,1]],
            "equality_rhs": [0,0,1,1],
            "inequalities": [[0,0,0,-1,0],[0,0,0,1,0],[0,0,0,0,-1],[0,0,0,0,1]],
            "inequality_rhs": [0,1,0,1],
            "parametric_form": "(0,s,1,s,1-s), 0<=s<=1",
            "objective_minimum": 0,
            "proof_summary": "x2=u0+u1 and J=(x2-1)^2>=0. Equality holds iff u0+u1=1; the control bounds then yield exactly the displayed closed segment.",
        },
        "membership_semantics": "Exact dyadic arithmetic for finite binary64 coordinates; no floating tolerance.",
        "membership_examples": examples,
        "evidence_limits": [
            "The complete relation is established analytically only for the strict profile listed above; admission rejects mutations outside that profile.",
            "The outer API labels assurance numerical. Validated assurance is unavailable in the shared registry contract.",
            "The proof capability is internally issued and non-forgeable by clients; serialized decoding creates an untrusted capability which publication rejects until a reviewed proof replay/exporter exists.",
            "This does not establish completeness for any generic synthesis strategy, another profile, or a decoded artifact.",
            "This report records the profile theorem and exact membership examples; it is not an independent mathematical review of the source implementation.",
        ],
        "performance": {"status": "exploratory_single_strategy" if measurement_dir else "unavailable", "reason": "Seven validated observations from a standalone Release harness; no comparison or speedup claim. Performance conclusions remain inconclusive without a limiter profile." if measurement_dir else "No standalone public T-S01 execution/measurement executable or accepted harness exists at the source commit. The C++ API test is correctness coverage, not a timing harness; no proxy timing is reported.", "comparison": "none", "speedup_claim": False},
    }
    record["scenario"]["sha256"] = report.digest(record["scenario"]["value"])
    record["input"]["sha256"] = report.digest(record["input"]["value"])
    if measurement_dir:
        measurement_dir = Path(measurement_dir)
        measurement = json.loads((measurement_dir / "collection.json").read_text(encoding="utf-8"))
        record["measurement"] = {**measurement, "events": [json.loads(line) for line in (measurement_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]}
    errors = report.validate(record)
    if errors:
        raise ValueError("invalid authored record: " + ", ".join(errors))
    out = Path(out) if out is not None else _ROOT / REPORT_ID
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "records.json", record)
    (out / "publication-map.json").write_bytes((json.dumps(publication_map.project(record), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    (out / "index.html").write_text(report.render_html(record), encoding="utf-8", newline="\n")
    (out / "raw-events.jsonl").write_bytes(b"".join(canonical(row) + b"\n" for row in examples))
    if measurement_dir:
        (out / "measurement-events.jsonl").write_bytes((measurement_dir / "events.jsonl").read_bytes())
        write_json(out / "measurement.json", record["measurement"])
        with (out / "timings.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=("repetition", "warmup", "status", "elapsed_ns", "consumed_result_marker", "termination", "outcome", "objective_lower", "objective_upper", "residuals_available"), lineterminator="\n")
            writer.writeheader()
            for event in record["measurement"]["events"]:
                writer.writerow({key: event[key] for key in writer.fieldnames})
    with (out / "trials.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("id", "point", "expected_member", "actual_member", "reason"), lineterminator="\n")
        writer.writeheader()
        for row in examples:
            writer.writerow({**row, "point": json.dumps(row["point"], separators=(",", ":"))})
    write_json(out / "scenarios.json", {"scenario": record["scenario"], "input": record["input"], "assumptions": record["assumptions"], "canonical_relation": record["canonical_relation"]})
    (out / "environment.json").write_text(json.dumps(record["measurement"]["environment"] if measurement_dir else {"measurement": "not performed", "timing": "unavailable", "reason": record["performance"]["reason"]}, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text(f"""# T-S01 result bundle\n\nSource commit: `{report.SOURCE_COMMIT}`. Timings are exploratory single-strategy observations, not a performance verdict or speedup comparison.\n\nRebuild a measurement from the pinned clean source worktree, rebuild the bundle in a fresh scratch directory, and validate the report and catalogue with:\n\n```powershell\npython reports/algorithm-results/tooling/ts01/collect.py --cmake 'C:/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe' --dependency-cache build/ts01-report/_deps --algorithm-source-commit {report.SOURCE_COMMIT} --build-root build/ts01-source-build --out build/ts01-measurement\npython reports/algorithm-results/tooling/ts01/build_bundle.py --measurement-dir build/ts01-measurement --out-dir build/ts01-rebuilt\npython reports/algorithm-results/tooling/ts01/report.py --check reports/algorithm-results/{REPORT_ID}/records.json\npython -m unittest tests.reporting.test_ts01_report -v\npython scripts/reports/site.py --catalog reports/algorithm-results/catalog.json --check --out build/ts01-report-site\n```\n\nSee `index.html` for the full assumptions, exact relation, membership examples, timing scope and assurance limits. `raw-events.jsonl` and `trials.csv` project exact membership results; `measurement-events.jsonl`, `measurement.json` and `timings.csv` retain raw trial timings and provenance.\n""", encoding="utf-8", newline="\n")
    manifest_files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
    write_json(out / "manifest.json", {"schema": "csl.syn07-ts01-report-manifest/1", "report_id": REPORT_ID, "source_commit": report.SOURCE_COMMIT, "files": manifest_files})
    print(REPORT_ID)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--measurement-dir", type=Path, required=True)
    args = parser.parse_args()
    build(args.out_dir, args.measurement_dir)
