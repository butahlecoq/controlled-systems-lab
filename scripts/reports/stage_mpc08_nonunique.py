"""Package and publish the saved nonunique MPC-08 optimizer-fiber pilot."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import shutil
import statistics
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
REPORT_ID = "mpc08-explicit-nonunique-v1"
SOURCE = ROOT / "benchmarks/reporting/mpc08_explicit"
GENERATED = SOURCE / "generated"
BUNDLE = ROOT / "reports/algorithm-results" / REPORT_ID
ARCHIVE = ROOT / "reports/algorithm-results" / f"{REPORT_ID}.zip"
FILES = (
    "index.html", "README.md", "record.json", "build-provenance.json",
    "manifest.json", "explicit-nonunique-double-integrator.json",
    "explicit-nonunique-queries.csv", "csl-nonunique-observations.jsonl",
    "optimal-fiber.svg", "mpc08_strategy_comparison.cpp",
    "explicit_nonunique_double_integrator.py",
)
DATA = {
    "explicit-nonunique-double-integrator.json": "explicit-nonunique-double-integrator.json",
    "explicit-nonunique-queries.csv": "explicit-nonunique-queries.csv",
    "csl-nonunique-observations.jsonl": "csl-nonunique-observations.jsonl",
    "optimal-fiber.svg": "explicit-nonunique-double-integrator.svg",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_readme() -> str:
    return f"""# MPC-08 nonunique optimizer-fiber pilot

