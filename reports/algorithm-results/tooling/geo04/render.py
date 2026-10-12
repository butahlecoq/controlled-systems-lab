#!/usr/bin/env python3
"""Render the saved GEO-04 report records without invoking native code."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import zipfile
from pathlib import Path

SCHEMA = "csl.geo04-polyhedral-report/1"
PHASES = ("intersection_ns", "prepare_ns", "workspace_ns", "conversion_run_ns", "lp_workspace_ns", "reduction_ns", "total_ns")
CATALOG_VERSION = "geo04-analytic-v1"
PINNED_EXPECTED = {
    "crossing_octagon": {"inputs": {"left_A": [[1,0],[-1,0],[0,1],[0,-1]], "left_b": [1,1,1,1],
                                     "right_A": [[1,1],[1,-1],[-1,1],[-1,-1]], "right_b": [1.5]*4},
                         "vertices": [[1,.5],[1,-.5],[-1,.5],[-1,-.5],[.5,1],[-.5,1],[.5,-1],[-.5,-1]], "inequalities": 8, "equalities": 0},
    "empty_intersection": {"inputs": {"left_A": [[1,0]], "left_b": [0], "right_A": [[-1,0]], "right_b": [-1]}, "vertices": [], "inequalities": 2},
    "affine_equality": {"inputs": {"A": [[1,0],[-1,0]], "b": [2,0], "E": [[0,1]], "f": [1]},
                        "vertices": [[0,1],[2,1]], "inequalities": 4, "equalities": 2},
    "essential_rows_highs": {"inputs": {"A": [[1,0],[-1,0],[0,1]], "b": [1,0,0], "E": [[0,1]], "f": [0]},
                             "inequalities": 3, "equalities": 1, "reduction_status": "incomplete", "lp_calls": 3, "removed_inequalities": []},
}
PINNED_SCENARIOS = tuple(PINNED_EXPECTED)
FILES = ("records.json", "collection-status.json", "raw-events.jsonl", "raw-driver-output.csv", "process-stderr.txt",
         "measurement-command.txt", "build-provenance.txt", "concurrent-work.txt", "profile-evidence.txt", "scenarios.json", "environment.json")


def vertices_match_expected(points: list, expected_points: list, tolerance: float = 1e-7) -> bool:
    if len(points) != len(expected_points):
        return False
    consumed: set[int] = set()
    for point in points:
        if len(point) != 2:
            return False
        match = next((index for index, candidate in enumerate(expected_points)
                      if index not in consumed and all(abs(float(actual)-float(wanted)) <= tolerance
                                                       for actual, wanted in zip(point, candidate))), None)
        if match is None:
            return False
        consumed.add(match)
    return len(consumed) == len(expected_points)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(payload: dict) -> None:
    if payload.get("schema") != SCHEMA or not payload.get("report_id", "").startswith("geo04-"):
        raise ValueError("unsupported GEO-04 record schema or report ID")
    if payload.get("algorithm", {}).get("id") != "GEO-04":
        raise ValueError("unexpected algorithm identity")
    claimed = payload.get("payload_sha256")
    unsigned = {key:value for key,value in payload.items() if key not in ("report_id", "payload_sha256", "payload_hash_scope")}
    actual = hashlib.sha256(json.dumps(unsigned,sort_keys=True,separators=(",", ":"),allow_nan=False).encode()).hexdigest()
    if claimed != actual or payload.get("payload_hash_scope") != "canonical JSON payload excluding report_id and payload_sha256":
        raise ValueError("saved record payload digest mismatch")
    scenarios = payload.get("expected", {})
    if payload.get("inputs", {}).get("scenario_catalog_version") != CATALOG_VERSION or scenarios != PINNED_EXPECTED:
        raise ValueError("scenario catalog differs from pinned catalog")
    catalog_hash = hashlib.sha256(json.dumps(PINNED_EXPECTED,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
    if catalog_hash != payload.get("inputs", {}).get("scenario_catalog_sha256"):
        raise ValueError("scenario catalog hash mismatch")
    for key in ("crossing_octagon", "empty_intersection", "affine_equality", "essential_rows_highs"):
        if key not in payload.get("summary", {}):
            raise ValueError(f"missing scenario summary: {key}")
    for trial in payload.get("trials", []):
        if trial["scenario"] not in payload["summary"]:
            raise ValueError("trial references unknown scenario")
        case = scenarios[trial["scenario"]]
        case_hash = hashlib.sha256(json.dumps(case,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        input_hash = hashlib.sha256(json.dumps(case["inputs"],sort_keys=True,separators=(",", ":")).encode()).hexdigest()
        if trial.get("scenario_sha256") != case_hash or trial.get("input_sha256") != input_hash:
            raise ValueError("trial input/scenario hash mismatch")
        for key in ("inequalities", "equalities"):
            if key in case and trial[key] != case[key]:
                raise ValueError(f"unexpected {key} for {trial['scenario']}")
        for phase in PHASES:
            value = trial.get(phase)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError("trial phase durations must be nonnegative integer nanoseconds")
        if "vertices" in case and trial.get("vertices_json") != case["vertices"]:
            points = trial.get("vertices_json", [])
            expected = case["vertices"]
            if not vertices_match_expected(points, expected):
                raise ValueError("saved vertex coordinates fail independent literal oracle")
        if trial["scenario"] == "essential_rows_highs" and not (
            trial["reduction_status"] == "incomplete" and trial["lp_calls"] == 3 and
            trial["lp_bounds"] == 0 and trial["lp_supported_bounds"] == 0 and
            trial["inequalities"] == 3 and trial["equalities"] == 1
        ):
            raise ValueError("saved HiGHS reduction evidence differs from the supported-bound contract")
    collection = payload["collection"]
    trials = payload.get("trials", [])
    repetitions = collection.get("measured_repetitions")
    expected_trials = collection.get("expected_trials")
    actual_trials = collection.get("actual_trials")
    if collection.get("state") not in ("complete", "failed"):
        raise ValueError("unknown collection state")
    if any(not isinstance(value, int) or isinstance(value, bool)
           for value in (repetitions, expected_trials, actual_trials, collection.get("failures"))):
        raise ValueError("collection counts must be integers")
    failed_rows = sum(trial["status"] != "passed" or not trial["oracle_passed"] for trial in trials)
    expected_failure_count = expected_trials - len(trials) + failed_rows
    trial_keys = [(trial["scenario"], trial["repetition"]) for trial in trials]
    expected_keys = {(scenario, repetition) for scenario in PINNED_SCENARIOS
                     for repetition in range(repetitions if isinstance(repetitions, int) and repetitions > 0 else 0)}
    if (not isinstance(repetitions, int) or repetitions < 7 or expected_trials != repetitions * len(PINNED_SCENARIOS) or
        actual_trials != len(trials) or len(set(trial_keys)) != len(trial_keys) or
        any(key not in expected_keys for key in trial_keys) or collection.get("failures") != expected_failure_count):
        raise ValueError("collection counts or scenario/repetition matrix are inconsistent")
    for scenario in PINNED_SCENARIOS:
        rows = [trial for trial in trials if trial["scenario"] == scenario]
        summary = payload["summary"][scenario]
        passed = sum(trial["status"] == "passed" and trial["oracle_passed"] for trial in rows)
        if summary["attempts"] != len(rows) or summary["passed"] != passed or summary["failures"] != len(rows)-passed:
            raise ValueError("scenario summary counts differ from saved trials")
        accepted = [row for row in rows if collection["state"] == "complete" and row["status"] == "passed" and row["oracle_passed"]]
        phases = summary.get("phases", {})
        if set(phases) != set(PHASES):
            raise ValueError("scenario summary phase set is incomplete or unexpected")
        for phase in PHASES:
            values = sorted(row[phase] for row in accepted)
            expected_stat = {
                "unit": "ns",
                "successful_trials": len(values),
                "median": (values[(len(values)-1)//2] + values[len(values)//2]) // 2 if values else None,
                "min": min(values) if values else None,
                "max": max(values) if values else None,
                "range": max(values)-min(values) if values else None,
                "trials_excluded_from_summary": len(rows)-len(values),
            }
            if phases[phase] != expected_stat:
                raise ValueError("phase summary differs from saved trial timings")
    if collection["state"] == "complete":
        if (set(trial_keys) != expected_keys or collection.get("failures") != 0 or
            collection.get("process_return_code") != 0 or collection.get("aborted_or_timed_out") or collection.get("parse_error") or
            any(trial["status"] != "passed" or not trial["oracle_passed"] for trial in trials)):
            raise ValueError("complete report has missing or failed trials")
    if collection["state"] != "complete":
        if any(value["median"] is not None for group in payload["summary"].values() for value in group["phases"].values()):
            raise ValueError("failed report must not summarize a filtered success subset")


def render_html(payload: dict) -> str:
    report_id = html.escape(payload["report_id"])
    algorithm = payload["algorithm"]
    rows = []
    for scenario, summary in payload["summary"].items():
        phases = summary["phases"]
        row = [html.escape(scenario), str(summary["attempts"]), str(summary["passed"]), str(summary["failures"])]
        for phase in ("intersection_ns", "prepare_ns", "workspace_ns", "conversion_run_ns", "lp_workspace_ns", "reduction_ns", "total_ns"):
            stat = phases[phase]
            value = "n/a" if stat["median"] is None else f"{stat['median']:,} ({stat['min']:,}–{stat['max']:,})"
            row.append(value)
        rows.append("<tr>"+"".join(f"<td>{value}</td>" for value in row)+"</tr>")
    trial_rows = []
    for trial in payload["trials"]:
        vals = [trial["scenario"], trial["repetition"], trial["status"], trial["oracle_passed"],
                *(trial[p] for p in ("intersection_ns", "prepare_ns", "workspace_ns", "conversion_run_ns", "lp_workspace_ns", "reduction_ns", "total_ns")),
                trial["lp_calls"], trial["lp_results"], trial["lp_optimal"], trial["lp_bounds"],
                trial["lp_supported_bounds"], trial["reduction_status"], json.dumps(trial["vertices_json"],separators=(",", ":")), trial["detail"]]
        trial_rows.append("<tr>"+"".join(f"<td>{html.escape(str(value))}</td>" for value in vals)+"</tr>")
    source = html.escape(algorithm["source_commit"])
    harness = html.escape(algorithm["harness_commit"])
    evidence = html.escape(payload["evidence"]["essential_row_result"])
    limits = "".join(f"<li>{html.escape(item)}</li>" for item in payload["evidence"]["limitations"])
    status = html.escape(payload["collection"]["state"])
    chart = render_svg(payload)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{report_id} — GEO-04</title><style>body{{font:16px system-ui,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#172033}}table{{border-collapse:collapse;width:100%;overflow:auto;display:block}}th,td{{border:1px solid #ccd3df;padding:.4rem;text-align:left;white-space:nowrap}}th{{background:#edf1f7}}code{{overflow-wrap:anywhere}}.note{{background:#f3f6fb;padding:1rem}}</style></head><body>
<h1>GEO-04 polyhedral intersection and halfspace reduction</h1><p>Report <code>{report_id}</code>; collection state: <strong>{status}</strong>.</p>
<p>Algorithm source <code>{source}</code>; report harness <code>{harness}</code>. Binary64 numerical fixtures; no exact validated-geometry claim.</p>
<h2>Measured phase summaries</h2><p>Nanoseconds; each cell is median (min–max) across passing repetitions. Failed attempts remain in the trial table and are excluded from summaries.</p>
<table><thead><tr><th>Scenario</th><th>Attempts</th><th>Passed</th><th>Failures</th><th>Intersection</th><th>Pipeline preparation</th><th>Conversion workspace</th><th>Conversion run</th><th>LP workspace</th><th>Reduction + LP</th><th>Whole trial</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>Phase timing figure</h2>{chart}<h2>Scientific and evidence scope</h2><div class="note"><p>{evidence}</p><p>The fixed-bound unit-test fixture is not a benchmark backend and supplies no performance measurements.</p></div>
<ul>{limits}</ul><p>No competitor, speedup, application-scale, or scalability claim is made. Workspace timing includes only the named public workspace creation phase; reduction timing includes its internal LP queries, whose separate timings are unavailable.</p>
<h2>Per-repetition records</h2><table><thead><tr><th>Scenario</th><th>Rep.</th><th>Status</th><th>Oracle</th><th>Intersection ns</th><th>Prepare ns</th><th>Converter workspace ns</th><th>Conversion run ns</th><th>LP workspace ns</th><th>Reduction ns</th><th>Whole trial ns</th><th>LP calls</th><th>LP results</th><th>Optimal claims</th><th>Objective bounds</th><th>Supported bounds</th><th>Reduction status</th><th>Observed V vertices (binary64)</th><th>Failure detail</th></tr></thead><tbody>{''.join(trial_rows)}</tbody></table>
<h2>Provenance and offline files</h2><ul>{''.join(f'<li><a href="{html.escape(name)}">{html.escape(name)}</a></li>' for name in FILES if name in payload.get('_files', []))}</ul>
<p>Hardware, OS, compiler/build flags, configured worker counts, tolerances, load observations and unavailable evidence are in records and provenance files. See the offline ZIP for the complete bundle.</p></body></html>'''


def render_svg(payload: dict) -> str:
    scenarios = list(payload["summary"].items())
    labels = ("intersection", "prepare", "converter ws", "conversion run", "LP workspace", "reduction + LP", "whole trial")
    keys = ("intersection_ns", "prepare_ns", "workspace_ns", "conversion_run_ns", "lp_workspace_ns", "reduction_ns", "total_ns")
    colors = ("#3568a8", "#4c956c", "#db8b25", "#8b63a8", "#a97842", "#bb5353", "#4b8f9c")
    max_value = max((phase["median"] or 0 for _, group in scenarios for phase in group["phases"].values()), default=0)
    width, left, scale = 900, 240, 600 / max(max_value, 1)
    height = 80 + 120*len(scenarios)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Median phase duration by GEO-04 scenario" viewBox="0 0 {width} {height}">',
             '<style>text{font:13px system-ui,sans-serif;fill:#172033}</style>']
    for si, (scenario, group) in enumerate(scenarios):
        y0 = 28 + si*120
        parts.append(f'<text x="8" y="{y0+13}">{html.escape(scenario)}</text>')
        for phase_index, (label, key, color) in enumerate(zip(labels, keys, colors)):
            y = y0 + phase_index*19
            parts.append(f'<text x="8" y="{y+12}">{label}</text>')
            value = group["phases"][key]["median"]
            if value is not None:
                bar_width = max(1, value*scale)
                parts.append(f'<rect x="{left}" y="{y}" width="{bar_width:.2f}" height="14" fill="{color}"/>')
                parts.append(f'<text x="{left+bar_width+6:.2f}" y="{y+12}">{value} ns</text>')
            else:
                parts.append(f'<text x="{left}" y="{y+12}">unavailable (failed group)</text>')
    parts.append('</svg>')
    return ''.join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", type=Path, required=True, help="collector output directory")
    parser.add_argument("--out", type=Path, required=True, help="new immutable report bundle directory")
    args = parser.parse_args()
    records_path = args.collection / "records.json"
    payload = json.loads(records_path.read_text(encoding="utf-8"))
    validate(payload)
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite existing report directory: {args.out}")
    missing = [name for name in FILES if not (args.collection / name).is_file()]
    if missing:
        raise SystemExit("saved collection is missing required files: "+", ".join(missing))
    args.out.mkdir(parents=True)
    for name in FILES:
        source = args.collection / name
        if source.is_file():
            shutil.copyfile(source, args.out / name)
    payload["_files"] = list(FILES)
    (args.out / "index.html").write_text(render_html(payload), encoding="utf-8")
    (args.out / "latency.svg").write_text(render_svg(payload), encoding="utf-8")
    summary = payload["summary"]
    with (args.out / "summary.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = ["scenario", "attempts", "passed", "failures", "phase", "unit", "successful_trials", "median", "min", "max", "range", "trials_excluded_from_summary"]
        import csv
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for scenario, group in summary.items():
            for phase, values in group["phases"].items():
                writer.writerow({"scenario":scenario,"attempts":group["attempts"],"passed":group["passed"],
                    "failures":group["failures"],"phase":phase,**values})
    manifest = {"schema":"csl.geo04-report-manifest/1","report_id":payload["report_id"],
                "files":{path.name:sha(path) for path in sorted(args.out.iterdir()) if path.is_file() and path.name!="manifest.json"}}
    (args.out / "manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    zip_path = args.out.parent / (payload["report_id"]+".zip")
    if zip_path.exists():
        raise SystemExit(f"refusing to overwrite existing offline bundle: {zip_path}")
    with zipfile.ZipFile(zip_path,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted(args.out.iterdir()):
            info=zipfile.ZipInfo(path.name,date_time=(1980,1,1,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=0o100644<<16
            archive.writestr(info,path.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    print(zip_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
