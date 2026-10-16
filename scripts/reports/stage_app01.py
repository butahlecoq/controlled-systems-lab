"""Validate and stage one saved APP-01 public plan-check measurement bundle."""
from __future__ import annotations

import argparse
import csv
import hashlib
from html import escape
import importlib.util
import io
import json
from pathlib import Path
import re
import statistics

import registered_reports as registered
import report_data

_spec = importlib.util.spec_from_file_location("csl_report_site_v1", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(site)

FIXTURES = ("valid_plan", "invalid_plan", "empty_inner")
SCOPE = "Registered inner state-plan check and original-problem trajectory verification on three literal scalar fixtures"
LIMITS = ("Binary64 supplied examples only; value 3 is conditional on original-problem verification. "
          "No validated inclusion, optimality, reachable-set completeness, comparator, speedup, or established performance limiter")
FIELDS = ("fixture", "round", "warmup", "batch", "elapsed_ns", "checked_calls", "failures",
          "basis", "membership", "bindings", "feasibility", "objective", "validated",
          "recomputed_objective", "numerical_achievable_value", "residual_count", "observation_token")
SUMMARY = ("fixture", "trials", "checked_calls", "failures", "batch", "median_elapsed_ns", "min_elapsed_ns", "max_elapsed_ns")
FILES = frozenset({"README.md", "build-graph.json", "build-log.txt", "build-provenance.json",
                   "configure-log.txt", "index.html", "latency.svg", "measurement-command.txt",
                   "pilot.json", "pilot-raw.jsonl", "profile.json", "profile-raw.jsonl",
                   "process-stderr.txt", "raw-events.jsonl", "records.json", "trials.csv", "summary.csv",
                   "plan_driver.cpp", "plan-driver.bin"})
INVENTORY = FILES | {"manifest.json", "bundle.zip"}


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()


def digest(value: object) -> str:
    return registered._digest(value)


def csv_bytes(fields: tuple[str, ...], rows: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows({field: row[field] for field in fields} for row in rows)
    return stream.getvalue().encode()


def local(bundle: Path, name: str) -> Path:
    require(name in INVENTORY and not bundle.is_symlink(), "unsafe APP-01 source path")
    path = bundle / name
    require(path.is_file() and not path.is_symlink(), "missing or linked APP-01 source file: " + name)
    return path


def read_json(path: Path) -> dict:
    value = report_data.parse_json(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "JSON object required: " + path.name)
    return value


def expected_profile(name: str) -> dict:
    if name == "valid_plan":
        return dict(basis="h_point_containment", membership="numerical_pass", bindings="numerical_pass",
                    feasibility="numerical_pass", objective="numerical_pass", validated="unsupported",
                    recomputed_objective=3, numerical_achievable_value=3, residual_count=4)
    if name == "invalid_plan":
        return dict(basis="h_point_containment", membership="numerical_pass", bindings="numerical_pass",
                    feasibility="violation", objective="numerical_pass", validated="unsupported",
                    recomputed_objective=3, numerical_achievable_value=None, residual_count=4)
    if name == "empty_inner":
        return dict(basis="empty_subset", membership="violation", bindings="not_checked",
                    feasibility="not_checked", objective="not_checked", validated="not_checked",
                    recomputed_objective=None, numerical_achievable_value=None, residual_count=0)
    raise ValueError("unknown APP-01 fixture")


def raw_projection(raw: bytes, batch: int, warmups: int, repetitions: int) -> list[dict]:
    events = [report_data.parse_json(line) for line in raw.decode("utf-8").splitlines()]
    require(len(events) == 1 + len(FIXTURES) * (warmups + repetitions), "APP-01 raw event count differs")
    require(events[0] == {"event": "header", "schema": "csl.app01-plan-raw/1", "batch": batch,
                          "warmups": warmups, "repetitions": repetitions}, "APP-01 raw header differs")
    measured = []
    tokens = {}
    for index, event in enumerate(events[1:]):
        name = FIXTURES[index // (warmups + repetitions)]
        round_index = index % (warmups + repetitions)
        require(set(event) == set(FIELDS) | {"event"} and event["event"] == "trial" and
                event["fixture"] == name and event["round"] == round_index and
                event["warmup"] is (round_index < warmups) and event["batch"] == batch and
                type(event["elapsed_ns"]) is int and event["elapsed_ns"] > 0 and
                event["checked_calls"] == batch and event["failures"] == 0 and
                all(event.get(key) == value for key, value in expected_profile(name).items()) and
                type(event["observation_token"]) is int and event["observation_token"] >= 0,
                "APP-01 raw result differs from literal fixture")
        if round_index >= warmups:
            measured.append({field: event[field] for field in FIELDS})
            tokens.setdefault(name, set()).add(event["observation_token"])
    require(all(len(tokens.get(name, ())) == 1 for name in FIXTURES) and
            len({next(iter(tokens[name])) for name in FIXTURES}) == len(FIXTURES),
            "APP-01 result consumption differs")
    return measured


def summarize(trials: list[dict], batch: int) -> list[dict]:
    rows = []
    for name in FIXTURES:
        group = [row for row in trials if row["fixture"] == name]
        require(len(group) == 7, "seven measured APP-01 repetitions required")
        values = [row["elapsed_ns"] for row in group]
        rows.append(dict(fixture=name, trials=7, checked_calls=sum(row["checked_calls"] for row in group),
                         failures=sum(row["failures"] for row in group), batch=batch,
                         median_elapsed_ns=statistics.median(values), min_elapsed_ns=min(values),
                         max_elapsed_ns=max(values)))
    return rows


def svg(summary: list[dict]) -> str:
    per_call = [row["median_elapsed_ns"] / row["batch"] for row in summary]
    maximum = max(per_call)
    bars = []
    for index, (name, value) in enumerate(zip(FIXTURES, per_call)):
        y = 40 + index * 58
        bars.append(f'<text x="12" y="{y+20}" font-size="15">{escape(name)}</text>'
                    f'<rect x="125" y="{y}" width="{int(410*value/maximum)}" height="26" fill="#285f89"/>'
                    f'<text x="545" y="{y+20}" font-size="15">{value:.2f} ns/call</text>')
    return '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="220" viewBox="0 0 760 220">' + ''.join(bars) + '</svg>\n'


def page(record: dict, figure: str) -> str:
    payload = record["payload"]
    timings = ''.join('<tr><td>' + escape(row["fixture"]) + '</td><td>' + str(row["trials"]) +
                      '</td><td>' + str(row["checked_calls"]) + '</td><td>' + str(row["failures"]) +
                      '</td><td>' + f'{row["median_elapsed_ns"]/row["batch"]:.2f}' + '</td><td>' +
                      f'{row["min_elapsed_ns"]/row["batch"]:.2f}' + '</td><td>' +
                      f'{row["max_elapsed_ns"]/row["batch"]:.2f}' + '</td></tr>' for row in payload["summary"])
    statuses = ''.join('<tr><td>' + escape(name) + '</td>' + ''.join(
        '<td>' + escape(str(payload["status_profiles"][name][field])) + '</td>'
        for field in ("basis", "membership", "bindings", "feasibility", "objective", "validated",
                      "recomputed_objective", "numerical_achievable_value")) + '</tr>' for name in FIXTURES)
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>APP-01 plan check results</title>'
            '</head><body><h1>APP-01 registered inner state-plan check</h1><p>Clean source commit <code>' +
            escape(payload["source_commit"]) + '</code>. ' + escape(SCOPE) + '.</p><p>' + escape(LIMITS) +
            '.</p><h2>Saved Release observations</h2><p>Seven measured batches of ' + str(payload["batch"]) +
            ' calls per fixture after seven warmup batches. Each interval includes the registered public check, '
            'literal result checks, report assignment and consumption. Problem and fixture construction are outside. '
            'Values are batch elapsed time divided by calls. No comparator or speedup is claimed; source-level '
            'limiter is unestablished.</p><table><thead><tr><th>Fixture</th><th>Trials</th><th>Checked calls</th>'
            '<th>Failures</th><th>Median ns/call</th><th>Min ns/call</th><th>Max ns/call</th></tr></thead><tbody>' +
            timings + '</tbody></table><figure aria-label="APP-01 plan check timings">' + figure +
            '</figure><h2>Observed claims</h2><table><thead><tr><th>Fixture</th><th>Basis</th>'
            '<th>Membership</th><th>Bindings</th><th>Feasibility</th><th>Objective</th><th>Validated</th>'
            '<th>Original objective</th><th>Numerical achievable value</th></tr></thead><tbody>' + statuses +
            '</tbody></table><p>The valid witness has original terminal objective 3. The changed control fails '
            'original feasibility and yields no achievable value. The zero-vertex V inner set fails membership '
            'before trajectory verification. All inclusion observations use supplied binary64 data.</p>'
            '<p>Hardware, compiler, build graph, commands, raw events and separate process profile are retained. '
            'The separate profile does not establish a source-level limiter. Setup, rendering, end-to-end use and '
            'internal phase counters were not measured.</p><ul><li><a href="records.json">Record</a></li>'
            '<li><a href="raw-events.jsonl">Raw events</a></li><li><a href="trials.csv">Trials CSV</a></li>'
            '<li><a href="summary.csv">Summary CSV</a></li><li><a href="profile.json">Profile</a></li>'
            '</ul></body></html>')


def validate(bundle: Path) -> registered.PublicationRecord:
    require(re.fullmatch(r"app01-plan-\d{8}-[0-9a-f]{8}", bundle.name) is not None and
            bundle.is_dir() and not bundle.is_symlink(), "unsafe APP-01 bundle identity")
    require({path.name for path in bundle.iterdir()} == INVENTORY and
            all(path.is_file() and not path.is_symlink() for path in bundle.iterdir()),
            "APP-01 source inventory differs")
    manifest = read_json(local(bundle, "manifest.json"))
    require(manifest.get("schema") == "csl.app01-source-manifest/1" and
            manifest.get("report_id") == bundle.name and set(manifest.get("files", {})) == FILES,
            "APP-01 manifest differs")
    for name in FILES:
        require(manifest["files"][name] == sha(local(bundle, name).read_bytes()), "APP-01 hash differs: " + name)
    native = registered.publication_zip(bundle.name,
                {name: local(bundle, name).read_bytes() for name in FILES | {"manifest.json"}})
    require(native == local(bundle, "bundle.zip").read_bytes(), "APP-01 native ZIP differs")
    record = read_json(local(bundle, "records.json"))
    payload = record.get("payload")
    require(isinstance(payload, dict) and record.get("schema") == "csl.app01-plan-report/1" and
            record.get("report_id") == bundle.name and payload.get("schema") == record["schema"] and
            record.get("payload_sha256") == digest(payload), "APP-01 record envelope differs")
    source = payload.get("source_commit")
    require(isinstance(source, str) and re.fullmatch(r"[0-9a-f]{40}", source) and
            bundle.name.endswith(source[:8]) and payload.get("module") == "csl.geometry.approximation.check_inner_state_plan" and
            payload.get("fixture") == {"initial": 2, "transition": "x[1] = u[0]", "control": 3,
                                        "reference_interval": [2, 4], "objective": "x[1]", "expected_value": 3} and
            payload.get("numerical") == {"absolute": 1e-8, "relative": 1e-8} and
            payload.get("workers") == {"requested": 1, "actual": 1, "native_threads": 1},
            "APP-01 source or literal contract differs")
    batch = payload.get("batch")
    require(type(batch) is int and 1000 <= batch <= 1000000 and
            payload.get("warmups") == 7 and payload.get("repetitions") == 7,
            "APP-01 measurement contract differs")
    raw = local(bundle, "raw-events.jsonl").read_bytes()
    trials = raw_projection(raw, batch, 7, 7)
    summary = summarize(trials, batch)
    require(payload.get("raw_sha256") == sha(raw) and payload.get("trials") == trials and
            payload.get("summary") == summary and payload.get("status_profiles") ==
            {name: expected_profile(name) for name in FIXTURES}, "APP-01 saved projection differs")
    require(local(bundle, "trials.csv").read_bytes() == csv_bytes(FIELDS, trials) and
            local(bundle, "summary.csv").read_bytes() == csv_bytes(SUMMARY, summary), "APP-01 CSV differs")
    for name, key in (("build-provenance.json", "build_sha256"), ("build-graph.json", "build_graph_sha256"),
                      ("configure-log.txt", "configure_log_sha256"), ("build-log.txt", "build_log_sha256"),
                      ("pilot.json", "pilot_sha256"), ("profile.json", "profile_sha256"),
                      ("process-stderr.txt", "stderr_sha256"), ("measurement-command.txt", "command_sha256")):
        require(payload.get(key) == sha(local(bundle, name).read_bytes()), "APP-01 sidecar hash differs: " + name)
    graph = read_json(local(bundle, "build-graph.json"))
    build = read_json(local(bundle, "build-provenance.json"))
    require(build.get("schema") == "csl.app01-build-provenance/1" and
            build.get("source_commit") == source and build.get("configuration") == "Release" and
            build.get("clean_source_before_build") is True and build.get("clean_source_after_build") is True and
            build.get("driver_sha256") == sha(local(bundle, "plan_driver.cpp").read_bytes()) and
            build.get("binary_sha256") == sha(local(bundle, "plan-driver.bin").read_bytes()) and
            graph.get("schema") == "csl.app01-build-graph/1" and graph.get("source_commit") == source and
            graph.get("binary_sha256") == build.get("binary_sha256") and
            graph.get("target") == "csl_app01_plan_report" and graph.get("release_cxx20_ndebug") is True,
            "APP-01 build provenance differs")
    require(local(bundle, "process-stderr.txt").read_bytes() == b"" and
            local(bundle, "measurement-command.txt").read_text() ==
            f"{batch} 7 7 (Release driver; cwd SOURCE_ROOT)\n", "APP-01 process contract differs")
    pilot = read_json(local(bundle, "pilot.json"))
    require(pilot.get("schema") == "csl.app01-pilot/1" and pilot.get("selected_batch") == batch and
            pilot.get("raw_sha256") == sha(local(bundle, "pilot-raw.jsonl").read_bytes()),
            "APP-01 pilot differs")
    raw_projection(local(bundle, "pilot-raw.jsonl").read_bytes(), pilot["pilot_batch"], 1, 1)
    profile = read_json(local(bundle, "profile.json"))
    require(profile.get("schema") == "csl.app01-profile/1" and profile.get("source_commit") == source and
            profile.get("raw_sha256") == sha(local(bundle, "profile-raw.jsonl").read_bytes()) and
            profile.get("purpose") == "separate non-report limiter observation",
            "APP-01 profile differs")
    raw_projection(local(bundle, "profile-raw.jsonl").read_bytes(), profile["batch"], 1, 1)
    figure = local(bundle, "latency.svg").read_bytes()
    report_data.validate_svg(figure)
    require(figure == svg(summary).encode(), "APP-01 figure differs")
    html = local(bundle, "index.html").read_text(encoding="utf-8")
    site.OfflineHTML(INVENTORY).feed(html)
    require(html == page(record, figure.decode()), "APP-01 HTML differs")
    identity = {"source_report_id": bundle.name,
                "files": {name: sha(local(bundle, name).read_bytes()) for name in sorted(INVENTORY)},
                "publisher": {name: sha((Path(__file__).parent / name).read_bytes())
                              for name in ("stage_app01.py", "registered_reports.py")}}
    public_id = bundle.name.rsplit("-", 1)[0] + "-" + digest(identity)
    publication = registered.PublicationRecord("app01-plan", public_id, digest(payload), source,
                                             SCOPE, LIMITS, tuple(sorted(INVENTORY)), payload["schema"],
                                             source_report_id=bundle.name)
    return registered.preserve_historical_publication(bundle, publication,
        lambda source, item: registered.publication_zip(item.report_id,
            registered.publication_artifacts(source, item, local(source, "index.html").read_bytes())))


def catalogue_entry(bundle: Path) -> dict:
    item = validate(bundle)
    files = registered.publication_artifacts(bundle, item, local(bundle, "index.html").read_bytes())
    archive = registered.publication_zip(item.report_id, files)
    return dict(report_id=item.report_id, report_kind=item.kind, source_report_id=item.source_report_id,
                payload_schema=item.payload_schema, payload_sha256=item.payload_sha256,
                source_commit=item.source_commit, measured_scope=item.measured_scope,
                evidence_limits=item.evidence_limits, zip_sha256=sha(archive))


def stage(catalogue: Path, site_dir: Path) -> str:
    catalog = read_json(catalogue)
    require(catalog.get("schema") == "csl.app01-report-extension/1" and
            isinstance(catalog.get("reports"), list) and len(catalog["reports"]) == 1,
            "APP-01 extension catalogue differs")
    source_id = catalog["reports"][0].get("source_report_id")
    require(isinstance(source_id, str) and re.fullmatch(r"app01-plan-\d{8}-[0-9a-f]{8}", source_id),
            "unsafe APP-01 catalogue source")
    bundle = catalogue.parent / source_id
    expected = catalogue_entry(bundle)
    require(catalog["reports"][0] == expected, "APP-01 catalogue differs from source")
    item = validate(bundle)
    artifacts = registered.publication_artifacts(bundle, item, local(bundle, "index.html").read_bytes())
    archive = registered.publication_zip(item.report_id, artifacts)
    require(sha(archive) == expected["zip_sha256"] and site_dir.is_dir() and
            not site_dir.is_symlink() and not (site_dir / item.report_id).exists(),
            "APP-01 public destination differs")
    destination = site_dir / item.report_id
    destination.mkdir()
    for name, content in artifacts.items():
        (destination / name).write_bytes(content)
    registered.validate_publication_manifest(destination, expected)
    (site_dir / (item.report_id + ".zip")).write_bytes(archive)
    index = (site_dir / "index.html").read_text(encoding="utf-8")
    require(index.count("</ul>") == 1 and item.report_id not in index, "APP-01 site index differs")
    link = ('<li><a href="' + escape(item.report_id) + '/index.html">' + escape(item.report_id) +
            '</a> — ' + escape(SCOPE) + '; <a href="' + escape(item.report_id) +
            '/records.json">raw JSON</a> · <a href="' + escape(item.report_id) + '.zip">offline ZIP</a></li>')
    (site_dir / "index.html").write_text(index.replace("</ul>", link + "</ul>"), encoding="utf-8")
    site.OfflineHTML({item.report_id + "/index.html", item.report_id + "/records.json",
                      item.report_id + ".zip"}).feed(link)
    return item.report_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.source is not None and args.catalog is None and args.site is None:
        print(json.dumps({"schema": "csl.app01-report-extension/1", "reports": [catalogue_entry(args.source)]},
                         ensure_ascii=False, sort_keys=True, indent=2))
    elif args.catalog is not None and args.site is not None and args.source is None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("pass --source, or --catalog and --site")


if __name__ == "__main__":
    main()
