"""Stage the frozen MPC-01 per-attempt capture as an offline Pages report."""
from __future__ import annotations

import argparse
import hashlib
import html
from pathlib import Path
import re
import shutil
from pathlib import PurePosixPath
from urllib.parse import urldefrag, urlparse

ROOT = Path(__file__).resolve().parents[3]
REPORT_ID = "mpc01-per-attempt-20261103-r3"
SOURCE = ROOT / "docs/research/evidence" / REPORT_ID
STRATEGY_AB_ID = "mpc01-strategy-ab-ts03-20261103-r1"
STRATEGY_AB_SOURCE = ROOT / "docs/research/evidence" / STRATEGY_AB_ID
STRATEGY_AB_ROUTE = Path("docs/research/evidence") / STRATEGY_AB_ID
STRATEGY_AB_FILES = (
    "strategy-ab-ts03-summary.html", "strategy-ab-ts03-summary.md",
    "strategy-ab-ts03-control-plane.svg", "strategy-ab-ts03-events.jsonl",
    "strategy-ab-ts03-stdout.jsonl", "comparison-record.json", "scenario.json",
    "capture-environment.json", "codec-environment.json", "resource-profile.json",
    "capture-supervisor.py", "build-note.md",
)
STRATEGY_AB_TS02_ID = "mpc01-strategy-ab-ts02-per-attempt-20261103"
STRATEGY_AB_TS02_SOURCE = ROOT / "docs/research/evidence" / STRATEGY_AB_TS02_ID
STRATEGY_AB_TS02_ROUTE = Path("docs/research/evidence") / STRATEGY_AB_TS02_ID
STRATEGY_AB_TS02_FILES = (
    "strategy-ab-ts02-summary.html", "strategy-ab-ts02-summary.md",
    "strategy-ab-ts02-control-plane.svg", "strategy-ab-ts02-events.jsonl",
    "strategy-ab-ts02-stdout.jsonl", "strategy-ab-ts02-comparison-record.json",
    "scenario.json", "strategy-ab-ts02-environment.json",
    "strategy-ab-ts02-csl-environment.json", "resource-profile.json",
    "capture-supervisor.py", "run-capture.py", "binary-dynamic-dependencies.txt",
    "systemd-scope-processes.jsonl", "build-note.json",
    "cmake-compiler-metadata.cmake", "target-flags.make", "target-link.txt",
    "build-record.py", "render-report.py", "write-build-note.py",
)


def _insert_landing_link(site: Path, marker: str, href: str, label: str) -> None:
    landing = site / "index.html"
    if landing.is_symlink() or not landing.is_file():
        raise ValueError("built Pages site must have a regular root index.html")
    source_page = landing.read_text(encoding="utf-8")
    marker_attr = f'id="{marker}"'
    if marker_attr in source_page:
        raise ValueError("Pages landing link already exists: " + marker)
    link = f'<p {marker_attr}><a href="{href}">{label}</a></p>'
    updated, count = re.subn(r"(<body\b[^>]*>)", lambda match: match.group(1) + link,
                             source_page, count=1, flags=re.IGNORECASE)
    if count != 1:
        raise ValueError("built Pages root index.html has no body element")
    landing.write_text(updated, encoding="utf-8")


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
<h2>Strategy A/B analytic comparison</h2><p><a href="../{STRATEGY_AB_TS02_ROUTE.as_posix()}/strategy-ab-ts02-summary.html">T-S02: five alternating Strategy A/B pairs, each with its own process-tree limit, plus a separate limiter profile.</a> This constant-objective fixture checks family plumbing and replay, not optimization difficulty or general performance.</p>
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
    _insert_landing_link(site, "mpc01-per-attempt-link", f"{REPORT_ID}/index.html",
                         "MPC-01 per-attempt OSQP and HPIPM capture →")
    stage_strategy_ab(site)
    stage_strategy_ab_ts02(site)
    return dest