This is a finite, exact two-step double-integrator case for [issue #604](https://github.com/butahlecoq/controlled-systems-lab/issues/604). It complements the separate unique one-step explicit-MPC report. It does not complete #604.

The dynamics are `p_next=p+v`, `v_next=v+u`, with each control in `[-1,1]`. The initial domain is `[-3,3] × [-2,2]`; the terminal objective is the square of terminal velocity. The exact optimal value is zero throughout that domain. The complete optimizer family is

```text
u0 ∈ [-1,1] ∩ [-v0-1, -v0+1]
u1 = -v0-u0
```

The analytic reference separately selects the minimum-norm history `u0=u1=-v0/2`. The figure's left panel shows the full initial rectangle, with fill color encoding that selected first action. The right panel shows the full optimal control fiber at `(p0,v0)=(0,0)` and marks the tie-broken selector.

The saved sample uses 15 initial states and 45 histories (each optimal fiber's endpoints and midpoint). Strategy A candidate relations contain all 270 sampled histories across their 45 warmups and 225 measured calls, but all calls stop with an operation rejection because HiGHS reports a nonzero quadratic coefficient at or below its `1e-12` native-removal threshold. Strategy B contains all sampled histories; 252 calls complete and 18 are noncompleted, and every mathematical outcome remains undetermined. The online two-control QP returns a feasible optimal point with value zero on all 270 calls. These checks do not establish equality between either strategy candidate and the analytic full family. The raw observations preserve every status.

Timing rows are descriptive only. Calls are interleaved with five measured repetitions per query and one warmup per method; no load or limiter profile was captured, so there is no performance-winner claim. See `build-provenance.json` for compiler, dependency, binary, source, input, and result hashes.

Reproduce from the source commit named in `build-provenance.json`:

```sh
python3 benchmarks/reporting/mpc08_explicit/explicit_nonunique_double_integrator.py
cmake -S . -B build/mpc08-nonunique -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=ON -DCSL_BUILD_MPC08_REPORT=ON
cmake --build build/mpc08-nonunique --target csl_mpc08_explicit_compare --parallel 4
build/mpc08-nonunique/csl_mpc08_explicit_compare benchmarks/reporting/mpc08_explicit/generated/explicit-nonunique-queries.csv > benchmarks/reporting/mpc08_explicit/generated/csl-nonunique-observations.jsonl
```

The experiment adds no public API or installed dependency. It uses the existing optional report target and existing HiGHS/Qhull pins. Exact solver outcomes and timing interpretation remain as recorded rather than being repaired or promoted into a full-family or speed claim.
"""


def render(record: dict) -> str:
    statuses = record["outcomes"]
    table = "".join(
        f"<tr><th scope=\"row\">{html.escape(name)}</th><td>{value['measured_calls']}</td>"
        f"<td>{value['median_elapsed_ns'] / 1e6:.3f} ms</td>"
        f"<td>{value['min_elapsed_ns'] / 1e6:.3f}–{value['max_elapsed_ns'] / 1e6:.3f} ms</td>"
        f"<td>{html.escape(value['result'])}</td></tr>"
        for name, value in statuses.items()
    )
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nonunique explicit-MPC optimizer fiber · MPC-08</title>
<style>body{{margin:0;background:#282828;color:#ebdbb2;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1050px;margin:auto;padding:2rem 1rem}}section{{background:#32302f;border:1px solid #504945;border-radius:.6rem;padding:1rem;margin:1rem 0}}a{{color:#8ec07c}}img{{width:100%;height:auto;background:white}}table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;padding:.55rem;border-bottom:1px solid #504945;vertical-align:top}}code{{color:#fabd2f}}.limit{{border-left:3px solid #fabd2f;padding-left:.8rem}}</style></head><body><main>
<p>MPC-08 · exact rational continuation · source {record['source_commit'][:12]}</p><h1>A nonunique optimal control family</h1>
<p>For this two-step double integrator, terminal velocity can be driven to zero from every state in the declared initial domain. The optimizer is a segment for many initial velocities, so one explicit tie-break is only a selector through the full optimal relation.</p>
<figure><img src="optimal-fiber.svg" alt="Initial-state rectangle colored by the minimum-norm selector, beside the full optimal control segment for zero initial velocity."></figure>
<section><h2>Exact result</h2><p><code>p_next=p+v</code>, <code>v_next=v+u</code>, <code>u0,u1∈[-1,1]</code>. Over <code>(p0,v0)∈[-3,3]×[-2,2]</code>, the exact minimum of <code>(v0+u0+u1)²</code> is zero.</p><p><code>u0∈[-1,1]∩[-v0-1,-v0+1]</code> and <code>u1=-v0-u0</code> give the complete analytic control fiber. Minimizing <code>u0²+u1²</code> selects <code>u0=u1=-v0/2</code>.</p><p>The figure's left color field encodes the tie-broken first action over the entire initial domain. At <code>(p0,v0)=(0,0)</code>, the right red segment is the whole optimizer fiber and the gold point is its minimum-norm selector.</p></section>
<section><h2>Current CSL paths</h2><table><thead><tr><th>Path</th><th>Measured calls</th><th>Median</th><th>Range</th><th>Outcome over all 270 calls, including warmups</th></tr></thead><tbody>{table}</tbody></table>
<p>Each path also had one warmup per query. Timing includes path-specific work and the methods return different products.</p>
<p class="limit">The 45 exact histories are sampled checks. Candidate membership does not establish equality or completeness. Strategy A rejects the rank-deficient QP request; Strategy B leaves its mathematical outcome undetermined. The condensed QP returns one feasible optimal point, not the complete family. Failures and noncompleted statuses remain in the raw records. No limiter or pre-run load was captured, so these descriptive timings do not support a performance-winner claim.</p></section>
<section><h2>Reproduce and inspect</h2><ul><li><a href="README.md">Methodology and exact commands</a></li><li><a href="explicit-nonunique-double-integrator.json">Exact reference record</a></li><li><a href="explicit-nonunique-queries.csv">Sampled exact histories</a></li><li><a href="csl-nonunique-observations.jsonl">Raw CSL observations</a></li><li><a href="build-provenance.json">Build and hash provenance</a></li><li><a href="manifest.json">Artifact manifest</a></li><li><a href="../{REPORT_ID}.zip">Offline ZIP</a></li><li><a href="https://github.com/butahlecoq/controlled-systems-lab/commit/{record['source_commit']}">Source commit</a></li><li><a href="https://github.com/butahlecoq/controlled-systems-lab/issues/604">Issue #604</a></li></ul></section>
</main></body></html>\n'''


def package() -> None:
    provenance = read_json(GENERATED / "nonunique-build-provenance.json")
    require(provenance.get("schema") == "csl.mpc08-nonunique-build-provenance/1", "unknown provenance schema")
    ref = read_json(GENERATED / "explicit-nonunique-double-integrator.json")
    observations = [json.loads(line) for line in (GENERATED / "csl-nonunique-observations.jsonl").read_text().splitlines()]
    require(ref["state_sample_count"] == 15 and ref["history_sample_count"] == 45, "exact sample inventory differs")
    require(len(observations) == 810, "observation inventory differs")
    by_method = {}
    for method in sorted({row["strategy"] for row in observations}):
        rows = [row for row in observations if row["strategy"] == method]
        measured = [row for row in rows if not row["warmup"]]
        elapsed = [row["elapsed_ns"] for row in measured]
        if method == "csl.synthesis.reach-back":
            result = "270 candidates contain samples; all 270 stop at a rejected degenerate QP"
        elif method == "csl.synthesis.strategy-b":
            result = "270 candidates contain samples; 252 completed, 18 noncompleted; all outcomes undetermined"
        else:
            result = "270 online solves return feasible optimal points with exact value zero"
        by_method[method] = {
            "calls": len(rows), "measured_calls": len(measured), "result": result,
            "median_elapsed_ns": int(statistics.median(elapsed)),
            "min_elapsed_ns": min(elapsed), "max_elapsed_ns": max(elapsed),
        }
    require(all(row["candidate_contains_exact_reference_history"] is True
                for row in observations if row["strategy"] != "online-condensed-qp"),
            "candidate sample membership changed")
    a = [row for row in observations if row["strategy"] == "csl.synthesis.reach-back"]
    b = [row for row in observations if row["strategy"] == "csl.synthesis.strategy-b"]
    qp = [row for row in observations if row["strategy"] == "online-condensed-qp"]
    require(len(a) == len(b) == len(qp) == 270, "per-method inventory differs")
    require(all(row["termination_code"] == 5 for row in a), "Strategy A rejection inventory differs")
    require(sum(row["termination_code"] != 0 for row in b) == 18, "Strategy B noncompleted count differs")
    require(all(row["action_and_value_match_exact_reference"] is True for row in qp), "online QP check differs")
    require(all(row["outcome_code"] == 4 for row in b), "Strategy B mathematical outcome is no longer undetermined")

    expected_hashes = provenance["artifact_sha256"]
    for name, source_name in DATA.items():
        path = GENERATED / source_name
        require(digest(path) == expected_hashes[source_name], f"capture hash differs for {source_name}")
    source_commit = provenance["source_commit"]
    record = {
        "schema": "csl.mpc08-nonunique-report/1", "report_id": REPORT_ID,
        "source_commit": source_commit,
        "source_url": f"https://github.com/butahlecoq/controlled-systems-lab/tree/{source_commit}/benchmarks/reporting/mpc08_explicit",
        "issue": "https://github.com/butahlecoq/controlled-systems-lab/issues/604",
        "fixture": ref["problem"], "initial_domain_exact": ref["initial_domain_exact"],
        "optimal_value_exact": ref["optimal_value_exact"],
        "complete_optimal_relation": ref["complete_optimal_relation"],
        "tie_break": ref["explicit_tie_break"],
        "state_samples": 15, "history_samples": 45,
        "outcomes": by_method,
        "evidence_limits": "sample membership is not family completeness; Strategy B mathematical outcomes are undetermined; no timing winner; no robust or minimax claim",
    }
    require(not BUNDLE.exists() and not ARCHIVE.exists(), "immutable MPC-08 report destination already exists")
    BUNDLE.mkdir(parents=True)
    for name, source_name in DATA.items():
        shutil.copyfile(GENERATED / source_name, BUNDLE / name)
    shutil.copyfile(GENERATED / "nonunique-build-provenance.json", BUNDLE / "build-provenance.json")
    shutil.copyfile(SOURCE / "mpc08_strategy_comparison.cpp", BUNDLE / "mpc08_strategy_comparison.cpp")
    shutil.copyfile(SOURCE / "explicit_nonunique_double_integrator.py", BUNDLE / "explicit_nonunique_double_integrator.py")
    (BUNDLE / "README.md").write_text(build_readme(), encoding="utf-8")
    write_json(BUNDLE / "record.json", record)
    (BUNDLE / "index.html").write_text(render(record), encoding="utf-8")
    manifest = {"schema": "csl.mpc08-nonunique-manifest/1", "report_id": REPORT_ID,
                "files_sha256": {name: digest(BUNDLE / name) for name in FILES if name != "manifest.json"}}
    write_json(BUNDLE / "manifest.json", manifest)
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in FILES:
            archive.write(BUNDLE / name, arcname=f"{REPORT_ID}/{name}")
    print(json.dumps({"report_id": REPORT_ID, "bundle_sha256": digest(ARCHIVE), "source_commit": source_commit}, sort_keys=True))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def stage(site: Path) -> None:
    sys.path.insert(0, str(ROOT / "scripts/reports"))
    import report_data

    require(BUNDLE.is_dir() and ARCHIVE.is_file(), "packaged report is missing")
    record = read_json(BUNDLE / "record.json")
    manifest = read_json(BUNDLE / "manifest.json")
    require(set(manifest["files_sha256"]) == set(FILES) - {"manifest.json"}, "bundle file inventory differs")
    for name, expected in manifest["files_sha256"].items():
        require(digest(BUNDLE / name) == expected, f"bundle hash differs for {name}")
    report_data.validate_svg((BUNDLE / "optimal-fiber.svg").read_bytes())
    site = site.resolve()
    route = site / REPORT_ID
    require(not route.exists(), "immutable Pages route already exists")
    route.mkdir(parents=True)
    for name in FILES:
        shutil.copyfile(BUNDLE / name, route / name)
    shutil.copyfile(ARCHIVE, site / f"{REPORT_ID}.zip")
    index = site / "index.html"
    html_text = index.read_text(encoding="utf-8")
    link = f'{REPORT_ID}/index.html'
    if link not in html_text:
        require("</ul>" in html_text, "archive index insertion point is missing")
        card = (f'<li><p class="eyebrow">Control synthesis · exact pilot</p><h3><a href="{link}">Nonunique explicit-MPC optimizer fiber</a></h3>'
                f'<p>Two-step exact double-integrator family, tied selector, Strategy A refusal, Strategy B candidate samples, and online QP checks.</p>'
                f'<p><a href="{REPORT_ID}/README.md">Methodology</a> · <a href="{REPORT_ID}/optimal-fiber.svg">Figure</a> · <a href="{REPORT_ID}.zip">Offline ZIP</a> · Source <code>{record["source_commit"]}</code></p></li>')
        index.write_text(html_text.replace("</ul>", card + "</ul>", 1), encoding="utf-8")
    gallery = site / "examples/index.html"
    gallery_html = gallery.read_text(encoding="utf-8")
    marker = '<section id="analytic-illustrations">'
    gallery_card = (f'<article class="saved-figure" id="{REPORT_ID}"><p class="eyebrow">Explicit MPC · exact optimal family</p>'
                    f'<h3>Nonunique double-integrator control fiber</h3><a href="../{REPORT_ID}/index.html">'
                    f'<img src="../{REPORT_ID}/optimal-fiber.svg" alt="The initial-state rectangle is colored by the minimum-norm selector; the full control optimizer fiber is shown beside it."></a>'
                    f'<p>Two-step exact case. Candidate membership samples and solver outcomes do not establish full-family equality.</p>'
                    f'<p><a href="../{REPORT_ID}/index.html">Open the report →</a></p></article>')
    if f'id="{REPORT_ID}"' not in gallery_html:
        require(marker in gallery_html, "examples gallery insertion point is missing")
        gallery.write_text(gallery_html.replace(marker, gallery_card + marker, 1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", action="store_true")
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.package:
        package()
    if args.site:
        stage(args.site)
    if not args.package and not args.site:
        parser.error("choose --package and/or --site")


if __name__ == "__main__":
    main()
