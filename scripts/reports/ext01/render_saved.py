"""Validate and render the EXT-01 numerical report from saved bytes only."""
from __future__ import annotations

import argparse
import csv
import hashlib
from html import escape
import io
import json
from pathlib import Path
import re
import statistics
import zipfile


REPORT_ID = "ext01-fixed-plan-20261016-11b7bc74"
SOURCE = "fd75a63657bc6b1d8cbd26c644bd8fb39cc1a3ec"
HARNESS = "11b7bc74e4756bafc2c6c450628d10c6a62f8f39"
FIXTURES = ("l19", "integrator_feasible", "integrator_violation", "b08_rounded")
SOURCE_FILES = frozenset({
    "README.md", "accepted.process.json", "accepted.stderr.txt", "accepted.stdout.jsonl",
    "build-graph.json", "collection-status.json", "driver.exe", "excluded-002.json",
    "excluded-002.process.json", "excluded-002.stderr.txt", "excluded-002.stdout.jsonl",
    "excluded-002.validation-error.txt", "excluded-profile-001.json",
    "excluded-profile-001.stderr.txt", "excluded-profile-001.stdout.jsonl",
    "fixed_plan_driver.cpp", "fresh-build.json", "profile.process.json",
    "profile.stderr.txt", "profile.stdout.jsonl", "records.json", "reference-b08.json",
    "smoke-ctest.txt",
})
RENDERED_FILES = frozenset({"index.html", "trials.csv", "summary.csv", "b08-trials.svg"})
MANIFEST = "manifest.json"
ARCHIVE = "bundle.zip"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def pairs_unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def read_json(content: bytes) -> object:
    return json.loads(content.decode("utf-8"), object_pairs_hook=pairs_unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON token")))


def local(bundle: Path, name: str) -> Path:
    require(name in SOURCE_FILES | RENDERED_FILES | {MANIFEST, ARCHIVE}, "unlisted report file")
    path = bundle / name
    require(path.is_file() and not path.is_symlink(), "missing or linked report file: " + name)
    return path


def result_matches(fixture: str, result: object) -> bool:
    if not isinstance(result, dict):
        return False
    if fixture == "l19":
        return result == {"status": "numerical_value", "worst_value": 1,
                          "maximizer": [0], "evaluated_vertices": 3,
                          "sampled_points": [0, 1, 2],
                          "observed_objective_values": [1, 0, 1],
                          "stationary_midpoint_value": 0}
    if fixture == "integrator_feasible":
        return result == {"status": "numerical_reachable", "stages": 3,
                          "terminal_candidates": 4, "terminal_worst_value": 4}
    if fixture == "integrator_violation":
        return result == {"status": "robust_violation", "stage": 1,
                          "violating_successor": [-1]}
    return (set(result) == {"status", "plan_count", "disturbance_histories",
                            "minimum_worst_value", "ties_at_1e-8"} and
            result["status"] == "numerical_reference" and result["plan_count"] == 625 and
            result["disturbance_histories"] == 160000 and result["ties_at_1e-8"] == 3 and
            type(result["minimum_worst_value"]) in (int, float) and
            abs(result["minimum_worst_value"] - 67.150601101407) <= 1e-8)


def check_rows(raw: bytes, *, min_ns: int) -> list[dict]:
    rows = [read_json(line) for line in raw.splitlines()]
    require(len(rows) == 32, "expected four fixtures x eight rounds")
    for round_number in range(8):
        group = rows[round_number * 4:(round_number + 1) * 4]
        order = FIXTURES if round_number % 2 == 0 else tuple(reversed(FIXTURES))
        require(tuple(row.get("fixture") for row in group) == order,
                "alternating fixture order differs")
        for row in group:
            fixture = row["fixture"]
            batch = 1 if fixture == "b08_rounded" else 10000 if fixture == "l19" else 5000
            require(set(row) == {"schema", "fixture", "round", "warmup", "batch",
                                 "checked_calls", "elapsed_ns", "result"} and
                    row["schema"] == "csl.ext01-raw-trial/1" and
                    row["round"] == round_number and
                    row["warmup"] is (round_number == 0) and
                    row["batch"] == batch and row["checked_calls"] == batch and
                    type(row["elapsed_ns"]) is int and row["elapsed_ns"] >= min_ns and
                    result_matches(fixture, row["result"]),
                    "raw work, status, oracle or interval differs")
    return rows


def check_capture(bundle: Path, name: str, *, successful: bool) -> dict:
    process = read_json(local(bundle, name + ".process.json").read_bytes())
    stdout = local(bundle, name + ".stdout.jsonl").read_bytes()
    stderr = local(bundle, name + ".stderr.txt").read_bytes()
    require(process["schema"] == "csl.ext01-process-capture/1" and
            process["stdout_sha256"] == digest(stdout) and
            process["stderr_sha256"] == digest(stderr) and
            type(process["wall_ns"]) is int and process["wall_ns"] > 0 and
            isinstance(process["samples"], list) and process["samples"],
            "process capture or raw hash differs")
    if successful:
        require(process["return_code"] == 0 and process["timed_out"] is False and not stderr and
                process["last_observed_cpu_seconds"] > 0 and
                process["max_observed_rss_bytes"] > 0,
                "reported process did not complete cleanly")
    return process


def validate_collection(bundle: Path) -> dict:
    bundle = Path(bundle)
    require(bundle.name == REPORT_ID and bundle.is_dir() and not bundle.is_symlink(),
            "EXT-01 versioned report directory differs")
    for name in SOURCE_FILES:
        local(bundle, name)
    record = read_json(local(bundle, "records.json").read_bytes())
    require(isinstance(record, dict) and record.get("schema") == "csl.ext01-fixed-plan-records/1" and
            record.get("report_id") == REPORT_ID and record.get("source_commit") == SOURCE and
            record.get("harness_commit") == HARNESS and record.get("source_tree") ==
            "1a90152038ab9d4eec8bd96329b7311121ab1a2c" and
            record.get("attempts") == 32 and record.get("successes") == 32 and
            record.get("failures") == 0,
            "fixed-source record identity or attempt counts differ")
    build = record["build"]
    require(build["configuration"] == "Release" and
            build["binary_sha256"] == digest(local(bundle, "driver.exe").read_bytes()) and
            build["driver_sha256"] == digest(local(bundle, "fixed_plan_driver.cpp").read_bytes()) and
            build["driver_sha256"] == record["inputs"]["authored_fixture_sha256"] and
            record["inputs"]["b08_saved_reference_sha256"] ==
            digest(local(bundle, "reference-b08.json").read_bytes()) and
            build["graph_sha256"] == digest(local(bundle, "build-graph.json").read_bytes()) and
            build["fresh_build_sha256"] == digest(local(bundle, "fresh-build.json").read_bytes()),
            "binary, fixture, reference or build provenance hash differs")
    graph = read_json(local(bundle, "build-graph.json").read_bytes())
    fresh = read_json(local(bundle, "fresh-build.json").read_bytes())
    names = set(graph["dependency_targets"])
    required = {"csl_ext01_fixed_plan_report", "csl_fixed_plan_disturbance",
                "csl_worst_case_vertex", "csl_objectives", "csl_model", "csl_sets"}
    targets = [target for target in graph["targets"] if target["name"] == "csl_ext01_fixed_plan_report"]
    require(required <= names and len(targets) == 1 and
            graph["compiler"] == build["compiler"] and graph["cmake"] == build["cmake"] and
            graph["compiler"]["compiler"]["id"] == "MSVC" and
            len(targets[0]["compileGroups"]) == 1 and
            targets[0]["compileGroups"][0]["languageStandard"]["standard"] == "20" and
            "/DNDEBUG" in " ".join(fragment["fragment"] for fragment in
                                   targets[0]["compileGroups"][0]["compileCommandFragments"]) and
            fresh["source_commit"] == SOURCE and fresh["harness_commit"] == HARNESS and
            fresh["return_code"] == 0 and fresh["timed_out"] is False and
            fresh["command"][-2:] == ["--clean-first", "--verbose"],
            "actual Release target graph or fresh build differs")
    accepted = check_capture(bundle, "accepted", successful=True)
    profile = check_capture(bundle, "profile", successful=True)
    raw = local(bundle, "accepted.stdout.jsonl").read_bytes()
    rows = check_rows(raw, min_ns=20_000_000)
    check_rows(local(bundle, "profile.stdout.jsonl").read_bytes(), min_ns=1)
    require(sum(row["elapsed_ns"] for row in rows) <= accepted["wall_ns"] and
            record["timing"]["raw_sha256"] == digest(raw) and
            record["timing"]["stderr_sha256"] == digest(local(bundle, "accepted.stderr.txt").read_bytes()) and
            record["timing"]["profile_is_reported"] is False and
            record["timing"]["measured_rounds"] == 7 and
            record["timing"]["warmup_rounds"] == 1,
            "reported timing scope or raw status differs")
    summary = []
    for fixture in FIXTURES:
        group = [row for row in rows if row["fixture"] == fixture and not row["warmup"]]
        values = [row["elapsed_ns"] for row in group]
        require(len(group) == 7, "seven measured repetitions required")
        summary.append({"fixture": fixture, "attempts": 7, "successes": 7, "failures": 0,
                        "batch": group[0]["batch"], "median_elapsed_ns": statistics.median(values),
                        "min_elapsed_ns": min(values), "max_elapsed_ns": max(values)})
    require(record["trials"] == rows and record["summary"] == summary and
            record["arithmetic"]["assurance"].startswith("numerical") and
            record["environment"]["requested_driver_workers"] == 1 and
            record["environment"]["actual_native_threads"] is None,
            "raw-to-summary, arithmetic or worker identity differs")
    status = read_json(local(bundle, "collection-status.json").read_bytes())
    require(status["status"] == "complete" and status["failure_count"] == 0 and
            status["records_sha256"] == digest(local(bundle, "records.json").read_bytes()) and
            status["raw_sha256"] == digest(raw), "collection status differs")
    first = read_json(local(bundle, "excluded-profile-001.json").read_bytes())
    second = read_json(local(bundle, "excluded-002.json").read_bytes())
    require(first["accepted_trial_started"] is False and first["timings_accepted"] is False and
            first["stdout_available"] is False and first["stderr_available"] is False and
            local(bundle, "excluded-profile-001.stdout.jsonl").read_bytes() == b"" and
            local(bundle, "excluded-profile-001.stderr.txt").read_bytes() == b"" and
            second["accepted"] is False and
            "ValueError" in local(bundle, "excluded-002.validation-error.txt").read_text(encoding="utf-8"),
            "excluded attempt status differs")
    excluded = check_capture(bundle, "excluded-002", successful=True)
    require(excluded["return_code"] == 0 and
            len(check_rows(local(bundle, "excluded-002.stdout.jsonl").read_bytes(), min_ns=1)) == 32,
            "excluded complete run differs")
    require(profile["wall_ns"] > 0, "separate profile absent")
    return record


def csv_bytes(fields: tuple[str, ...], rows: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def svg(record: dict) -> bytes:
    values = [row["elapsed_ns"] / 1_000_000 for row in record["trials"]
              if row["fixture"] == "b08_rounded" and not row["warmup"]]
    require(len(values) == 7, "B08 figure needs seven measured values")
    bottom, top = min(values) - 1, max(values) + 1
    points = [(70 + 68 * index, 225 - 155 * (value - bottom) / (top - bottom))
              for index, value in enumerate(values)]
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    circles = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#246489"/>'
                      for x, y in points)
    labels = "".join(f'<text x="{x:.1f}" y="250" text-anchor="middle" font-size="13">{i}</text>'
                     for i, (x, _) in enumerate(points, 1))
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="540" height="275" '
            'viewBox="0 0 540 275" role="img" aria-label="Seven B08 full-catalogue '
            'batch observations in milliseconds"><line x1="50" y1="225" x2="500" y2="225" '
            'stroke="#555"/><line x1="50" y1="45" x2="50" y2="225" stroke="#555"/>'
            f'<text x="5" y="55" font-size="12">{top:.1f} ms</text>'
            f'<text x="5" y="225" font-size="12">{bottom:.1f} ms</text>'
            f'<polyline points="{polyline}" fill="none" stroke="#246489" stroke-width="2"/>'
            f'{circles}{labels}<text x="225" y="270" font-size="13">Measured round</text>'
            '</svg>\n').encode("utf-8")


