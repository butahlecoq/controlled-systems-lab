"""Validate and render issue #3 from immutable saved capture bytes only.

No command in this module starts the numerical driver or collects measurements.
"""
from __future__ import annotations

import argparse
import csv
from html import escape
import hashlib
import io
import json
from pathlib import Path
import statistics

SOURCE = "994f3ee4310b4087d289e2eb02adbdb9dfd97827"
HARNESS = "2f915110ba42515fdc448a0c226dc1290b80f82d"
SOURCE_TREE = "2b07e8378561b74fd763e43ca70c78cfd1145b99"
HARNESS_TREE = "c3259b26fa792b5abd70919366cf8c40882e69af"
RAW_SHA256 = "b4632ce76510aa4f2bb136baa193bc78da66506336a90d048cd8495c2d7926de"
BINARY_SHA256 = "18efe090a2809c092263b99c5b87d5bdaeea8007fc848826bc64ecb2eb2c88f7"
FIXTURE_SHA256 = "9494dec664f6fed74f39886ec3ab94c576dba6cdb5349f1f19329c6c31acc85a"
REPORT_ID = "issue3-finite-catalogue-" + RAW_SHA256[:16]
SCHEMA = "csl.issue3-finite-catalogue-records/1"
NAMES = ("l19", "integrator", "all_infeasible", "empty_catalogue",
         "no_scenarios", "unsupported", "cancelled", "b08_rounded")
EVIDENCE_NAMES = {
    "accepted.process.json", "accepted.stderr", "accepted.stdout", "build-graph.json",
    "collection-status.json", "configure.process.json", "configure.stderr",
    "configure.stdout", "driver.exe", "finite_catalogue_driver.cpp", "fresh-build.json",
    "fresh-build.process.json", "fresh-build.stderr", "fresh-build.stdout",
    "preflight.json", "process-capture.json", "smoke-check.process.json",
    "smoke-check.stderr", "smoke-check.stdout", "smoke.process.json", "smoke.stderr",
    "smoke.stdout",
}
DERIVED = {"records.json", "trials.csv", "summary.csv", "latency.svg", "index.html"}
SOURCE_FILES = DERIVED | {"evidence/accepted-001/" + name for name in EVIDENCE_NAMES}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def strict_json(content: bytes):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key: " + key)
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError("nonfinite JSON number: " + value)
    return json.loads(content.decode("utf-8"), object_pairs_hook=object_pairs,
                      parse_constant=reject_constant)


def encoded(value) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def evidence(bundle: Path, name: str) -> bytes:
    return (bundle / "evidence" / "accepted-001" / name).read_bytes()


def parse_rows(content: bytes) -> list[dict]:
    require(content.endswith(b"\n"), "JSONL must end on a complete line")
    return [strict_json(line) for line in content.splitlines()]


LITERALS = {
    "l19": {"status": "numerical_optimal", "value": 1, "plan_count": 2,
            "minimizing_plan_indices": [0, 1], "evaluated_vertices": 4,
            "worst_values": [1, 1], "maximizers": [[0], [2]],
            "sampled_objective_values": [1, 0, 1]},
    "integrator": {"status": "numerical_optimal", "value": 1, "plan_count": 2,
                   "minimizing_plan_indices": [0], "worst_values": [1, 4],
                   "evaluated_vertices": 4},
    "all_infeasible": {"status": "infeasible", "rejected_plans": [
        {"action_indices": [0], "stage": 1, "violating_successor": [2]},
        {"action_indices": [1], "stage": 1, "violating_successor": [1]}]},
    "empty_catalogue": {"status": "empty_catalogue"},
    "no_scenarios": {"status": "no_scenarios"},
    "unsupported": {"status": "unsupported", "field": "finite_minimax.capacity"},
    "cancelled": {"status": "stopped", "reason": "cancelled"},
}
PLAN_COUNTS = {"l19": 2, "integrator": 2, "all_infeasible": 2,
               "empty_catalogue": 0, "b08_rounded": 625}
