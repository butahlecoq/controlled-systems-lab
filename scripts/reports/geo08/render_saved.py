"""Regenerate the GEO-08 report and offline bundle from saved raw records."""
from __future__ import annotations

import argparse
import csv
from html import escape
import importlib.util
import io
from pathlib import Path
import statistics
import zipfile

spec = importlib.util.spec_from_file_location("geo08_collect", Path(__file__).with_name("collect.py"))
collect = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(collect)

RENDERED = ("index.html", "example-2d.html", "lazy-2d.svg", "summary.csv")


def validate(bundle: Path) -> dict:
    collect.require(bundle.is_dir() and not bundle.is_symlink(), "GEO-08 saved bundle missing")
    for name in collect.SAVED:
        path = bundle / name
        collect.require(path.is_file() and not path.is_symlink(),
                        "Missing GEO-08 source file: " + name)
    record = collect.read_json(bundle / "records.json")
    unsigned = {key: value for key, value in record.items() if key != "report_id"}
    collect.require(record.get("schema") == collect.SCHEMA and
                    record.get("report_id") ==
                    "geo08-lazy-" + collect.sha(collect.encoded(unsigned))[:16] == bundle.name and
                    record.get("fixture") == {**collect.FIXTURE,
                        "input_sha256": collect.sha(collect.encoded(collect.FIXTURE))},
                    "GEO-08 record identity or literal fixture differs")
    host, pre, post, build = (collect.read_json(bundle / name) for name in
                             ("host.json", "prebuild.json", "postrun.json",
                              "build-provenance.json"))
    collect.require(record["environment"] == host and record["build"] == build and
                    record["source_receipts"] == {"prebuild": pre, "postrun": post} and
                    pre["schema"] == post["schema"] == "csl.geo08-source-receipt/1" and
                    pre["phase"] == "prebuild" and post["phase"] == "postrun" and
                    pre["commit"] == post["commit"] == host["source_commit"] ==
                    record["source_commit"] and
                    pre["tree"] == post["tree"] == host["source_tree"] ==
                    record["source_tree"] and
                    pre["status"] == post["status"] == host["source_status"] == [] and
                    pre["tracked_count"] == post["tracked_count"] and
                    pre["observed_utc"] < post["observed_utc"] <= host["collected_utc"] and
                    post["executable_sha256"] == build["executable_sha256"],
                    "GEO-08 saved source/build receipts differ")
    collect.require(build["provenance_sanitization"] ==
                    "Public receipts replace absolute source and build directories with <SOURCE_DIR> and <BUILD_DIR>; unredacted capture remains local",
                    "GEO-08 public provenance policy differs")
    for name, field in (("driver.cpp", "driver_source_sha256"),
                        ("configure.public.log", "configure_log_sha256"),
                        ("build.public.log", "build_log_sha256"),
                        ("CMakeCache.public.txt", "cmake_cache_sha256"),
                        ("CMakeCXXCompiler.public.cmake", "cmake_compiler_sha256")):
        collect.require(collect.sha((bundle / name).read_bytes()) == build[field],
                        "GEO-08 build receipt differs: " + name)
    cache = (bundle / "CMakeCache.public.txt").read_text(encoding="utf-8")
    collect.require("<SOURCE_DIR>" in cache and "<BUILD_DIR>" in cache and
                    all(".worktrees" not in (bundle / name).read_text(encoding="utf-8")
                        for name in ("configure.public.log", "build.public.log",
                                     "CMakeCache.public.txt", "CMakeCXXCompiler.public.cmake")),
                    "GEO-08 local checkout path leaked into public receipt")
    collect.require(all(option + ":BOOL=" + value in cache for option, value in
                        (("BUILD_TESTING", "OFF"), ("CSL_ENABLE_HIGHS", "OFF"),
                         ("CSL_ENABLE_QHULL", "OFF"), ("CSL_BUILD_GEO08_REPORT", "ON"))) and
                    "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" in cache,
                    "GEO-08 saved Release settings differ")
    collect.require((bundle / "smoke.stderr.txt").read_bytes() == b"" and
                    (bundle / "measure.stderr.txt").read_bytes() == b"",
                    "GEO-08 saved driver stderr differs")
    collect.require(collect.sha((bundle / "smoke.csv").read_bytes()) ==
                    record["measurement"]["raw_smoke_sha256"] and
                    collect.sha((bundle / "measure.csv").read_bytes()) ==
                    record["measurement"]["raw_measure_sha256"],
                    "GEO-08 raw CSV hash differs")
    collect.rows(bundle / "smoke.csv", "smoke")
    measured = collect.rows(bundle / "measure.csv", "measure")
    trials = [int(row["elapsed_ns"]) for row in measured if row["phase"] == "trial"]
    summary = {"batches": 7, "calls_per_batch": 100, "successes": 700, "failures": 0,
               "median_batch_ns": statistics.median(trials),
               "min_batch_ns": min(trials), "max_batch_ns": max(trials)}
    collect.require(measured == record["measurement"]["trials"] and
                    summary == record["measurement"]["summary"] and
                    record["measurement"]["native_threads_requested"] ==
                    record["measurement"]["native_threads_actual"] ==
                    "not applicable: no native solver backend" and
                    record["measurement"]["random_seed"] ==
                    "not applicable: deterministic fixture and driver" and
                    record["measurement"]["result_comparison"] ==
                    "literal exact equality for finite binary64 support, evidence, growth and all 16 returned V rows; no numerical tolerance",
                    "GEO-08 saved trials or summary differ")
    return record