def page(record: dict, figure: bytes) -> bytes:
    summary_rows = "".join(
        '<tr><th scope="row">' + escape(row["fixture"]) + '</th><td>' + str(row["batch"]) +
        '</td><td>' + str(row["successes"]) + '/7</td><td>' +
        f'{row["median_elapsed_ns"]/1_000_000:.3f}' + '</td><td>' +
        f'{row["min_elapsed_ns"]/1_000_000:.3f}–{row["max_elapsed_ns"]/1_000_000:.3f}' +
        '</td></tr>' for row in record["summary"])
    b08 = next(row["result"] for row in record["trials"]
               if row["fixture"] == "b08_rounded" and not row["warmup"])
    env = record["environment"]
    compiler = record["build"]["compiler"]["compiler"]
    links = (('<li><a href="' + name + '">' + escape(label) + '</a></li>') for name, label in (
        ("records.json", "Complete typed record"), ("accepted.stdout.jsonl", "Exact raw JSONL"),
        ("accepted.stderr.txt", "Process stderr"), ("trials.csv", "Accepted attempts CSV"),
        ("summary.csv", "Summary CSV"), ("build-graph.json", "Release compiler and target graph"),
        ("fresh-build.json", "Fresh build transcript"), ("profile.process.json", "Separate profile observations"),
        ("excluded-profile-001.json", "Excluded profile capture deadlock"),
        ("excluded-002.json", "Excluded short-batch gate attempt"),
        ("manifest.json", "Exact-byte manifest"), ("bundle.zip", "Offline source bundle")))
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>EXT-01 fixed-plan numerical reference</title><style>'
        'body{font:16px system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#18232d}'
        'h1,h2{line-height:1.2}table{border-collapse:collapse;width:100%;margin:1rem 0}'
        'th,td{border:1px solid #bbc8d0;padding:.5rem;text-align:left}'
        'th{background:#eaf0f4}code{overflow-wrap:anywhere}figure{margin:1rem 0}'
        '</style></head><body><h1>EXT-01 fixed-plan numerical reference</h1>'
        '<p>Source <code>' + SOURCE + '</code>; reviewed harness <code>' + HARNESS +
        '</code>. Native affine fixed-plan disturbance propagation and convex vertex worst-case '
        'objective. MSVC Release, HiGHS/Qhull disabled. All assurances are numerical.</p>'
        '<h2>Observed numerical outcomes</h2><table><thead><tr><th>Fixture</th><th>Expected or sourced</th>'
        '<th>Observed</th><th>Evidence scope</th></tr></thead><tbody>'
        '<tr><th scope="row">L19</th><td>(x−1)² on [0,2]: midpoint 0; endpoint worst 1</td>'
        '<td>Public evaluations [1, 0, 1]; global V-row worst 1 at x=0</td>'
        '<td>Authored compact V set and numerically admitted convex objective</td></tr>'
        '<tr><th scope="row">Integrator, feasible</th><td>Four terminal corner candidates '
        '[-2, 0, 0, 2]; worst x²=4</td><td>Four candidates; worst 4</td>'
        '<td>Two independent compact disturbances; convex H safety</td></tr>'
        '<tr><th scope="row">Integrator, violation</th><td>Stage-one successor −1 outside '
        '[-0.5,0.5]</td><td>Robust violation at stage 1, successor −1; no tube</td>'
        '<td>Whole-set containment, without clipping</td></tr>'
        '<tr><th scope="row">B08 rounded</th><td>Independent saved discrete reference '
        '67.150601101407, three ties at 1e−8</td><td>' +
        f'{b08["minimum_worst_value"]:.15f}' + '; 625 plans × 256 disturbance histories, three ties</td>'
        '<td>Displayed rounded matrices and finite action catalogue only</td></tr>'
        '</tbody></table><p>No numerical residual vector is exposed by these two public APIs. '
        'The published 67.12, original unrounded MATLAB arrays, nonlinear trajectories, '
        'historical runtime and validated rounding are not reproduced. The B08 finite-plan '
        'reference does not establish feedback optimality or a complete optimal family.</p>'
        '<h2>Saved Release batch observations</h2><p>One excluded warmup then seven measured '
        'rounds per fixture; zero process or literal-oracle failures. Durations are batch '
        'milliseconds, not single-call latencies. Each timed interval includes fixture '
        'construction, public API execution, literal checks and JSON result construction. '
        'It excludes process startup, serialization, persistence, plotting and rendering. '
        'Different batch sizes make fixture rows unsuitable as a speed comparison.</p>'
        '<table><thead><tr><th>Fixture</th><th>Calls/batch</th><th>Successful rounds</th>'
        '<th>Median ms/batch</th><th>Range ms/batch</th></tr></thead><tbody>' +
        summary_rows + '</tbody></table><figure aria-label="B08 measured batch times">' +
        figure.decode("utf-8") + '<figcaption>Seven full B08 catalogue scans; one scan '
        'checks 160,000 plan-history objective evaluations. The figure shows within-profile '
        'variation, not a method comparison.</figcaption></figure><p>The L19 batch is short '
        '(about 45 ms); its per-call time is not inferred. Host load observations were ' +
        f'{env["host_cpu_percent_before_profile"]:.1f}%, '
        f'{env["host_cpu_percent_between_runs"]:.1f}%, and '
        f'{env["host_cpu_percent_after_measurement"]:.1f}% around the runs. '
        'The separate profile recorded process CPU and resident memory, but did not '
        'identify a source-level limiter. Performance remains exploratory and '
        'inconclusive; no comparator or speedup is claimed.</p>'
        '<h2>Provenance and limits</h2><dl><dt>Host</dt><dd>' +
        escape(env["system"] + " " + env["release"] + " " + env["version"]) +
        f'; {env["physical_cores"]} physical cores, {env["logical_processors"]} logical processors; '
        f'{env["memory_total_bytes"] / (1024**3):.1f} GiB RAM</dd>'
        '<dt>Compiler</dt><dd>' + escape(compiler["id"] + " " + compiler["version"]) +
        '; C++20 /O2 /Ob2 /DNDEBUG, exact File API graph linked below</dd>'
        '<dt>Arithmetic</dt><dd>binary64; absolute and relative objective policy 1e−8; '
        'B08 tie tolerance 1e−8; no validated rounding enclosure</dd>'
        '<dt>Workers</dt><dd>One requested sequential driver process; native thread count '
        'unavailable from its API</dd><dt>Input identity</dt><dd>Embedded fixture source and '
        'saved B08 reference SHA-256 in records.json; fresh executable SHA-256 ' +
        record["build"]["binary_sha256"] + '</dd></dl>'
        '<p>The first profile collection blocked on an unread pipe; its output bytes were '
        'unavailable and no accepted trial had begun. A second complete run failed a '
        'provisional 50 ms batch gate; its raw output is retained but excluded. The final '
        'run used a 20 ms admission floor after another fresh clean Release rebuild.</p>'
        '<h2>Download and audit</h2><ul>' + ''.join(links) + '</ul></body></html>\n')
    return html.encode("utf-8")


