"""Regenerate and verify the APP-03 HTML report from saved raw records."""
from __future__ import annotations

import argparse
import csv
from html import escape
import importlib.util
import io
from pathlib import Path
import zipfile

spec = importlib.util.spec_from_file_location("app03_collect", Path(__file__).with_name("collect.py"))
collect = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(collect)

RENDERED = ("index.html", "example-2d.html", "zonotope-2d.svg", "summary.csv")


def validate(bundle: Path) -> dict:
    collect.require(bundle.is_dir() and not bundle.is_symlink(),
                    "APP-03 saved bundle missing")
    for name in collect.SOURCE_FILES:
        path = bundle / name
        collect.require(path.is_file() and not path.is_symlink(),
                        "Missing APP-03 source file: " + name)
    record = collect.read_json(bundle / "records.json")
    unsigned = {key: value for key, value in record.items() if key != "report_id"}
    collect.require(record.get("schema") == collect.SCHEMA and
                    record.get("report_id") ==
                    "app03-zonotope-" + collect.sha(collect.encoded(unsigned))[:16] == bundle.name and
                    record.get("fixtures") == collect.fixtures(),
                    "APP-03 record identity or literal fixtures differ")
    host, pre, post, build = (collect.read_json(bundle / name) for name in
                             ("host.json", "prebuild.json", "postrun.json",
                              "build-provenance.json"))
    collect.require(record["environment"] == host and record["build"] == build and
                    record["source_receipts"] == {"prebuild": pre, "postrun": post} and
                    pre["schema"] == post["schema"] == "csl.app03-source-receipt/1" and
                    pre["phase"] == "prebuild" and post["phase"] == "postrun" and
                    pre["commit"] == post["commit"] == host["source_commit"] ==
                    record["source_commit"] and
                    pre["tree"] == post["tree"] == host["source_tree"] ==
                    record["source_tree"] and
                    pre["status"] == post["status"] == host["source_status"] == [] and
                    pre["tracked_count"] == post["tracked_count"] and
                    pre["observed_utc"] < post["observed_utc"] <= host["collected_utc"] and
                    post["executable_sha256"] == build["executable_sha256"],
                    "APP-03 saved source/build receipts differ")
    for name, field in (("driver.cpp", "driver_source_sha256"),
                        ("configure.log", "configure_log_sha256"),
                        ("build.log", "build_log_sha256"),
                        ("CMakeCache.raw.txt", "cmake_cache_sha256"),
                        ("CMakeCXXCompiler.raw.cmake", "cmake_compiler_sha256")):
        collect.require(collect.sha((bundle / name).read_bytes()) == build[field],
                        "APP-03 build receipt differs: " + name)
    cache = (bundle / "CMakeCache.raw.txt").read_text(encoding="utf-8")
    collect.require(all(option + ":BOOL=" + value in cache for option, value in
                        (("BUILD_TESTING", "OFF"), ("CSL_ENABLE_HIGHS", "OFF"),
                         ("CSL_ENABLE_QHULL", "OFF"), ("CSL_BUILD_APP03_REPORT", "ON"))) and
                    "CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022" in cache,
                    "APP-03 saved Release settings differ")
    collect.require((bundle / "smoke.stderr.txt").read_bytes() == b"" and
                    (bundle / "measure.stderr.txt").read_bytes() == b"",
                    "APP-03 saved driver stderr differs")
    collect.require(collect.sha((bundle / "smoke.csv").read_bytes()) ==
                    record["measurement"]["raw_smoke_sha256"] and
                    collect.sha((bundle / "measure.csv").read_bytes()) ==
                    record["measurement"]["raw_measure_sha256"],
                    "APP-03 raw CSV hash differs")
    collect.rows(bundle / "smoke.csv", "smoke")
    trials = collect.rows(bundle / "measure.csv", "measure")
    collect.require(trials == record["measurement"]["trials"] and
                    collect.summary(trials) == record["measurement"]["summary"],
                    "APP-03 saved trials or summary differ")
    return record


