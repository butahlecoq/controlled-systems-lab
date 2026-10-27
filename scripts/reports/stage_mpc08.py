"""Package, validate, and stage the saved MPC-08 explicit-set pilot."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
from html.parser import HTMLParser
import json
import platform
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import zipfile
from collections import Counter

import report_data


REPORT_ID = "mpc08-explicit-pilot-v1"
ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "benchmarks/reporting/mpc08_explicit"
GENERATED = SOURCE_DIR / "generated"
BUNDLE = ROOT / "reports/algorithm-results" / REPORT_ID
ARCHIVE = ROOT / "reports/algorithm-results" / f"{REPORT_ID}.zip"
FILES = (
    "index.html", "record.json", "build-provenance.json", "manifest.json",
    "README.md", "explicit-double-integrator.json", "explicit-double-integrator-queries.csv",
    "csl-candidate-observations.jsonl", "critical-regions.svg",
)
DATA_FILES = {
    "explicit-double-integrator.json": "explicit-double-integrator.json",
    "explicit-double-integrator-queries.csv": "explicit-double-integrator-queries.csv",
    "csl-candidate-observations.jsonl": "csl-candidate-observations.jsonl",
    "critical-regions.svg": "explicit-double-integrator.svg",
}
SOURCE_FILES = (
    "CMakeLists.txt", "cmake/OptionalReports.cmake",
    "benchmarks/reporting/mpc08_explicit/README.md",
    "benchmarks/reporting/mpc08_explicit/explicit_double_integrator.py",
    "benchmarks/reporting/mpc08_explicit/mpc08_strategy_comparison.cpp",
    "scripts/reports/stage_mpc08.py", ".github/workflows/algorithm-reports.yml",
)
CARD = (
    '<article class="saved-figure" id="mpc08-explicit-pilot-v1">'
    '<p class="eyebrow">Explicit MPC · exact analytic pilot</p>'
    '<h3>Double-integrator feasible domain and critical regions</h3>'
    '<a href="../mpc08-explicit-pilot-v1/index.html">'
    '<img src="../mpc08-explicit-pilot-v1/critical-regions.svg" '
    'alt="Nine critical regions cover the feasible initial-state polygon; a separate terminal invariant set is shown beside it."></a>'
    '<p>Exact rational one-step terminal-only fixture. The report preserves candidate failures and makes no performance-winner claim.</p>'
    '<p><a href="../mpc08-explicit-pilot-v1/index.html">Open the report, raw observations, and offline bundle →</a></p></article>'
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), f"missing or unsafe file: {path}")
    return digest(path.read_bytes())


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def command_line(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip().splitlines()[0]


def package(source_commit: str) -> None:
    require(re.fullmatch(r"[0-9a-f]{40}", source_commit) is not None, "source commit must be a full SHA")
    reference = read_json(GENERATED / "explicit-double-integrator.json")
    observations = [json.loads(line) for line in
                   (GENERATED / "csl-candidate-observations.jsonl").read_text(encoding="utf-8").splitlines()]
    queries = (GENERATED / "explicit-double-integrator-queries.csv").read_text(encoding="utf-8").splitlines()
    require(reference["schema"] == "csl.mpc08-explicit-double-integrator/1", "unexpected reference schema")
    require(reference["explicit_solution"]["critical_region_count"] == 9 and
            reference["solver_validation_query_count"] == 45, "reference fixture inventory differs")
    require(len(queries) == 46 and len(observations) == 810, "query or observation count differs")
    candidate_rows = [row for row in observations if row["strategy"] != "online-condensed-qp"]
    online_rows = [row for row in observations if row["strategy"] == "online-condensed-qp"]
    require(len(candidate_rows) == 540 and len(online_rows) == 270, "method observation counts differ")
    require(all(row["candidate_contains_exact_reference_history"] is True and
                row["action_and_value_match_exact_reference"] is None for row in candidate_rows),
            "candidate observation fields conflate full histories and pointwise controls")
    require(all(row["candidate_contains_exact_reference_history"] is False and
                row["action_and_value_match_exact_reference"] is True for row in online_rows),
            "online QP observation fields do not report action/value checks distinctly")

    source_hashes = {name: file_digest(ROOT / name) for name in SOURCE_FILES}
    raw_hashes = {name: file_digest(GENERATED / name) for name in (
        "explicit-double-integrator.json", "explicit-double-integrator-queries.csv",
        "csl-candidate-observations.jsonl", "explicit-double-integrator.svg")}
    grouped = {}
    for method in sorted({row["strategy"] for row in observations}):
        rows = [row for row in observations if row["strategy"] == method]
        measured = [row for row in rows if not row["warmup"]]
        elapsed = [row["elapsed_ns"] for row in measured]
        grouped[method] = {
            "attempts_including_warmup": len(rows), "warmups": sum(row["warmup"] for row in rows),
            "measured_attempts": len(measured),
            "statuses": dict(sorted(Counter(row["status"] for row in rows).items())),
            "median_elapsed_ns": int(statistics.median(elapsed)),
            "min_elapsed_ns": min(elapsed), "max_elapsed_ns": max(elapsed),
        }
    noncompleted = [row for row in observations if row["termination_code"] not in (0, -1)]
    require(len(noncompleted) == 6 and all(row["query_id"] == "Q017" for row in noncompleted),
            "retained numerical-failure inventory differs")

    BUNDLE.mkdir(parents=True, exist_ok=True)
    for target, source in DATA_FILES.items():
        shutil.copyfile(GENERATED / source, BUNDLE / target)
    readme = (SOURCE_DIR / "README.md").read_text(encoding="utf-8")
    readme = readme.replace(
        "../../../reports/algorithm-results/mpc08-explicit-pilot-v1/index.html",
        "index.html",
    )
    readme = readme.replace("generated/explicit-double-integrator.svg", "critical-regions.svg")
    readme = readme.replace("generated/csl-candidate-observations.jsonl", "csl-candidate-observations.jsonl")
    (BUNDLE / "README.md").write_text(readme, encoding="utf-8")
    source_url = (f"https://github.com/butahlecoq/controlled-systems-lab/blob/"
                  f"{source_commit}/benchmarks/reporting/mpc08_explicit/README.md")
    record = {
        "schema": "csl.mpc08-explicit-pilot-record/1", "report_id": REPORT_ID,
        "issue": "https://github.com/butahlecoq/controlled-systems-lab/issues/604",
        "source_commit": source_commit, "base_commit": "0994a51478b4fa3aa448308bddc2e6308c37111d",
        "source_url": source_url, "scenario_sha256": raw_hashes["explicit-double-integrator.json"],
        "query_sha256": raw_hashes["explicit-double-integrator-queries.csv"],
        "observations_sha256": raw_hashes["csl-candidate-observations.jsonl"],
        "figure_sha256": raw_hashes["explicit-double-integrator.svg"],
        "feasible_initial_area": reference["explicit_solution"]["feasible_area"],
        "critical_regions": reference["explicit_solution"]["critical_region_count"],
        "total_region_facets": sum(len(region["vertices"]) for region in reference["regions"]),
        "solver_validation_queries": reference["solver_validation_query_count"],
        "point_location_queries": reference["measurement"]["point_location_queries"],
        "offline_region_construction_ns_single_run": reference["measurement"]["offline_region_construction_ns"],
        "point_location_rounds_ns": reference["measurement"]["point_location_rounds_ns"],
        "methods": grouped,
        "noncompleted_attempts": [{"query_id": row["query_id"], "strategy": row["strategy"],
                                    "warmup": row["warmup"], "repetition": row["repetition"],
                                    "termination_code": row["termination_code"], "stop_details": row["stop_details"]}
                                   for row in noncompleted],
        "evidence_limits": [
            "A and B return candidate relations for one fixed initial state; containment is not a completeness proof.",
            "The online QP returns one first action and an independently recomputed value; it does not return a joint family.",
            "Strategy B has five measured numerical failures at Q017 plus its warmup failure; those outcomes remain in raw observations.",
            "Timings do different work and no fastest-method verdict is supported; no source profiler was available.",
            "No uncertainty, predecessor quantifier, minimax, nonunique new-fixture, region-growth, or approximation comparison is made.",
        ],
    }
    write_json(BUNDLE / "record.json", record)
    provenance = {
        "schema": "csl.mpc08-explicit-pilot-provenance/1", "source_commit": source_commit,
        "source_files_sha256": source_hashes,
        "host": {"system": platform.system(), "release": platform.release(),
                 "machine": platform.machine(), "cpu": "AMD Ryzen 5 3550H with Radeon Vega Mobile Gfx",
                 "logical_cpus": 8, "load_isolated_or_captured": False},
        "compiler": command_line("g++", "--version"),
        "cmake": command_line("/home/butahlecoq/.local/share/mise/installs/cmake/3.31.6/cmake-3.31.6-linux-x86_64/bin/cmake", "--version"),
        "generator": "Ninja 1.12.1", "build_type": "Release", "release_flags": "-O3 -DNDEBUG",
        "highs": {"version": "1.11.0", "archive_sha256": "2b44b074cf41439325ce4d0bbdac2d51379f56faf17ba15320a410d3c1f07275",
                  "solver_threads": 1},
        "qhull": {"version": "8.0.2", "archive_sha256": "8774e9a12c70b0180b95d6b0b563c5aa4bea8d5960c15e18ae3b6d2521d64f8b"},
        "measurement": {"methods": 3, "queries": 45, "warmups_per_method_query": 1,
                        "measured_repetitions_per_method_query": 5, "order": "interleaved, rotated by repetition",
                        "clock": "std::chrono::steady_clock; elapsed_ns per record",
                        "compiler_setup_included": False, "source_profiler": "unavailable",
                        "timing_scope": "see README; candidate construction and condensed online QP return different products"},
        "reproduction": [
            "python3 benchmarks/reporting/mpc08_explicit/explicit_double_integrator.py",
            "cmake -S . -B build/mpc08 -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=ON -DCSL_BUILD_MPC08_REPORT=ON",
            "cmake --build build/mpc08 --target csl_mpc08_explicit_compare --parallel 4",
            "build/mpc08/csl_mpc08_explicit_compare benchmarks/reporting/mpc08_explicit/generated/explicit-double-integrator-queries.csv > benchmarks/reporting/mpc08_explicit/generated/csl-candidate-observations.jsonl",
        ],
        "raw_artifacts_sha256": raw_hashes,
    }
    write_json(BUNDLE / "build-provenance.json", provenance)
    (BUNDLE / "index.html").write_text(render_html(record), encoding="utf-8")
    report_data.validate_svg((BUNDLE / "critical-regions.svg").read_bytes())
    manifest = {"schema": "csl.mpc08-explicit-pilot-manifest/1", "report_id": REPORT_ID,
                "files_sha256": {name: file_digest(BUNDLE / name) for name in FILES if name != "manifest.json"}}
    write_json(BUNDLE / "manifest.json", manifest)
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in FILES:
            archive.write(BUNDLE / name, arcname=f"{REPORT_ID}/{name}")
    print(json.dumps({"bundle": str(BUNDLE), "archive": str(ARCHIVE),
                      "record_sha256": file_digest(BUNDLE / "record.json"),
                      "archive_sha256": file_digest(ARCHIVE)}, sort_keys=True))


def render_html(record: dict) -> str:
    methods = record["methods"]
    rows = []
    for method, label, note in (
        ("csl.synthesis.reach-back", "Strategy A reach-back candidate", "Candidate contains exact analytic history at all points."),
        ("csl.synthesis.strategy-b", "Strategy B direct-joint candidate", "Candidate contains the history; Q017 numerical failures are retained."),
        ("online-condensed-qp", "Condensed online scalar QP", "Exact-reference first action and independently recomputed value."),
    ):
        item = methods[method]
        median_ms = item["median_elapsed_ns"] / 1e6
        low_ms, high_ms = item["min_elapsed_ns"] / 1e6, item["max_elapsed_ns"] / 1e6
        rows.append(f"<tr><th scope=\"row\">{escape(label)}</th><td>{item['measured_attempts']}</td>"
                    f"<td>{median_ms:.3f} ms</td><td>{low_ms:.3f}–{high_ms:.3f} ms</td><td>{escape(note)}</td></tr>")
    source_link = (f"https://github.com/butahlecoq/controlled-systems-lab/blob/"
                   f"{record['source_commit']}/benchmarks/reporting/mpc08_explicit/README.md")
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Exact explicit MPC pilot · MPC-08</title>
<style>:root{{color-scheme:dark;--bg:#282828;--panel:#32302f;--fg:#ebdbb2;--muted:#bdae93;--accent:#8ec07c;--line:#504945}}body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,sans-serif}}main{{max-width:1040px;margin:auto;padding:2rem 1.2rem}}a{{color:var(--accent)}}h1,h2{{line-height:1.2}}.panel{{background:var(--panel);border:1px solid var(--line);border-radius:.5rem;padding:1rem;margin:1rem 0}}table{{border-collapse:collapse;width:100%;font-size:.94rem}}th,td{{text-align:left;vertical-align:top;padding:.55rem;border-bottom:1px solid var(--line)}}img{{max-width:100%;height:auto;background:#fff}}code{{color:#fabd2f}}small,.muted{{color:var(--muted)}}.limits{{border-left:3px solid #fabd2f;padding-left:.8rem}}</style></head><body><main>
<p class="muted">MPC-08 · exact one-step analytic pilot · source {record['source_commit'][:12]}</p><h1>Explicit MPC and the feasible-state geometry</h1>
<p>This pilot keeps four products distinct: feasible initial states <code>F</code>, the invariant terminal set <code>T</code>, the explicit value and first action, and CSL's fixed-initial candidate history relation.</p>
<figure><img src="critical-regions.svg" alt="Nine exact critical regions cover the feasible initial-state polygon; the invariant terminal set is shown separately."><figcaption>Left: the initial box <code>X</code>, feasible domain <code>F</code>, and nine control regions. Right: the separate invariant terminal set in terminal-state coordinates.</figcaption></figure>
<section class="panel"><h2>Fixture and exact result</h2><p>One-step double integrator: <code>p1=p+v</code>, <code>v1=v+u</code>, <code>u∈[-1,1]</code>, initial box <code>X=[-3,3]×[-2,2]</code>, terminal set <code>|p1+2v1|≤1</code>, <code>|p1+v1|≤1</code>, terminal-only objective <code>p1²+v1²</code>.</p>
<p>Exact rational elimination gives feasible area <strong>{escape(record['feasible_initial_area'])}</strong> and <strong>{record['critical_regions']}</strong> critical regions with <strong>{record['total_region_facets']}</strong> total polygon edges. Region area coverage, positive-area overlaps, and shared-boundary control agreement are checked over rational half-spaces. The solver validation set has {record['solver_validation_queries']} exact points from region centroids, vertices, and edge midpoints.</p></section>
<section class="panel"><h2>Fixed-initial observations</h2><table><thead><tr><th>Path</th><th>Calls</th><th>Median</th><th>Range</th><th>Observed result</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<p>Each method has one warmup and five interleaved measured calls per point. Timings include the path-specific work stated in the report README; these paths return different products. No timing winner is claimed.</p></section>
<section class="panel"><h2>Evidence limits</h2><p class="limits">Strategy A/B records check whether a candidate relation contains the analytic unique history for one fixed initial state; they do not establish a complete family. The online QP returns a scalar input, so its record reports action/value agreement, not history-relation membership. Strategy B's numerical failures at <code>Q017=(-1,0)</code> remain in raw data. The exact new fixture has a unique scalar control; the separate T-S01 nonunique-history case is not rerun here.</p><p>This pilot makes no disturbance, robust-predecessor, minimax, scaling, region-explosion, or approximation claim. The comparisons remain inconclusive for performance.</p></section>
<section class="panel"><h2>Reproduce and download</h2><ul><li><a href="README.md">Full methodology, commands, timings, and scope limits</a></li><li><a href="explicit-double-integrator.json">Exact region record</a></li><li><a href="explicit-double-integrator-queries.csv">Exact solver-validation queries</a></li><li><a href="csl-candidate-observations.jsonl">All 810 raw method observations</a></li><li><a href="build-provenance.json">Build and environment provenance</a></li><li><a href="manifest.json">Per-file SHA-256 manifest</a></li><li><a href="../{REPORT_ID}.zip">Offline report bundle</a></li><li><a href="{escape(source_link)}">Versioned report source tree</a></li><li><a href="{escape(record['issue'])}">Open issue #604</a></li></ul></section>
</main></body></html>\n'''


class SafeHTML(HTMLParser):
    allowed_tags = {"html", "head", "meta", "title", "style", "body", "main", "p", "h1", "h2", "section", "figure", "img", "figcaption", "strong", "code", "table", "thead", "tbody", "tr", "th", "td", "a", "ul", "li"}

    def __init__(self, files: set[str]):
        super().__init__(convert_charrefs=True)
        self.files = files
        self.style = False

    def handle_starttag(self, tag, attrs):
        require(tag in self.allowed_tags, "unsafe tag in saved MPC-08 HTML")
        attrs = dict(attrs)
        allowed = {"html": {"lang"}, "meta": {"charset", "name", "content"},
                   "a": {"href"}, "img": {"src", "alt"}, "th": {"scope"},
                   "p": {"class"}, "section": {"class"}}
        require(set(attrs) <= allowed.get(tag, set()), "unsafe HTML attribute in saved MPC-08 report")
        if tag in ("a", "img"):
            value = attrs.get("href", attrs.get("src", ""))
            if value.startswith("https://"):
                require(value.startswith("https://github.com/butahlecoq/controlled-systems-lab/"),
                        "external HTML resource is not allowlisted")
            else:
                require(value and value.split("#")[0] in self.files | {"../" + REPORT_ID + ".zip"},
                        "report link escapes bundle")
        self.style = tag == "style"

    def handle_endtag(self, tag):
        if tag == "style":
            self.style = False

    def handle_data(self, value):
        if self.style:
            require(re.search(r"@import|url\s*\(", value, re.I) is None, "external CSS resource is not allowed")


def validate_bundle(source: Path) -> dict:
    require(source.is_dir() and not source.is_symlink(), "MPC-08 report bundle is missing or unsafe")
    manifest = read_json(source / "manifest.json")
    require(manifest.get("schema") == "csl.mpc08-explicit-pilot-manifest/1" and
            manifest.get("report_id") == REPORT_ID, "unexpected report manifest")
    require(set(manifest["files_sha256"]) == set(FILES) - {"manifest.json"}, "manifest inventory differs")
    for name, sha in manifest["files_sha256"].items():
        require(file_digest(source / name) == sha, f"report checksum differs for {name}")
    record = read_json(source / "record.json")
    provenance = read_json(source / "build-provenance.json")
    require(record.get("schema") == "csl.mpc08-explicit-pilot-record/1" and
            provenance.get("schema") == "csl.mpc08-explicit-pilot-provenance/1", "record/provenance schema mismatch")
    require(record.get("source_commit") == provenance.get("source_commit"), "source identity differs")
    require((source / "index.html").read_text(encoding="utf-8") == render_html(record), "HTML differs from record renderer")
    SafeHTML(set(FILES)).feed((source / "index.html").read_text(encoding="utf-8"))
    report_data.validate_svg((source / "critical-regions.svg").read_bytes())
    observations = [json.loads(line) for line in (source / "csl-candidate-observations.jsonl").read_text(encoding="utf-8").splitlines()]
    online = [row for row in observations if row["strategy"] == "online-condensed-qp"]
    require(online and all(not row["candidate_contains_exact_reference_history"] and
                           row["action_and_value_match_exact_reference"] for row in online),
            "online QP records misstate candidate-family membership")
    return record


def stage(source: Path, site: Path) -> None:
    source, site = source.resolve(), site.resolve()
    validate_bundle(source)
    gallery = site / "examples/index.html"
    require(gallery.is_file() and not gallery.is_symlink(), "examples gallery is missing")
    html = gallery.read_text(encoding="utf-8")
    marker = '<section id="analytic-illustrations">'
    require(marker in html or f'id="{REPORT_ID}"' in html, "gallery insertion point is missing")
    require(f'id="{REPORT_ID}"' not in html or CARD in html, "gallery report identity collides")
    route = site / REPORT_ID
    route.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copyfile(source / name, route / name)
    shutil.copyfile(ARCHIVE, site / f"{REPORT_ID}.zip")
    if f'id="{REPORT_ID}"' not in html:
        gallery.write_text(html.replace(marker, CARD + marker, 1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", action="store_true", help="build the immutable report from generated pilot outputs")
    parser.add_argument("--source-commit", help="full commit containing the measured driver and reference generator")
    parser.add_argument("--source", type=Path, default=BUNDLE, help="saved report bundle to validate and stage")
    parser.add_argument("--site", type=Path, help="generated static site root")
    args = parser.parse_args()
    if args.package:
        require(args.source_commit is not None, "--package requires --source-commit")
        package(args.source_commit)
    if args.site is not None:
        stage(args.source, args.site)
    if not args.package and args.site is None:
        parser.error("choose --package and/or --site")


if __name__ == "__main__":
    main()