def generated(record: dict) -> dict[str, bytes]:
    trials = [{"fixture": row["fixture"], "round": row["round"],
               "warmup": str(row["warmup"]).lower(), "batch": row["batch"],
               "checked_calls": row["checked_calls"], "elapsed_ns": row["elapsed_ns"],
               "status": row["result"]["status"],
               "result_json": json.dumps(row["result"], sort_keys=True, separators=(",", ":"))}
              for row in record["trials"]]
    trial_fields = ("fixture", "round", "warmup", "batch", "checked_calls", "elapsed_ns",
                    "status", "result_json")
    summary_fields = ("fixture", "attempts", "successes", "failures", "batch",
                      "median_elapsed_ns", "min_elapsed_ns", "max_elapsed_ns")
    figure = svg(record)
    return {"index.html": page(record, figure), "b08-trials.svg": figure,
            "trials.csv": csv_bytes(trial_fields, trials),
            "summary.csv": csv_bytes(summary_fields, record["summary"])}


def manifest(bundle: Path, assets: dict[str, bytes]) -> bytes:
    files = {name: digest(local(bundle, name).read_bytes()) for name in sorted(SOURCE_FILES)}
    files.update({name: digest(content) for name, content in assets.items()})
    return json_bytes({"schema": "csl.ext01-native-manifest/1", "report_id": REPORT_ID,
                       "source_commit": SOURCE, "harness_commit": HARNESS, "files": files})


