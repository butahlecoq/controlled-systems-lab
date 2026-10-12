#!/usr/bin/env python3
"""Validate the saved OPT-05 report and regenerate its offline integrity bundle."""
from __future__ import annotations

import csv
import hashlib
import json
import statistics
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def report_files() -> list[Path]:
    excluded = {"manifest.sha256", "bundle.zip", "bundle.zip.sha256"}
    return sorted(
        p for p in ROOT.rglob("*")
        if p.is_file() and p.name not in excluded and "__pycache__" not in p.parts and p.suffix != ".pyc"
    )


def validate_csv(path: Path, expected_rows: list[dict[str, object]]) -> None:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        expected_headers = list(expected_rows[0]) if expected_rows else []
        assert reader.fieldnames == expected_headers, (
            f"{path.name} headers mismatch: expected {expected_headers}, got {reader.fieldnames}"
        )
    assert len(rows) == len(expected_rows), (
        f"{path.name} row count mismatch: expected {len(expected_rows)}, got {len(rows)}"
    )
    for row_number, (actual, expected) in enumerate(zip(rows, expected_rows), start=2):
        assert set(actual) == set(expected), f"{path.name}:{row_number} has unexpected or missing columns"
        for field, expected_value in expected.items():
            assert actual[field] == str(expected_value), (
                f"{path.name}:{row_number} {field} mismatch: "
                f"expected {expected_value!s}, got {actual[field]!r}"
            )


def main() -> None:
    records_path = ROOT / "records.json"
    records = json.loads(records_path.read_text(encoding="utf-8"))
    primary = json.loads((ROOT / "evidence/accepted-002/records.json").read_text(encoding="utf-8"))
    assert records == primary, "root records differ from accepted-002 JSON"

    trials = records["trials"]
    measured = [t for t in trials if not t["warmup"]]
    warmups = [t for t in trials if t["warmup"]]
    assert len(measured) == 21 and len(warmups) == 3
    assert all(t["verified"] and t["status"] == "complete" for t in measured)
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
        assert len(rows) == 7
        assert statistics.median(values) == summary["median_ns"]
        assert min(values) == summary["min_ns"] and max(values) == summary["max_ns"]
        assert all(t["lp_calls"] == summary["median_lp_calls"] for t in rows)
    validate_csv(ROOT / "evidence/accepted-002/summary.csv", expected_summary_rows)
    validate_csv(ROOT / "evidence/accepted-002/trials.csv", expected_trial_rows)

    temp = ROOT / ".render-check"
    temp.mkdir(exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / "render_saved.py"), "--records", str(records_path), "--out", str(temp)], check=True)
    for name in ("index.html", "latency.svg"):
        assert (ROOT / name).read_bytes() == (temp / name).read_bytes(), f"{name} is not reproducible from saved records"
    for item in temp.iterdir():
        item.unlink()
    temp.rmdir()
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    for href in ("records.json", "trials.csv", "summary.csv", "profile/README.md", "README.md", "latency.svg"):
        assert href in page, f"missing report link/reference {href}"
    assert "2.136" in page and "7.932" in page and "18.908" in page

    forbidden = [p for p in ROOT.rglob("*") if p.is_file() and (p.suffix.lower() == ".etl" or "symbolized.txt" in p.name or "cpu-samples.txt" == p.name)]
    assert not forbidden, f"system-wide profiler exports remain: {forbidden}"

    files = report_files()
    manifest = "".join(f"{sha256(p)}  {p.relative_to(ROOT).as_posix()}\n" for p in files)
    (ROOT / "manifest.sha256").write_text(manifest, encoding="utf-8", newline="\n")
    zip_path = ROOT / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted([*files, ROOT / "manifest.sha256"]):
            archive_path = f"{ROOT.name}/{path.relative_to(ROOT).as_posix()}"
            info = zipfile.ZipInfo(archive_path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    (ROOT / "bundle.zip.sha256").write_text(f"{sha256(zip_path)}  bundle.zip\n", encoding="ascii", newline="\n")

    with zipfile.ZipFile(zip_path) as bundle:
        names = bundle.namelist()
        assert len(names) == len(set(names)), "duplicate ZIP path"
        assert all(".." not in Path(name).parts for name in names), "escaping ZIP path"
        assert f"{ROOT.name}/index.html" in names and f"{ROOT.name}/manifest.sha256" in names
    print(f"PASS: {len(measured)} verified trials, {len(warmups)} warmups, summary/CSV consistency, deterministic HTML/SVG, offline ZIP integrity")
    print(f"Files: {len(files)}; ZIP: {zip_path.stat().st_size} bytes; SHA-256: {sha256(zip_path)}")


if __name__ == "__main__":
    main()
