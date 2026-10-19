"""Render and verify APP-04 HTML, 2D SVG, manifest and offline ZIP from saved bytes."""
from __future__ import annotations

import argparse
import csv
from html import escape
import importlib.util
import io
import json
from pathlib import Path
import zipfile

spec = importlib.util.spec_from_file_location("app04_collect", Path(__file__).with_name("collect.py"))
collect = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(collect)

RENDERED = ("index.html", "example-2d.html", "ellipsoid-2d.svg", "summary.csv")


def validate(bundle: Path) -> dict:
    collect.require(bundle.is_dir() and not bundle.is_symlink(), "APP-04 bundle missing")
    for name in collect.SOURCE_FILES:
        path = bundle / name
        collect.require(path.is_file() and not path.is_symlink(),
                        "Missing APP-04 source file: " + name)
    record = collect.read_json(bundle / "records.json")
    unsigned = {key: value for key, value in record.items() if key != "report_id"}
    collect.require(record.get("schema") == collect.SCHEMA and
                    record.get("report_id") ==
                    "app04-ellipsoid-" + collect.sha(collect.encoded(unsigned))[:16] == bundle.name and
                    record.get("fixtures") == collect.fixtures(),
                    "APP-04 record identity or literal fixtures differ")
    host, pre, post, build = (collect.read_json(bundle / name) for name in
                             ("host.json", "prebuild.json", "postrun.json",
                              "build-provenance.json"))
    collect.require(record["environment"] == host and record["build"] == build and
                    record["source_receipts"] == {"prebuild": pre, "postrun": post} and
                    pre["schema"] == post["schema"] == "csl.app04-source-receipt/1" and
                    pre["phase"] == "prebuild" and post["phase"] == "postrun" and
                    pre["commit"] == post["commit"] == host["source_commit"] ==
                    record["source_commit"] and
                    pre["tree"] == post["tree"] == host["source_tree"] ==
                    record["source_tree"] and
                    pre["status"] == post["status"] == host["source_status"] == [] and
                    pre["tracked_count"] == post["tracked_count"] and
                    pre["observed_utc"] < post["observed_utc"] <= host["collected_utc"] and
                    post["executable_sha256"] == build["executable_sha256"],
                    "APP-04 saved source/build receipts differ")
    for name, field in (("driver.cpp", "driver_source_sha256"),
                        ("configure.log", "configure_log_sha256"),
                        ("build.log", "build_log_sha256"),
                        ("CMakeCache.raw.txt", "cmake_cache_sha256"),
                        ("CMakeCXXCompiler.raw.cmake", "cmake_compiler_sha256")):
        collect.require(collect.sha((bundle / name).read_bytes()) == build[field],
                        "APP-04 build receipt differs: " + name)
    cache = (bundle / "CMakeCache.raw.txt").read_text(encoding="utf-8")
    collect.require(all(option + ":BOOL=" + value in cache for option, value in
                        (("BUILD_TESTING", "OFF"), ("CSL_ENABLE_HIGHS", "OFF"),
                         ("CSL_ENABLE_QHULL", "OFF"), ("CSL_BUILD_APP04_REPORT", "ON"))) and
                    "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" in cache,
                    "APP-04 saved Release settings differ")
    collect.require((bundle / "smoke.stderr.txt").read_bytes() == b"" and
                    (bundle / "measure.stderr.txt").read_bytes() == b"",
                    "APP-04 saved driver stderr differs")
    collect.require(collect.sha((bundle / "smoke.csv").read_bytes()) ==
                    record["measurement"]["raw_smoke_sha256"] and
                    collect.sha((bundle / "measure.csv").read_bytes()) ==
                    record["measurement"]["raw_measure_sha256"],
                    "APP-04 raw CSV hash differs")
    collect.rows(bundle / "smoke.csv", "smoke")
    trials = collect.rows(bundle / "measure.csv", "measure")
    collect.require(trials == record["measurement"]["trials"] and
                    collect.summary(trials) == record["measurement"]["summary"],
                    "APP-04 saved rows or summary differ")
    return record


