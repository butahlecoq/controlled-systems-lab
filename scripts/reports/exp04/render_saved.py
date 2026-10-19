"""Validate saved EXP-04 source bytes and regenerate the offline report."""
from __future__ import annotations

import argparse
import csv
from html import escape
import importlib.util
import io
import json
from pathlib import Path
import zipfile

spec = importlib.util.spec_from_file_location("exp04_collect", Path(__file__).with_name("collect.py"))
collect = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(collect)

RENDERED = ("index.html", "trajectory.svg", "summary.csv")


def validate(bundle: Path) -> dict:
    collect.require(bundle.is_dir() and not bundle.is_symlink(), "source bundle is missing or linked")
    for name in collect.SOURCE_FILES:
        path = bundle / name
        collect.require(path.is_file() and not path.is_symlink(), "missing source file: " + name)
    record = collect.read_json(bundle / "records.json")
    unsigned = {key: value for key, value in record.items() if key != "report_id"}
    collect.require(record.get("schema") == collect.SCHEMA and
                    record.get("source_commit") == collect.SOURCE and
                    record.get("report_id") == "exp04-replay-" + collect.sha(collect.encoded(unsigned))[:16] == bundle.name,
                    "source report identity differs")
    collect.require(record["fixtures"] == collect.fixture(), "saved literal fixtures differ")
    host = collect.read_json(bundle / "host.json")
    build = collect.read_json(bundle / "build-provenance.json")
    collect.require(host == record["environment"] and build == record["build"] and
                    host["source_commit"] == collect.SOURCE and host["source_status"] == [] and
                    host["source_tree"] == record["source_tree"] and
                    collect.sha((bundle / "driver.cpp").read_bytes()) == build["driver_source_sha256"],
                    "saved source/build provenance differs")
    collect.require((bundle / "smoke.stderr.txt").read_bytes() == b"" and
                    (bundle / "measure.stderr.txt").read_bytes() == b"", "saved driver stderr differs")
    collect.require(collect.sha((bundle / "smoke.csv").read_bytes()) ==
                    record["measurement"]["raw_smoke_sha256"] and
                    collect.sha((bundle / "measure.csv").read_bytes()) ==
                    record["measurement"]["raw_measure_sha256"], "saved raw CSV hash differs")
    collect.rows(bundle / "smoke.csv", "smoke")
    rows = collect.rows(bundle / "measure.csv", "measure")
    collect.require(rows == record["measurement"]["trials"], "saved trial projection differs")
    for summary in record["measurement"]["summary"]:
        samples = [int(row["elapsed_ns"]) for row in rows
                   if row["phase"] == "trial" and row["case"] == summary["case"]]
        collect.require(len(samples) == 7 and summary == {
            "case": summary["case"], "batches": 7, "calls_per_batch": 1000,
            "successes": 7000, "failures": 0,
            "median_batch_ns": __import__("statistics").median(samples),
            "min_batch_ns": min(samples), "max_batch_ns": max(samples)},
            "saved timing summary differs")
    collect.require(len(record["measurement"]["summary"]) == 4 and
                    {row["case"] for row in record["measurement"]["summary"]} == set(collect.EXPECTED),
                    "saved summary case inventory differs")
    return record