def _check_manifest(bundle: Path, required_files: tuple[str, ...] = STRATEGY_AB_FILES) -> set[str]:
    manifest = bundle / "SHA256SUMS"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Strategy A/B source checksum manifest is required")
    names: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("unsafe Strategy A/B manifest path: " + name)
        path = bundle / name
        if (name in names or path.is_symlink() or not path.is_file() or
                not path.resolve().is_relative_to(bundle.resolve()) or
                hashlib.sha256(path.read_bytes()).hexdigest() != digest):
            raise ValueError("Strategy A/B source-bundle checksum mismatch: " + name)
        names.add(name)
    if not set(required_files).issubset(names):
        raise ValueError("Strategy A/B source-bundle inventory is incomplete")
    actual = {path.relative_to(bundle).as_posix() for path in bundle.rglob("*")
              if path.is_file() and path.name != "SHA256SUMS"}
    if actual != names or any(path.is_symlink() for path in bundle.rglob("*")):
        raise ValueError("Strategy A/B source-bundle contents differ from its checksum manifest")
    return names


def stage_strategy_ab(site: Path) -> Path:
    if (STRATEGY_AB_SOURCE.is_symlink() or not STRATEGY_AB_SOURCE.is_dir() or
            site.is_symlink() or not site.is_dir()):
        raise ValueError("Strategy A/B evidence source and built site directory are required")
    _check_manifest(STRATEGY_AB_SOURCE)
    destination = site / STRATEGY_AB_ROUTE
    if destination.exists() or destination.is_symlink():
        raise ValueError("Strategy A/B report route must be fresh")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(STRATEGY_AB_SOURCE, destination, symlinks=False)

    # Keep the immutable report's source link working at its documented relative path.
    source_dir = site / "scripts/reports/mpc01"
    source_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("summarize_strategy_ab_ts03.py", "build_strategy_ab_records.py"):
        source = ROOT / "scripts/reports/mpc01" / filename
        target = source_dir / filename
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise ValueError("Strategy A/B renderer route conflicts with an existing site file")
        if not target.exists():
            shutil.copy2(source, target)

    _insert_landing_link(
        site, "mpc01-strategy-ab-ts03-link",
        f"{STRATEGY_AB_ROUTE.as_posix()}/strategy-ab-ts03-summary.html",
        "MPC-01 Strategy A/B T-S03 report →")
    return destination