def figure(record: dict) -> bytes:
    trials = record["measurement"]["trials"]
    axis = next(row for row in trials if row["case"] == "square-axis")
    diagonal = next(row for row in trials if row["case"] == "square-diagonal")
    axis_r = float(axis["radius_x"])
    diagonal_r = float(diagonal["radius_x"]) / 2**0.5
    # The diagonal orientation [[1,1],[1,-1]] maps equal radii to a circle
    # with physical radius r/sqrt(2).
    square = " ".join(f"{500+100*x},{250-100*y}" for x, y in
                      record["fixtures"]["square-axis"]["input_vertices"])
    points = "".join(f'<circle cx="{500+100*x}" cy="{250-100*y}" r="5" fill="#f6c177"/>'
                     for x, y in record["fixtures"]["square-axis"]["input_vertices"])
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 500" role="img" aria-labelledby="title desc">
<title id="title">Two directional ellipsoids enclosing a square</title>
<desc id="desc">The square from minus one to one on both axes sits inside an axis circle of radius square root of two and a diagonal-orientation circle of radius two.</desc>
<rect width="840" height="500" fill="#16161e"/>
<path d="M 280 250 H 765 M 500 35 V 465" stroke="#6e6a86" stroke-width="1"/>
<circle cx="500" cy="250" r="{diagonal_r*100:.8f}" fill="none" stroke="#9ccfd8" stroke-width="3" stroke-dasharray="8 5"/>
<circle cx="500" cy="250" r="{axis_r*100:.8f}" fill="none" stroke="#c4a7e7" stroke-width="3"/>
<polygon points="{square}" fill="#f6c177" fill-opacity=".18" stroke="#f6c177" stroke-width="3"/>
{points}
<g fill="#e0def4" font-family="sans-serif" font-size="15"><text x="770" y="255">x</text><text x="505" y="30">y</text>
<text x="20" y="30">APP-04: stored binary64 square and outer ellipsoids</text>
<text x="25" y="390" fill="#f6c177">Square vertices (±1, ±1)</text>
<text x="25" y="420" fill="#c4a7e7">Axis orientation: radius √2</text>
<text x="25" y="450" fill="#9ccfd8">Diagonal orientation: radius 2</text></g>
</svg>'''
    return (svg + "\n").encode()


def summary_csv(record: dict) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=["case", "batches", "calls_per_batch",
        "successes", "failures", "median_batch_ns", "min_batch_ns", "max_batch_ns"],
        lineterminator="\n")
    writer.writeheader()
    writer.writerows(record["measurement"]["summary"])
    return output.getvalue().encode()


def page(record: dict, example: bool) -> bytes:
    report_id = escape(record["report_id"])
    source = escape(record["source_commit"])
    host = escape(record["environment"]["host"])
    os_name = escape(record["environment"]["os"])
    summary_rows = "".join(
        f'<tr><th scope="row">{escape(row["case"])}</th><td>{row["successes"]}</td>'
        f'<td>{row["median_batch_ns"]}</td><td>{row["min_batch_ns"]}–{row["max_batch_ns"]}</td></tr>'
        for row in record["measurement"]["summary"])
    fixture_rows = "".join(
        f'<tr><th scope="row">{escape(name)} <code>{escape(item["method"])}</code></th><td><code>{escape(str(item["input_vertices"]))}</code></td>'
        f'<td><code>{escape(str(item["orientation_rows"]))}</code></td>'
        f'<td><code>{escape(str(item["projected_bounds"]))}</code></td></tr>'
        for name, item in record["fixtures"].items())
    intro = ("A minimal two-dimensional example derived from the saved square fixtures. "
             "Both ellipses are outer; the horizontal segment retains a zero second radius."
             if example else
             "Saved single-adapter observations of the public APP-04 approximation route.")
    links = ('<a href="index.html">Full report</a> · <a href="example-2d.html">2D example</a> · '
             '<a href="ellipsoid-2d.svg">SVG</a> · <a href="records.json">Saved records</a> · '
             '<a href="measure.csv">Raw measured calls</a> · <a href="smoke.csv">Raw smoke</a> · '
             '<a href="summary.csv">Summary CSV</a> · <a href="manifest.json">Manifest</a> · '
             f'<a href="../{report_id}.zip">Offline ZIP</a>')
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>APP-04 directional ellipsoidal approximation</title><style>
:root{{color-scheme:dark}}body{{max-width:980px;margin:auto;padding:2rem 1rem;background:#16161e;color:#e0def4;font:16px/1.5 system-ui}}
a{{color:#9ccfd8}}h1,h2{{color:#c4a7e7}}nav{{padding:1rem 0;border-block:1px solid #6e6a86}}table{{width:100%;border-collapse:collapse;margin:1rem 0}}th,td{{text-align:left;border-bottom:1px solid #6e6a86;padding:.45rem;vertical-align:top}}code,pre{{color:#f6c177;overflow-wrap:anywhere}}figure{{margin:1rem 0}}img{{width:100%;height:auto}}.note{{border-left:4px solid #f6c177;padding-left:1rem}}footer{{font-size:.9rem}}
</style></head><body><header><p>Controlled Systems Lab · APP-04</p><h1>Directional ellipsoidal approximation</h1>
<p>{intro}</p><nav>{links}</nav></header><main>
<section><h2>Complete literal inputs</h2><table><thead><tr><th>Case</th><th>V vertices (x,y)</th><th>Orientation B</th><th>Projected bounds m</th></tr></thead><tbody>{fixture_rows}</tbody></table>
<p>All centers are (0,0), labels are x and y, the requested relation is outer, assurance is numerical, and the size budget is one ellipsoid. The native adapter computes finite radii satisfying <code>r_i² ≥ 2m_i²</code>.</p></section>
<section><h2>Independently checkable inclusion</h2><p>For the axis square, m=(1,1), r=(√2,√2) rounded upward. Each vertex has two squared normalized terms of at most 1/2, so every vertex lies in the ellipsoid. Convexity encloses the whole square. The diagonal orientation yields m=(2,2) and a circle of radius 2 in physical coordinates. The segment has m=(1,0); its second projected coordinate is an equality and its shape is rank one.</p>
<figure><img src="ellipsoid-2d.svg" alt="Square vertices and two enclosing circles on labelled x and y axes"><figcaption>Saved square fixtures, plotted in x and y coordinates. Curves illustrate the literal stored result; the independent vertex check is performed by the driver and policy.</figcaption></figure></section>
<section><h2>Recorded public-call batches</h2><table><thead><tr><th>Case</th><th>Verified calls</th><th>Median batch (ns)</th><th>Range (ns)</th></tr></thead><tbody>{summary_rows}</tbody></table>
<p>Each batch sums 100 separately timed public <code>run_registered</code> calls. One 100-call warmup per case was excluded, followed by seven rotated batches per case. The timed interval includes registry selection, new workspace, construction and independent policy admission. Fixture setup, literal post-call checks, serialization and rendering are outside it. There were zero observed failures. These single-adapter durations are descriptive; no competitor or speedup is claimed.</p></section>
<section><h2>Provenance and limits</h2><p>Source commit <a href="https://github.com/butahlecoq/controlled-systems-lab/tree/{source}"><code>{source}</code></a>; host <code>{host}</code>; OS <code>{os_name}</code>; Release x64 with HiGHS and Qhull disabled. The saved <a href="build-provenance.json">build receipt</a>, <a href="CMakeCache.raw.txt">CMake cache</a>, <a href="driver.cpp">driver source</a> and raw records bind this report to that build.</p>
<p class="note">Claims concern exact sets defined by stored binary64 coefficients. There is no validated rounding guarantee for earlier model computations, finite approximation error bound, minimum-volume result, MATLAB or Ellipsoidal Toolbox comparison, source-mapped limiter, or scalability claim.</p>
<p>Reproduce from a clean checkout at the source commit with <code>python scripts/reports/app04/capture.py --source &lt;checkout&gt; --capture &lt;new-directory&gt; --commit {source} --cmake &lt;cmake&gt;</code>, then run <code>collect.py</code> and <code>render_saved.py</code> on the saved capture. The ZIP contains the report and raw data for offline reading.</p></section></main>
<footer><p>Immutable report ID: <code>{report_id}</code></p></footer></body></html>'''
    # The shared offline HTML validator has a deliberately small element set.
    for tag in ("header", "main", "section", "footer", "nav"):
        html = html.replace("<" + tag + ">", "<div>").replace("</" + tag + ">", "</div>")
    return (html + "\n").encode()