def figure(record: dict) -> bytes:
    cases = record["fixtures"]
    forward = cases["plane-forward"]["expected_states"]
    reverse = cases["plane-reverse"]["expected_states"]
    def xy(state: list[float]) -> tuple[int, int]:
        return 86 + round(state[0] * 160), 302 - round(state[1] * 230)
    def path(states: list[list[float]]) -> str:
        return " ".join(f"{x},{y}" for x, y in map(xy, states))
    origin_x, origin_y = xy(forward[0])
    reverse_x, reverse_y = xy(reverse[-1])
    forward_x, forward_y = xy(forward[-1])
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="710" height="370" viewBox="0 0 710 370" '
           'role="img" aria-label="Two state replay trajectories in x and y coordinates">'
           '<rect width="710" height="370" fill="#272822"/>'
           '<line x1="86" y1="302" x2="630" y2="302" stroke="#f8f8f2"/>'
           '<line x1="86" y1="302" x2="86" y2="35" stroke="#f8f8f2"/>'
           '<text x="545" y="342" fill="#f8f8f2" font-size="15">x (length)</text>'
           '<text x="15" y="32" fill="#f8f8f2" font-size="15">y (action)</text>'
           '<polyline points="' + path(forward) + '" fill="none" stroke="#66d9ef" stroke-width="3"/>'
           '<polyline points="' + path(reverse) + '" fill="none" stroke="#fd971f" stroke-width="3"/>'
           + f'<circle cx="{origin_x}" cy="{origin_y}" r="7" fill="#f8f8f2"/>'
             f'<text x="{origin_x+10}" y="{origin_y+22}" fill="#f8f8f2" font-size="13">'
             'both t=0; forward t=1 (0,0)</text>'
             f'<circle cx="{reverse_x}" cy="{reverse_y}" r="7" fill="#fd971f"/>'
             f'<text x="{reverse_x-64}" y="{reverse_y-18}" fill="#fd971f" font-size="13">'
             'reverse t=1,3 (2,1)</text>'
             f'<circle cx="{forward_x}" cy="{forward_y}" r="7" fill="#66d9ef"/>'
             f'<text x="{forward_x-8}" y="{forward_y+24}" fill="#66d9ef" font-size="13">'
             'forward t=3 (3,1)</text></svg>\n')
    return svg.encode()


def summary_csv(record: dict) -> bytes:
    output = io.StringIO(newline="")
    fields = ["case", "batches", "calls_per_batch", "successes", "failures",
              "median_batch_ns", "min_batch_ns", "max_batch_ns"]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(record["measurement"]["summary"])
    return output.getvalue().encode()