TERMINAL_ROWS = {"l19": 4, "integrator": 4, "all_infeasible": 0,
                 "empty_catalogue": 0, "b08_rounded": 160000}


def check_result(fixture: str, row: dict) -> None:
    observed = row["result"]
    checks = row["checks"]
    require(checks["passed"] is True and checks["observed"] == observed,
            fixture + " expected/observed check differs")
    if fixture != "b08_rounded":
        require(observed == checks["expected"] == LITERALS[fixture],
                fixture + " literal oracle differs")
    else:
        require(checks["absolute_tolerance"] == 1e-8 and
                checks["expected"] == {"status": "numerical_optimal", "value": 67.150601101407,
                                       "plan_count": 625, "evaluated_vertices": 160000,
                                       "minimizing_plan_indices": [17, 33, 129]} and
                set(observed) == set(checks["expected"]) and
                observed["status"] == "numerical_optimal" and
                observed["plan_count"] == 625 and
                observed["evaluated_vertices"] == 160000 and
                observed["minimizing_plan_indices"] == [17, 33, 129] and
                abs(observed["value"] - 67.150601101407) <= 1e-8,
                "B08 public literal oracle differs")


def check_inputs(row: dict) -> None:
    fixture = row["fixture"]
    require(row["input_sha256"] == sha(row["input_canonical"].encode("utf-8")),
            fixture + " canonical input SHA-256 differs")
    request = strict_json(row["input_canonical"].encode("utf-8"))
    require(isinstance(request, dict) and row["problem_id"] and row["request_id"] and
            row["limits"]["max_plans"] >= 1 and
            row["objective_convention"] and
            row["assurance"] == ("numerical" if fixture in
            {"l19", "integrator", "all_infeasible", "b08_rounded"} else None) and
            row["plan_count"] == PLAN_COUNTS.get(fixture) and
            row["evaluated_terminal_rows"] == TERMINAL_ROWS.get(fixture),
            fixture + " problem/request/limits/assurance/counts differ")
    if fixture == "l19":
        require(request["actions"] == [[0], [1]] and
                request["disturbance_vertices"] == [[0], [1]] and
                request["model"]["horizon"] == 1 and
                row["objective_convention"] == "0.5*x'Q*x+q'x+c",
                "L19 endpoint fixture differs")
    if fixture == "b08_rounded":
        vertices = request["disturbance_vertices_binary64_hex"]
        require(len(request["actions"]) == 5 and request["model"]["horizon"] == 4 and
                len(vertices) == 4 and all(len(stage) == 4 for stage in vertices) and
                vertices[2][0][0] == float.hex(-(0.1 + 0.1 * 2)) and
                vertices[2][0][0] != float.hex(-0.3) and
                vertices[3][0][1] == float.hex(-(0.1 + 0.3 * 3)) and
                row["limits"] == {"max_plans": 625, "max_points_per_stage": 256,
                                  "near_optimal_tolerance": 1e-8} and
                row["objective_convention"] == "Euclidean terminal residual norm",
                "B08 exact binary64 input or catalogue limits differ")