def figure(record: dict) -> bytes:
    fixture = record["fixture"]
    source = fixture["vertices"]
    mapped = [[1 + 2 * x, -1 + y] for x, y in source]
    summed = [[x + u, y + v] for x, y in mapped for u, v in source]
    def xy(point: list) -> str:
        return f"{90 + 125 * point[0]},{380 - 125 * point[1]}"
    def outline(points: list, color: str) -> str:
        corners = [points[index] for index in (0, 1, 3, 2)]
        return f'<polygon points="{" ".join(xy(point) for point in corners)}" fill="none" stroke="{color}" stroke-width="3"/>'
    image = f'''<svg xmlns="http://www.w3.org/2000/svg" width="760" height="570" viewBox="0 0 760 570" role="img" aria-label="Planar source square, affine image and independent Minkowski sum with x and y axes">
<rect width="760" height="570" fill="#272822"/>
<line x1="35" y1="380" x2="700" y2="380" stroke="#f8f8f2"/><line x1="90" y1="80" x2="90" y2="520" stroke="#f8f8f2"/>
<text x="705" y="385" fill="#f8f8f2">x</text><text x="96" y="80" fill="#f8f8f2">y</text>
{outline(source, '#66d9ef')}{outline(mapped, '#fd971f')}
<polygon points="{' '.join(xy(point) for point in ([1, -1], [4, -1], [4, 1], [1, 1]))}" fill="none" stroke="#a6e22e" stroke-width="3"/>
<circle cx="590" cy="255" r="6" fill="#f92672"/><text x="365" y="235" fill="#f92672">(4,1): support 5 for (1,1)</text>
<text x="35" y="495" fill="#66d9ef">Blue: source [0,1]²</text><text x="270" y="495" fill="#fd971f">Orange: affine image [1,3] × [-1,0]</text>
<text x="35" y="525" fill="#a6e22e">Green: independent sum [1,4] × [-1,1]</text>
<text x="35" y="550" fill="#a6e22e">16 stored V rows, including duplicate points</text>
</svg>\n'''
    collect.require(len(summed) == 16 and [4, 1] in summed,
                    "Saved GEO-08 fixture does not support the plotted answer")
    return image.encode()


def summary_csv(record: dict) -> bytes:
    output = io.StringIO(newline="")
    fields = list(record["measurement"]["summary"])
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerow(record["measurement"]["summary"])
    return output.getvalue().encode()


