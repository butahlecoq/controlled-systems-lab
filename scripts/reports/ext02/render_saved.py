from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
import sys
import zipfile


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def render(record_path: Path, output: Path) -> None:
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("schema") != "csl.ext02-portfolio-record/1":
        raise ValueError("unsupported EXT-02 saved record")
    measured = [trial for trial in record["trials"] if not trial["warmup"]]
    if len(measured) != 7:
        raise ValueError("expected seven measured EXT-02 records")
    branches = measured[0]["branches"]
    points = [(float(branch["objective"]), float(branch["discrete_value"]))
              for branch in branches]
    if len(points) != 3:
        raise ValueError("expected three saved catalogue branches")
    output.mkdir(parents=True, exist_ok=False)
    record_bytes = record_path.read_bytes()
    (output / "measurement.json").write_bytes(record_bytes)
    points_markup = []
    for branch, (x1, x2) in zip(branches, points):
        px, py = 240 + x1 * 120, 230 - x2 * 110
        label = f"q={branch['discrete_value']}; index={branch['catalogue_index']}"
        points_markup.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="7" fill="#087e8b" />'
            f'<text x="{px + 13:.1f}" y="{py + 5:.1f}">{html.escape(label)}</text>')
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="420" viewBox="0 0 640 420">'
           '<rect width="640" height="420" fill="white"/>'
           '<text x="320" y="28" text-anchor="middle" font-size="18">'
           'Terminal states of all optimal catalogue branches</text>'
           '<line x1="100" y1="230" x2="540" y2="230" stroke="#444"/>'
           '<line x1="240" y1="65" x2="240" y2="365" stroke="#444"/>'
           '<text x="540" y="254" text-anchor="end">terminal x1</text>'
           '<text x="90" y="70" text-anchor="end">terminal x2</text>'
           '<text x="250" y="395">Each catalogue branch minimizes terminal x1 to zero; '
           'the discrete value fixes terminal x2.</text>' + ''.join(points_markup) + '</svg>')
    (output / "figure.svg").write_text(svg, encoding="utf-8")
    summary = record["summary"]
    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EXT-02 finite/mixed branch portfolio</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#18212b}}table{{border-collapse:collapse}}td,th{{border:1px solid #b7c3cc;padding:.4rem .7rem;text-align:left}}figure{{margin:2rem 0}}figure img{{max-width:100%;height:auto}}.limits{{background:#f3f6f8;padding:1rem}}</style></head>
