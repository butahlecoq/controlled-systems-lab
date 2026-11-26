"""Build and stage the #1096 nonaxis parallelotope A/B campaign report.

The builder reads the extracted campaign evidence directory (saved attempts and
comparison records) and writes one deterministic, content-addressed report
directory.  The stager validates that directory byte for byte and adds it to a
built report site.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from html import escape
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import site_additions

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "csl.app02-nonaxis-campaign/1"
CATALOG_SCHEMA = "csl.app02-nonaxis-publications/1"
SOURCE_COMMIT = "3c3c694331497f2f3e991dbe7c1a6e328052af56"
PREFIX = "app02-nonaxis-ab-"
CONTROLLERS = {
    "axis": "native-continuous-history-parallelotope-ipopt/1",
    "fixed-45": "native-continuous-history-parallelotope-rotated-ipopt/1",
    "selected": "native-continuous-history-parallelotope-selected-ipopt/1",
}
TASKS = ("syn-nl-lv-01", "earth-orbit", "syn-nl-fuel-01")
TASK_LABELS = {
    "syn-nl-lv-01": "Lotka–Volterra",
    "earth-orbit": "Earth orbit",
    "syn-nl-fuel-01": "Fuel transfer",
}
EVIDENCE_FILES = ("summary.json", "attempts.csv", "support-gaps.csv", "certificates.csv")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def evidence_members(evidence: Path) -> dict[str, bytes]:
    members = {}
    for name in EVIDENCE_FILES:
        path = evidence / name
        if path.is_file():
            members[name] = path.read_bytes()
    for path in sorted(evidence.glob("*.svg")):
        members[path.name] = path.read_bytes()
    for path in sorted((evidence / "figures").glob("*.svg")):
        members[path.name] = path.read_bytes()
    require(len(members) >= len(EVIDENCE_FILES), "campaign evidence files are incomplete")
    return members


def _fmt(value: float, digits: int = 6) -> str:
    if value == 0:
        return "0"
    magnitude = abs(value)
    if magnitude >= 1e5 or magnitude < 1e-4:
        return f"{value:.{digits}e}"
    return f"{value:.{digits}g}"


def render_index(summary: dict, figure_names: list[str], support_samples: list[int]) -> bytes:
    costs = summary["costs"]
    gaps = [row for row in summary["support"] if row["role"] == "all"]
    frames = summary["frames"]
    unique_rows = sum(
        row["independent_geometry_rows"] for row in frames["attempts"] if row["repetition"] == 1
    )
    min_margin = min(row["min_margin"] for row in summary["certificates"])
    directions = max(support_samples) if support_samples else 0
    short_rows = sum(1 for value in support_samples if value < directions)
    condition: dict[tuple[str, str, str], dict[str, float]] = {}
    for row in frames["attempts"]:
        key = (row["pair"], row["task"], row["frame"])
        item = condition.setdefault(key, {"max": 0.0, "blowup": 0})
        item["max"] = max(item["max"], row["max_abs_frame_bound"])
        item["blowup"] += int(bool(row["numerical_blowup"]))
    totals = frames["totals"]
    parts = [
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
        "<title>Nonaxis parallelotope frames in closed-loop history control</title><style>",
        "body{background:#272822;color:#f8f8f2;font:16px/1.55 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1.5rem}",
        "a{color:#66d9ef}h1,h2{color:#a6e22e}code{color:#fd971f}img{max-width:100%}",
        "table{border-collapse:collapse;width:100%;margin:1rem 0;font-size:14px}",
        "th,td{border:1px solid #49483e;padding:.35rem .5rem;text-align:left}",
        "th{background:#3e3d32}pre{white-space:pre-wrap;overflow-wrap:anywhere}",
        "</style></head><body>",
        "<h1>Nonaxis parallelotope frames in closed-loop history control</h1>",
        f"<p>Saved A/B campaign at source commit <code>{SOURCE_COMMIT}</code>. "
        "Two paired comparisons run one excluded warmup and five alternating measured repetitions "
        "on the three admitted observed-state tasks. Timings are descriptive process observations; "
        "no speed winner is claimed.</p>",
        "<p><strong>Scope.</strong> Sampled 2D directional support excess is a diagnostic, not a "
        "uniform error bound or inclusion certificate. The frame-coordinate cover and the certified "
        "frame-direction margins are the cover checks. Unsupported and failed routes are retained. "
        "Frame membership counts repeat the same stage/role rows across the five measured attempts: "
        f"{frames['totals'].get('framed_memberships', 0):,} checks cover {unique_rows:,} unique rows. "
        "The frame check verifies orthonormality, ordered frame bounds and the H rows, not "
        "boundedness or cover tightness, so the vacuous Earth-orbit rotated boxes still pass it.</p>",
        "<h2>Coverage and cost</h2><table><thead><tr><th>Pair</th><th>Task</th><th>Frame</th>"
        "<th>Measured</th><th>Complete</th><th>Wall median (s)</th><th>Wall range (s)</th>"
        "<th>CPU median (s)</th><th>Max RSS (KiB)</th><th>Objective median</th></tr></thead><tbody>",
    ]
    for row in costs:
        parts.append(
            "<tr>"
            f"<td>{escape(row['pair'])}</td><td>{escape(TASK_LABELS[row['task']])}</td>"
            f"<td>{escape(row['frame'])}</td><td>{row['measured_attempts']}</td>"
            f"<td>{row['complete_measured']}</td><td>{_fmt(row['wall_median'])}</td>"
            f"<td>{_fmt(row['wall_range'][0])}–{_fmt(row['wall_range'][1])}</td>"
            f"<td>{_fmt(row['worker_cpu_median'])}</td><td>{row['max_rss_kib']}</td>"
            f"<td>{_fmt(row['total_objective_median'])}</td></tr>"
        )
    parts += [
        "</tbody></table>",
        "<h2>Sampled directional support excess</h2>",
        f"<p>Up to {directions} directions per 2D projection at the first query, all stages and "
        f"roles; {short_rows} rows used only 2 directions, including the two largest Earth-orbit "
        "rotated maxima below. Positive values mean the parallelotope projection is looser than the "
        "exported full-state H reference. Rows come from measured repetition 1; the native frame "
        "bounds are deterministic across measured repetitions.</p><table><thead><tr><th>Pair</th><th>Task</th><th>Frame</th><th>Plane</th>"
        "<th>Rows</th><th>Max excess</th><th>Median row max</th><th>Frame checks</th></tr></thead><tbody>",
    ]
    for row in gaps:
        parts.append(
            "<tr>"
            f"<td>{escape(row['pair'])}</td><td>{escape(TASK_LABELS[row['task']])}</td>"
            f"<td>{escape(row['frame'])}</td><td>{escape(row['plane'])}</td>"
            f"<td>{row['membership_rows']}</td><td>{_fmt(row['max_excess'])}</td>"
            f"<td>{_fmt(row['median_of_row_maxima'])}</td>"
            f"<td>{row['frame_checks_passed']}/{row['membership_rows']}</td></tr>"
        )
    parts += [
        "</tbody></table>",
        "<h2>Frame findings</h2>",
        f"<p>Framed memberships checked: {totals.get('frame_checks_passed', 0):,} / "
        f"{totals.get('framed_memberships', 0):,}, covering {unique_rows:,} unique stage/role rows "
        "repeated across five measured attempts. Independent geometry rows passed: "
        f"{totals.get('independent_geometry_passed', 0):,} / "
        f"{totals.get('independent_geometry_rows', 0):,}. Independent receipts accepted: "
        f"{totals.get('independent_accepted', 0)} / {totals.get('attempts', 0)} measured attempts. "
        f"Certified margins span {_fmt(min_margin)} upward; none falls below the 1e-9 noise "
        "threshold, so they are directional necessary conditions rather than an inclusion proof.</p>",
        "<h2>Limitations</h2>",
        "<p>The support-selected rule retained the axis frame, so axis vs selected is a numerical "
        "near-control rather than a second nonaxis treatment. The fixed 45 degree profile is the "
        "only realized nonaxis orientation; on Earth orbit it exported frame bounds above the "
        "1e6 diagnostic threshold in five attempts, and its sampled excess reaches 3.6e21. On "
        "Lotka-Volterra and fuel the rotated bounds stay finite but are much looser: maximum "
        "sampled excess 100 and 40 against about 1e-12 for the axis profile. Those outcomes are "
        "retained in the tables and records above, not treated as successful nonaxis samples. "
        "Sampled excess is a diagnostic, not a uniform error bound, and the timings claim no "
        "speed winner.</p>",
        f"<p>Selected-frame choices: <code>{escape(json.dumps(frames['selected_choices'], sort_keys=True))}</code>. "
        "A selected count of <code>selected axis</code> equal to the selected membership count "
        "means the support-selected controller retained the axis frame; the axis-vs-selected pair "
        "is then a numerical near-control, not a second nonaxis treatment. The fixed 45° profile "
        "is the only realized nonaxis orientation.</p>",
        "<table><thead><tr><th>Pair</th><th>Task</th><th>Frame</th>"
        "<th>Max absolute frame bound</th><th>Blow-up attempts (&gt;1e6)</th></tr></thead><tbody>",
    ]
    for (pair, task, frame), item in sorted(condition.items()):
        parts.append(
            "<tr>"
            f"<td>{escape(pair)}</td><td>{escape(TASK_LABELS[task])}</td><td>{escape(frame)}</td>"
            f"<td>{_fmt(item['max'])}</td><td>{item['blowup']}</td></tr>"
        )
    parts += [
        "</tbody></table>",
        "<h2>Figures</h2>",
        "<p>The <code>*-projections.svg</code> figures are drawn from the saved observed-state "
        "replay of the first affine query: solid lines are frame boxes and dashed lines are sampled "
        "supports of the exported H set. The <code>*-support-excess.svg</code> figures instead plot "
        "maximum sampled directional excess against stage for each task and plane; they contain no "
        "replay or H-set overlay.</p>",
    ]
    for name in figure_names:
        stem = Path(name).stem
        kind = (
            "Projection figure"
            if name.endswith("-projections.svg")
            else "Sampled support-excess figure"
        )
        parts.append(
            f"<figure><img src=\"{escape(name)}\" alt=\"{kind} {escape(stem)}\">"
            f"<figcaption><code>{escape(stem)}</code></figcaption></figure>"
        )
    parts += [
        "<h2>Files</h2><ul>",
        "<li><a href=\"summary.json\">Machine-readable summary</a></li>",
        "<li><a href=\"attempts.csv\">Per-attempt outcomes and resources</a></li>",
        "<li><a href=\"support-gaps.csv\">Per stage/role/plane sampled excess from measured "
        "repetition 1</a></li>",
        "<li><a href=\"certificates.csv\">Certified frame-direction support margins from measured "
        "repetition 1</a></li>",
        "<li><a href=\"bundle.zip\">Offline ZIP of this report</a> · "
        "<a href=\"bundle.zip.sha256\">checksum</a></li>",
        "</ul></body></html>\n",
    ]
    return "".join(parts).encode("utf-8")


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(members):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, members[name])
    return buffer.getvalue()


def build_bundle(evidence: Path, out: Path) -> str:
    members = evidence_members(evidence)
    summary = json.loads(members["summary.json"])
    require(
        summary.get("schema") == "csl.1096.nonaxis-ab-campaign/1"
        and summary.get("source_commit") == SOURCE_COMMIT,
        "campaign summary source differs",
    )
    figure_names = sorted(name for name in members if name.endswith(".svg"))
    support_samples = [
        int(row["samples"])
        for row in csv.DictReader(io.StringIO(members["support-gaps.csv"].decode("utf-8")))
    ]
    members["index.html"] = render_index(summary, figure_names, support_samples)
    digest_material = "\n".join(f"{name} {sha(members[name])}" for name in sorted(members))
    report_id = PREFIX + sha(digest_material.encode())[:16]
    manifest = {
        "schema": SCHEMA,
        "report_id": report_id,
        "source_commit": SOURCE_COMMIT,
        "campaign": {
            "tasks": list(TASKS),
            "controllers": CONTROLLERS,
            "pairs": ["axis-vs-rotated", "axis-vs-selected"],
            "warmup_pairs": 1,
            "measured_repetitions": 5,
        },
        "freeze_sha256": sha((evidence.parent / "1096-campaign-artifacts" / "freeze.json").read_bytes())
        if (evidence.parent / "1096-campaign-artifacts" / "freeze.json").is_file()
        else None,
        "files_sha256": {name: sha(members[name]) for name in sorted(members)},
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    out.mkdir(parents=True, exist_ok=True)
    for name, data in members.items():
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (out / "manifest.json").write_bytes(manifest_bytes)
    archive = _zip_bytes({**members, "manifest.json": manifest_bytes})
    (out / "bundle.zip").write_bytes(archive)
    (out / "bundle.zip.sha256").write_text(f"{sha(archive)}  bundle.zip\n", encoding="utf-8")
    return report_id


def validate(bundle: Path) -> dict:
    bundle = bundle.resolve()
    manifest_bytes = (bundle / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    require(manifest.get("schema") == SCHEMA, "campaign report schema differs")
    report_id = manifest.get("report_id")
    require(isinstance(report_id, str) and report_id.startswith(PREFIX), "campaign report id is unsafe")
    require(manifest.get("source_commit") == SOURCE_COMMIT, "campaign source commit differs")
    require(manifest["campaign"]["tasks"] == list(TASKS), "campaign task list differs")
    require(manifest["campaign"]["controllers"] == CONTROLLERS, "campaign controllers differ")
    listed = manifest["files_sha256"]
    members = evidence_members(bundle)
    members["index.html"] = (bundle / "index.html").read_bytes()
    require(set(listed) == set(members), "campaign report members differ from the manifest")
    for name, digest in listed.items():
        require(sha(members[name]) == digest, f"campaign report member differs: {name}")
    expected_id = PREFIX + sha(
        "\n".join(f"{name} {sha(members[name])}" for name in sorted(members)).encode()
    )[:16]
    require(report_id == expected_id, "campaign report identity differs")
    archive = (bundle / "bundle.zip").read_bytes()
    require(
        (bundle / "bundle.zip.sha256").read_text(encoding="utf-8") == f"{sha(archive)}  bundle.zip\n",
        "campaign archive checksum differs",
    )
    require(
        archive == _zip_bytes({**members, "manifest.json": manifest_bytes}),
        "campaign archive is not the deterministic member archive",
    )
    with ZipFile(BytesIO(archive)) as saved:
        require(set(saved.namelist()) == set(members) | {"manifest.json"}, "archive members differ")
    return manifest


def catalog_entry(bundle: Path) -> dict:
    manifest = validate(bundle)
    return {
        "report_id": manifest["report_id"],
        "source_commit": manifest["source_commit"],
        "schema": manifest["schema"],
        "manifest_sha256": sha((bundle / "manifest.json").read_bytes()),
        "zip_sha256": sha((bundle / "bundle.zip").read_bytes()),
        "builder_sha256": sha(Path(__file__).read_bytes()),
        "stager_sha256": sha(Path(__file__).read_bytes()),
    }


def stage(catalog: Path, site_dir: Path) -> str:
    data = json.loads(catalog.read_text(encoding="utf-8"))
    require(
        data.get("schema") == CATALOG_SCHEMA
        and isinstance(data.get("reports"), list)
        and len(data["reports"]) == 1,
        "campaign publication catalogue differs",
    )
    bundle = catalog.parent / data["reports"][0]["report_id"]
    entry = catalog_entry(bundle)
    require(data["reports"][0] == entry, "campaign catalogue differs from the saved report")
    require(site_dir.is_dir() and not site_dir.is_symlink(), "campaign site root must exist")
    report_id = entry["report_id"]
    files = {
        f"{report_id}/{path.name}": path.read_bytes()
        for path in sorted(bundle.iterdir())
        if path.is_file()
    }
    index_path = site_dir / "index.html"
    require(index_path.is_file() and not index_path.is_symlink(), "site catalogue must exist")
    index = index_path.read_text(encoding="utf-8")
    require(index.count("</ul>") == 1 and report_id not in index, "site catalogue insertion differs")
    link = (
        f'<li><a href="{escape(report_id)}/index.html">Nonaxis parallelotope A/B campaign</a>'
        " — three observed-state tasks, fixed 45° and support-selected frames"
        f' · <a href="{escape(report_id)}/summary.json">raw JSON</a>'
        f' · <a href="{escape(report_id)}/bundle.zip">offline ZIP</a></li>'
    )
    files["index.html"] = index.replace("</ul>", link + "</ul>").encode("utf-8")
    plan = site_additions.prepare(
        site_dir,
        files,
        replace_existing=("index.html",),
        require_absent=(report_id,),
    )
    site_additions.commit(plan)
    return report_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.evidence is not None and args.out is not None and args.catalog is None:
        print(build_bundle(args.evidence, args.out))
    elif args.source is not None and args.catalog is None and args.site is None:
        print(json.dumps({"schema": CATALOG_SCHEMA, "reports": [catalog_entry(args.source)]}, indent=2))
    elif args.catalog is not None and args.site is not None and args.evidence is None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("use --evidence/--out, --source alone, or --catalog/--site")
    return 0


if __name__ == "__main__":
    sys.exit(main())