def stage_strategy_ab_ts02(site: Path) -> Path:
    if (STRATEGY_AB_TS02_SOURCE.is_symlink() or not STRATEGY_AB_TS02_SOURCE.is_dir() or
            site.is_symlink() or not site.is_dir()):
        raise ValueError("Strategy A/B T-S02 evidence source and built site directory are required")
    _check_manifest(STRATEGY_AB_TS02_SOURCE, STRATEGY_AB_TS02_FILES)
    destination = site / STRATEGY_AB_TS02_ROUTE
    if destination.exists() or destination.is_symlink():
        raise ValueError("Strategy A/B T-S02 report route must be fresh")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(STRATEGY_AB_TS02_SOURCE, destination, symlinks=False)
    source_dir = site / "scripts/reports/mpc01"
    source_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("summarize_strategy_ab_ts02.py", "build_strategy_ab_records.py"):
        source = ROOT / "scripts/reports/mpc01" / filename
        target = source_dir / filename
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise ValueError("T-S02 Strategy A/B renderer route conflicts with an existing site file")
        if not target.exists():
            shutil.copy2(source, target)
    _insert_landing_link(
        site, "mpc01-strategy-ab-ts02-link",
        f"{STRATEGY_AB_TS02_ROUTE.as_posix()}/strategy-ab-ts02-summary.html",
        "MPC-01 Strategy A/B T-S02 per-attempt report →")
    return destination


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
    for reference in re.findall(r'(?:href|src)="([^"]+)"', report_html):
        parsed = urlparse(reference)
        if parsed.scheme or parsed.netloc:
            continue
        target = (route / urldefrag(parsed.path)[0]).resolve()
        if not target.is_relative_to(site.resolve()) or not target.is_file():
            raise ValueError("MPC-01 report links to a missing or escaping file: " + reference)

    strategy_landing = site / STRATEGY_AB_ROUTE / "strategy-ab-ts03-summary.html"
    strategy_source = STRATEGY_AB_SOURCE
    strategy_route = site / STRATEGY_AB_ROUTE
    if (strategy_source.is_symlink() or not strategy_source.is_dir() or
            strategy_route.is_symlink() or not strategy_route.is_dir() or
            strategy_landing.is_symlink() or not strategy_landing.is_file()):
        raise ValueError("staged Strategy A/B T-S03 report route is missing")
    expected_names = _check_manifest(strategy_source)
    if _check_manifest(strategy_route) != expected_names:
        raise ValueError("staged Strategy A/B report inventory differs from source")
    renderer_dir = site / "scripts/reports/mpc01"
    for filename in ("summarize_strategy_ab_ts03.py", "build_strategy_ab_records.py"):
        renderer = renderer_dir / filename
        source = ROOT / "scripts/reports/mpc01" / filename
        if (renderer.is_symlink() or not renderer.is_file() or
                renderer.read_bytes() != source.read_bytes()):
            raise ValueError("staged Strategy A/B renderer differs from source: " + filename)
    for name in expected_names:
        if (strategy_route / name).read_bytes() != (strategy_source / name).read_bytes():
            raise ValueError("staged Strategy A/B report differs from source: " + name)
    page = strategy_landing.read_text(encoding="utf-8")
    for reference in re.findall(r'(?:href|src)="([^"]+)"', page):
        parsed = urlparse(reference)
        if parsed.scheme or parsed.netloc:
            continue
        target = (strategy_landing.parent / urldefrag(parsed.path)[0]).resolve()
        if not target.is_relative_to(site.resolve()) or not target.is_file():
            raise ValueError("Strategy A/B report links to a missing or escaping file: " + reference)
    landing_html = landing.read_text(encoding="utf-8")
    if f'href="{STRATEGY_AB_ROUTE.as_posix()}/strategy-ab-ts03-summary.html"' not in landing_html:
        raise ValueError("Strategy A/B T-S03 link is missing from the Pages landing page")

    ts02_source = STRATEGY_AB_TS02_SOURCE
    ts02_route = site / STRATEGY_AB_TS02_ROUTE
    ts02_landing = ts02_route / "strategy-ab-ts02-summary.html"
    if (ts02_source.is_symlink() or not ts02_source.is_dir() or ts02_route.is_symlink() or
            not ts02_route.is_dir() or ts02_landing.is_symlink() or not ts02_landing.is_file()):
        raise ValueError("staged Strategy A/B T-S02 report route is missing")
    ts02_names = _check_manifest(ts02_source, STRATEGY_AB_TS02_FILES)
    if _check_manifest(ts02_route, STRATEGY_AB_TS02_FILES) != ts02_names:
        raise ValueError("staged Strategy A/B T-S02 report inventory differs from source")
    for name in ts02_names:
        if (ts02_route / name).read_bytes() != (ts02_source / name).read_bytes():
            raise ValueError("Strategy A/B T-S02 report differs from source: " + name)
    for filename in ("summarize_strategy_ab_ts02.py", "build_strategy_ab_records.py"):
        renderer = renderer_dir / filename
        source = ROOT / "scripts/reports/mpc01" / filename
        if renderer.is_symlink() or not renderer.is_file() or renderer.read_bytes() != source.read_bytes():
            raise ValueError("staged Strategy A/B T-S02 renderer differs from source: " + filename)
    page = ts02_landing.read_text(encoding="utf-8")
    for reference in re.findall(r'(?:href|src)="([^"]+)"', page):
        parsed = urlparse(reference)
        if parsed.scheme or parsed.netloc:
            continue
        target = (ts02_landing.parent / urldefrag(parsed.path)[0]).resolve()
        if not target.is_relative_to(site.resolve()) or not target.is_file():
            raise ValueError("Strategy A/B T-S02 report links to a missing or escaping file: " + reference)
    if f'href="{STRATEGY_AB_TS02_ROUTE.as_posix()}/strategy-ab-ts02-summary.html"' not in landing_html:
        raise ValueError("Strategy A/B T-S02 link is missing from the Pages landing page")


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
