#!/usr/bin/env python3
"""Render an OPT-04 report from saved records only; never runs a solver."""
from __future__ import annotations

import argparse
import html
import hashlib
import json
from pathlib import Path
import zipfile


SCHEMA = "csl.opt04-phase-one-report/1"
PHASES = ("setup", "public_run", "verification", "end_to_end")


def read_records(path: Path) -> dict:
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, dict) or records.get("schema") != SCHEMA:
        raise ValueError(f"unsupported records schema (expected {SCHEMA})")
    return records


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def svg(records: dict) -> str:
    rows = records["summary"]["rows"]
    fixtures = records["catalog"]["fixtures"]
    sides = records["measurement"]["sides"]
    if not records["summary"].get("valid"):
        return ('<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="chart-title chart-desc" viewBox="0 0 720 150">'
                '<title id="chart-title">Timing aggregates are ineligible</title>'
                '<desc id="chart-desc">The saved collection contains failures, missing trials, or another validation error; no aggregate timing chart is shown.</desc>'
                '<style>text{font:16px system-ui,sans-serif;fill:#182532}</style>'
                '<text id="chart-title" x="24" y="56">No eligible aggregate timing chart</text>'
                '<text x="24" y="88">Review failed attempts and collection status in the report.</text></svg>')
    width, height = 920, max(300, 210 + 72 * len(fixtures))
    left, right, top, bottom = 90, 30, 34, 66
    plot_w, plot_h = width - left - right, height - top - bottom
    chart_rows = [r for r in rows if r["phase"] in ("public_run", "end_to_end")]
    maximum = max((r["max_ns"] for r in chart_rows if r.get("max_ns") is not None), default=1)
    y_max = max(1.0, float(maximum) * 1.12)
    y = lambda value: top + plot_h * (1.0 - float(value) / y_max)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="chart-title chart-desc" viewBox="0 0 {width} {height}">',
        '<title id="chart-title">OPT-04 measured timing ranges</title>',
        '<desc id="chart-desc">Median timing marks and minimum-to-maximum ranges for public run and end-to-end phases, grouped by fixture and implementation side.</desc>',
        '<style>text{font:13px system-ui,sans-serif;fill:#192735}.axis{stroke:#48596a}.grid{stroke:#dce3e9}.range{stroke-width:3}.median{stroke-width:8;stroke-linecap:round}</style>',
        '<text x="12" y="18">Nanoseconds</text>',
    ]
    for tick in range(5):
        value = y_max * tick / 4
        yy = y(value)
        out.append(f'<line class="grid" x1="{left}" x2="{width-right}" y1="{yy:.2f}" y2="{yy:.2f}"/>')
        out.append(f'<text x="{left-9}" y="{yy+4:.2f}" text-anchor="end">{value:.0f}</text>')
    count = max(1, len(fixtures))
    group_h = plot_h / count
    colors = {"phase-one-bland": "#226f9b", "highs-reference": "#a24d2c"}
    for fi, fixture in enumerate(fixtures):
        base_y = top + group_h * (fi + 0.5)
        out.append(f'<text x="{left}" y="{base_y-group_h*0.28:.1f}" font-weight="700">{_e(fixture["id"])}</text>')
        for si, side in enumerate(sides):
            for pi, phase in enumerate(("public_run", "end_to_end")):
                row = next(r for r in rows if r["fixture"] == fixture["id"] and r["side"] == side and r["phase"] == phase)
                slot = (si * 2 + pi)
                xx = left + plot_w * (slot + 0.5) / max(1, len(sides) * 2)
                yy_min, yy_med, yy_max = (y(row[key]) for key in ("min_ns", "median_ns", "max_ns"))
                color = colors.get(side, "#52657a")
                out.append(f'<line class="range" x1="{xx:.1f}" x2="{xx:.1f}" y1="{yy_max:.2f}" y2="{yy_min:.2f}" stroke="{color}"/>')
                out.append(f'<line class="median" x1="{xx-9:.1f}" x2="{xx+9:.1f}" y1="{yy_med:.2f}" y2="{yy_med:.2f}" stroke="{color}"/>')
                out.append(f'<text x="{xx:.1f}" y="{height-31}" text-anchor="middle">{_e(side)} / {_e(phase.replace("_", " "))}</text>')
    out.extend((f'<line class="axis" x1="{left}" x2="{left}" y1="{top}" y2="{height-bottom}"/>',
                f'<line class="axis" x1="{left}" x2="{width-right}" y1="{height-bottom}" y2="{height-bottom}"/>',
                '<text x="50%" y="18" text-anchor="middle">Median marker; line spans observed minimum to maximum</text>',
                '</svg>'))
    return "".join(out)


