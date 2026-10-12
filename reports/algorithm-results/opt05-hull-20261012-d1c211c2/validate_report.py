#!/usr/bin/env python3
"""Check saved OPT-05 evidence and its offline bundle; package only on request."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PACKAGE_NAMES = {"manifest.sha256", "bundle.zip", "bundle.zip.sha256"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def report_files() -> list[Path]:
    return sorted(
        p for p in ROOT.rglob("*")
        if p.is_file() and p.relative_to(ROOT).as_posix() not in PACKAGE_NAMES
        and "__pycache__" not in p.parts and p.suffix != ".pyc"
    )


def validate_csv(path: Path, expected_rows: list[dict[str, object]]) -> None:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        expected_headers = list(expected_rows[0]) if expected_rows else []
        require(reader.fieldnames == expected_headers,
                f"{path.name} headers mismatch: expected {expected_headers}, got {reader.fieldnames}")
    require(len(rows) == len(expected_rows),
            f"{path.name} row count mismatch: expected {len(expected_rows)}, got {len(rows)}")
    for row_number, (actual, expected) in enumerate(zip(rows, expected_rows), start=2):
        require(set(actual) == set(expected), f"{path.name}:{row_number} has unexpected or missing columns")
        for field, expected_value in expected.items():
            require(actual[field] == str(expected_value),
                    f"{path.name}:{row_number} {field} mismatch: "
                    f"expected {expected_value!s}, got {actual[field]!r}")


def validate_records() -> int:
    records_path = ROOT / "records.json"
    records = json.loads(records_path.read_text(encoding="utf-8"))
    primary = json.loads((ROOT / "evidence/accepted-002/records.json").read_text(encoding="utf-8"))
    require(records == primary, "root records differ from accepted-002 JSON")

    trials = records["trials"]
    measured = [t for t in trials if not t["warmup"]]
    warmups = [t for t in trials if t["warmup"]]
    require(len(measured) == 21 and len(warmups) == 3, "measured/warmup trial counts differ")
    require(all(t["verified"] and t["status"] == "complete" for t in measured),
            "measured trial was not verified and complete")
    trial_fields = (
        "case_id", "round", "points", "warmup", "elapsed_ns", "status", "verified",
        "lp_calls", "attempts", "removed", "retained",
    )
    outcome_fields = (
        "feasible", "infeasible", "unsupported", "stopped", "numerical_failure", "malformed_result",
    )
    expected_trial_rows = [
        {
            **{field: trial[field] for field in trial_fields},
            **{field: trial["outcomes"][field] for field in outcome_fields},
        }
        for trial in trials
    ]
    validate_csv(ROOT / "trials.csv", expected_trial_rows)
    summary_fields = (
        "case_id", "points", "attempts", "successes", "failures", "median_ns", "min_ns",
        "max_ns", "median_lp_calls",
    )
    expected_summary_rows = [
        {field: summary[field] for field in summary_fields}
        for summary in records["summary"]
    ]
    validate_csv(ROOT / "summary.csv", expected_summary_rows)
    for summary in records["summary"]:
        rows = [t for t in measured if t["case_id"] == summary["case_id"]]
        values = [t["elapsed_ns"] for t in rows]
        require(len(rows) == 7, f"{summary['case_id']} does not have seven measured trials")
        require(statistics.median(values) == summary["median_ns"],
                f"{summary['case_id']} median mismatch")
        require(min(values) == summary["min_ns"] and max(values) == summary["max_ns"],
                f"{summary['case_id']} range mismatch")
        require(all(t["lp_calls"] == summary["median_lp_calls"] for t in rows),
                f"{summary['case_id']} LP-call count mismatch")
    validate_csv(ROOT / "evidence/accepted-002/summary.csv", expected_summary_rows)
    validate_csv(ROOT / "evidence/accepted-002/trials.csv", expected_trial_rows)

    # Rendering uses an OS temporary directory, leaving the report tree untouched.
    with tempfile.TemporaryDirectory(prefix="opt05-render-check-") as temp_dir:
        temp = Path(temp_dir)
        subprocess.run([sys.executable, str(ROOT / "render_saved.py"),
                        "--records", str(records_path), "--out", str(temp)], check=True)
        for name in ("index.html", "latency.svg"):
            require((ROOT / name).read_bytes() == (temp / name).read_bytes(),
                    f"{name} is not reproducible from saved records")
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    for href in ("records.json", "trials.csv", "summary.csv", "profile/README.md", "README.md", "latency.svg"):
        require(href in page, f"missing report link/reference {href}")
    require(all(value in page for value in ("2.136", "7.932", "18.908")),
            "rendered summary values missing")

    forbidden = [p for p in ROOT.rglob("*") if p.is_file() and
                 (p.suffix.lower() == ".etl" or "symbolized.txt" in p.name or p.name == "cpu-samples.txt")]
    require(not forbidden, f"system-wide profiler exports remain: {forbidden}")
    return len(measured)


def expected_manifest(files: list[Path]) -> bytes:
    return "".join(f"{sha256(p)}  {p.relative_to(ROOT).as_posix()}\n" for p in files).encode("ascii")


def package(files: list[Path]) -> None:
    """Explicitly regenerate the deterministic package after reviewed edits."""
    (ROOT / "manifest.sha256").write_bytes(expected_manifest(files))
    zip_path = ROOT / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted([*files, ROOT / "manifest.sha256"]):
            archive_path = f"{ROOT.name}/{path.relative_to(ROOT).as_posix()}"
            info = zipfile.ZipInfo(archive_path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    (ROOT / "bundle.zip.sha256").write_bytes(f"{sha256(zip_path)}  bundle.zip\n".encode("ascii"))


def validate_package(files: list[Path]) -> None:
    manifest_path = ROOT / "manifest.sha256"
    require(manifest_path.read_bytes() == expected_manifest(files),
            "manifest.sha256 inventory or file hash mismatch")
    zip_path = ROOT / "bundle.zip"
    require((ROOT / "bundle.zip.sha256").read_bytes() ==
            f"{sha256(zip_path)}  bundle.zip\n".encode("ascii"),
            "bundle.zip.sha256 does not match saved bundle.zip")
    expected = {f"{ROOT.name}/{path.relative_to(ROOT).as_posix()}": path
                for path in [*files, manifest_path]}
    with zipfile.ZipFile(zip_path) as bundle:
        names = bundle.namelist()
        require(len(names) == len(set(names)), "duplicate ZIP path")
        require(set(names) == set(expected), "bundle.zip inventory differs from saved report files")
        for name in names:
            require(".." not in Path(name).parts, f"escaping ZIP path: {name}")
            info = bundle.getinfo(name)
            require(info.date_time == (1980, 1, 1, 0, 0, 0) and
                    info.compress_type == zipfile.ZIP_DEFLATED and
                    info.external_attr == 0o100644 << 16,
                    f"bundle.zip metadata differs for {name}")
            require(bundle.read(name) == expected[name].read_bytes(),
                    f"bundle.zip bytes differ for {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", action="store_true",
                        help="regenerate the manifest and deterministic ZIP after saved-file edits")
    args = parser.parse_args()
    measured = validate_records()
    files = report_files()
    if args.package:
        package(files)
    validate_package(files)
    print(f"PASS: {measured} verified trials, 3 warmups, summary/CSV consistency, deterministic HTML/SVG, offline ZIP integrity")
    print(f"Files: {len(files)}; ZIP: {(ROOT / 'bundle.zip').stat().st_size} bytes; SHA-256: {sha256(ROOT / 'bundle.zip')}")


if __name__ == "__main__":
    main()