def validate_evidence(bundle: Path) -> tuple[list[dict], dict]:
    folder = bundle / "evidence" / "accepted-001"
    require(folder.is_dir() and not folder.is_symlink() and
            {p.name for p in folder.iterdir()} == EVIDENCE_NAMES and
            all(p.is_file() and not p.is_symlink() for p in folder.iterdir()),
            "accepted evidence inventory differs")
    pre = strict_json(evidence(bundle, "preflight.json"))
    graph = strict_json(evidence(bundle, "build-graph.json"))
    fresh = strict_json(evidence(bundle, "fresh-build.json"))
    status = strict_json(evidence(bundle, "collection-status.json"))
    require(pre["schema"] == "csl.issue3-preflight/1" and
            pre["source_commit"] == SOURCE and pre["harness_commit"] == HARNESS and
            pre["source_tree"] == SOURCE_TREE and pre["harness_tree"] == HARNESS_TREE and
            pre["fixture_sha256"] == FIXTURE_SHA256 and
            pre["binary_sha256"] == BINARY_SHA256 and
            pre["build_configuration"] == "Release" and
            pre["build_graph_sha256"] == sha(evidence(bundle, "build-graph.json")) and
            pre["fresh_build_sha256"] == sha(evidence(bundle, "fresh-build.json")) and
            sha(evidence(bundle, "driver.exe")) == BINARY_SHA256 and
            sha(evidence(bundle, "finite_catalogue_driver.cpp")) == FIXTURE_SHA256,
            "source/harness/binary/fixture/build provenance differs")
    require(graph["file_api_paths"] == {"source": "SOURCE_ROOT", "build": "BUILD_ROOT"} and
            graph["cmake"] == pre["cmake"] and graph["compiler"] == pre["compiler"] and
            "csl_finite_action_minimax" in graph["dependency_targets"] and
            "csl_issue3_finite_action_report" in graph["dependency_targets"],
            "Release CMake graph differs")
    target = next((t for t in graph["targets"] if t.get("name") ==
                   "csl_issue3_finite_action_report"), None)
    require(target is not None and
            any(a.get("path") == "Release/csl_issue3_finite_action_report.exe"
                for a in target["artifacts"]) and
            any(c.get("languageStandard", {}).get("standard") == "20" and
                {"NDEBUG", 'CSL_ISSUE3_HARNESS_COMMIT="' + HARNESS + '"',
                 'CSL_ISSUE3_FIXTURE_SHA256="' + FIXTURE_SHA256 + '"'} <=
                {d["define"] for d in c.get("defines", [])}
                for c in target["compileGroups"]),
            "Release target/NDEBUG/C++20/embedded identities differ")
    require(fresh["source_commit"] == SOURCE and fresh["harness_commit"] == HARNESS and
            fresh["return_code"] == 0 and fresh["timed_out"] is False and
            fresh["stderr"] == "" and
            "/D NDEBUG" in fresh["stdout"] and "/std:c++20" in fresh["stdout"],
            "fresh Release build record differs")
    for name in ("configure", "fresh-build", "smoke", "smoke-check", "accepted"):
        process = strict_json(evidence(bundle, name + ".process.json"))
        require(process["schema"] == "csl.issue3-process-capture/1" and
                process["return_code"] == 0 and process["timed_out"] is False and
                process["stdout_sha256"] == sha(evidence(bundle, name + ".stdout")) and
                process["stderr_sha256"] == sha(evidence(bundle, name + ".stderr")),
                name + " process capture differs")
        if name == "accepted":
            require(process["command"][-2:] == ["--measure", "7"] and
                    process["command"][0].endswith("csl_issue3_finite_action_report.exe"),
                    "accepted command differs from reviewed measurement protocol")
        if name == "smoke":
            require(process["command"][-1] == "--smoke", "smoke command differs")
    final = strict_json(evidence(bundle, "process-capture.json"))
    require(final["schema"] == "csl.issue3-process-capture/1" and
            final["return_code"] == 0 and final["timed_out"] is False and
            final["stdout_sha256"] == RAW_SHA256 and
            final["stderr_sha256"] == sha(b"") and
            evidence(bundle, "accepted.stderr") == b"" and
            evidence(bundle, "smoke.stderr") == b"" and
            evidence(bundle, "smoke-check.stderr") == b"" and
            status == {"schema": "csl.issue3-collection-status/1", "status": "complete",
                       "trial_count": 64, "warmup_count": 8, "measured_count": 56,
                       "raw_sha256": RAW_SHA256},
            "accepted process/status identity differs")
    raw = evidence(bundle, "accepted.stdout")
    require(sha(raw) == RAW_SHA256, "accepted raw JSONL pin differs")
    smoke = parse_rows(evidence(bundle, "smoke.stdout"))
    require([row["fixture"] for row in smoke] == list(NAMES), "smoke catalogue differs")
    for row in smoke:
        require(row["schema"] == "csl.issue3-raw-trial/1" and
                row["source_commit"] == SOURCE and row["harness_commit"] == HARNESS and
                row["fixture_sha256"] == FIXTURE_SHA256 and
                row["batch"] == row["checked_calls"] == 1 and
                row["elapsed_ns"] > 0 and row["checks"]["absolute_tolerance"] ==
                (1e-8 if row["fixture"] == "b08_rounded" else 0),
                "smoke identity or work count differs")
        check_inputs(row)
        check_result(row["fixture"], row)
    rows = parse_rows(raw)
    require(len(rows) == 64, "accepted raw trial count differs")
    by_smoke = {row["fixture"]: row for row in smoke}
    retained = ("input_canonical", "input_sha256", "problem_id", "request_id", "limits",
                "objective_convention", "assurance", "plan_count", "evaluated_terminal_rows")
    for round_no in range(8):
        group = rows[8 * round_no:8 * round_no + 8]
        require([row["fixture"] for row in group] ==
                (list(NAMES) if round_no % 2 == 0 else list(reversed(NAMES))),
                "alternating round/fixture order differs")
        for row in group:
            fixture = row["fixture"]
            batch = 1 if fixture == "b08_rounded" else 10000 if fixture == "l19" else 5000
            require(row["schema"] == "csl.issue3-raw-trial/1" and
                    row["source_commit"] == SOURCE and row["harness_commit"] == HARNESS and
                    row["fixture_sha256"] == FIXTURE_SHA256 and
                    row["round"] == round_no and row["warmup"] is (round_no == 0) and
                    row["batch"] == row["checked_calls"] == batch and
                    type(row["elapsed_ns"]) is int and row["elapsed_ns"] >= 20_000_000 and
                    all(row[field] == by_smoke[fixture][field] for field in retained),
                    fixture + " raw identity/work/interval differs")
            check_inputs(row)
            check_result(fixture, row)
    return rows, pre