<body><h1>EXT-02 finite/mixed-control branch portfolio</h1>
<p>This versioned report runs a one-stage nominal open-loop problem with a two-dimensional state, one bounded continuous control and a three-row finite control catalogue. Every catalogue-index history is solved independently through the registered reach-back strategy. The verified complete branch families all attain terminal objective zero.</p>
<figure><img src="figure.svg" alt="Terminal state points for the three optimal catalogue branches in the terminal x1-x2 plane"><figcaption>Figure generated from the saved branch records. Each point is a terminal state in one branch’s optimal family.</figcaption></figure>
<h2>Recorded solve profile</h2><table><tbody>
<tr><th>Measured calls</th><td>{summary['trials']}</td></tr>
<tr><th>Median API interval</th><td>{summary['median_elapsed_ns']} ns</td></tr>
<tr><th>Range</th><td>{summary['minimum_elapsed_ns']}–{summary['maximum_elapsed_ns']} ns</td></tr>
<tr><th>Horizon / catalogue / solved histories</th><td>{summary['horizon']} / {summary['catalogue_size']} / {summary['history_count']}</td></tr>
<tr><th>Retained relation rows</th><td>{summary['retained_relation_rows']}</td></tr>
<tr><th>Retained numeric scalars / bytes</th><td>{summary['retained_relation_scalars']} / {summary['retained_numeric_bytes']} bytes</td></tr>
<tr><th>Failures</th><td>{summary['failures']}</td></tr></tbody></table>
<h2>Branch results</h2><table><thead><tr><th>Catalogue index</th><th>Discrete value</th><th>Objective</th><th>Complete-family evidence</th></tr></thead><tbody>
{''.join(f"<tr><td>{b['catalogue_index']}</td><td>{b['discrete_value']}</td><td>{b['objective']}</td><td>{'registry-verified complete family' if b['complete_family_verified'] else 'missing'}</td></tr>" for b in branches)}
</tbody></table>
<h2>Measurement scope</h2><p>{html.escape(summary['timed_interval'])}. Process RSS is sampled separately and includes process startup, warmup and the measured calls; its sampling interval and limitation are recorded in <code>measurement.json</code>.</p>
<div class="limits"><h2>Assurance and limits</h2><p>Binary64 numerical assurance. The branch completeness evidence is the registered strategy’s verified complete-family result for this admitted profile; it is not validated arithmetic. The single one-stage fixture describes only this workload. It is not a comparative benchmark, a speedup claim, a hard memory limit, or evidence of asymptotic scalability. Numeric-byte accounting covers H-matrix coefficients and right-hand sides only, excluding object and vector overhead, solver workspace, transient branch materialization and allocator slack.</p></div>
<h2>Inputs and reproduction</h2><p>Scenario: <a href="https://github.com/butahlecoq/controlled-systems-lab/blob/{record['source_commit']}/{html.escape(record['scenario'], quote=True)}"><code>{html.escape(record['scenario'])}</code></a>. Source commit: <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{record['source_commit']}"><code>{record['source_commit']}</code></a>. Scenario SHA-256: <code>{record['scenario_sha256']}</code>. Executable SHA-256: <code>{record['executable_sha256']}</code>.</p>
<pre><code>cmake --preset highs -DCSL_ENABLE_QHULL=ON -DCSL_BUILD_EXT02_REPORT=ON
cmake --build --preset highs --target csl_ext02_portfolio_report
ctest --test-dir build/highs -R '^ext02_portfolio_report_smoke$' --output-on-failure
python3 scripts/reports/ext02/collect.py build/highs/csl_ext02_portfolio_report build/highs/ext02-evidence
python3 scripts/reports/ext02/render_saved.py build/highs/ext02-evidence/measurement.json reports/algorithm-results/ext02-two-state-mixed-v1</code></pre>
<p>Raw records: <a href="measurement.json">JSON</a>; <a href="raw.jsonl">JSONL</a>; <a href="trials.csv">CSV</a>; <a href="figure.svg">SVG figure</a>.</p></body></html>"""
    (output / "index.html").write_text(body, encoding="utf-8")
    raw_path = record_path.parent / "raw.jsonl"
    if raw_path.is_file():
        (output / "raw.jsonl").write_bytes(raw_path.read_bytes())
    csv_path = record_path.parent / "trials.csv"
    if csv_path.is_file():
        (output / "trials.csv").write_bytes(csv_path.read_bytes())
    (output / "README.md").write_text(
        "# EXT-02 report bundle\n\nStandalone HTML and figure are rendered from `measurement.json`; "
        "raw JSONL and CSV preserve all attempts. The bytes field counts numeric coefficients and RHS "
        "values only. This is one descriptive analytic fixture, not a comparative or scalability claim.\n",
        encoding="utf-8")
    files = sorted(path for path in output.iterdir() if path.is_file())
    sums = "".join(f"{sha(path.read_bytes())}  {path.name}\n" for path in files)
    (output / "SHA256SUMS").write_text(sums, encoding="ascii")
    with zipfile.ZipFile(output.with_suffix(".zip"), "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.iterdir()):
            if path.is_file():
                archive.write(path, path.name)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: render_saved.py MEASUREMENT_JSON OUTPUT_DIRECTORY")
    render(Path(sys.argv[1]), Path(sys.argv[2]))