def page(records: dict) -> str:
    scenarios = records["catalog"]["fixtures"]
    sides = records["measurement"]["sides"]
    summary = records["summary"]
    trials = records["trials"]
    matched = sum(t["status"] == "passed" and t.get("oracle_match") is True for t in trials)
    failures = summary.get("failure_count", sum(t["status"] != "passed" for t in trials))
    missing = summary.get("missing_count", 0)
    summary_valid = summary.get("valid") is True
    summary_eligibility = ("Timing aggregates are ineligible because the collection contains failed attempts, missing trials, or collection errors."
                           if not summary_valid else "Timing aggregates are descriptive only; this report declares no performance winner or speedup.")
    rows = []
    for item in summary["rows"]:
        fixture = next(f for f in scenarios if f["id"] == item["fixture"])
        median = f'{item["median_ns"]:,}' if isinstance(item.get("median_ns"), (int, float)) else "unavailable"
        low = item.get("min_ns")
        high = item.get("max_ns")
        range_text = f"{low:,} to {high:,}" if isinstance(low, (int, float)) and isinstance(high, (int, float)) else "unavailable"
        rows.append("<tr>" + "".join(f"<td>{_e(v)}</td>" for v in (
            fixture["id"], item["side"], item["phase"].replace("_", " "),
            median, range_text, item["count"],
        )) + "</tr>")
    failures_table = []
    for trial in [*records.get("warmup_trials", []), *trials]:
        if trial["status"] != "passed":
            failures_table.append("<tr>" + "".join(f"<td>{_e(v)}</td>" for v in (
                trial["fixture"], trial["side"], "warmup" if trial in records.get("warmup_trials", []) else trial["repetition"], trial.get("observed_status", "unavailable"), trial.get("error") or "",
            )) + "</tr>")
    figure = svg(records)
    fixture_rows = "".join(
        f'<tr><th scope="row">{_e(f["id"])}</th><td>{f["rows"]}</td><td>{f["columns"]}</td><td>{_e(f["expected_status"])}</td></tr>'
        for f in scenarios)
    limits = "".join(f"<li>{_e(line)}</li>" for line in records.get("evidence_limits", []))
    boundaries = records["measurement"]["timing_boundaries"]
    phase_labels = {"setup": "Setup", "public_run": "Public run", "verification": "Verification", "end_to_end": "End to end"}
    boundary_rows = "".join(f"<tr><th scope=\"row\">{phase_labels.get(k, _e(k))}</th><td>{_e(v)}</td></tr>" for k, v in boundaries.items())
    chart_caption = ("Seven measured repetitions per fixture and side; warmups are excluded. "
                     if summary_valid else "Seven measured repetitions were planned per fixture and side; missing or failed attempts make aggregates ineligible. ")
    provenance = records.get("provenance", {})
    source = _e(provenance.get("source_commit", "not recorded"))
    harness = _e(provenance.get("harness_commit", "not recorded"))
    exe_sha = _e(provenance.get("executable_sha256", "not recorded"))
    cache_sha = _e(provenance.get("cmake_cache_sha256", "not recorded"))
    build_sha = _e(provenance.get("release_build_sha256", "not recorded"))
    compiler = _e(f'{provenance.get("compiler_id", "not recorded")} {provenance.get("compiler_version", "")}')
    generator = _e(provenance.get("cmake_generator", "not recorded"))
    release_flags = _e(provenance.get("release_flags", "not recorded"))
    host = _e(provenance.get("host_platform", "not recorded"))
    processor = _e(provenance.get("processor", "not recorded"))
    created = _e(records.get("created_utc", "not recorded"))
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OPT-04 phase-I analytic fixture report</title>
<style>
:root{{color-scheme:light;--ink:#182532;--muted:#536474;--line:#cbd5de;--panel:#f1f5f8;--accent:#165b82}}*{{box-sizing:border-box}}body{{margin:0 auto;padding:clamp(1rem,4vw,2.5rem);max-width:1120px;font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink)}}h1,h2{{line-height:1.2}}h1{{font-size:clamp(1.8rem,4vw,2.6rem)}}h2{{margin-top:2rem}}p,li{{max-width:85ch}}.lede,.notice{{padding:1rem 1.2rem;background:var(--panel);border-left:4px solid var(--accent)}}.notice{{border-color:#9a5a2d}}.scroll{{overflow-x:auto;margin:1rem 0}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}th,td{{padding:.55rem .65rem;border:1px solid var(--line);text-align:left;vertical-align:top}}thead{{background:var(--panel)}}figure{{margin:1.2rem 0}}figure svg{{display:block;width:100%;height:auto}}code{{overflow-wrap:anywhere}}.small{{color:var(--muted);font-size:.92rem}}@media(max-width:640px){{body{{font-size:15px}}th,td{{padding:.4rem;font-size:.88rem}}}}
</style></head><body>
<h1>Phase-I simplex on analytic fixtures</h1>
<p class="lede">Saved report <code>{_e(records["report_id"])}</code>, generated {created}. Algorithm <code>{_e(records["algorithm"]["registration_id"])}</code> { _e(records["algorithm"]["version"]) }; reference <code>{_e(records["reference"]["registration_id"])}</code> {_e(records["reference"]["version"])}.</p>
<p class="notice">Evidence support: {_e(records["evidence_support"])}. This report presents paired descriptive measurements on the listed analytic fixtures. It makes no speedup claim and does not establish feasibility numerics.</p>
<h2>Measured timings</h2>
<figure>{figure}<figcaption class="small">Markers show medians; vertical lines show observed minimum-to-maximum ranges. {chart_caption}All four timing phases are listed below.</figcaption></figure>
<div class="scroll"><table><thead><tr><th>Fixture</th><th>Side</th><th>Phase</th><th>Median (ns)</th><th>Range (ns)</th><th>Trials</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2>Fixtures and oracle checks</h2><p>{matched} of {len(trials)} measured trials passed the authored status and candidate checks; {failures} attempts failed and {missing} expected attempts are missing. {_e(summary_eligibility)} Status comparisons use the literal catalog classification. A passed phase-I row also requires its named oracle checks and recorded residuals to satisfy the fixture tolerance.</p>
<div class="scroll"><table><thead><tr><th>Fixture</th><th>Rows</th><th>Columns</th><th>Expected status</th></tr></thead><tbody>{fixture_rows}</tbody></table></div>
<h2>Timing definitions</h2><div class="scroll"><table><tbody>{boundary_rows}</tbody></table></div>
<h2>Failures</h2>{('<p>No failed trial rows were recorded. Check the missing count and collection status above.</p>' if not failures_table else '<div class="scroll"><table><thead><tr><th>Fixture</th><th>Side</th><th>Repetition</th><th>Observed status</th><th>Diagnostic</th></tr></thead><tbody>'+''.join(failures_table)+'</tbody></table></div>')}
<h2>Provenance and collection status</h2><p>Source commit <code>{source}</code>; harness commit <code>{harness}</code>. Executable SHA-256 <code>{exe_sha}</code>; CMake cache SHA-256 <code>{cache_sha}</code>; clean Release build SHA-256 <code>{build_sha}</code>. Compiler: {_e(compiler)}; CMake generator: {_e(generator)}; C++ standard: {_e(provenance.get("cxx_standard", "not recorded"))}; Release flags: <code>{release_flags}</code>. Host: {_e(host)}; processor: {_e(processor)}; logical processors: {_e(provenance.get("logical_processors", "not recorded"))}. Process exit: {_e(records.get("process_exit_code", "not recorded"))}; aborted: {_e(records.get("aborted", "not recorded"))}. The sanitized clean Release build log is <a href="release-build.txt">release-build.txt</a>. Catalog version {_e(records["catalog"]["version"])}. Execution order and trial evidence are in <a href="records.json">records.json</a>; saved driver output is in <a href="driver-stdout.txt">driver-stdout.txt</a> and <a href="stderr.txt">stderr.txt</a>. The standalone SVG is also available as <a href="performance.svg">performance.svg</a>.</p>{('<ul>'+''.join(f'<li>{_e(message)}</li>' for message in records.get('collection_errors', []))+'</ul>' if records.get('collection_errors') else '')}<ul>{limits}</ul>
<p class="small">This page and figure are rendered from saved records. Rendering does not invoke a solver.</p>
</body></html>'''


def render_report(records: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "performance.svg").write_text(svg(records), encoding="utf-8", newline="\n")
    (out / "index.html").write_text(page(records), encoding="utf-8", newline="\n")
    package_report(out)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def report_files(root: Path) -> list[Path]:
    excluded = {"manifest.sha256", "bundle.zip", "bundle.zip.sha256"}
    return sorted(path for path in root.rglob("*") if path.is_file()
                  and path.relative_to(root).as_posix() not in excluded
                  and "__pycache__" not in path.parts and path.suffix != ".pyc")


def package_report(root: Path) -> None:
    """Write a stable SHA manifest and ZIP from the saved report tree."""
    files = report_files(root)
    manifest = "".join(f"{_sha256(path.read_bytes())}  {path.relative_to(root).as_posix()}\n"
                       for path in files).encode("ascii")
    manifest_path = root / "manifest.sha256"
    manifest_path.write_bytes(manifest)
    bundle_path = root / "bundle.zip"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in [*files, manifest_path]:
            name = f"{root.name}/{path.relative_to(root).as_posix()}"
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    (root / "bundle.zip.sha256").write_text(f"{_sha256(bundle_path.read_bytes())}  bundle.zip\n", encoding="ascii", newline="\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--records", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    render_report(read_records(args.records), args.out)


if __name__ == "__main__":
    main()