def record_from(bundle: Path) -> dict:
    rows, pre = validate_evidence(bundle)
    summary = []
    for fixture in NAMES:
        trials = [r for r in rows if r["fixture"] == fixture and not r["warmup"]]
        times = [r["elapsed_ns"] for r in trials]
        reference = trials[0]
        require(len(trials) == 7 and all(r["result"] == reference["result"] for r in trials),
                fixture + " trial group or checked result differs")
        summary.append({"fixture": fixture, "batch_checked_calls": reference["batch"],
                        "measured_batches": 7, "failed_batches": 0,
                        "status": reference["result"]["status"],
                        "result": reference["result"],
                        "input_sha256": reference["input_sha256"],
                        "median_batch_ns": statistics.median(times),
                        "min_batch_ns": min(times), "max_batch_ns": max(times)})
    return {"schema": SCHEMA, "report_id": REPORT_ID,
            "source_commit": SOURCE, "harness_commit": HARNESS,
            "source_tree": SOURCE_TREE, "harness_tree": HARNESS_TREE,
            "fixture_sha256": FIXTURE_SHA256, "binary_sha256": BINARY_SHA256,
            "raw_sha256": RAW_SHA256, "preflight": pre,
            "warmups": 8, "measured_batches": 56, "failed_batches": 0,
            "timing_scope": ("Per batch: fixture construction, fresh public finite_action_minimax "
                             "calls, literal checks and result construction; excludes process startup, "
                             "JSONL serialization, persistence, plotting and rendering."),
            "performance_conclusion": "Inconclusive: one adapter, no comparator or source-mapped limiter.",
            "concurrent_work_note": ("Other project worktrees had active local builds/tests during "
                                     "collection; host contention may affect batch durations."),
            "summary": summary}


