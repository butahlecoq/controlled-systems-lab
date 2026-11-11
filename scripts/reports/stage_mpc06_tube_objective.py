"""Validate and stage the exact MPC-06 tube-policy cost report on Pages."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/mpc06-tube-objective-v1"
SOURCE_MODULES = {
    "benchmarks/scenarios/mpc06-tube-objective-v1.json",
    "benchmarks/scenarios/mpc06-nilpotent-tube-v1.json",
    ".github/workflows/algorithm-reports.yml",
    "reports/algorithm-results/mpc06-nilpotent-tube-pilot-v1/result.json",
    "scripts/reports/mpc06/check_tube.py",
    "scripts/reports/mpc06/tube_objective.py",
    "scripts/reports/mpc06/check_tube_objective.py",
    "tests/reporting/test_mpc06_tube_objective.py",
    ".github/workflows/mpc06-tube-objective-pages-augmentation.yml",
    "scripts/reports/mpc06/render_tube_objective.py",
    "scripts/reports/mpc06/build_tube_objective.py",
    "scripts/reports/stage_mpc06_tube_objective.py",
}
FILES = {"README.md", "index.html", "manifest.json", "result.json", "scenario.json",
         "base-result.json", "base-scenario.json", "trajectory.svg", "verification.json", "SHA256SUMS"}
SOURCE_SNAPSHOT_ROOT = Path("docs/research/evidence/mpc06-tube-objective-source-snapshot")
MANIFEST_SHA256 = "a4c5fc40dbb4ea72bc29d10fd72b1559abff01edbd26c0f380825fefb32c6f9e"
SOURCE_SNAPSHOT_SHA256 = {
    ".github/workflows/algorithm-reports.yml": "321feccc93d8402af6e8acd39c578bdf92882483353ab692b38ef8ef7df5dc9f",
    ".github/workflows/mpc06-tube-objective-pages-augmentation.yml": "973be97cb17d0b5cf09fe51a6e38ecf3230c93f07398a05947739658cb6f4475",
    "scripts/reports/stage_mpc06_tube_objective.py": "99710a4a6a5399d64cf741ce63fad89f61b836681fbccd494c45c53fc818bfef",
    "tests/reporting/test_mpc06_tube_objective.py": "519c00e0e1530bbd33b8f195972fa7efab32d521c5ee7375cb7a4343f7483613",
}
sys.path.insert(0, str(ROOT / "scripts/reports/mpc06"))
import render_tube_objective


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate(source: Path) -> dict[str, bytes]:
    if source.is_symlink() or not source.is_dir() or any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("MPC-06 objective report cannot contain symlinks")
    files = {path.name: path.read_bytes() for path in source.iterdir() if path.is_file()}
    if set(files) != FILES:
        raise ValueError("MPC-06 objective report inventory differs")
    sums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if not match or match.group(2) in sums:
            raise ValueError("MPC-06 objective checksum list is invalid")
        sums[match.group(2)] = match.group(1)
    if sums != {name: digest(data) for name, data in files.items() if name != "SHA256SUMS"}:
        raise ValueError("MPC-06 objective report checksum mismatch")
    manifest = json.loads(files["manifest.json"])
    if digest(files["manifest.json"]) != MANIFEST_SHA256:
        raise ValueError("MPC-06 objective frozen manifest identity differs")
    if (manifest.get("schema") != "csl.mpc06-tube-objective-manifest/1" or
            manifest.get("report_id") != source.name or set(manifest.get("files", {})) != set(files) - {"manifest.json", "SHA256SUMS"} or
            set(manifest.get("source_files", {})) != SOURCE_MODULES):
        raise ValueError("MPC-06 objective manifest identity or inventory differs")
    for name, expected in manifest["files"].items():
        if digest(files[name]) != expected:
            raise ValueError("MPC-06 objective manifest file hash differs: " + name)
    for name, expected in manifest["source_files"].items():
        snapshot_hash = SOURCE_SNAPSHOT_SHA256.get(name)
        path = ROOT / SOURCE_SNAPSHOT_ROOT / name if snapshot_hash else ROOT / name
        if (snapshot_hash and expected != snapshot_hash) or path.is_symlink() or not path.is_file() or digest(path.read_bytes()) != expected:
            raise ValueError("MPC-06 objective source hash differs: " + name)
    result = json.loads(files["result.json"])
    verification = json.loads(files["verification.json"])
    scenario = json.loads(files["scenario.json"])
    if (files["base-result.json"] != (ROOT / "reports/algorithm-results/mpc06-nilpotent-tube-pilot-v1/result.json").read_bytes() or
            files["base-scenario.json"] != (ROOT / "benchmarks/scenarios/mpc06-nilpotent-tube-v1.json").read_bytes()):
        raise ValueError("MPC-06 objective base evidence differs from the frozen feasibility pilot")
    if (result.get("schema") != "csl.mpc06-tube-objective-result/1" or
            scenario.get("schema") != "csl.mpc06-tube-objective-input/1" or
            verification.get("schema") != "csl.mpc06-tube-objective-check/1" or
            verification.get("status") != "verified" or
            result.get("objective", {}).get("worst_case_actual_cost") != "3/8" or
            result.get("objective", {}).get("nominal_surrogate_cost") != "0" or
            result.get("policy_semantics", {}).get("is_minimax_optimum") is not False):
        raise ValueError("MPC-06 objective semantics or exact outputs differ")
    result_obj = json.loads(files["result.json"])
    if files["trajectory.svg"].decode("utf-8") != render_tube_objective.render_svg(result_obj):
        raise ValueError("MPC-06 objective figure differs from saved result")
    if files["index.html"].decode("utf-8") != render_tube_objective.render_html(result_obj):
        raise ValueError("MPC-06 objective page differs from saved result")
    return files


def stage(source: Path, site: Path) -> str:
    files = validate(source)
    index = site / "index.html"
    landing = index.read_text(encoding="utf-8")
    if landing.count("</body>") != 1:
        raise ValueError("MPC-06 objective landing insertion point differs")
    identity = {name: digest(content) for name, content in sorted(files.items())}
    route = "mpc06-tube-cost-" + digest(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())[:20]
    destination, archive_path = site / route, site / f"{route}.zip"
    if destination.exists() or archive_path.exists():
        raise ValueError("MPC-06 objective route already exists")
    generated = {name: data for name, data in files.items() if name != "SHA256SUMS"}
    publication = {
        "schema": "csl.mpc06-tube-objective-publication/1",
        "report_id": route,
        "source_report_id": source.name,
        "source_commit": json.loads(files["result.json"])["source_commit"],
        "source_files": identity,
        "published_files": {name: digest(data) for name, data in sorted(generated.items())},
    }
    generated["publication-manifest.json"] = (json.dumps(publication, indent=2, sort_keys=True) + "\n").encode()
    generated["SHA256SUMS"] = "".join(f"{digest(generated[name])}  {name}\n" for name in sorted(generated)
                                        if name != "SHA256SUMS").encode("ascii")
    destination.mkdir()
    for name, data in generated.items():
        (destination / name).write_bytes(data)
    link = (f'<section><h2>Exact tube-MPC cost example</h2><p>For one fixed nominal plan and full-state ancillary feedback, '
            f'the exact nominal surrogate is 0 and the continuous-box finite-horizon worst actual cost is 3/8. '
            f'This is not an optimized minimax value. <a href="{route}/index.html">Open the report</a> · '
            f'<a href="{route}.zip">Download the offline bundle</a>.</p></section>')
    index.write_text(landing.replace("</body>", link + "</body>"), encoding="utf-8")
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(generated.items()):
            item = zipfile.ZipInfo(f"{route}/{name}", date_time=(2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data)
    return route


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))