def figure(record: dict) -> bytes:
    fixture = record["fixtures"]["diamond-axis-cover"]
    source = fixture["input_generators"]
    points = sorted({(sum(source[0][column] * (1 if mask & (1 << column) else -1)
                          for column in range(3)),
                      sum(source[1][column] * (1 if mask & (1 << column) else -1)
                          for column in range(3))) for mask in range(8)})
    def cross(a: tuple, b: tuple, c: tuple) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    lower: list[tuple] = []
    upper: list[tuple] = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    hull = lower[:-1] + upper[:-1]
    radii = [fixture["expected_generators"][0][0],
             fixture["expected_generators"][1][1]]
    outer = [(-radii[0], -radii[1]), (radii[0], -radii[1]),
             (radii[0], radii[1]), (-radii[0], radii[1])]
    def xy(point: tuple) -> str:
        return f"{280 + 125 * point[0]},{250 - 125 * point[1]}"
    def polygon(values: list[tuple]) -> str:
        return " ".join(xy(point) for point in values)
    dots = "".join(f'<circle cx="{280 + 125*x}" cy="{250 - 125*y}" r="4" fill="#f8f8f2"/>'
                   for x, y in points)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="610" viewBox="0 0 640 610" role="img" aria-label="Input planar zonotope and its independently admitted outer axis cover in x and y coordinates">
<rect width="640" height="610" fill="#272822"/>
<line x1="40" y1="250" x2="520" y2="250" stroke="#f8f8f2"/>
<line x1="280" y1="25" x2="280" y2="480" stroke="#f8f8f2"/>
<text x="525" y="255" fill="#f8f8f2">x</text><text x="286" y="25" fill="#f8f8f2">y</text>
<polygon points="{polygon(outer)}" fill="none" stroke="#fd971f" stroke-width="3"/>
<polygon points="{polygon(hull)}" fill="none" stroke="#66d9ef" stroke-width="3"/>
{dots}
<text x="35" y="520" fill="#66d9ef">Blue: input generators (1,0), (0,1), (0.5,0.5)</text>
<text x="35" y="547" fill="#fd971f">Orange: outer axis cover [-1.5,1.5] × [-1.5,1.5]</text>
<text x="35" y="574" fill="#f8f8f2">White: all eight signed input generator sums</text></svg>\n'''.encode()


def summary_csv(record: dict) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=["case", "batches", "calls_per_batch",
        "successes", "failures", "median_batch_ns", "min_batch_ns", "max_batch_ns"],
        lineterminator="\n")
    writer.writeheader()
    writer.writerows(record["measurement"]["summary"])
    return output.getvalue().encode()


def html(record: dict) -> bytes:
    rows = []
    for name, fixture in record["fixtures"].items():
        result = next(row for row in record["measurement"]["summary"]
                      if row["case"] == name)
        rows.append(f'<tr><td>{escape(name)}</td><td>{escape(fixture["relation"])}</td>'
                    f'<td>{escape(str(fixture["expected_generators"]))}</td>'
                    f'<td>{result["median_batch_ns"]:,} ns '
                    f'(range {result["min_batch_ns"]:,}–{result["max_batch_ns"]:,})</td></tr>')
    source = record["source_commit"]
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>APP-03 zonotope reductions</title><style>
body{{background:#272822;color:#f8f8f2;font:16px/1.55 system-ui,sans-serif;max-width:1020px;margin:2rem auto;padding:0 1.5rem}}a{{color:#66d9ef}}h1,h2{{color:#a6e22e}}code{{color:#fd971f}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #75715e;padding:.5rem;text-align:left;vertical-align:top}}img{{max-width:100%}}small{{color:#b7b7af}}</style></head><body>
<h1>APP-03: zonotope reduction and outer cover</h1>
<p>Three authored planar cases exercised the registered public <code>CSL::approximation</code> and conversion paths at <a href="https://github.com/butahlecoq/controlled-systems-lab/tree/{source}"><code>{source}</code></a>. The cover retains selected generator factors and replaces omitted factors with independent coordinate-axis generators. The exact method removes zero generator columns only.</p>
<h2>Checked numerical results</h2><table><caption>Literal output generator matrices and descriptive 100-call batch durations</caption><thead><tr><th>Case</th><th>Relation</th><th>Output rows</th><th>Median batch duration</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<figure><img src="zonotope-2d.svg" alt="Input zonotope, signed generator points and enclosing axis square in x-y coordinates"><figcaption>The blue input uses generators (1,0), (0,1) and (0.5,0.5); orange shows the independently admitted axis cover. The input support in direction (1,−1) is 2, and the cover support is 3. <a href="example-2d.html">Open the standalone 2D example</a>.</figcaption></figure>
<h2>Evidence and limits</h2><p>The raw fixture declarations and SHA-256 input identities are in <a href="records.json">records.json</a>. Each completed public call was checked against the literal generator matrix, factor count, relation, evidence identity and absence of an error bound after timing. The approximation policy separately checks stored-binary64 outer inclusion. The constrained case relaxes its input factor equality, which is declared in the saved fixture and method evidence. No finite approximation error bound, validated real-arithmetic guarantee, optimizer result or complete optimal family is claimed.</p>
<h2>Measurement scope</h2><p>One excluded 100-call warmup per case preceded seven rotated three-case rounds of 100 calls per case: 2,100 measured calls with zero recorded failures. Each steady-clock interval includes selection, a fresh provider workspace, public adapter work and independent admission for the outer cases. Fixture and registry construction, post-call literal checking, CSV writing, process launch and rendering are excluded. One worker and one native thread were used; internal counters are unavailable. These single-adapter observations have no comparator, speedup, source-mapped limiter or scalability conclusion.</p>
<p>Host {escape(record['environment']['host'])}: {escape(record['environment']['processor'])}; {escape(record['environment']['os'])}. The saved <a href="build-provenance.json">build provenance</a>, <a href="configure.log">configure log</a>, <a href="build.log">build log</a>, raw CMake cache and compiler receipt describe the Release configuration. HiGHS and Qhull were disabled.</p>
<h2>Reproduce and inspect</h2><p>At the linked source commit, configure CMake with <code>BUILD_TESTING=OFF</code>, <code>CSL_ENABLE_HIGHS=OFF</code>, <code>CSL_ENABLE_QHULL=OFF</code> and <code>CSL_BUILD_APP03_REPORT=ON</code>. Build <code>csl_app03_zonotope_report</code> in Release, then run <code>smoke</code> and <code>measure</code>. The <a href="driver.cpp">saved driver</a>, <a href="measure.csv">raw measured CSV</a> and source receipts allow independent inspection.</p>
<ul><li><a href="smoke.csv">Smoke CSV</a></li><li><a href="summary.csv">Summary CSV</a></li><li><a href="manifest.json">Exact-byte manifest</a></li><li><a href="bundle.zip">Offline ZIP</a></li></ul>
<small>Report ID {escape(record['report_id'])}. The results cover only these stored binary64 fixtures.</small></body></html>\n'''
    return page.encode()


