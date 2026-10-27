#!/usr/bin/env python3
"""Create the immutable B06 scenario-manifest correction companion without running a solver."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import scenario_contract

ROOT = Path(__file__).resolve().parents[3]
SOURCE_ID = "b06-owner-confirmed-7df01ba3af5e4c46"
CORRECTION_ID = "b06-manifest-correction-v1"
PUBLIC_SOURCE_ID = "issue6-b06-reference-761bdc6e40b93814f873f105313d1eed4f63711653aa583a16a2ddfbc67c2a82"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def build() -> Path:
    source = ROOT / "reports/algorithm-results" / SOURCE_ID
    output = ROOT / "reports/algorithm-results" / CORRECTION_ID
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing correction bundle: {output}")
    checked = __import__("subprocess").run([sys.executable,
        str(ROOT / "scripts/reports/issue6/check_capture.py"), str(source)],
        cwd=ROOT, capture_output=True, text=True)
    if checked.returncode:
        raise SystemExit("saved B06 bundle failed immutable-source audit: " + checked.stderr.strip())
    corrected_path = ROOT / "benchmarks/scenarios/b06-owner-confirmed-disturbance-v1.json"
    corrected_bytes = corrected_path.read_bytes()
    scenario_contract.validate(json.loads(corrected_bytes))
    original_bytes = (source / "scenario.json").read_bytes()
    original = json.loads(original_bytes)
    corrected = json.loads(corrected_bytes)
    original_a = original["model"]["A_row_major"]
    corrected_a = corrected["model"]["A_row_major"]
    if len(original_a) != 15 or len(corrected_a) != 16 or original_a != corrected_a[:13] + corrected_a[14:]:
        raise SystemExit("correction is not the single source-verified missing A entry")
    files = {
        "corrected-scenario.json": corrected_bytes,
        "terminal-projections.svg": (source / "terminal-projections.svg").read_bytes(),
        "example-2d.html": (source / "example-2d.html").read_bytes(),
    }
    source_index = (source / "index.html").read_text(encoding="utf-8")
    source_index = source_index.replace(
        f"../{SOURCE_ID}.zip", "original-source.zip")
    standalone = (source / "example-2d.html").read_text(encoding="utf-8")
    for name in ("index.html", "scenario.json", "geometry.json", "exact-oracle.json",
                 "raw-runs.jsonl", "records.json"):
        standalone = standalone.replace(f'href="{name}"', f'href="source-report/{name}"')
    files.update({f"source-report/{path.name}": path.read_bytes()
                  for path in sorted(source.iterdir()) if path.is_file()})
    files["source-report/index.html"] = source_index.encode("utf-8")
    files["source-report/original-source.zip"] = (source.parent / (SOURCE_ID + ".zip")).read_bytes()
    files["example-2d.html"] = standalone.encode("utf-8")
    original_manifest_bytes = (source / "manifest.json").read_bytes()
    original_archive_bytes = (source.parent / (SOURCE_ID + ".zip")).read_bytes()
    rows = [json.loads(line) for line in (source / "raw-runs.jsonl").read_text().splitlines()]
    oracle = json.loads((source / "exact-oracle.json").read_text())
    correction = {
        "schema": "csl.issue6-b06-manifest-correction/1",
        "correction_id": CORRECTION_ID,
        "original_public_report_id": PUBLIC_SOURCE_ID,
        "original_source_report_id": SOURCE_ID,
        "original_bundle_manifest_sha256": digest(original_manifest_bytes),
        "original_bundle_zip_sha256": digest(original_archive_bytes),
        "original_fixture_sha256": rows[0]["fixture_sha256"],
        "corrected_fixture_sha256": digest(corrected_bytes),
        "measured_source_commit": rows[0]["source_commit"],
        "measured_driver_sha256": rows[0]["driver_sha256"],
        "independent_oracle_sha256": oracle["oracle_sha256"],
        "defect": {"field": "model.A_row_major", "declared_shape": [4, 4],
                   "captured_entries": 15, "corrected_entries": 16,
                   "corrected_row_major": corrected_a,
                   "correction": "insert the source-verified zero at row 4, column 2 (zero-based index 13)"},
        "source_evidence": {
            "historical_driver": "The measured source commit constructs A as a complete 4x4 matrix with final row [0, 0, -2, 1].",
            "independent_oracle": "Its independent integer recurrence applies x4_next = x4 - 2*x3, consistent with that final row.",
            "model_scope": "The other captured scenario fields match the corrected canonical scenario; only the original A_row_major omission differs.",
        },
        "other_report_families_audit": {
            "scope": "Audited model-bearing input fixtures under benchmarks/scenarios and report inputs carrying a csl.scenario/1 model.",
            "flat_dimension_arrays": "Only the B06 owner-confirmed fixture uses declared dimensions with flat A_row_major, B, and D_row_major arrays in the audited benchmark-scenario directory.",
            "nested_matrix_fixtures": [
                "b04-historical.json",
                "b07-historical.json",
                "b07-owner-approved-eight-case-v1.json",
                "r29-corrected-scalar-reference.json"
            ],
            "typed_scenario_loader": "The SYN-TS01 paired report input uses csl.scenario/1 and the core scenario loader; malformed A/B dimensions are covered by tests/unit/input/scenario_loader_tests.cpp and tests/contract/input/scenario_file_tests.cpp.",
            "boundary": "This audit covers model-bearing input fixtures and their ingestion paths, not arbitrary matrices recorded as output data in every report family."
        },
        "measurement_decision": {
            "solver_rerun": False,
            "decision": "Existing measurements may be referenced as executions of the hardcoded complete measured model, with the malformed captured manifest disclosed.",
            "limits": "Source-level model correspondence is verified. Existing solver results retain binary64 numerical assurance and are not newly recertified; this is not a historical reproduction of the paper.",
        },
        "preservation": "The original report directory, manifest, ZIP, public report ID, and public report bytes are unchanged.",
    }
    files["manifest-correction.json"] = json_bytes(correction)
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>B06 scenario manifest correction v1</title>
<style>body{{font:16px/1.55 system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#17212b}}img{{max-width:100%}}code{{overflow-wrap:anywhere}}dt{{font-weight:650}}dd{{margin:0 0 .8rem}}</style></head><body><main>
<p>Controlled Systems Lab · B06 correction companion · version 1</p><h1>Correcting the B06 scenario manifest</h1>
<p>The original immutable capture remains byte-for-byte unchanged. Its scenario declares a 4×4 matrix but contains 15 entries. The corrected canonical scenario has 16 entries and records the source-supported final row <code>[0, 0, -2, 1]</code>.</p>
<h2>What the saved measurements represent</h2><p>The measured driver at source commit <code>{rows[0]['source_commit']}</code> hardcodes the complete 4×4 transition matrix. The separate integer oracle uses <code>x4′ = x4 − 2x3</code>, independently confirming the final row. The immutable capture’s only difference from the corrected canonical scenario is the missing zero in the manifest. The evidence supports associating those measurements with the hardcoded model, while retaining the original manifest defect in the record.</p>
<p>No solver was rerun. Existing solver results retain binary64 numerical assurance and are not newly recertified; this is not a historical reproduction of the paper.</p>
<h2>Corrected files and provenance</h2><dl><dt>Corrected canonical scenario</dt><dd><a href="corrected-scenario.json">Download corrected-scenario.json</a> · SHA-256 <code>{digest(corrected_bytes)}</code></dd><dt>Machine-readable correction and preservation record</dt><dd><a href="manifest-correction.json">Open manifest-correction.json</a></dd><dt>Original immutable report</dt><dd><a href="source-report/index.html">Original source report</a> · <a href="source-report/original-source.zip">Original capture ZIP</a></dd><dt>Original measurements and source report</dt><dd><a href="source-report/raw-runs.jsonl">Raw runs</a> · <a href="source-report/exact-oracle.json">Independent oracle</a></dd></dl>
<h2>4D fuel geometry shown in 2D</h2><p>The figures below are the saved projections of the same 4D terminal set; the correction changes the manifest and provenance explanation, not the archived measured vertices.</p><figure><img src="terminal-projections.svg" alt="Saved flow and stock-balance projections of the B06 four-dimensional terminal set"><figcaption>Flow (x1, x3) and stock-balance (x2, x4) projections from the immutable B06 capture. <a href="example-2d.html">Open the standalone example.</a></figcaption></figure>
 </main></body></html>'''.encode()
    files["index.html"] = page
    output.mkdir(parents=True)
    for name, content in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    manifest = {"schema": "csl.issue6-b06-correction-files/1",
                "files": {name: digest(content) for name, content in sorted(files.items())}}
    manifest_bytes = json_bytes(manifest)
    (output / "manifest.json").write_bytes(manifest_bytes)
    (output.parent / (CORRECTION_ID + ".manifest.sha256")).write_text(digest(manifest_bytes) + "  manifest.json\n")
    archive_path = output.parent / (CORRECTION_ID + ".zip")
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(p for p in output.rglob("*") if p.is_file()):
            info = ZipInfo(f"{CORRECTION_ID}/{path.relative_to(output).as_posix()}", (1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)
    return output


if __name__ == "__main__":
    print(build())
