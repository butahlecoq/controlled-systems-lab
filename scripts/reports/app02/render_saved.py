"""Validate APP-02 raw source bytes and regenerate its offline HTML bundle."""
from __future__ import annotations

import argparse
import csv
from html import escape
import importlib.util
import io
import json
from pathlib import Path
import zipfile

spec = importlib.util.spec_from_file_location("app02_collect", Path(__file__).with_name("collect.py"))
collect = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(collect)

RENDERED = ("index.html", "polygons.svg", "summary.csv")


def validate(bundle: Path) -> dict:
    collect.require(bundle.is_dir() and not bundle.is_symlink(), "APP-02 source bundle missing")
    for name in collect.SOURCE_FILES:
        path = bundle / name
        collect.require(path.is_file() and not path.is_symlink(), "Missing source file: " + name)
    record = collect.read_json(bundle / "records.json")
    unsigned = {key: value for key, value in record.items() if key != "report_id"}
    collect.require(record.get("schema") == collect.SCHEMA and
                    record.get("source_commit") == collect.SOURCE and
                    record.get("source_tree") == collect.TREE and
                    record.get("report_id") == "app02-box-" + collect.sha(collect.encoded(unsigned))[:16] == bundle.name and
                    record.get("fixtures") == collect.fixtures(),
                    "APP-02 record identity or literal fixture differs")
    host, pre, post, build = (collect.read_json(bundle / name) for name in
                             ("host.json", "prebuild.json", "postrun.json", "build-provenance.json"))
    collect.require(record["environment"] == host and record["build"] == build and
                    record["source_receipts"] == {"prebuild": pre, "postrun": post} and
                    pre["schema"] == post["schema"] == "csl.app02-source-receipt/1" and
                    pre["phase"] == "prebuild" and post["phase"] == "postrun" and
                    pre["commit"] == post["commit"] == host["source_commit"] == collect.SOURCE and
                    pre["tree"] == post["tree"] == host["source_tree"] == collect.TREE and
                    pre["status"] == post["status"] == host["source_status"] == [] and
                    pre["tracked_count"] == post["tracked_count"] and
                    pre["observed_utc"] < post["observed_utc"] <= host["collected_utc"] and
                    post["executable_sha256"] == build["executable_sha256"],
                    "APP-02 saved source/build provenance differs")
    for name, field in (("driver.cpp", "driver_source_sha256"),
                        ("configure.log", "configure_log_sha256"),
                        ("build.log", "build_log_sha256"),
                        ("CMakeCache.raw.txt", "cmake_cache_sha256"),
                        ("CMakeCXXCompiler.raw.cmake", "cmake_compiler_sha256")):
        collect.require(collect.sha((bundle / name).read_bytes()) == build[field],
                        "APP-02 saved build receipt differs: " + name)
    cache = (bundle / "CMakeCache.raw.txt").read_text(encoding="utf-8")
    compiler = (bundle / "CMakeCXXCompiler.raw.cmake").read_text(encoding="utf-8")
    collect.require(all(option + ":BOOL=" + value in cache for option, value in
                        (("BUILD_TESTING", "OFF"), ("CSL_ENABLE_HIGHS", "OFF"),
                         ("CSL_ENABLE_QHULL", "OFF"), ("CSL_BUILD_APP02_REPORT", "ON"))) and
                    "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" in cache and
                    'CMAKE_CXX_COMPILER_VERSION "19.44.' in compiler and
                    "MSBuild version" in (bundle / "build.log").read_text(encoding="utf-8-sig"),
                    "APP-02 saved Release build options differ")
    collect.require((bundle / "smoke.stderr.txt").read_bytes() == b"" and
                    (bundle / "measure.stderr.txt").read_bytes() == b"",
                    "APP-02 saved driver stderr differs")
    collect.require(collect.sha((bundle / "smoke.csv").read_bytes()) ==
                    record["measurement"]["raw_smoke_sha256"] and
                    collect.sha((bundle / "measure.csv").read_bytes()) ==
                    record["measurement"]["raw_measure_sha256"],
                    "APP-02 raw CSV hash differs")
    collect.rows(bundle / "smoke.csv", "smoke")
    trials = collect.rows(bundle / "measure.csv", "measure")
    collect.require(trials == record["measurement"]["trials"] and
                    collect.summary(trials) == record["measurement"]["summary"],
                    "APP-02 saved trials or summary differ")
    return record