def csv_bytes(fields: list[str], rows: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def svg_bytes(summary: list[dict]) -> bytes:
    # These are batch durations with different call counts; the graphic labels every batch.
    max_ms = max(row["max_batch_ns"] for row in summary) / 1e6
    lines = ['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="410" viewBox="0 0 900 410" role="img" aria-label="Median verified batch duration by fixture; batches have different call counts">',
             '<title>Verified batch durations (not comparable per-call latency)</title>',
             '<rect width="900" height="410" fill="white"/>',
             '<text x="20" y="26" font-size="18">Median verified batch duration, ms</text>']
    for index, row in enumerate(summary):
        y = 52 + index * 43
        width = 480 * (row["median_batch_ns"] / 1e6) / max_ms
        lines += [f'<text x="20" y="{y + 17}" font-size="12">{escape(row["fixture"])} ({row["batch_checked_calls"]} calls)</text>',
                  f'<rect x="330" y="{y}" width="{width:.2f}" height="24" fill="#28688b"/>',
                  f'<text x="{345 + width:.2f}" y="{y + 17}" font-size="12">{row["median_batch_ns"] / 1e6:.3f} ms</text>']
    lines += ['<text x="20" y="400" font-size="12">Different batch sizes; no cross-fixture speed comparison or single-call latency inference.</text>', '</svg>']
    return ("\n".join(lines) + "\n").encode("utf-8")


def html_bytes(record: dict) -> bytes:
    rows = record["summary"]
    pre = record["preflight"]
    table = "".join('<tr><th scope="row">' + escape(r["fixture"]) + '</th><td>' +
                    escape(r["status"]) + '</td><td>' + str(r["batch_checked_calls"]) +
                    '</td><td>' + str(r["measured_batches"]) + '</td><td>' +
                    f'{r["median_batch_ns"] / 1e6:.3f}' + '</td><td>' +
                    f'{r["min_batch_ns"] / 1e6:.3f}–{r["max_batch_ns"] / 1e6:.3f}' +
                    '</td><td><code>' + escape(r["input_sha256"]) + '</code></td></tr>' for r in rows)
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Finite-action minimax: checked catalogue batches</title><style>'
            'body{font:16px system-ui,sans-serif;max-width:1120px;margin:2rem auto;padding:0 1rem;color:#172737}'
            'table{border-collapse:collapse;width:100%}th,td{border:1px solid #b8c7d2;padding:.5rem;text-align:left;vertical-align:top}'
            'code{overflow-wrap:anywhere}figure{margin:1.5rem 0}svg{max-width:100%}'
            '</style></head><body><h1>Finite-action minimax: checked catalogue batches</h1>'
            '<p><strong>Performance conclusion: inconclusive.</strong> One numerical adapter was measured without a comparator or source-mapped limiter. The eight fixtures use different batch sizes; the timings do not establish a speedup or single-call latency.</p>'
            '<p>Frozen algorithm source <code>' + SOURCE + '</code>; reviewed harness <code>' + HARNESS +
            '</code>. Release MSVC/C++20, binary64 numerical assurance. One excluded warmup and seven measured batches per fixture, 56 measured batches in all; zero failed checked batches.</p>'
            '<p>Host: ' + escape(pre["processor"]) + ', ' + escape(pre["os"]) +
            '; ' + str(pre["logical_processors"]) + ' logical processors. Compiler: ' +
            escape(pre["compiler"]["compiler"]["id"]) + ' ' +
            escape(pre["compiler"]["compiler"]["version"]) +
            '; CMake generator: ' + escape(pre["cmake"]["generator"]) +
            '. Each public call is checked; process/runtime caches may be warm after the excluded warmup.</p>'
            '<p>The timed interval includes fresh public calls, fixture construction, literal result checks and result construction. It excludes process startup, JSONL serialization, disk persistence, plotting and HTML rendering. Native thread count and internal phase counters were unavailable; one driver worker was requested. Other project worktrees had active local builds/tests during collection, so host contention may affect these exploratory durations.</p>'
            '<h2>Verified outcomes and batch durations</h2><table><thead><tr><th scope="col">Fixture</th><th scope="col">Status</th><th scope="col">Checked calls per batch</th><th scope="col">Measured batches</th><th scope="col">Median batch ms</th><th scope="col">Batch range ms</th><th scope="col">Input SHA-256</th></tr></thead><tbody>' + table + '</tbody></table>'
            '<figure aria-label="Batch durations"><a href="latency.svg">Open standalone SVG batch chart</a><figcaption>Each bar is a median batch duration. Call counts differ by fixture.</figcaption></figure>'
            '<h2>Scientific scope</h2><p>L19 checks two one-step actions and endpoint maximizers at 0 and 2; the stationary midpoint has lower objective. The integrator has a unique minimizing plan. Infeasible evidence retains both ordered violating successors. Empty catalogue, no scenarios, Unsupported and cancellation are distinct statuses and publish no optimum.</p>'
            '<p>The displayed rounded B08 four-step linear model enumerates 625 fixed open-loop plans and 256 disturbance corners per plan, 160,000 terminal evaluations. Its numerical minimum is about 67.1506011014, with plan indices 17, 33 and 129 tied within 1e-8. This does not establish the historical 67.12, unrounded or nonlinear model, feedback optimum, or validated arithmetic enclosure.</p>'
            '<h2>Saved evidence</h2><ul><li><a href="records.json">Validated report record</a></li><li><a href="trials.csv">All 64 trial rows in CSV</a></li><li><a href="summary.csv">Batch summary CSV</a></li><li><a href="evidence/accepted-001/accepted.stdout">Exact raw JSONL</a></li><li><a href="evidence/accepted-001/preflight.json">Build and host provenance</a></li><li><a href="manifest.json">Exact-byte manifest</a></li></ul>'
            '<p>All checked results, source and harness IDs, fixture/input hashes, process outcomes, and build logs are retained in the offline bundle. Publication and live URL verification follow independent saved-result review.</p></body></html>')
    return (page + "\n").encode("utf-8")


