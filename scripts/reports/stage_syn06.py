"""Saved-only, typed SYN-06 report extension for the existing Pages publisher.

The four historical report publishers are intentionally unchanged: their public
identities include hashes of their publisher source. This extension uses the
same envelope, manifest, offline ZIP and HTML/SVG safety machinery.
"""
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

_site_spec = importlib.util.spec_from_file_location("csl_report_site_v1", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(_site_spec)
_site_spec.loader.exec_module(site)

SOURCE_FILES = frozenset({
    "README.md", "build-log.txt", "build-provenance.json", "index.html", "latency.svg",
    "measurement-command.txt", "pilot.json", "pilot-raw.jsonl", "process-stderr.txt",
    "profile.json", "profile-raw.jsonl", "raw-events.jsonl", "records.json", "summary.csv", "trials.csv",
    "verifier_driver.cpp",
})
SOURCE_INVENTORY = SOURCE_FILES | {"manifest.json", "bundle.zip"}
TRIAL_FIELDS = ("fixture", "round", "warmup", "batch", "elapsed_ns", "bindings",
                "feasibility", "objective", "completeness", "recomputed_objective",
                "residual_count", "observation_token")
SUMMARY_FIELDS = ("fixture", "trials", "failures", "batch", "median_elapsed_ns",
                  "min_elapsed_ns", "max_elapsed_ns")
FIXTURES = ("valid", "violating")
SCOPE = "Original-data numerical verification of two literal two-stage integrator witnesses"
LIMITS = "Single Release adapter, no solver or optimal-family completeness claim; microbenchmark excludes resolution, setup, rendering and end-to-end use"


def digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def digest(value: object) -> str:
    return registered._digest(value)


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def local(bundle: Path, name: str) -> Path:
    require(name in SOURCE_INVENTORY and not bundle.is_symlink(), "unsafe SYN-06 source path")
    path = bundle / name
    require(path.is_file() and not path.is_symlink(), "missing or linked SYN-06 source file: " + name)
    return path


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "JSON object required: " + path.name)
    return value


def expected_fixture() -> dict:
    return {
        "name": "two-stage scalar integrator",
        "dynamics": "x[k+1] = x[k] + u[k]",
        "times": [0, 1, 2],
        "initial": [0], "terminal": [1],
        "control_bounds": [0, 1],
        "objective": {"kind": "linear_terminal", "weights": [1], "offset": 0},
        "witnesses": {
            "valid": {"states": [[0], [0.25], [1]], "controls": [[0.25], [0.75]], "objective": 1},
            "violating": {"states": [[0], [0.25], [1]], "controls": [[0.25], [1.25]], "objective": 1},
        },
    }