def files(record: dict) -> dict[str, bytes]:
    return {"index.html": page(record, False),
            "example-2d.html": page(record, True),
            "ellipsoid-2d.svg": figure(record),
            "summary.csv": summary_csv(record)}


def archive_bytes(bundle: Path, inventory: list[str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in inventory:
            info = zipfile.ZipInfo(bundle.name + "/" + name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (bundle / name).read_bytes())
    return output.getvalue()


def render(bundle: Path, check: bool = False) -> Path:
    record = validate(bundle)
    generated = files(record)
    for name, data in generated.items():
        path = bundle / name
        if check:
            collect.require(path.read_bytes() == data, "Changed rendered APP-04 file: " + name)
        else:
            collect.require(not path.exists(), "APP-04 rendered file already exists: " + name)
            path.write_bytes(data)
    inventory = sorted((*collect.SOURCE_FILES, *RENDERED))
    manifest = {"schema": "csl.app04-manifest/1", "report_id": bundle.name,
                "files": {name: collect.sha((bundle / name).read_bytes()) for name in inventory}}
    manifest_bytes = collect.encoded(manifest)
    manifest_path = bundle / "manifest.json"
    if check:
        collect.require(manifest_path.read_bytes() == manifest_bytes,
                        "APP-04 manifest differs")
    else:
        collect.require(not manifest_path.exists(), "APP-04 manifest already exists")
        manifest_path.write_bytes(manifest_bytes)
    zip_path = bundle.parent / (bundle.name + ".zip")
    zip_data = archive_bytes(bundle, [*inventory, "manifest.json"])
    if check:
        collect.require(zip_path.read_bytes() == zip_data, "APP-04 ZIP differs")
    else:
        collect.require(not zip_path.exists(), "APP-04 ZIP already exists")
        zip_path.write_bytes(zip_data)
    collect.require(set(path.name for path in bundle.iterdir()) ==
                    set((*inventory, "manifest.json")), "APP-04 bundle inventory differs")
    return zip_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(render(args.bundle.resolve(strict=True), args.check))
