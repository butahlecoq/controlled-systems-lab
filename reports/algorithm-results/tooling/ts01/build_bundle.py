"""Build the immutable T-S01 report bundle from its authored exact record."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys

import report
import publication_map

ROOT = Path(__file__).resolve().parents[2]
REPORT_ID = "syn07-ts01-20261013-fe5095ce27ab"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def write_json(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8"))


def build(out=None):
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
        "performance": {"status": "unavailable", "reason": "No standalone public T-S01 execution/measurement executable or accepted harness exists at the source commit. The C++ API test is correctness coverage, not a timing harness; no proxy timing is reported.", "comparison": "none", "speedup_claim": False},
    }
    errors = report.validate(record)
    if errors:
        raise ValueError("invalid authored record: " + ", ".join(errors))
    out = Path(out) if out is not None else ROOT / REPORT_ID
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "records.json", record)
    (out / "publication-map.json").write_bytes((json.dumps(publication_map.project(record), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    (out / "index.html").write_text(report.render_html(record), encoding="utf-8", newline="\n")
    (out / "raw-events.jsonl").write_bytes(b"".join(canonical(row) + b"\n" for row in examples))
    with (out / "trials.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("id", "point", "expected_member", "actual_member", "reason"), lineterminator="\n")
        writer.writeheader()
        for row in examples:
            writer.writerow({**row, "point": json.dumps(row["point"], separators=(",", ":"))})
    write_json(out / "scenarios.json", {"assumptions": record["assumptions"], "canonical_relation": record["canonical_relation"]})
    (out / "environment.json").write_text(json.dumps({"measurement": "not performed", "timing": "unavailable", "reason": record["performance"]["reason"]}, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text(f"""# T-S01 result bundle\n\nSource commit: `{report.SOURCE_COMMIT}`. This is a correctness and analytic-result record, not a performance measurement.\n\nRebuild the native sidecars into a fresh scratch directory and validate the committed report and site with:\n\n```powershell\npython reports/algorithm-results/tooling/ts01/build_bundle.py --out-dir build/ts01-rebuilt\npython reports/algorithm-results/tooling/ts01/report.py --check reports/algorithm-results/{REPORT_ID}/records.json\npython scripts/reports/site.py --catalog reports/algorithm-results/catalog.json --check --out build/ts01-report-site\n```\n\nSee `index.html` for the full assumptions, exact relation, membership examples and assurance limits. `raw-events.jsonl` and `trials.csv` are deterministic membership-result projections.\n""", encoding="utf-8", newline="\n")
    manifest_files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
    write_json(out / "manifest.json", {"schema": "csl.syn07-ts01-report-manifest/1", "report_id": REPORT_ID, "source_commit": report.SOURCE_COMMIT, "files": manifest_files})
    print(REPORT_ID)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    build(args.out_dir)
