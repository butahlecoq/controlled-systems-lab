#!/usr/bin/env python3
"""Render a self-contained HTML report from the saved dyadic pilot records."""
from __future__ import annotations

import csv
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).parent
REPORT_ID = "exp02-it17-dyadic-interior-20261027-r1"


def fixture_points(count: int):
    points = [(0, 0), (32, 0), (32, 32), (0, 32)]
    used = set()
    state = 0x6D2B79F5
    while len(points) < count:
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        x = 1 + state % 31
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        y = 1 + state % 31
        if (x, y) not in used:
            used.add((x, y))
            points.append((x, y))
    return points


def plot_svg() -> str:
    panels = []
    for offset, count in ((0, 64), (440, 256)):
        points = fixture_points(count)
        x0, y0, size = offset + 70, 60, 300
        circles = []
        for index, (x, y) in enumerate(points):
            cx = x0 + x / 32 * size
            cy = y0 + (32 - y) / 32 * size
            klass = "corner" if index < 4 else "interior"
            circles.append(f'<circle class="{klass}" cx="{cx:.1f}" cy="{cy:.1f}" r="{3.5 if count == 64 else 2.5}"/>')
        panels.append(
            f'<g><text class="panel-title" x="{x0}" y="30">{count} points · {count-4} interior</text>'
            f'<rect class="hull" x="{x0}" y="{y0}" width="{size}" height="{size}"/>'
            + "".join(circles)
            + f'<text class="axis" x="{x0+size/2}" y="{y0+size+30}">x</text>'
            + f'<text class="axis" x="{x0-26}" y="{y0+size/2}">y</text></g>')
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 880 440" role="img" '
        'aria-labelledby="plot-title plot-desc"><title id="plot-title">Two dyadic square hull fixtures</title>'
        '<desc id="plot-desc">Two unit-square point clouds with all four square corners on the hull. '
        'The 64-point cloud has 60 interior points; the 256-point cloud has 252 interior points. '
        'Teal dots are generated interior points and purple dots are square corners.</desc>'
        '<style>text{font-family:system-ui,sans-serif;fill:#e7e5e4}.panel-title{font-size:17px;font-weight:700}'
        '.axis{font-size:14px}.hull{fill:#7869c422;stroke:#b6a6ff;stroke-width:2}'
        '.interior{fill:#43c7a5}.corner{fill:#c1a9ff;stroke:#fff;stroke-width:1}</style>'
        + "".join(panels) + '</svg>')


