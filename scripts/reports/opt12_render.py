#!/usr/bin/env python3
"""Validate retained OPT-12 evidence, then render a standalone report."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import statistics
import zipfile
from pathlib import Path

from opt12_fixtures import SCENARIOS, fixture_descriptions, validate_driver_fixture_events

EVIDENCE_FILES = ("raw-events.jsonl", "raw-stderr.txt", "release-build-log.txt",
                  "build-provenance.json", "executable.sha256", "measurement.exe",
                  "measurement-command.txt", "trials.csv")
MODES = ("cold", "warm")
TIMED_FIELDS = ("model_load_seconds", "basis_transfer_seconds", "solve_seconds")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_evidence(records_path: Path) -> tuple[dict, list[dict], dict[str, bytes]]:
    root = records_path.parent
    payload = json.loads(records_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("metadata"), dict) or not isinstance(payload.get("trials"), list):
        raise ValueError("records must contain metadata and a trial list")
    metadata, trials = payload["metadata"], payload["trials"]
    if metadata.get("schema") != "csl.opt12-cost-report/1":
        raise ValueError("unsupported OPT-12 records schema")
    files = {name: (root / name).read_bytes() for name in EVIDENCE_FILES}
    raw_stdout = files["raw-events.jsonl"]
    raw_stderr = files["raw-stderr.txt"]
    build_log = files["release-build-log.txt"]
    graph = json.loads(files["build-provenance.json"])
    events = [json.loads(line) for line in raw_stdout.decode("utf-8").splitlines() if line]
    if not events or events[0].get("schema") != "csl.opt12-build/1":
        raise ValueError("raw event stream lacks its build identity")
    raw_trials = [event for event in events[1:] if event.get("schema") == "csl.opt12-cost-trial/1"]
    if raw_trials != trials:
        raise ValueError("typed trial records differ from retained raw JSONL")
    validate_driver_fixture_events(events[1:])
    if len(raw_trials) + len(SCENARIOS) != len(events[1:]):
        raise ValueError("raw event stream contains an unknown OPT-12 event")
    with (root / "trials.csv").open(encoding="utf-8", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    if len(csv_rows) != len(trials):
        raise ValueError("CSV row count differs from typed trials")
    for csv_row, trial in zip(csv_rows, trials, strict=True):
        if any(csv_row.get(key, "") != ("" if trial.get(key) is None else str(trial.get(key))) for key in csv_row):
            raise ValueError("CSV trial data differs from typed records")
    process = metadata.get("process", {})
    checks = {
        "stdout_sha256": sha256(raw_stdout), "stderr_sha256": sha256(raw_stderr),
        "build_log_sha256": sha256(build_log),
        "build_graph_sha256": sha256(json.dumps(graph, sort_keys=True).encode()),
    }
    for field, expected in checks.items():
        actual = process.get(field) if field in ("stdout_sha256", "stderr_sha256") else metadata.get(field)
        if actual != expected:
            raise ValueError(f"{field} does not match retained evidence")
    exe_sidecar = files["executable.sha256"].decode("ascii").strip().split()
    if len(exe_sidecar) != 2 or exe_sidecar[0] != metadata.get("executable_sha256") or len(exe_sidecar[0]) != 64:
        raise ValueError("executable hash sidecar differs from metadata")
    if sha256(files["measurement.exe"]) != exe_sidecar[0]:
        raise ValueError("retained measurement executable differs from its SHA-256")
    if metadata.get("build_log_sha256") != checks["build_log_sha256"]:
        raise ValueError("build log hash differs from metadata")
    if process.get("timed_out") is not False or process.get("return_code") != 0 or process.get("parse_error") is not None:
        raise ValueError("measurement process is incomplete or failed")
    if metadata.get("build_configuration") != "Release" or metadata.get("build_identity") != events[0]:
        raise ValueError("build identity or configuration differs from the raw event stream")
    if metadata.get("source_commit") != events[0].get("source_commit") or events[0].get("ndebug") is not True:
        raise ValueError("source commit or Release assertion identity is invalid")
    repetitions = metadata.get("policy", {}).get("repetitions_per_side_per_case")
    if type(repetitions) is not int or repetitions < 5 or len(trials) != repetitions * len(SCENARIOS) * len(MODES):
        raise ValueError("trial count does not match the paired repetition policy")
    fixtures = metadata.get("input_fixtures")
    if not isinstance(fixtures, dict) or set(fixtures) != set(SCENARIOS):
        raise ValueError("input fixture descriptions do not match the measured scenarios")
    expected_dimensions = {"tiny-overhead": (1, 1), "small-reuse": (1, 40), "transfer-cost": (1, 100000)}
    for scenario, fixture in fixtures.items():
        if not isinstance(fixture, dict):
            raise ValueError(f"input fixture description is invalid: {scenario}")
        if (type(fixture.get("rows")) is not int or type(fixture.get("columns")) is not int
                or (fixture["rows"], fixture["columns"]) != expected_dimensions[scenario]):
            raise ValueError(f"input fixture dimensions are invalid: {scenario}")
        if not all(isinstance(fixture.get(key), (int, float)) and not isinstance(fixture.get(key), bool)
                   and math.isfinite(fixture[key]) for key in ("source_rhs", "changed_rhs", "expected_objective")):
            raise ValueError(f"input fixture values are invalid: {scenario}")
        fixture_hash = fixture.get("sha256")
        fixture_payload = {key: value for key, value in fixture.items() if key != "sha256"}
        expected_hash = sha256(json.dumps(fixture_payload, sort_keys=True, separators=(",", ":")).encode())
        if fixture_hash != expected_hash:
            raise ValueError(f"input fixture hash is invalid: {scenario}")
        if not isinstance(fixture.get("objective_change", "unchanged"), str):
            raise ValueError(f"input fixture objective description is invalid: {scenario}")
    canonical_fixtures = fixture_descriptions()
    for scenario in SCENARIOS:
        if fixtures[scenario] != canonical_fixtures[scenario]:
            raise ValueError(f"input fixture description differs from canonical scenario: {scenario}")
    for trial in trials:
        if not isinstance(trial, dict) or trial.get("schema") != "csl.opt12-cost-trial/1" or trial.get("status") != "verified":
            raise ValueError("trial schema or numerical verification status is invalid")
        if trial.get("scenario") not in SCENARIOS or trial.get("mode") not in MODES:
            raise ValueError("unknown scenario or mode")
        for field in ("wall_ns", *TIMED_FIELDS):
            value = trial.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"trial has invalid timing field: {field}")
    for pair in range(repetitions):
        for scenario in SCENARIOS:
            members = [row for row in trials if row.get("pair") == pair and row.get("scenario") == scenario]
            order = ["cold", "warm"] if pair % 2 == 0 else ["warm", "cold"]
            if len(members) != 2 or [row.get("mode") for row in sorted(members, key=lambda row: row.get("order", -1))] != order:
                raise ValueError("trial pairing or alternating execution order is invalid")
    return metadata, trials, files


def median_range(values: list[float]) -> str:
    if not values:
        return "unavailable"
    return f"{statistics.median(values):.6g} [{min(values):.6g}, {max(values):.6g}]"


def summary(rows: list[dict]) -> list[dict]:
    result = []
    for scenario in SCENARIOS:
        for mode in MODES:
            trials = [row for row in rows if row["scenario"] == scenario and row["mode"] == mode]
            work = [sum(float(row[field]) for field in TIMED_FIELDS) for row in trials]
            iterations = [int(row["simplex_iterations"]) for row in trials if row.get("simplex_iterations") is not None]
            result.append({"scenario": scenario, "mode": mode, "n": len(trials),
                           "wall_ns": median_range([float(row["wall_ns"]) for row in trials]),
                           "load_s": median_range([float(row["model_load_seconds"]) for row in trials]),
                           "basis_s": median_range([float(row["basis_transfer_seconds"]) for row in trials]),
                           "solve_s": median_range([float(row["solve_seconds"]) for row in trials]),
                           "native_work_s": median_range(work), "iterations": median_range(iterations)})
    return result


def comparison_svg(rows: list[dict]) -> str:
    summaries = summary(rows)
    panels = (("Public solve wall time (ns)", "wall_ns"), ("Native component work (s)", "native_work_s"))
    body = ['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="430" viewBox="0 0 900 430">',
            '<rect width="900" height="430" fill="white"/>',
            '<style>text{font:14px system-ui,sans-serif;fill:#17202a}.axis{stroke:#687782}.cold{fill:#56758a}.warm{fill:#d27632}</style>']
    for panel_index, (title, field) in enumerate(panels):
        x0, y0, width = 70 + panel_index * 440, 65, 360
        body.append(f'<text x="{x0}" y="30" font-weight="bold">{html.escape(title)}</text>')
        values = [statistics.median([float(row[field]) if field == "wall_ns" else sum(float(row[k]) for k in TIMED_FIELDS)
                                     for row in rows if row["scenario"] == case and row["mode"] == mode])
                  for case in SCENARIOS for mode in MODES]
        maximum = max(values) or 1.0
        body.append(f'<line class="axis" x1="{x0}" y1="{y0}" x2="{x0}" y2="{y0+275}"/>')
        for case_index, case in enumerate(SCENARIOS):
            group_y = y0 + 34 + case_index * 95
            body.append(f'<text x="{x0}" y="{group_y-8}">{html.escape(case)}</text>')
            for mode_index, mode in enumerate(MODES):
                sample = [float(row[field]) if field == "wall_ns" else sum(float(row[k]) for k in TIMED_FIELDS)
                          for row in rows if row["scenario"] == case and row["mode"] == mode]
                value = statistics.median(sample)
                bar_y = group_y + mode_index * 25
                bar_width = max(1.0, width * value / maximum)
                body.append(f'<rect class="{mode}" x="{x0}" y="{bar_y}" width="{bar_width:.1f}" height="17"/>')
                body.append(f'<text x="{x0+bar_width+5:.1f}" y="{bar_y+14}">{mode}: {value:.6g}</text>')
    body.extend(['<rect class="cold" x="70" y="400" width="14" height="14"/><text x="90" y="413">cold</text>',
                 '<rect class="warm" x="150" y="400" width="14" height="14"/><text x="170" y="413">warm</text>', '</svg>'])
    return "\n".join(body) + "\n"


def render(records: Path, out: Path) -> dict:
    metadata, rows, evidence = parse_evidence(records)
    if out.exists():
        raise ValueError("output destination must be new")
    out.mkdir(parents=True)
    (out / "records.json").write_bytes(records.read_bytes())
    for name, content in evidence.items():
        (out / name).write_bytes(content)
    rows_summary = summary(rows)
    cost_scenarios = []
    for scenario in SCENARIOS:
        median_work = {mode: statistics.median([sum(float(row[field]) for field in TIMED_FIELDS)
                                                for row in rows if row["scenario"] == scenario and row["mode"] == mode])
                       for mode in MODES}
        if median_work["warm"] > median_work["cold"]:
            cost_scenarios.append(scenario)
    cost_text = (f"Warm reuse records higher median aggregate native work in: {', '.join(cost_scenarios)}. "
                 "Simplex iteration counts are reported separately."
                 if cost_scenarios
                 else "This run does not establish higher median aggregate native work for warm reuse in any case.")
    summary_html = "\n".join("<tr>" + "".join(f"<td>{html.escape(str(row[key]))}</td>" for key in
        ("scenario", "mode", "n", "wall_ns", "load_s", "basis_s", "solve_s", "native_work_s", "iterations")) + "</tr>" for row in rows_summary)
    trial_html = "\n".join(f'<tr><td>{row["scenario"]}</td><td>{row["pair"]}</td><td>{row["mode"]}</td><td>{row.get("cache_state")}</td><td>{row.get("basis_accepted")}</td><td>{row["wall_ns"]}</td><td>{row.get("simplex_iterations")}</td><td><details><summary>raw diagnostics</summary><pre>{html.escape(row.get("diagnostics", ""))}</pre></details></td></tr>' for row in rows)
    fixtures = metadata.get("input_fixtures", {})
    fixtures_html = "".join(f'<tr><td>{html.escape(name)}</td><td>{fixture["rows"]} × {fixture["columns"]}</td><td>{fixture["sha256"]}</td><td>{fixture["source_rhs"]} → {fixture["changed_rhs"]}</td><td>{html.escape(fixture.get("objective_change", "unchanged"))}</td><td>{fixture["expected_objective"]}</td></tr>' for name, fixture in fixtures.items())
    meta_html = "".join(f'<tr><th>{html.escape(key)}</th><td>{html.escape(json.dumps(value, sort_keys=True))}</td></tr>' for key, value in metadata.items() if key != "input_fixtures")
    (out / "comparison.svg").write_text(comparison_svg(rows), encoding="utf-8", newline="\n")
    files = sorted(path.name for path in out.iterdir() if path.is_file())
    links = " ".join(f'<a href="{html.escape(name)}">{html.escape(name)}</a>' for name in files if name != "index.html")
    report_id = out.name
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(report_id)} — OPT-12</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#17202a}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}th,td{{border:1px solid #9aa4ad;padding:.45rem;text-align:left;vertical-align:top}}th{{background:#edf2f5}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;max-height:24rem;overflow:auto}}.note{{padding:1rem;border-left:4px solid #46647a;background:#f3f6f8}}img{{max-width:100%;height:auto}}</style></head><body>
<h1>OPT-12: HiGHS cross-query basis reuse</h1><p class="note">{html.escape(cost_text)} Measurements describe three synthetic LPs on the recorded host. They do not establish a general speedup or worst-case complexity change.</p>
<p>Source commit <code>{html.escape(metadata["source_commit"])}</code>; adapter {html.escape(metadata["adapter_version"])}; native solver {html.escape(metadata["native_solver"])}; Release.</p>
<h2>Workload and independent checks</h2><p>Each warm trial performs one unreported source solve in a fresh workspace, then solves the same changed LP as its paired cold trial. Measured results pass optimal-status, feasibility, and literal-objective checks. Side order alternates within each pair. Public-call wall time wraps <code>LPWorkspace.solve</code>; native load, basis-transfer setup, and solve intervals are reported separately.</p>
<table><thead><tr><th>Case</th><th>Size</th><th>Input SHA-256</th><th>RHS change</th><th>Objective change</th><th>Expected objective</th></tr></thead><tbody>{fixtures_html}</tbody></table>
<h2>Paired medians</h2><img src="comparison.svg" alt="Median cold and warm wall time and native component work"><p>Native work sums model-load, basis-transfer, and solve intervals. It excludes independent result verification.</p>
<table><thead><tr><th>Case</th><th>Mode</th><th>n</th><th>Wall ns median [min, max]</th><th>Load s</th><th>Basis setup s</th><th>Solve s</th><th>Native work s</th><th>Simplex iterations</th></tr></thead><tbody>{summary_html}</tbody></table>
<h2>Trials</h2><table><thead><tr><th>Case</th><th>Pair</th><th>Mode</th><th>Cache</th><th>Basis accepted</th><th>Wall ns</th><th>Iterations</th><th>Diagnostics</th></tr></thead><tbody>{trial_html}</tbody></table>
<h2>Provenance</h2><table><tbody>{meta_html}</tbody></table><p>Saved evidence: {links} <a href="../{html.escape(report_id)}.zip">offline ZIP</a></p>
<small>Rendered only from retained evidence. Consult the OPT-12 design note and published algorithm-results policy for scope and interpretation.</small></body></html>'''
    (out / "index.html").write_text(page, encoding="utf-8", newline="\n")
    manifest = {"schema": "csl.opt12-cost-manifest/1", "report_id": report_id,
                "files": {path.name: sha256(path.read_bytes()) for path in sorted(out.iterdir()) if path.is_file()}}
    (out / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    archive = out.parent / f"{report_id}.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(out.iterdir()):
            if path.is_file():
                zipped.write(path, f"{report_id}/{path.name}")
        zipped.writestr(f"{report_id}/offline-index.html", '<!doctype html><meta charset="utf-8"><a href="index.html">Open report</a>')
    (out.parent / f"{report_id}.zip.sha256").write_text(f"{sha256(archive.read_bytes())}  {report_id}.zip\n", encoding="ascii")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = render(args.records.resolve(strict=True), args.out)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.error(f"cannot render unverified OPT-12 evidence: {error}")
    print(json.dumps({"report_id": args.out.name, "files": manifest["files"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
