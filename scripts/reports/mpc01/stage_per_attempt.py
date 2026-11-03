"""Stage the frozen MPC-01 per-attempt capture as an offline Pages report."""
from __future__ import annotations

import argparse
import hashlib
import html
from pathlib import Path
import re
import shutil
from urllib.parse import urldefrag, urlparse

ROOT = Path(__file__).resolve().parents[3]
REPORT_ID = "mpc01-per-attempt-20261103-r3"
SOURCE = ROOT / "docs/research/evidence" / REPORT_ID


def page() -> str:
    summary = (SOURCE / "benchmark-summary.md").read_text(encoding="utf-8")
    rows = []
    in_table = False
    for line in summary.splitlines():
        if line.startswith("| Fixture |"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
            if len(cells) == 7:
                rows.append("<tr>" + "".join("<td>" + html.escape(c) + "</td>" for c in cells) + "</tr>")
        elif in_table:
            break
    table = "\n".join(rows)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MPC-01 per-attempt solver capture</title><style>
:root{{color-scheme:light dark}}body{{margin:0;background:#101827;color:#e5edf7;font:16px/1.6 system-ui,sans-serif}}
main{{max-width:1120px;margin:auto;padding:2rem}}a{{color:#7dd3fc}}.scope{{border-left:4px solid #f59e0b;background:#1b2638;padding:1rem}}
table{{border-collapse:collapse;width:100%;font-size:.9rem;font-variant-numeric:tabular-nums;display:block;overflow-x:auto;white-space:nowrap}}
th,td{{border-bottom:1px solid #526174;padding:.45rem .6rem;text-align:left}}img{{width:100%;height:auto}}code{{overflow-wrap:anywhere}}
</style></head><body><main>
<p><a href="../examples/index.html">Visual examples</a> / MPC-01 solver capture</p>
<h1>MPC-01: per-attempt OSQP and HPIPM capture</h1>
<p>Five cold and five warm-if-available repetitions per solver and fixture, captured in individually limited process scopes. The seven fixtures cover T-S01, T-S02, singular T-S03, infeasible and unbounded cases, the exact #421 double integrator, and the separately identified article-derived B04 reference input.</p>
<div class="scope"><strong>Evidence limits.</strong> This is a native solver-arm experiment, not a closed-loop MPC run or a general solver ranking. Solve medians and ranges are descriptive for this host and workload. Warm attempts include their cold seed solve in the attempt resource budget. HPIPM inconclusive statuses on infeasible, singular and unbounded cases remain recorded; they are not counted as successful classifications. B04 solver residual checks are inconclusive, so its plotted native paths are illustrations only.</div>
<h2>Saved B04 trajectory projections</h2><p>The paired plots show oxidizer state <code>(x1,x2)</code> and fuel state <code>(x3,x4)</code>. They illustrate representative solver paths for the MPC fixture; the TwoPoints environment report is the differential-game reachability example.</p>
<p><a href="b04-repeated-projections.html"><img src="b04-repeated-projections.svg" alt="Exact reference trajectory and representative OSQP and HPIPM trajectories in the oxidizer and fuel phase planes"></a></p>
<h2>Native solve time, five repetitions per arm</h2><table><thead><tr><th>Fixture</th><th>Solver</th><th>Start</th><th>Outcomes</th><th>Median (ms)</th><th>Range (ms)</th><th>Attempt median (ms)</th></tr></thead><tbody>{table}</tbody></table>
<h2>Resource and verification scope</h2><p>Each of 140 attempts ran sequentially with a 300-second process-tree watchdog, 8 GiB cgroup-v2 memory cap, swap disabled, one CPU quota, and one pinned logical CPU. The host had 7.55 GiB physical RAM, below the per-attempt memory cap; observed peak process-tree memory was 12,173,312 bytes. There were no timeouts, failed attempts, or OOM events.</p>
<p>An independent exact-rational checker verified feasibility and objective bounds for 90 attempts classified optimal. Full attempt receipts, checker records, solver outputs, environment identity, and their source checksums are included below.</p>
<h2>Evidence files</h2><ul><li><a href="benchmark-summary.md">Benchmark summary and reproduction context</a></li><li><a href="attempts.jsonl">140 resource and outcome receipts</a></li><li><a href="comparison-records.jsonl">Canonical comparison records</a></li><li><a href="native-attempts.jsonl">Native solver attempt rows</a></li><li><a href="exact-candidate-checks.jsonl">Independent exact checks</a></li><li><a href="exact-check-manifest.json">Exact-check manifest</a></li><li><a href="capture-profile.json">Capture profile</a></li><li><a href="build-identity.json">Build and source identity</a></li><li><a href="SHA256SUMS">Original source-bundle checksums</a></li></ul>
<p>Capture date: 2026-11-02. Source revision: <code>452db1ceb0312607fe7791b5ff4d84a2730df6ff</code>. No package or release change.</p>
</main></body></html>'''


def stage(site: Path) -> Path:
    if SOURCE.is_symlink() or not SOURCE.is_dir() or site.is_symlink() or not site.is_dir():
        raise ValueError("evidence source and built site directory are required")
    landing = site / "index.html"
    if landing.is_symlink() or not landing.is_file():
        raise ValueError("built Pages site must have a root index.html")
    dest = site / REPORT_ID
    if dest.exists() or dest.is_symlink():
        raise ValueError("report route must be fresh")
    shutil.copytree(SOURCE, dest, symlinks=False)
    (dest / "index.html").write_text(page(), encoding="utf-8")
    source_page = landing.read_text(encoding="utf-8")
    if 'id="mpc01-per-attempt-link"' in source_page:
        raise ValueError("MPC-01 landing link already exists")
    link = (f'<p id="mpc01-per-attempt-link"><a href="{REPORT_ID}/index.html">'
            'MPC-01 per-attempt OSQP and HPIPM capture →</a></p>')
    updated, count = re.subn(r"(<body\b[^>]*>)", lambda match: match.group(1) + link,
                             source_page, count=1, flags=re.IGNORECASE)
    if count != 1:
        raise ValueError("built Pages root index.html has no body element")
    landing.write_text(updated, encoding="utf-8")
    return dest


def validate(site: Path) -> None:
    route = site / REPORT_ID
    landing = site / "index.html"
    if site.is_symlink() or not site.is_dir() or route.is_symlink() or not route.is_dir():
        raise ValueError("staged Pages site and MPC-01 route are required")
    if landing.is_symlink() or not landing.is_file() or not (route / "index.html").is_file():
        raise ValueError("staged Pages landing or MPC-01 report is missing")
    landing_html = landing.read_text(encoding="utf-8")
    if f'href="{REPORT_ID}/index.html"' not in landing_html:
        raise ValueError("MPC-01 report link is missing from the Pages landing page")
    for line in (route / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        path = route / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("MPC-01 source-bundle checksum mismatch: " + name)
    report_html = (route / "index.html").read_text(encoding="utf-8")
    if "not a closed-loop MPC run" not in report_html or "TwoPoints environment report" not in report_html:
        raise ValueError("MPC-01 report scope statement differs")
    for href in re.findall(r'href="([^"]+)"', report_html):
        parsed = urlparse(href)
        if parsed.scheme or parsed.netloc:
            continue
        target = (route / urldefrag(parsed.path)[0]).resolve()
        if not target.is_relative_to(site.resolve()) or not target.is_file():
            raise ValueError("MPC-01 report links to a missing or escaping file: " + href)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="validate an already augmented Pages site")
    args = parser.parse_args()
    if args.check:
        validate(args.site)
        print(REPORT_ID)
    else:
        print(stage(args.site).as_posix())
