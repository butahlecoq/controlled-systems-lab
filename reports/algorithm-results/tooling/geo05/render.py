"""Render the GEO-05 offline page from a validated saved record only."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from report import PHASES, SCENARIOS, strict_json_loads, validate_record


def _duration(value: int | float | None) -> str:
    return "unavailable" if value is None else f"{value:g} ns"


def render_svg(record: dict) -> str:
    validate_record(record)
    values = [record["collection"]["by_scenario"][scenario]["phases"]["end_to_end_ns"]["median_ns"]
              for scenario in SCENARIOS]
    maximum = max((value for value in values if value is not None), default=1)
    bars = []
    for index, (scenario, value) in enumerate(zip(SCENARIOS, values)):
        y = 24 + index * 30
        width = 0 if value is None else max(1, round(500 * value / maximum))
        label = "unavailable" if value is None else f"{value:g} ns"
        bars.append(f'<text x="8" y="{y+15}">{html.escape(scenario)}</text>'
                    f'<rect x="270" y="{y}" width="{width}" height="20" fill="#3572a5"/>'
                    f'<text x="{280+width}" y="{y+15}">{html.escape(label)}</text>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 880 160" role="img" aria-label="End-to-end timing by fixture">' + ''.join(bars) + '</svg>'


def render_html(record: dict) -> str:
    validate_record(record)
    state = ("timings are smoke/test evidence only" if record["purpose"] == "test"
             else "measurement record pending independent review")
    collection = record["collection"]
    rows = []
    for trial in record["trials"]:
        durations = trial.get("durations_ns", {})
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in (
            trial.get("scenario"), trial.get("repetition"), trial.get("status"),
            trial.get("oracle_passed"), trial.get("work_observed"), trial.get("input_rows"),
            trial.get("output_rows"), trial.get("result_kind"), trial.get("result_encoding"),
            trial.get("input_sha256"), trial.get("scenario_sha256"),
            trial.get("expected_fm_peak_rows"), trial.get("max_rows")))
            + "".join(f"<td>{html.escape(_duration(durations.get(phase)))}</td>" for phase in PHASES)
            + f"<td>{html.escape(str(trial.get('detail', '')))}</td></tr>")
    summary_rows = []
    for phase in PHASES:
        stat = collection["phases"][phase]
        summary_rows.append("<tr>" + f"<th>{html.escape(phase)}</th>"
            + f"<td>{html.escape(_duration(stat['median_ns']))}</td>"
            + f"<td>{html.escape(_duration(stat['min_ns']))}</td>"
            + f"<td>{html.escape(_duration(stat['max_ns']))}</td>"
            + f"<td>{stat['successful_trials']}</td><td>{stat['unavailable_trials']}</td></tr>")
    warmup_rows = []
    for trial in record.get("warmup_trials", []):
        warmup_rows.append("<li>" + html.escape(f"{trial.get('scenario')}: {trial.get('status')} — {trial.get('detail', '')}") + "</li>")
    limits = "".join(f"<li>{html.escape(item)}</li>" for item in record["evidence_limits"])
    counts = html.escape(json.dumps(collection["counts"], sort_keys=True))
    algorithm = record["algorithm"]
    build_fields = {key: algorithm.get(key) for key in
                    ("configuration", "cxx_standard", "cmake", "build_log_sha256", "executable", "dependency_targets")}
    compiler = html.escape(json.dumps(algorithm.get("compiler", "unavailable"), sort_keys=True, indent=2))
    build = html.escape(json.dumps(build_fields, sort_keys=True, indent=2))
    environment = html.escape(json.dumps(algorithm.get("environment", "unavailable"), sort_keys=True, indent=2))
    scenario_rows = []
    for scenario in SCENARIOS:
        stat = collection["by_scenario"][scenario]
        e2e = stat["phases"]["end_to_end_ns"]
        scenario_rows.append(f"<tr><th>{html.escape(scenario)}</th><td>{stat['attempts']}</td>"
            + f"<td>{html.escape(_duration(e2e['median_ns']))}</td>"
            + f"<td>{html.escape(_duration(e2e['min_ns']))}</td>"
            + f"<td>{html.escape(_duration(e2e['max_ns']))}</td></tr>")
    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>GEO-05 numerical report {html.escape(record['report_id'])}</title>
<style>body{{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#17212b}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}th,td{{border:1px solid #b8c3cc;padding:.45rem;text-align:left}}th{{background:#edf2f6}}.scroll{{overflow-x:auto}}.state{{padding:.8rem;background:#fff2cc;border-left:4px solid #a36c00}}code{{overflow-wrap:anywhere}}</style>
<h1>GEO-05 numerical report</h1><p class="state">{html.escape(state)}</p>
<p>Report ID <code>{html.escape(record['report_id'])}</code>; schema <code>{html.escape(record['schema'])}</code>.</p>
<p>Source commit <code>{html.escape(str(record['algorithm'].get('source_commit')))}</code>; harness commit <code>{html.escape(str(record['algorithm'].get('harness_commit')))}</code>.</p>
<h2>Build provenance</h2><h3>Compiler</h3><pre><code>{compiler}</code></pre><h3>Build configuration</h3><pre><code>{build}</code></pre>
<h2>Environment provenance</h2><pre><code>{environment}</code></pre>
<h2>Evidence limits</h2><ul>{limits}</ul>
<h2>Attempt counts</h2><p><code>{counts}</code></p>
<h2>End-to-end by scenario</h2>{render_svg(record)}<div class="scroll"><table><thead><tr><th>Fixture</th><th>Attempts</th><th>Median</th><th>Min</th><th>Max</th></tr></thead><tbody>{''.join(scenario_rows)}</tbody></table></div>
<h2>Timing summary</h2><div class="scroll"><table><thead><tr><th>Scope</th><th>Median</th><th>Min</th><th>Max</th><th>Successful rows</th><th>Unavailable rows</th></tr></thead><tbody>{''.join(summary_rows)}</tbody></table></div>
<h2>Warmup attempts</h2><ul>{''.join(warmup_rows) or '<li>None</li>'}</ul>
<h2>Trial evidence</h2><div class="scroll"><table><thead><tr><th>Scenario</th><th>Round</th><th>Status</th><th>Literal checks</th><th>Work observed</th><th>Input rows</th><th>Output rows</th><th>Result kind</th><th>Result encoding</th><th>Input SHA-256</th><th>Scenario SHA-256</th><th>Expected FM peak</th><th>Configured max rows</th>{''.join(f'<th>{html.escape(p)}</th>' for p in PHASES)}<th>Detail</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="new output directory")
    args = parser.parse_args()
    record = strict_json_loads(args.records.read_text(encoding="utf-8"))
    validate_record(record)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "index.html").write_text(render_html(record), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
