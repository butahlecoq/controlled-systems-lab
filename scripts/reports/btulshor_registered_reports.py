"""Register the immutable, saved BTULSHOR source-faithful comparison bundle."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import registered_reports as common
import report_data
import stage_btulshor

KIND = "btulshor-source-faithful"
SOURCE_ID = "btulshor-source-faithful-20261110-v1"
SOURCE_PATTERN = re.escape(SOURCE_ID)
PUBLIC_PATTERN = r"btulshor-source-faithful-[0-9a-f]{64}"
PAYLOAD_SCHEMA = stage_btulshor.SCHEMA
LIMITS = ("Source-faithful legacy implementation compared with independent methods on the saved fixture set; "
          "exact-check outcomes are preserved per fixture, including near-tolerance failures; timings are "
          "descriptive observations and establish no performance winner.")


def artifact_links(report_id: str, ref: str = "main") -> tuple[str, str, str]:
    label = report_data.artifact_reference(ref)
    if not isinstance(report_id, str) or (report_id != SOURCE_ID and
            re.fullmatch(PUBLIC_PATTERN, report_id) is None):
        raise ValueError("unsafe BTULSHOR report identity")
    base = "https://github.com/butahlecoq/controlled-systems-lab/"
    path = "/reports/algorithm-results/" + report_id
    return base + "tree/" + ref + path, base + "blob/" + ref + path + ".zip", label


def _json_bytes(data: bytes, label: str) -> dict:
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON in BTULSHOR {label}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"BTULSHOR {label} must be a JSON object")
    return value


def _validate_comparisons(bundle: Path, files: dict[str, bytes], manifest_bytes: bytes) -> tuple[dict, str]:
    raw = {name: _json_bytes(data, name) for name, data in files.items()
           if name.startswith("raw/") and name.endswith(".json")}
    if not raw:
        raise ValueError("BTULSHOR bundle has no raw comparison records")
    summary_name = "raw/summary.json" if "raw/summary.json" in raw else "summary.json"
    summary = raw.get(summary_name)
    if summary is None:
        raise ValueError("BTULSHOR bundle must include raw/summary.json")
    if summary.get("schema") != "csl.btulshor-summary/1":
        raise ValueError("unsupported BTULSHOR comparison summary schema")
    manifest = _json_bytes(manifest_bytes, "manifest")
    commit = manifest.get("capture_source_commit")
    if summary.get("source_commit", summary.get("capture_source_commit")) != commit:
        raise ValueError("BTULSHOR summary source commit differs from native manifest")
    comparison_files = summary.get("comparison_files")
    if (not isinstance(comparison_files, dict) or not comparison_files or
            any(not isinstance(fixture, str) or not isinstance(name, str) or
                name not in raw or name.startswith("raw/runs/") or
                raw[name].get("fixture_id") != fixture for fixture, name in comparison_files.items()) or
            len(set(comparison_files.values())) != len(comparison_files)):
        raise ValueError("BTULSHOR summary aggregate comparison links differ from raw inventory")
    providers = set()
    fixture_ids = set()
    saw_near_tolerance = False
    aggregates = {fixture: raw[name] for fixture, name in comparison_files.items()}
    for name in comparison_files.values():
        document = raw[name]
        if document.get("schema") != "csl.btulshor-comparison/1":
            raise ValueError(f"unsupported raw BTULSHOR comparison schema: {name}")
        if not isinstance(document.get("fixture_id"), str) or not document["fixture_id"]:
            raise ValueError(f"raw BTULSHOR fixture identity missing: {name}")
        fixture_ids.add(document["fixture_id"])
        dimension, points = document.get("dimension"), document.get("input_points")
        if not isinstance(dimension, int) or dimension < 2 or not isinstance(points, list) or not points:
            raise ValueError(f"raw BTULSHOR comparison input is invalid: {name}")
        if document.get("input_count") != len(points) or any(
                not isinstance(point, list) or len(point) != dimension for point in points):
            raise ValueError(f"raw BTULSHOR comparison dimensions differ: {name}")
        provenance = document.get("provenance")
        if not isinstance(provenance, dict) or provenance.get("source_commit") != commit:
            raise ValueError(f"raw BTULSHOR provenance differs from native source commit: {name}")
        listed = document.get("providers")
        if not isinstance(listed, list) or not listed:
            raise ValueError(f"raw BTULSHOR methods missing: {name}")
        method_ids = set()
        for provider in listed:
            if not isinstance(provider, dict) or not isinstance(provider.get("method_id"), str):
                raise ValueError(f"invalid BTULSHOR method record: {name}")
            method = provider["method_id"]
            if method in method_ids:
                raise ValueError(f"duplicate BTULSHOR method in {name}: {method}")
            method_ids.add(method)
            if not isinstance(provider.get("status"), str):
                raise ValueError(f"BTULSHOR method status missing: {name}/{method}")
            exact = provider.get("exact_check")
            if exact is not None and (not isinstance(exact, dict) or
                    exact.get("status") not in ("verified", "rejected", "inconclusive", "not_applicable") or
                    "hull_equal" not in exact or "irredundancy" not in exact):
                raise ValueError(f"BTULSHOR exact-check record incomplete: {name}/{method}")
            samples = provider.get("elapsed_ns_samples")
            if samples is not None and (not isinstance(samples, list) or len(samples) != 5 or
                                        any(not isinstance(value, int) or value < 0 for value in samples)):
                raise ValueError(f"BTULSHOR measured timing needs five nonnegative integer samples: {name}/{method}")
            sample_statuses = provider.get("sample_statuses")
            if not isinstance(sample_statuses, list) or len(sample_statuses) != 5:
                raise ValueError(f"BTULSHOR sample statuses need five entries: {name}/{method}")
            exact_samples = provider.get("exact_check_samples")
            if not isinstance(exact_samples, list) or len(exact_samples) != 5:
                raise ValueError(f"BTULSHOR exact-check samples need five entries: {name}/{method}")
            elapsed = provider.get("elapsed_ns")
            if elapsed is not None and (not isinstance(elapsed, int) or elapsed < 0):
                raise ValueError(f"BTULSHOR elapsed_ns is invalid: {name}/{method}")
            providers.add(method)
            saw_near_tolerance |= document.get("fixture_id") == "near-tolerance"
    if not saw_near_tolerance:
        raise ValueError("BTULSHOR near-tolerance fixture must remain in raw evidence")
    if (summary.get("build_config") != "Release" or summary.get("sample_count_per_fixture") != 5 or
            not isinstance(summary.get("compiler_id"), str) or not summary["compiler_id"] or
            not isinstance(summary.get("compiler_version"), str) or not summary["compiler_version"] or
            set(summary.get("fixture_ids", [])) != fixture_ids or
            not isinstance(summary.get("method_ids"), list) or
            not providers <= set(summary["method_ids"])):
        raise ValueError("BTULSHOR summary capture metadata differs from raw fixtures")
    for field in ("method_statuses", "exact_checks", "elapsed_ns_samples"):
        mapping = summary.get(field)
        if not isinstance(mapping, dict) or set(mapping) != fixture_ids:
            raise ValueError(f"BTULSHOR summary {field} fixture inventory differs")
        for fixture, methods in mapping.items():
            if not isinstance(methods, dict) or not providers <= set(methods):
                raise ValueError(f"BTULSHOR summary {field} methods are incomplete: {fixture}")
            for method in providers:
                values = methods[method]
                if not isinstance(values, list) or len(values) != 5:
                    raise ValueError(f"BTULSHOR summary {field} needs five samples: {fixture}/{method}")
    runs = summary.get("driver_runs")
    if not isinstance(runs, list) or len(runs) != 5 * len(fixture_ids):
        raise ValueError("BTULSHOR summary must record five driver runs per fixture")
    run_keys = set()
    run_paths = set()
    for run in runs:
        if not isinstance(run, dict) or run.get("fixture_id") not in fixture_ids or run.get("sample") not in range(1, 6):
            raise ValueError("BTULSHOR driver-run identity is malformed")
        key = (run["fixture_id"], run["sample"])
        if key in run_keys:
            raise ValueError("BTULSHOR driver-run identity is duplicated")
        run_keys.add(key)
        path = run.get("path")
        if path in run_paths:
            raise ValueError("BTULSHOR driver-run file is reused")
        run_paths.add(path)
        if path not in files or not path.startswith("raw/runs/"):
            raise ValueError("BTULSHOR driver-run file is missing from native inventory")
        run_doc = _json_bytes(files[path], path)
        if run_doc.get("schema") != "csl.btulshor-comparison/1" or run_doc.get("fixture_id") != run["fixture_id"]:
            raise ValueError("BTULSHOR driver-run content does not match its index")
        run_providers = run_doc.get("providers")
        if not isinstance(run_providers, list) or any(not isinstance(item, dict) for item in run_providers):
            raise ValueError("BTULSHOR driver-run providers are malformed")
        actual_order = [item.get("method_id") for item in run_providers]
        if (not isinstance(run.get("provider_order"), list) or
                run.get("provider_order") != run_doc.get("provider_order") or
                run["provider_order"] != actual_order or len(actual_order) != len(providers) or
                set(actual_order) != providers):
            raise ValueError("BTULSHOR driver-run provider order is incomplete")
        fixture = run["fixture_id"]
        aggregate = aggregates[fixture]
        if any(run_doc.get(field) != aggregate.get(field) for field in
               ("dimension", "input_count", "input_points", "provenance")):
            raise ValueError("BTULSHOR driver-run inputs or provenance differ from aggregate")
        sample_index = run["sample"] - 1
        aggregate_providers = {item["method_id"]: item for item in aggregate["providers"]}
        for item in run_providers:
            method = item["method_id"]
            elapsed = item.get("elapsed_ns")
            if elapsed is not None and (isinstance(elapsed, bool) or not isinstance(elapsed, int) or elapsed < 0):
                raise ValueError("BTULSHOR driver-run timing is invalid")
            derived = aggregate_providers[method]
            if (item.get("status") != derived["sample_statuses"][sample_index] or
                    item.get("status") != summary["method_statuses"][fixture][method][sample_index] or
                    elapsed != summary["elapsed_ns_samples"][fixture][method][sample_index] or
                    derived["exact_check_samples"][sample_index] != summary["exact_checks"][fixture][method][sample_index]):
                raise ValueError("BTULSHOR driver-run samples differ from derived records")
            if "elapsed_ns_samples" in derived and elapsed != derived["elapsed_ns_samples"][sample_index]:
                raise ValueError("BTULSHOR aggregate timing differs from driver run")
    auxiliary = set(raw) - {summary_name} - set(comparison_files.values()) - run_paths
    allowed_auxiliary = {"raw/oracle-differential.json", "raw/figure-export.json"}
    if not auxiliary <= allowed_auxiliary:
        raise ValueError("BTULSHOR raw evidence contains an unindexed record")
    oracle = raw.get("raw/oracle-differential.json")
    if oracle is not None and (oracle.get("source_sha256") != stage_btulshor.ORIGINAL_SOURCE_SHA256 or
            oracle.get("cases") != 45 or oracle.get("passed") != 45 or oracle.get("failed") != 0 or
            oracle.get("driver_sha256") != summary.get("driver_sha256") or
            not isinstance(oracle.get("driver_sha256"), str) or
            re.fullmatch(r"[0-9a-f]{64}", oracle["driver_sha256"]) is None):
        raise ValueError("BTULSHOR original-source differential receipt is invalid")
    return summary, commit


def adapt(bundle: Path) -> common.PublicationRecord:
    bundle = Path(bundle)
    if bundle.name != SOURCE_ID:
        raise ValueError("BTULSHOR native source identity differs")
    admitted = stage_btulshor.validate(bundle)
    manifest = admitted["manifest"]
    summary, commit = _validate_comparisons(bundle, admitted["files"], admitted["manifest_bytes"])
    native_files = {name: hashlib.sha256(data).hexdigest()
                    for name, data in admitted["files"].items()}
    native_files.update({"manifest.json": hashlib.sha256(admitted["manifest_bytes"]).hexdigest(),
                         "SHA256SUMS": hashlib.sha256(admitted["sums_bytes"]).hexdigest(),
                         stage_btulshor.ZIP_NAME: hashlib.sha256(admitted["zip_bytes"]).hexdigest()})
    publisher_bytes = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    identity = {"schema": "csl.btulshor-source-faithful-publication-identity/1",
                "source_report_id": bundle.name, "native_inventory": native_files,
                "publisher_sha256": hashlib.sha256(publisher_bytes).hexdigest()}
    report_id = KIND + "-" + common._digest(identity)
    files = tuple(sorted(set(native_files)))
    return common.PublicationRecord(KIND, report_id, common._digest(manifest), commit,
                                    "Saved multi-fixture BTULSHOR comparison; five alternating measured driver runs per fixture; "
                                    "method statuses, exact-check results, and elapsed nanoseconds retained in raw JSON.",
                                    LIMITS, files, PAYLOAD_SCHEMA,
                                    hashlib.sha256(admitted["manifest_bytes"]).hexdigest(), bundle.name)


def render_page(bundle: Path, publication: common.PublicationRecord) -> str:
    # The native page is manifest-covered. Return it byte-for-byte after decoding UTF-8.
    return (Path(bundle) / "index.html").read_bytes().decode("utf-8")


def publication_artifacts(bundle: Path, publication: common.PublicationRecord) -> dict[str, bytes]:
    admitted = stage_btulshor.validate(Path(bundle))
    envelope = {"schema": "csl.algorithm-report-envelope/1", "report_id": publication.report_id,
                "report_kind": publication.kind, "payload_schema": publication.payload_schema,
                "payload_sha256": publication.payload_sha256,
                "native_payload_sha256": publication.native_payload_sha256,
                "source_commit": publication.source_commit, "measured_scope": publication.measured_scope,
                "evidence_limits": publication.evidence_limits,
                "source_report_id": publication.source_report_id, "payload": admitted["manifest"]}
    source_files = (*admitted["files"].keys(), "manifest.json", "SHA256SUMS", stage_btulshor.ZIP_NAME)
    return common.assemble_publication(bundle, publication, page=render_page(bundle, publication),
                                       envelope=envelope, source_files=source_files)


def offline_zip(bundle: Path, publication: common.PublicationRecord) -> bytes:
    return common.publication_zip(publication.report_id, publication_artifacts(bundle, publication))


def catalogue_entry(bundle: Path) -> dict:
    publication = adapt(bundle)
    archive = offline_zip(bundle, publication)
    return {"report_id": publication.report_id, "report_kind": publication.kind,
            "source_report_id": publication.source_report_id, "payload_schema": publication.payload_schema,
            "payload_sha256": publication.payload_sha256,
            "native_payload_sha256": publication.native_payload_sha256,
            "source_commit": publication.source_commit, "measured_scope": publication.measured_scope,
            "evidence_limits": publication.evidence_limits,
            "zip_sha256": hashlib.sha256(archive).hexdigest()}
