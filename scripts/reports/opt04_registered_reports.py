"""Registered saved-data publisher for OPT-04; never executes a solver."""
import hashlib
from html import escape
import importlib.util
from pathlib import Path
import re
import zipfile

import registered_reports as common
import report_data as data

KIND = "opt04-phase-one"
SCHEMA = "csl.opt04-phase-one-report/2"
SOURCE_PATTERN = r"opt04-\d{8}T\d{6}Z-[0-9a-f]{12}"
SOURCE_FILES = frozenset({"records.json", "stdout.jsonl", "driver-stdout.txt", "stderr.txt",
    "release-build.txt", "index.html", "performance.svg", "manifest.sha256", "bundle.zip", "bundle.zip.sha256"})
TOOLING = Path(__file__).resolve().parents[2] / "reports/algorithm-results/tooling/opt04"
# Native schema v2 has no trustworthy collection/test discriminator. Only an
# independently reviewed, exact saved bundle may cross production admission.
# Pins are reviewed against the complete saved native inventory (all ten files),
# including the producer ZIP and its checksum. Self-declared purpose/commit
# values cannot register a bundle.
REVIEWED_NATIVE_BUNDLES = {
    "opt04-20261013T172839Z-6451c4b89d3b": "238ff015f68d98e385593d844436a562317e12bb0f7cdedbe07e96af7f32bda7",
}