def html(record: dict) -> bytes:
    rows = []
    for name, case in record["fixtures"].items():
        summary = next(row for row in record["measurement"]["summary"] if row["case"] == name)
        rows.append("<tr><td>" + escape(name) + "</td><td>" +
                    escape(str(case["controls"])) + "</td><td>" +
                    escape(str(case["expected_states"][-1])) + "</td><td>" +
                    escape(str(case["expected_objective"])) + " " +
                    escape(case["plant"]["objective_unit"]) + "</td><td>" +
                    f'{summary["median_batch_ns"]:,} ns (range {summary["min_batch_ns"]:,}–'
                    f'{summary["max_batch_ns"]:,})' + "</td></tr>")
    source = record["source_commit"]
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EXP-04 independent plant replay</title><style>
body{{background:#272822;color:#f8f8f2;font:16px/1.55 system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1.5rem}}
a{{color:#66d9ef}}h1,h2{{color:#a6e22e}}code{{color:#fd971f}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #75715e;padding:.5rem;text-align:left}}figure{{margin:1rem 0}}img{{max-width:100%}}small{{color:#b7b7af}}
</style></head><body><h1>EXP-04: independent plant replay</h1>
<p>Authored analytic examples on the public <code>CSL::simulation</code> exact-discrete map. Source commit <a href="https://github.com/butahlecoq/controlled-systems-lab/tree/{source}"><code>{source}</code></a>. This is a sampled simulation of chosen controls, with no nonlinear optimization or historical B04 reproduction claim.</p>
<h2>Input and checked outcome</h2><p>The scalar plant starts at x=0 and applies x[k+1]=x[k]+u[k]+u[k]² at times 0,1,2. Controls (0,1) and (0.5,0.5) both sum to 1 in the separate linear calculation; their original-plant terminal objectives are 2 and 1.5. Each case declares gain=1, constant control on each interval, an exact discrete transition map, and finite 10⁻¹² absolute and relative tolerance metadata. The callback has no independently certified rounding enclosure.</p>
<p>The two-state plant starts at (x,y)=(0,0), times are 0,1,3, and controls are one-dimensional. Its transition is x[k+1]=x[k]+(t[k+1]−t[k])u[k]+u[k]² and y[k+1]=y[k]+u[k]. State units are length and action; terminal x in length is the original objective. Reversing (0,1) to (1,0) changes the terminal state from (3,1) to (2,1).</p>
<table><caption>Literal checked public replay outcomes and descriptive 1,000-call batch time</caption><thead><tr><th scope="col">Case</th><th scope="col">Ordered controls</th><th scope="col">Terminal state</th><th scope="col">Original objective</th><th scope="col">Median batch duration</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<figure aria-label="Two-state physical trajectory"><img src="trajectory.svg" alt="Two labelled two-state trajectories at physical times 0, 1 and 3"><figcaption>Two-dimensional state coordinates and stages. Forward controls are (0,1); reverse controls are (1,0). Reproduce with the saved driver and commands below.</figcaption></figure>
<h2>Measurement scope and limits</h2><p>One excluded warmup batch and seven rotated measured batches per case, each with 1,000 fresh public replay calls. Every call checked the complete literal trajectory, terminal objective, declaration and status after its measured interval. The batch duration sums the public record's steady-clock replay duration; fixture construction, oracle checks, serialization, process launch and rendering are outside that interval. A single worker and one native thread were requested and used; immutable plant and controls were reused. No internal counter or source-mapped limiter was available. These single-adapter timings are exploratory and support no speedup or broad performance conclusion.</p>
<p>Host: {escape(record['environment']['cpu']['Name'])}, {escape(record['environment']['os'])} {escape(record['environment']['os_version'])}, MSVC 19.44 x64 Release. No HiGHS or Qhull backend was enabled. The four cases completed all 28,000 measured replay calls with zero recorded failures; smoke and warmup calls are excluded from those totals.</p>
<h2>Reproduce and inspect</h2><p>Configure a fresh source checkout at the linked commit with <code>python -m cmake -S . -B build/exp04 -DBUILD_TESTING=OFF -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF -DCSL_BUILD_EXP04_REPORT=ON</code>, build target <code>csl_exp04_replay_report</code> in Release, then run it with <code>smoke</code> and <code>measure</code>. The driver source, exact inputs, raw CSV and file hashes are saved here.</p>
<ul><li><a href="records.json">Raw record and full input declarations</a></li><li><a href="measure.csv">Measured CSV</a></li><li><a href="smoke.csv">Smoke CSV</a></li><li><a href="summary.csv">Summary CSV</a></li><li><a href="driver.cpp">Frozen driver source</a></li><li><a href="build-provenance.json">Build provenance</a></li></ul><p>The offline bundle is linked from the site catalogue.</p>
<small>Report ID: {escape(record['report_id'])}. No fitted archival coefficients or invented control histories are used.</small></body></html>\n'''
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
    files.update({"index.html": html(record), "trajectory.svg": figure(record),
                  "summary.csv": summary_csv(record)})
    files["manifest.json"] = collect.encoded({"schema": "csl.exp04-report-manifest/1",
                                               "report_id": record["report_id"],
                                               "files": {name: collect.sha(files[name]) for name in sorted(files)}})
    files["bundle.zip"] = zip_bytes(files)
    return files


def render(bundle: Path, check: bool = False) -> None:
    expected = expected_files(bundle)
    if check:
        collect.require({path.name for path in bundle.iterdir()} == set(expected),
                        "saved report file inventory differs")
        for name, value in expected.items():
            collect.require((bundle / name).read_bytes() == value,
                            "saved report differs from regeneration: " + name)
    else:
        for name in RENDERED + ("manifest.json", "bundle.zip"):
            (bundle / name).write_bytes(expected[name])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    render(args.bundle, args.check)


if __name__ == "__main__":
    main()