def render() -> None:
    rows = list(csv.DictReader((ROOT / "summary.csv").open(encoding="utf-8", newline="")))
    raw_rows = [json.loads(line) for line in (ROOT / "validated-rows.jsonl").read_text(encoding="utf-8").splitlines()]
    source_commit = raw_rows[0]["source_commit"]
    input_hashes = {row["fixture"]: row["input_sha256"] for row in raw_rows}
    if len(raw_rows) != 72 or len(input_hashes) != 2 or any(row["source_commit"] != source_commit for row in raw_rows):
        raise ValueError("saved run matrix/source identity differs")
    svg = plot_svg()
    (ROOT / "fixture-geometry.svg").write_text(svg, encoding="utf-8")

    good_rows = []
    failed_rows = []
    names = {
        "geometric-quickhull": "Geometric QuickHull",
        "basis-reuse-related-to-A43": "Phase-one basis reuse",
        "A44-incremental-LP-paper-adaptation": "A44 incremental LP adaptation",
        "lp-membership-baseline": "LP membership baseline",
        "ordered-membership-related-to-A44": "Ordered membership adaptation",
        "A43-certificate-safe-basis-adaptation": "A43 certificate-safe basis adaptation",
    }
    for row in rows:
        name = html.escape(names[row["method"]])
        fixture = "64" if row["fixture"].endswith("64") else "256"
        if int(row["passed"]) == 5:
            good_rows.append(
                f'<tr><th scope="row">{fixture}</th><td>{name}</td><td>{row["passed"]}/5</td>'
                f'<td>{row["retained_counts"].split(";")[0]}</td><td>{float(row["median_ms_of_passes"]):.4f}</td>'
                f'<td>{float(row["min_ms_of_passes"]):.4f}–{float(row["max_ms_of_passes"]):.4f}</td></tr>')
        else:
            failed_rows.append(
                f'<tr><th scope="row">{fixture}</th><td>{name}</td><td>{row["passed"]}/5</td>'
                f'<td>{row["retained_counts"].split(";")[0]}</td><td>Retained as diagnostic only</td></tr>')

    record = {
        "schema": "csl.exploratory-comparison-report/1",
        "report_id": REPORT_ID,
        "source_commit": source_commit,
        "measured_scope": "Six hull methods on deterministic 64- and 256-point 2D dyadic interior-heavy squares; five measured attempts plus one warmup per method and size",
        "evidence_limits": "Exploratory two-fixture pilot; three methods fail completion checks; LP workspace setup excluded; no source-mapped limiter; no general winner, scalability or historical-reproduction claim",
        "input_sha256": input_hashes,
        "attempts": len(raw_rows),
        "measurement_rows": 60,
        "method_count": 6,
    }
    (ROOT / "record.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = "".join(good_rows)
    failures = "".join(failed_rows)
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EXP-02 dyadic ITIS17 hull pilot</title>
<style>
:root{{color-scheme:dark;--bg:#17191d;--panel:#22252b;--ink:#f2f1ed;--muted:#b5b4ae;--accent:#b6a6ff;--line:#41444c}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,sans-serif}}
main{{max-width:1040px;margin:auto;padding:2rem 1.25rem 4rem}}h1,h2{{line-height:1.2}}h1{{font-size:2.2rem}}h2{{margin-top:2.5rem}}p{{max-width:82ch;color:var(--muted)}}
.badge{{display:inline-block;border:1px solid #e0a75e;color:#ffd598;padding:.15rem .6rem;border-radius:1rem;font-size:.9rem}}
figure,.panel{{background:var(--panel);border:1px solid var(--line);border-radius:.8rem;padding:1rem;margin:1.2rem 0}}
svg{{width:100%;height:auto}}table{{border-collapse:collapse;width:100%;margin:1rem 0;background:var(--panel)}}th,td{{text-align:left;padding:.65rem;border:1px solid var(--line);vertical-align:top}}thead{{background:#302b43}}code{{overflow-wrap:anywhere}}a{{color:#c7baff}}.small{{font-size:.92rem}}
</style></head><body><main>
<p class="badge">Exploratory · performance verdict inconclusive</p>
<h1>QuickHull and ITIS17 paper-informed LP adaptations</h1>
<p>This bounded follow-up records five interleaved attempts per method on two identical 2D dyadic square clouds. It adds evidence to EXP-02 but does not complete the issue’s control-strategy, higher-dimensional hull, H/V, or representation matrix.</p>
<figure>{svg}<figcaption>Shared unit-square geometry. Purple marks the four hull corners; teal marks generated interior points. The figure shows input geometry, not algorithm execution steps.</figcaption></figure>
<h2>Passing methods</h2><p>The table shows median and full range for the five attempts that passed the driver’s checks.</p>
<table><thead><tr><th scope="col">Input size</th><th scope="col">Method</th><th scope="col">Passed</th><th scope="col">Retained</th><th scope="col">Median (ms)</th><th scope="col">Range (ms)</th></tr></thead><tbody>{summary}</tbody></table>
<h2>Failed attempts</h2><p>These elapsed values are not successful-performance measurements. Raw rows and diagnostics retain every failure.</p>
<table><thead><tr><th scope="col">Input size</th><th scope="col">Method</th><th scope="col">Passed</th><th scope="col">Retained on attempts</th><th scope="col">Timing use</th></tr></thead><tbody>{failures}</tbody></table>
<h2>Method identity and validation</h2><p>A43 and A44 are paper-informed C++ adaptations, not faithful paper ports. No corresponding Pascal source was recovered from the available local search. The A43 row uses a certificate-safe basis adaptation; A44 uses incremental membership with a final recheck. The driver checks complete point accounting, verifier identity, the exact source-index hull checker, and all four expected square corners. It does not independently replay each removal certificate.</p>
<p>For LP methods, workspace creation occurs before timing. The timer covers the reducer call and excludes workspace setup and validation. QuickHull is timed around its call, then checked. HiGHS is configured for one thread; observed OS thread count was not recorded. A separate <code>top</code> run showed one logical CPU near saturation and about 8.8 MiB RSS, but no source-function profile was available. These boundaries do not establish an end-to-end winner.</p>
<h2>Reproduce and inspect</h2><ul>
<li><a href="summary.csv">Summary table</a></li><li><a href="validated-rows.jsonl">All validated rows</a></li>
<li><a href="raw/n64.jsonl">Raw 64-point rows</a></li><li><a href="raw/n256.jsonl">Raw 256-point rows</a></li>
<li><a href="raw/n64.stderr">64-point validation diagnostics</a></li><li><a href="raw/n256.stderr">256-point validation diagnostics</a></li>
<li><a href="raw/top-profile.txt">Separate profile-only run</a></li><li><a href="README.md">Full methodology and reproduction commands</a></li>
<li><a href="https://github.com/butahlecoq/controlled-systems-lab/issues/94">EXP-02 issue and remaining acceptance</a></li></ul>
<p class="small">Source commit: <code>{source_commit}</code>. Report ID: <code>{REPORT_ID}</code>. Input SHA-256 hashes are in <a href="record.json">record.json</a>. Requested comparison limits were not enforced by a process limiter. Failures, unsupported paths and unavailable metrics remain visible.</p>
</main></body></html>'''
    (ROOT / "index.html").write_text(page, encoding="utf-8")
    names_to_hash = sorted(path for path in ROOT.rglob("*") if path.is_file() and path.name != "SHA256SUMS")
    lines = []
    for path in names_to_hash:
        if path.is_symlink():
            raise ValueError(f"symlink is not publishable: {path}")
        rel = path.relative_to(ROOT).as_posix()
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {rel}")
    (ROOT / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rendered {REPORT_ID}: {len(names_to_hash)} files")


if __name__ == "__main__":
    render()