def _module(filename):
    spec = importlib.util.spec_from_file_location("csl_opt04_publication_" + filename[:-3], TOOLING / filename)
    if spec is None or spec.loader is None:
        raise ValueError("OPT-04 saved-data tooling is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(path):
    return data.parse_json(Path(path).read_text(encoding="utf-8"))


def _jsonl(path):
    return [data.parse_json(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _inventory(bundle):
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("unsafe OPT-04 source directory")
    actual = set()
    for path in bundle.rglob("*"):
        if path.is_symlink():
            raise ValueError("OPT-04 source evidence cannot contain symlinks")
        if path.is_file():
            actual.add(path.relative_to(bundle).as_posix())
    if actual != SOURCE_FILES:
        raise ValueError("OPT-04 native bundle inventory differs from the exact allowlist")
    # The native validator subsequently compares the complete manifest bytes and
    # ZIP inventory. Reject unsafe/duplicate manifest names before any file use.
    listed = set()
    for line in (bundle / "manifest.sha256").read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)", line)
        if match is None or match[2] not in SOURCE_FILES or match[2] in listed:
            raise ValueError("unsafe or duplicate OPT-04 native manifest path")
        listed.add(match[2])
    if listed != SOURCE_FILES - {"manifest.sha256", "bundle.zip", "bundle.zip.sha256"}:
        raise ValueError("OPT-04 manifest inventory mismatch")


def _source_hashes(bundle):
    return {name: hashlib.sha256((bundle / name).read_bytes()).hexdigest() for name in sorted(SOURCE_FILES)}


def _admit(record, source_hashes, allow_test):
    if allow_test:
        if record.get("purpose") != "test":
            raise ValueError("OPT-04 test-only admission requires explicit purpose: test")
        return
    if record.get("purpose") == "test":
        raise ValueError("OPT-04 test-only evidence cannot enter production admission")
    inventory_digest = common._digest(source_hashes)
    if REVIEWED_NATIVE_BUNDLES.get(record["report_id"]) != inventory_digest:
        raise ValueError("OPT-04 production admission requires an independently reviewed complete native inventory digest")


def _publication_id(source_id, source_hashes):
    publisher = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    identity = {"schema": "csl.registered-publication-identity/1", "source_report_id": source_id,
        "source_files": source_hashes,
        "publisher_sha256": hashlib.sha256(publisher).hexdigest()}
    return source_id.rsplit("-", 1)[0] + "-" + common._digest(identity)


def adapt(bundle, *, allow_test=False):
    """Cross the native evidence boundary before projecting publication data."""
    bundle = Path(bundle)
    try:
        _inventory(bundle)
        record = _json(bundle / "records.json")
        if not isinstance(record, dict) or record.get("schema") != SCHEMA:
            raise ValueError("unsupported OPT-04 native report schema")
        source_id = record.get("report_id")
        if not isinstance(source_id, str) or re.fullmatch(SOURCE_PATTERN, source_id) is None or source_id != bundle.name:
            raise ValueError("unsafe or mismatched OPT-04 native report identity")
        source_hashes = _source_hashes(bundle)
        _admit(record, source_hashes, allow_test)
        # Native CTest consumers import site.py without report-only packages.
        # Load the schema validator only when an admitted OPT-04 bundle needs it.
        try:
            from jsonschema import Draft202012Validator, ValidationError
        except ImportError as exc:
            raise ValueError("OPT-04 validation requires report-only jsonschema; install scripts/reports/requirements.txt") from exc
        try:
            Draft202012Validator(_json(TOOLING / "schema-v2.json")).validate(record)
        except ValidationError as exc:
            raise ValueError("OPT-04 native schema-v2 validation failed: " + exc.message) from exc
        native = _module("validate_report.py")
        native.validate_records(record)
        if record["summary"]["valid"] is not True:
            raise ValueError("OPT-04 failed, incomplete or aborted evidence is ineligible for publication; retain the native bundle privately")
        collector = _module("collect.py")
        expected_catalog = [{"id": name, **fixture, **collector.fixture_fingerprints(fixture),
            "expected_reference_status": fixture["expected_status"], "absolute_tolerance": 1e-8, "relative_tolerance": 0.0}
            for name, fixture in collector.FIXTURES.items()]
        if record["catalog"]["fixtures"] != expected_catalog:
            raise ValueError("OPT-04 catalogue differs from the five registered analytic fixtures")
        if record["algorithm"] != {"registration_id": "phase-one-bland", "version": "1"} or record["reference"] != {
                "registration_id": "highs_lp", "version": "1.0.0+highs.1.11.0"}:
            raise ValueError("OPT-04 adapter identity differs from the registered protocol")
        expected_boundaries = {
            "setup": "program publication, registration, selection, preparation and fresh workspace creation",
            "public_run": "BoundWorkspace.run",
            "verification": "independent expected outcome, candidate, equality residual and nonnegativity checks",
            "end_to_end": "fixture construction through independent verification; excludes process startup and serialization"}
        if record["measurement"]["timing_boundaries"] != expected_boundaries or record["claims"]["scope"] != "paired descriptive analytic fixtures":
            raise ValueError("OPT-04 measured scope differs from the registered protocol")
        provenance = record["provenance"]
        for key in ("source_commit", "harness_commit"):
            if re.fullmatch(r"[0-9a-f]{40}", provenance[key]) is None or provenance[key] == "0" * 40:
                raise ValueError("OPT-04 publication provenance requires a full nonzero source commit")
        native.validate_report(bundle)
        saved_rows = [*record["warmup_trials"], *record["trials"]]
        if _jsonl(bundle / "stdout.jsonl") != saved_rows:
            raise ValueError("OPT-04 stdout.jsonl projection differs from saved typed trials")
        # Parse with the shared strict JSON reader (duplicates/NaN fail), then
        # use the existing collector's pure normalization and pair projection.
        driver_rows = _jsonl(bundle / "driver-stdout.txt")
        warmups, trials, errors, missing = collector.normalize_and_pair(driver_rows)
        if errors or missing or warmups != record["warmup_trials"] or trials != record["trials"]:
            raise ValueError("OPT-04 driver output projection differs from saved typed trials")
        data.validate_svg(public_svg(record))
        scope = ("Five analytic equality/nonnegative feasibility fixtures; phase-one-bland and HiGHS reference; "
            "70 measured attempts plus 10 excluded warmups; fresh requests and workspaces; "
            "setup, BoundWorkspace.run, independent verification and input-to-verified-result timing; "
            "process startup and serialization excluded")
        original_limits = record.get("evidence_limits", [])
        if not isinstance(original_limits, list) or not all(isinstance(item, str) and item for item in original_limits):
            raise ValueError("OPT-04 evidence_limits must contain nonempty text")
        limits = "; ".join(["Descriptive five-fixture report; feasibility-numerics support remains Unestablished",
            "Unvalidated binary64 checks, no exact feasibility certificate or complete solution family",
            "No speedup, application-scale or scalability claim; limiter attribution remains unestablished",
            "Collinear-input acceptance and OPT-04 issue #29 remain outside this report", *original_limits])
        digest = common._digest(record)
        return common.PublicationRecord(KIND, _publication_id(source_id, source_hashes), digest, provenance["source_commit"],
            scope, limits, tuple(sorted(SOURCE_FILES)), SCHEMA, digest, source_id)
    except ValueError:
        raise
    except (OSError, UnicodeError, KeyError, TypeError, AttributeError, IndexError, OverflowError, zipfile.BadZipFile) as exc:
        raise ValueError("malformed OPT-04 registered report bundle") from exc


def public_svg(record):
    """Project the typed native figure into the shared SVG CSS vocabulary."""
    figure = _module("render.py").svg(record)
    figure = re.sub(r"<style>.*?</style>",
        '<style>text{font:13px system-ui,sans-serif;fill:#192735}</style>', figure)
    for name, attributes in {"axis": 'stroke="#48596a"', "grid": 'stroke="#dce3e9"',
            "range": 'stroke-width="3"', "median": 'stroke-width="8" stroke-linecap="round"'}.items():
        figure = figure.replace('class="' + name + '"', attributes)
    return figure.encode("utf-8")


def render_page(bundle, publication):
    """Render typed records under site.OfflineHTML; producer HTML is evidence."""
    record = _json(Path(bundle) / "records.json")
    rows = []
    for row in record["summary"]["rows"]:
        rows.append("<tr>" + "".join("<td>" + escape(str(row[key])) + "</td>" for key in
            ("fixture", "side", "phase", "count", "median_ns", "min_ns", "max_ns")) + "</tr>")
    links = "".join('<li><a href="source-evidence/' + name + '">' + name + '</a></li>' for name in sorted(SOURCE_FILES))
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width,initial-scale=1"><title>OPT-04 phase-I — ' + escape(publication.report_id) +
        '</title></head><body><h1>OPT-04 phase-I descriptive report</h1><p>Publication <code>' +
        escape(publication.report_id) + '</code>; native source <code>' + escape(publication.source_report_id) +
        '</code>.</p><h2>Measured scope</h2><p>' + escape(publication.measured_scope) +
        '</p><h2>Saved trial summaries</h2><table><thead><tr><th>Fixture</th><th>Side</th><th>Phase</th>'
        '<th>Count</th><th>Median ns</th><th>Min ns</th><th>Max ns</th></tr></thead><tbody>' + ''.join(rows) +
        '</tbody></table><p>Failures: ' + str(record["summary"]["failure_count"]) + '; missing: ' +
        str(record["summary"]["missing_count"]) + '. The contradictory_rows fixture retains its expected '
        'infeasible outcome; these attempts are included.</p><h2>Evidence limits</h2><p>' +
        escape(publication.evidence_limits) + '</p><p>Source commit <code>' + escape(publication.source_commit) +
        '</code>; harness commit <code>' + escape(record["provenance"]["harness_commit"]) +
        '</code>.</p><p><a href="performance.svg">Saved descriptive timing figure</a> · '
        '<a href="records.json">Typed native records</a> · <a href="stdout.jsonl">All trials and warmups</a> · '
        '<a href="report-envelope.json">Versioned envelope</a> · '
        '<a href="publication-manifest.json">Publication manifest</a></p><h2>Complete native source evidence</h2><ul>' +
        links + '</ul></body></html>')


def publication_artifacts(bundle, publication):
    bundle = Path(bundle)
    # Preserve all original bytes, including producer HTML and its own ZIP and
    # hashes. Public view files cannot replace or relabel native source evidence.
    files = {"source-evidence/" + name: (bundle / name).read_bytes() for name in publication.files}
    for name in SOURCE_FILES - {"index.html", "manifest.sha256", "bundle.zip", "bundle.zip.sha256"}:
        files[name] = (bundle / name).read_bytes()
    files["performance.svg"] = public_svg(_json(bundle / "records.json"))
    files["index.html"] = render_page(bundle, publication).encode("utf-8")
    files["report-envelope.json"] = common._json_bytes({"schema": "csl.algorithm-report-envelope/1",
        "report_id": publication.report_id, "report_kind": publication.kind, "payload_schema": publication.payload_schema,
        "payload_sha256": publication.payload_sha256, "native_payload_sha256": publication.native_payload_sha256,
        "source_report_id": publication.source_report_id, "source_commit": publication.source_commit,
        "measured_scope": publication.measured_scope, "evidence_limits": publication.evidence_limits,
        "payload": _json(bundle / "records.json")})
    files["publication-manifest.json"] = common._json_bytes({"schema": "csl.algorithm-report-publication-manifest/1",
        "report_id": publication.report_id, "report_kind": publication.kind,
        "files": {name: hashlib.sha256(files[name]).hexdigest() for name in sorted(files)}})
    return files


def offline_zip(bundle, publication):
    return common.publication_zip(publication.report_id, publication_artifacts(bundle, publication))


def validate_publication_manifest(report_dir, expected):
    return common.validate_publication_manifest(report_dir, expected)