def native_zip(bundle: Path, assets: dict[str, bytes], native_manifest: bytes) -> bytes:
    files = {name: local(bundle, name).read_bytes() for name in SOURCE_FILES}
    files.update(assets)
    files[MANIFEST] = native_manifest
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        root_index = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                      '<title>Offline EXT-01 report</title><h1>Offline EXT-01 report</h1>'
                      '<a href="' + REPORT_ID + '/index.html">Open the saved report</a></html>\n').encode("utf-8")
        entries = ([("index.html", root_index)] +
                   [(REPORT_ID + "/" + name, files[name]) for name in sorted(files)])
        for name, content in entries:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return buffer.getvalue()


def render(bundle: Path, *, check: bool) -> None:
    record = validate_collection(bundle)
    assets = generated(record)
    native_manifest = manifest(bundle, assets)
    archive = native_zip(bundle, assets, native_manifest)
    expected = assets | {MANIFEST: native_manifest, ARCHIVE: archive}
    inventory = {path.name for path in bundle.iterdir() if path.is_file()}
    complete_inventory = SOURCE_FILES | set(expected)
    require(inventory == complete_inventory if check else
            inventory in (SOURCE_FILES, complete_inventory),
            "source bundle inventory differs")
    if check:
        for name, content in expected.items():
            require(local(bundle, name).read_bytes() == content,
                    "saved report differs from raw regeneration: " + name)
    else:
        for name, content in expected.items():
            (bundle / name).write_bytes(content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    render(args.bundle, check=args.check)
    print("checked" if args.check else "rendered", args.bundle)


if __name__ == "__main__":
    main()