def figure(record: dict) -> bytes:
    # These coordinates map the literal (x,y) fixtures; paths are explanatory.
    def xy(point: list[int]) -> str:
        return f"{270 + 90 * point[0]},{270 - 90 * point[1]}"
    diamond = record["fixtures"]["diamond-rotated-outer"]["input_vertices"]
    box = record["fixtures"]["diamond-axis-inner"]["expected_v_vertices"]
    outer = [[-2, -2], [2, -2], [2, 2], [-2, 2]]
    path = lambda points: " ".join(xy(point) for point in points)
    dots = "".join(f'<circle cx="{270 + 90 * x}" cy="{270 - 90 * y}" r="5" fill="#f8f8f2"/>'
                   for x, y in diamond)
    value = f'''<svg xmlns="http://www.w3.org/2000/svg" width="650" height="590" viewBox="0 0 650 590" role="img" aria-label="Diamond input, axis aligned outer box, rotated outer diamond, and inner box in x and y coordinates">
<rect width="650" height="590" fill="#272822"/>
<line x1="50" y1="270" x2="500" y2="270" stroke="#f8f8f2"/>
<line x1="270" y1="50" x2="270" y2="490" stroke="#f8f8f2"/>
<text x="505" y="275" fill="#f8f8f2">x</text><text x="275" y="45" fill="#f8f8f2">y</text>
<polygon points="{path(outer)}" fill="none" stroke="#fd971f" stroke-width="3"/>
<polygon points="{path(diamond)}" fill="none" stroke="#66d9ef" stroke-width="3"/>
<polygon points="{path(box)}" fill="none" stroke="#a6e22e" stroke-width="3"/>
{dots}
<text x="45" y="525" fill="#fd971f">Orange: outer axis box [-2,2] × [-2,2]</text>
<text x="45" y="548" fill="#66d9ef">Blue: input diamond and rotated outer bound |x|+|y| ≤ 2</text>
<text x="45" y="571" fill="#a6e22e">Green: inner axis box [-1,1] × [-1,1]</text></svg>\n'''
    return value.encode()


def summary_csv(record: dict) -> bytes:
    buffer = io.StringIO(newline="")
    fields = ["case", "batches", "calls_per_batch", "successes", "failures",
              "median_batch_ns", "min_batch_ns", "max_batch_ns"]
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(record["measurement"]["summary"])
    return buffer.getvalue().encode()