def example(record: dict) -> bytes:
    case = record["fixtures"]["diamond-axis-cover"]
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>APP-03 2D example</title><style>body{{background:#272822;color:#f8f8f2;font:16px/1.5 system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem}}a{{color:#66d9ef}}img{{max-width:100%}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}</style></head><body><h1>2D zonotope outer cover</h1><p>The input set ID is <code>diamond-source</code>, center (0,0), coordinate labels x and y, and unconstrained generator rows {escape(str(case['input_generators']))} with factor IDs {escape(str(case['input_factor_ids']))}. Request identity: problem <code>app03-report</code>, request <code>diamond</code>, ideal output <code>diamond-physical</code>. Select <code>csl.geometry.zonotope.axis-cover</code> with output representation <code>csl.zonotope</code>, outer relation, generator budget 2 and numerical assurance. The public output has generator rows {escape(str(case['expected_generators']))} and encloses every signed input combination. The independent policy verifies the cover from stored binary64 coefficients.</p><img src="zonotope-2d.svg" alt="Blue input zonotope inside orange axis cover, with x-y labels"><p>The source support in direction (1,−1) is 2; the output support is 3. See the <a href="index.html">full saved report</a> and <a href="records.json">fixture record</a>.</p><h2>Reproduce on Windows with MSVC</h2><p>Check out source commit <code>{record['source_commit']}</code>, then run:</p><pre>cmake -S . -B build/app03-example -DBUILD_TESTING=OFF -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF -DCSL_BUILD_APP03_REPORT=ON
cmake --build build/app03-example --config Release --target csl_app03_zonotope_report
build/app03-example/Release/csl_app03_zonotope_report.exe smoke</pre></body></html>\n'''.encode()


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
    files = {name: (bundle / name).read_bytes() for name in collect.SOURCE_FILES}
    files.update({"index.html": html(record), "example-2d.html": example(record),
                  "zonotope-2d.svg": figure(record), "summary.csv": summary_csv(record)})
    files["manifest.json"] = collect.encoded({"schema": "csl.app03-report-manifest/1",
        "report_id": record["report_id"],
        "files": {name: collect.sha(files[name]) for name in sorted(files)}})
    files["bundle.zip"] = zip_bytes(files)
    return files


def render(bundle: Path, check: bool = False) -> None:
    expected = expected_files(bundle)
    if check:
        collect.require({path.name for path in bundle.iterdir()} == set(expected),
                        "APP-03 saved file inventory differs")
        for name, value in expected.items():
            collect.require((bundle / name).read_bytes() == value,
                            "APP-03 saved file differs from regeneration: " + name)
    else:
        for name in RENDERED + ("manifest.json", "bundle.zip"):
            (bundle / name).write_bytes(expected[name])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    render(args.bundle, args.check)