def html(record: dict, example: bool = False) -> bytes:
    title = "GEO-08 planar lazy geometry example" if example else "GEO-08 lazy geometry numerical report"
    summary = record["measurement"]["summary"]
    source = escape(record["source_commit"])
    introduction = ("This standalone example uses the saved measured fixture." if example else
                    "This versioned report records one checked native binary64 public route.")
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>
body{{background:#272822;color:#f8f8f2;font:16px/1.55 system-ui,sans-serif;max-width:850px;margin:2rem auto;padding:0 1.5rem}}a{{color:#66d9ef}}img{{max-width:100%}}code{{color:#fd971f}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}table{{border-collapse:collapse}}th,td{{border:1px solid #75715e;padding:.4rem}}</style></head><body><h1>{title}</h1>
<p>{introduction} Frozen <a href="https://github.com/butahlecoq/controlled-systems-lab/tree/{source}">source commit <code>{source}</code></a>; fixture hash <code>{record['fixture']['input_sha256']}</code>. The plot labels coordinates x and y; the public source handle has no coordinate-name metadata because a general affine map drops those names.</p>
<h2>Complete 2D input and request</h2><p>Native V source ID <code>geo08-square</code>: vertices (0,0), (1,0), (0,1), (1,1); no rays. Apply affine map [[2,0],[0,1]] and offset (1,-1), then independently add the original square. Query support in direction (1,1) through <code>csl.geometry.lazy-support</code>, and explicitly materialize native V with vertex cap 16 and ray cap 0. All requests use numerical assurance and an equivalent mathematical relation.</p>
<figure><img src="lazy-2d.svg" alt="Labelled x-y plot of square, affine image, Minkowski sum and support corner"><figcaption>This drawing illustrates saved input and output shapes, not intermediate execution steps. The 16 returned V rows include duplicate points.</figcaption></figure>
<h2>Check by hand</h2><p>The affine image is [1,3] × [-1,0], so the independent sum is [1,4] × [-1,1]. Its support in direction (1,1) is 4+1=5 at (4,1). The driver checks that answer, evidence scope, growth 8→16, and each of the 16 returned rows on every call.</p>
<h2>Observed work</h2><table><caption>Descriptive checked 100-call batch durations</caption><thead><tr><th>Batches</th><th>Measured calls</th><th>Median</th><th>Range</th><th>Failures</th></tr></thead><tbody><tr><td>7</td><td>700</td><td>{summary['median_batch_ns']} ns</td><td>{summary['min_batch_ns']}–{summary['max_batch_ns']} ns</td><td>0</td></tr></tbody></table>
<p>One excluded 100-call warmup preceded seven measured 100-call batches. Each steady-clock interval includes expression construction, support, explicit materialization, fresh workspaces and literal result checks. Source and selected provider registration, CSV writing, process launch and rendering are excluded. One worker ran the deterministic fixture; native solver threads and random seed are not applicable. The driver compares the finite binary64 support, evidence, growth and all 16 V rows with literal exact equality and no tolerance. Internal counters are unavailable. These single-route observations establish no competitor, speedup, source-mapped limiter or scalability conclusion.</p>
<p>Host {escape(record['environment']['host'])}: {escape(record['environment']['processor'])}; {escape(record['environment']['os'])}. The <a href="build-provenance.json">build receipt</a>, <a href="configure.public.log">configure log</a>, <a href="build.public.log">build log</a>, CMake cache and compiler receipt describe the Release configuration. Public receipts replace local source and build directory paths with placeholders. HiGHS and Qhull were disabled.</p>
<h2>Evidence and reproduction</h2><p>Mathematical equivalence and these stored binary64 outputs do not establish validated rounding or an inclusion enclosure. A finite direction sample is not a complete set. The <a href="records.json">raw record</a> contains complete inputs, source and executable hashes, all trial rows and timing scope.</p>
<pre>cmake -S . -B build/geo08-example -DBUILD_TESTING=OFF -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF -DCSL_BUILD_GEO08_REPORT=ON
cmake --build build/geo08-example --config Release --target csl_geo08_lazy_report
build/geo08-example/Release/csl_geo08_lazy_report.exe smoke</pre>
<ul><li><a href="driver.cpp">Saved driver</a></li><li><a href="measure.csv">Raw measured CSV</a></li><li><a href="summary.csv">Summary CSV</a></li><li><a href="manifest.json">Exact-byte manifest</a></li><li><a href="bundle.zip">Offline ZIP</a></li>{'' if example else '<li><a href="example-2d.html">Standalone 2D example</a></li>'}</ul>
<small>Report ID {escape(record['report_id'])}; only the declared planar fixture is covered.</small></body></html>\n'''
    return page.encode()


def zip_bytes(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name])
    return output.getvalue()


def expected_files(bundle: Path) -> dict[str, bytes]:
    record = validate(bundle)
    files = {name: (bundle / name).read_bytes() for name in collect.SAVED}
    files.update({"index.html": html(record), "example-2d.html": html(record, True),
                  "lazy-2d.svg": figure(record), "summary.csv": summary_csv(record)})
    files["manifest.json"] = collect.encoded({"schema": "csl.geo08-report-manifest/1",
        "report_id": record["report_id"],
        "files": {name: collect.sha(files[name]) for name in sorted(files)}})
    files["bundle.zip"] = zip_bytes(files)
    return files


def render(bundle: Path, check: bool = False) -> None:
    expected = expected_files(bundle)
    if check:
        collect.require({path.name for path in bundle.iterdir()} == set(expected),
                        "GEO-08 saved file inventory differs")
        for name, value in expected.items():
            collect.require((bundle / name).read_bytes() == value,
                            "GEO-08 saved file differs from regeneration: " + name)
    else:
        for name in RENDERED + ("manifest.json", "bundle.zip"):
            (bundle / name).write_bytes(expected[name])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    render(args.bundle, args.check)