def html(record: dict) -> bytes:
    rows = []
    for name, fixture in record["fixtures"].items():
        result = next(row for row in record["measurement"]["summary"] if row["case"] == name)
        checked = ("H rows " + str(fixture["expected_h_rows"]) + ", bounds " +
                   str(fixture["expected_h_bounds"]) if fixture["direction"] == "outer" else
                   "V corners " + str(fixture["expected_v_vertices"]))
        rows.append(f'<tr><td>{escape(name)}</td><td>{escape(fixture["direction"])}</td>'
                    f'<td>{escape(checked)}</td><td>{result["median_batch_ns"]:,} ns '
                    f'(range {result["min_batch_ns"]:,}–{result["max_batch_ns"]:,})</td></tr>')
    source = record["source_commit"]
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>APP-02 box and parallelotope approximations</title><style>
body{{background:#272822;color:#f8f8f2;font:16px/1.55 system-ui,sans-serif;max-width:1020px;margin:2rem auto;padding:0 1.5rem}}
a{{color:#66d9ef}}h1,h2{{color:#a6e22e}}code{{color:#fd971f}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #75715e;padding:.5rem;text-align:left;vertical-align:top}}img{{max-width:100%}}small{{color:#b7b7af}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}
</style></head><body><h1>APP-02: box and parallelotope approximations</h1>
<p>Five authored interval and planar examples exercised the registered public <code>CSL::approximation</code> path at source commit <a href="https://github.com/butahlecoq/controlled-systems-lab/tree/{source}"><code>{source}</code></a>. The outer adapters produce H slabs from bounded V vertices. The inner adapters return four supplied corners after checking each against the H input. Exact inclusion checks operate on stored binary64 values. No finite approximation error bound is available.</p>
<h2>Checked numerical results</h2><table><caption>Literal outputs and descriptive 100-call batch durations</caption><thead><tr><th>Case</th><th>Relation</th><th>Checked output</th><th>Median batch duration</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<figure><img src="polygons.svg" alt="Labelled x-y plot of diamond input, outer axis box, rotated outer diamond and inscribed box"><figcaption>The diamond vertices are (0,2), (2,0), (0,-2), (-2,0). The orange axis box encloses it, the blue rotated outer bound coincides with it, and the green box lies inside. These are saved output shapes, drawn as a geometric illustration rather than a trace of algorithm steps.</figcaption></figure>
<h2>Inputs and independent check</h2><p>The 1D interval vertices are −1.5 and 2.25. The complete rows, bounds, orientation and corner declarations for every case, plus SHA-256 input identities, are in <a href="records.json">records.json</a>. The driver checks literal H coefficients and bounds or every literal V corner after every public call; it also checks relation, structural proof basis and the explicit absence of an error bound. The independent policy verifies V-to-H containment or H-to-V containment before returning an enclosure.</p>
<h2>Measurement scope</h2><p>One excluded 100-call warmup per case was followed by seven rotated five-case rounds of 100 calls per case: 3,500 measured calls with zero recorded failures. Each per-call steady-clock interval includes registry selection, fresh provider workspace, adapter execution and independent containment verification. Fixture and registry construction, the post-call literal oracle, CSV output, process launch and HTML rendering are excluded. One worker and one native thread were requested and used. Internal counters are unavailable. These single-adapter observations have no comparator, speedup, source-mapped limiter or scalability conclusion.</p>
<p>Host {escape(record['environment']['host'])}: {escape(record['environment']['processor'])}; {escape(record['environment']['os'])}; MSVC 19.44 x64 Release. HiGHS and Qhull were disabled. <a href="build-provenance.json">Build provenance</a>, <a href="configure.log">configure log</a>, <a href="build.log">build log</a>, <a href="prebuild.json">prebuild receipt</a>, <a href="postrun.json">postrun receipt</a>, raw CMake cache and compiler receipt are saved.</p>
<h2>Reproduce and inspect</h2><p>At the linked source commit, run <code>python -m cmake -S . -B build/app02 -DBUILD_TESTING=OFF -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF -DCSL_BUILD_APP02_REPORT=ON</code>, build target <code>csl_app02_approximation_report</code> in Release, and run it with <code>smoke</code> and <code>measure</code>. The saved <a href="driver.cpp">driver source</a> and <a href="measure.csv">raw measured CSV</a> support independent inspection.</p>
<ul><li><a href="smoke.csv">Smoke CSV</a></li><li><a href="summary.csv">Summary CSV</a></li><li><a href="manifest.json">Exact-byte manifest</a></li><li><a href="bundle.zip">Offline ZIP</a></li></ul>
<small>Report ID {escape(record['report_id'])}. This report is scoped to the declared stored binary64 fixtures; no generic optimality or validated real-arithmetic claim is made.</small></body></html>\n'''
    return page.encode()


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name])
    return buffer.getvalue()


def expected_files(bundle: Path) -> dict[str, bytes]:
    record = validate(bundle)
    files = {name: (bundle / name).read_bytes() for name in collect.SOURCE_FILES}
    files.update({"index.html": html(record), "polygons.svg": figure(record),
                  "summary.csv": summary_csv(record)})
    files["manifest.json"] = collect.encoded({"schema": "csl.app02-report-manifest/1",
        "report_id": record["report_id"],
        "files": {name: collect.sha(files[name]) for name in sorted(files)}})
    files["bundle.zip"] = zip_bytes(files)
    return files


def render(bundle: Path, check: bool = False) -> None:
    expected = expected_files(bundle)
    if check:
        collect.require({path.name for path in bundle.iterdir()} == set(expected),
                        "APP-02 saved file inventory differs")
        for name, value in expected.items():
            collect.require((bundle / name).read_bytes() == value,
                            "APP-02 saved file differs from regeneration: " + name)
    else:
        for name in RENDERED + ("manifest.json", "bundle.zip"):
            (bundle / name).write_bytes(expected[name])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    render(args.bundle, args.check)