def projections(bundle: Path) -> dict[str, bytes]:
    record = record_from(bundle)
    rows = parse_rows(evidence(bundle, "accepted.stdout"))
    trials = [{"round": r["round"], "fixture": r["fixture"], "warmup": str(r["warmup"]).lower(),
               "batch_checked_calls": r["batch"], "elapsed_ns": r["elapsed_ns"],
               "status": r["result"]["status"], "checks_passed": str(r["checks"]["passed"]).lower(),
               "input_sha256": r["input_sha256"], "problem_id": r["problem_id"],
               "request_id": r["request_id"]} for r in rows]
    summary = [{k: r[k] for k in ("fixture", "status", "batch_checked_calls",
               "measured_batches", "failed_batches", "median_batch_ns", "min_batch_ns",
               "max_batch_ns", "input_sha256")} for r in record["summary"]]
    return {"records.json": encoded(record),
            "trials.csv": csv_bytes(list(trials[0]), trials),
            "summary.csv": csv_bytes(list(summary[0]), summary),
            "latency.svg": svg_bytes(record["summary"]),
            "index.html": html_bytes(record)}


def render(bundle: Path, *, check: bool) -> dict:
    bundle = Path(bundle)
    require(bundle.name == REPORT_ID and bundle.is_dir() and not bundle.is_symlink(),
            "unsafe report source identity")
    expected = projections(bundle)
    if check:
        actual = {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()}
        require(actual == SOURCE_FILES | {"manifest.json"} and
                not any(p.is_symlink() for p in bundle.rglob("*")),
                "source bundle inventory differs")
        for name, content in expected.items():
            require((bundle / name).read_bytes() == content,
                    "saved projection differs: " + name)
        manifest = strict_json((bundle / "manifest.json").read_bytes())
        require(manifest == {"schema": "csl.issue3-finite-catalogue-manifest/1",
                             "report_id": REPORT_ID,
                             "files": {name: sha((bundle / name).read_bytes())
                                       for name in sorted(SOURCE_FILES)}},
                "source manifest inventory/hash differs")
    else:
        require(not any((bundle / name).exists() for name in DERIVED | {"manifest.json"}),
                "render target already exists")
        for name, content in expected.items():
            (bundle / name).write_bytes(content)
        (bundle / "manifest.json").write_bytes(encoded({
            "schema": "csl.issue3-finite-catalogue-manifest/1", "report_id": REPORT_ID,
            "files": {name: sha((bundle / name).read_bytes()) for name in sorted(SOURCE_FILES)}}))
    return strict_json(expected["records.json"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(render(args.bundle, check=args.check)["report_id"])


if __name__ == "__main__":
    main()