def raw_projection(raw: bytes, batch: int, warmups: int, repetitions: int) -> list[dict]:
    lines = raw.decode("utf-8").splitlines()
    require(len(lines) == 1 + len(FIXTURES) * (warmups + repetitions), "raw event count differs")
    events = [json.loads(line) for line in lines]
    header = events[0]
    require(header.get("event") == "header" and header.get("schema") == "csl.syn06-verifier-raw/1" and
            header.get("batch") == batch and header.get("warmups") == warmups and
            header.get("trials_per_fixture") == repetitions and
            type(header.get("timer_overhead_median_ns")) is int and header["timer_overhead_median_ns"] >= 0,
            "raw header differs")
    measured = []
    for index, event in enumerate(events[1:]):
        fixture = FIXTURES[index // (warmups + repetitions)]
        round_index = index % (warmups + repetitions)
        require(set(event) == set(TRIAL_FIELDS) | {"event"} and event["event"] == "trial" and
                event["fixture"] == fixture and event["round"] == round_index and
                event["warmup"] is (round_index < warmups) and event["batch"] == batch and
                type(event["elapsed_ns"]) is int and event["elapsed_ns"] > 0 and
                event["bindings"] == "numerical_pass" and
                event["feasibility"] == ("numerical_pass" if fixture == "valid" else "violation") and
                event["objective"] == "numerical_pass" and event["completeness"] == "unsupported" and
                event["recomputed_objective"] == 1 and event["residual_count"] == 10 and
                type(event["observation_token"]) is int and event["observation_token"] >= 0,
                "raw verifier result differs from analytic fixture")
        if round_index >= warmups:
            measured.append({field: event[field] for field in TRIAL_FIELDS})
    require(len({t["observation_token"] for t in measured if t["fixture"] == "valid"}) == 1 and
            len({t["observation_token"] for t in measured if t["fixture"] == "violating"}) == 1 and
            measured[0]["observation_token"] != measured[-1]["observation_token"],
            "verifier output consumption token differs")
    return measured


def summarize(trials: list[dict], batch: int) -> list[dict]:
    result = []
    for fixture in FIXTURES:
        group = [t for t in trials if t["fixture"] == fixture]
        values = [t["elapsed_ns"] for t in group]
        require(len(values) == 7, "seven measured repetitions required per fixture")
        result.append({"fixture": fixture, "trials": len(values), "failures": 0, "batch": batch,
                       "median_elapsed_ns": statistics.median(values),
                       "min_elapsed_ns": min(values), "max_elapsed_ns": max(values)})
    return result


def svg(summary: list[dict]) -> str:
    maximum = max(row["median_elapsed_ns"] / row["batch"] for row in summary)
    bars = []
    for index, row in enumerate(summary):
        value = row["median_elapsed_ns"] / row["batch"]
        y = 40 + index * 70
        bars.append(f'<text x="12" y="{y+20}" font-size="16">{row["fixture"]}</text>'
                    f'<rect x="110" y="{y}" width="{int(440*value/maximum)}" height="28" fill="#285f89"/>'
                    f'<text x="560" y="{y+20}" font-size="16">{value:.2f} ns/call</text>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="760" height="200" viewBox="0 0 760 200">'
            + ''.join(bars) + '</svg>\n')


def page(record: dict, figure: str) -> str:
    payload = record["payload"]
    rows = ''.join('<tr><td>' + escape(row["fixture"]) + '</td><td>' + str(row["trials"]) +
                   '</td><td>' + f'{row["median_elapsed_ns"] / row["batch"]:.2f}' +
                   '</td><td>' + f'{row["min_elapsed_ns"] / row["batch"]:.2f}' +
                   '</td><td>' + f'{row["max_elapsed_ns"] / row["batch"]:.2f}' +
                   '</td></tr>' for row in payload["summary"])
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>SYN-06 verifier results</title>'
            '</head><body><h1>SYN-06 original-data trajectory verification</h1><p>Source commit <code>' +
            escape(payload["source_commit"]) + '</code>. ' + escape(SCOPE) + '.</p><p>' + escape(LIMITS) +
            '.</p><h2>Saved Release timings</h2><p>Seven measured batches of ' + str(payload["batch"]) +
            ' calls per fixture, after seven warmup batches. Each interval contains '
            '<code>verify_trajectory</code>, report assignment and consumption of every returned report; resolution and setup '
            'are outside. Values are batch elapsed time divided by calls, in nanoseconds per call. '
            'No comparator or speedup is claimed.</p><table><thead><tr><th>Witness</th><th>Trials</th>'
            '<th>Median ns/call</th><th>Min ns/call</th><th>Max ns/call</th></tr></thead><tbody>' +
            rows + '</tbody></table><figure aria-label="Verifier timings">' + figure +
            '</figure><h2>Analytic outputs</h2><p>The valid witness passes original transitions, domains '
            'and objective. The deliberately altered final control violates an original domain and transition. '
            'Both retain unsupported optimal-family completeness and validated-proof claims.</p><p>Hardware, '
            'compiler, pilot, timer overhead, and separate limiter observations are in the raw records and '
            'sidecars. Setup, end-to-end latency, and internal phase counters were not measured.</p><ul>'
            '<li><a href="records.json">Raw record</a></li><li><a href="raw-events.jsonl">All raw events</a>'
            '</li><li><a href="trials.csv">Trials CSV</a></li><li><a href="summary.csv">Summary CSV</a>'
            '</li><li><a href="profile.json">Separate limiter profile</a></li></ul></body></html>')


def csv_bytes(fields: tuple[str, ...], rows: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def validate(bundle: Path) -> registered.PublicationRecord:
    bundle = Path(bundle)
    require(re.fullmatch(r"syn06-verifier-\d{8}-[0-9a-f]{8}", bundle.name) is not None,
            "unsafe SYN-06 native identity")
    require(bundle.is_dir() and not bundle.is_symlink(), "SYN-06 source directory required")
    require({path.name for path in bundle.iterdir()} == SOURCE_INVENTORY and
            all(path.is_file() and not path.is_symlink() for path in bundle.iterdir()),
            "SYN-06 exact source inventory differs")
    manifest = read_json(local(bundle, "manifest.json"))
    require(manifest.get("schema") == "csl.syn06-source-manifest/1" and
            manifest.get("report_id") == bundle.name and set(manifest.get("files", {})) == SOURCE_FILES,
            "SYN-06 source manifest differs")
    for name, expected in manifest["files"].items():
        require(re.fullmatch(r"[0-9a-f]{64}", str(expected)) is not None and
                digest_bytes(local(bundle, name).read_bytes()) == expected,
                "SYN-06 source hash differs: " + name)
    native = registered.publication_zip(bundle.name,
                                        {name: local(bundle, name).read_bytes() for name in SOURCE_FILES | {"manifest.json"}})
    require(local(bundle, "bundle.zip").read_bytes() == native, "SYN-06 native ZIP differs")
    record = read_json(local(bundle, "records.json"))
    payload = record.get("payload")
    require(isinstance(payload, dict) and record.get("schema") == "csl.syn06-verifier-report/1" and
            record.get("report_id") == bundle.name and payload.get("schema") == record["schema"] and
            record.get("payload_sha256") == digest(payload), "SYN-06 record envelope differs")
    source = payload.get("source_commit")
    require(isinstance(source, str) and re.fullmatch(r"[0-9a-f]{40}", source) and
            bundle.name.endswith(source[:8]) and payload.get("fixture") == expected_fixture() and
            payload.get("module") == {"id": "csl.trajectory.original", "version": "1"} and
            payload.get("numerical") == {"absolute": 1e-8, "relative": 1e-8} and
            payload.get("workers") == {"requested": 1, "actual": 1, "native_threads": 1},
            "SYN-06 source/fixture/module contract differs")
    batch, warmups, repetitions = (payload.get(key) for key in ("batch", "warmups", "repetitions"))
    require(type(batch) is int and 1000 <= batch <= 10000000 and warmups == 7 and repetitions == 7,
            "SYN-06 repetition contract differs")
    raw = local(bundle, "raw-events.jsonl").read_bytes()
    require(payload.get("raw_sha256") == digest_bytes(raw), "SYN-06 raw evidence hash differs")
    trials = raw_projection(raw, batch, warmups, repetitions)
    require(payload.get("trials") == trials and payload.get("summary") == summarize(trials, batch),
            "SYN-06 saved trial/summary projection differs")
    require(local(bundle, "trials.csv").read_bytes() == csv_bytes(TRIAL_FIELDS, trials) and
            local(bundle, "summary.csv").read_bytes() == csv_bytes(SUMMARY_FIELDS, payload["summary"]),
            "SYN-06 CSV differs from validated records")
    for name, key in (("build-provenance.json", "build_sha256"), ("build-log.txt", "build_log_sha256"),
                      ("pilot.json", "pilot_sha256"),
                      ("profile.json", "profile_sha256"), ("process-stderr.txt", "stderr_sha256"),
                      ("measurement-command.txt", "command_sha256")):
        require(payload.get(key) == digest_bytes(local(bundle, name).read_bytes()),
                "SYN-06 sidecar digest differs: " + name)
    build = read_json(local(bundle, "build-provenance.json"))
    driver = local(bundle, "verifier_driver.cpp")
    require(build.get("source_commit") == source and build.get("configuration") == "Release" and
            build.get("driver_sha256") == digest_bytes(driver.read_bytes()),
            "SYN-06 build provenance differs")
    pilot = read_json(local(bundle, "pilot.json"))
    require(pilot.get("selected_batch") == batch and isinstance(pilot.get("observations"), list) and
            pilot["observations"] and all(type(row.get("elapsed_ns")) is int and row["elapsed_ns"] > 0
                                          for row in pilot["observations"]) and
            pilot.get("raw_sha256") == digest_bytes(local(bundle, "pilot-raw.jsonl").read_bytes()),
            "SYN-06 pilot differs")
    profile = read_json(local(bundle, "profile.json"))
    require(profile.get("purpose") == "non-report limiter observation" and
            profile.get("source_commit") == source and
            profile.get("raw_sha256") == digest_bytes(local(bundle, "profile-raw.jsonl").read_bytes()),
            "SYN-06 limiter profile differs")
    figure = local(bundle, "latency.svg").read_bytes()
    report_data.validate_svg(figure)
    require(figure == svg(payload["summary"]).encode("utf-8"), "SYN-06 figure differs from records")
    html = local(bundle, "index.html").read_text(encoding="utf-8")
    site.OfflineHTML(SOURCE_INVENTORY).feed(html)
    require(html == page(record, figure.decode("utf-8")), "SYN-06 HTML differs from records")
    publisher = {name: digest_bytes((Path(__file__).parent / name).read_bytes())
                 for name in ("stage_syn06.py", "registered_reports.py")}
    identity = {"schema": "csl.syn06-publication-identity/1", "source_report_id": bundle.name,
                "files": {name: digest_bytes(local(bundle, name).read_bytes()) for name in sorted(SOURCE_INVENTORY)},
                "publisher": publisher}
    report_id = bundle.name.rsplit("-", 1)[0] + "-" + digest(identity)
    return registered.PublicationRecord("syn06-verifier", report_id, digest(payload), source, SCOPE, LIMITS,
                                        tuple(sorted(SOURCE_INVENTORY)), payload["schema"],
                                        source_report_id=bundle.name)


def catalogue_entry(bundle: Path) -> dict:
    item = validate(bundle)
    artifacts = registered.publication_artifacts(bundle, item, local(bundle, "index.html").read_bytes())
    archive = registered.publication_zip(item.report_id, artifacts)
    return {"report_id": item.report_id, "report_kind": item.kind,
            "source_report_id": item.source_report_id, "payload_schema": item.payload_schema,
            "payload_sha256": item.payload_sha256, "source_commit": item.source_commit,
            "measured_scope": item.measured_scope, "evidence_limits": item.evidence_limits,
            "zip_sha256": digest_bytes(archive)}


def stage(catalogue_path: Path, site_dir: Path) -> str:
    catalogue = read_json(catalogue_path)
    require(catalogue.get("schema") == "csl.syn06-report-extension/1" and
            isinstance(catalogue.get("reports"), list) and len(catalogue["reports"]) == 1,
            "SYN-06 extension catalogue differs")
    source_id = catalogue["reports"][0].get("source_report_id")
    require(isinstance(source_id, str) and re.fullmatch(r"syn06-verifier-\d{8}-[0-9a-f]{8}", source_id),
            "unsafe SYN-06 catalogue source")
    bundle = catalogue_path.parent / source_id
    expected = catalogue_entry(bundle)
    require(catalogue["reports"][0] == expected, "SYN-06 catalogue differs from source")
    item = validate(bundle)
    artifacts = registered.publication_artifacts(bundle, item, local(bundle, "index.html").read_bytes())
    archive = registered.publication_zip(item.report_id, artifacts)
    require(digest_bytes(archive) == expected["zip_sha256"], "SYN-06 public ZIP differs")
    destination = site_dir / item.report_id
    require(site_dir.is_dir() and not site_dir.is_symlink() and not destination.exists(),
            "SYN-06 destination must be a fresh route in a staged site")
    destination.mkdir()
    for name, content in artifacts.items():
        (destination / name).write_bytes(content)
    registered.validate_publication_manifest(destination, expected)
    (site_dir / (item.report_id + ".zip")).write_bytes(archive)
    original = (site_dir / "index.html").read_text(encoding="utf-8")
    require(original.count("</ul>") == 1 and item.report_id not in original,
            "SYN-06 catalogue index insertion point differs")
    link = ('<li><a href="' + escape(item.report_id) + '/index.html">' + escape(item.report_id) +
            '</a> — ' + escape(SCOPE) + '; <a href="' + escape(item.report_id) +
            '/records.json">raw JSON</a> · <a href="' + escape(item.report_id) +
            '.zip">offline ZIP</a></li>')
    (site_dir / "index.html").write_text(original.replace("</ul>", link + "</ul>"), encoding="utf-8")
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
        print(json.dumps({"schema": "csl.syn06-report-extension/1", "reports": [catalogue_entry(args.source)]},
                         ensure_ascii=False, sort_keys=True, indent=2))
    elif args.catalog is not None and args.site is not None and args.source is None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("pass --source for catalogue generation, or --catalog and --site for staging")


if __name__ == "__main__":
    main()
