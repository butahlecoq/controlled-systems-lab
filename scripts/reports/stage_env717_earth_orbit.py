"""Validate and stage the ENV-717 EarthOrbitalMotion report bundle."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/env717-earth-orbit-pilot-v1"
CHECKER = ROOT / "scripts/reports/env717/check_earth_orbit.py"
FILES = ("README.md", "capture.json", "figure-data.json", "index.html",
         "orbit-phase-plane.svg", "result.json", "SHA256SUMS")
UPSTREAM_SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verified_bundle(source: Path) -> dict[str, bytes]:
    if source.is_symlink() or not source.is_dir() or {p.name for p in source.iterdir()} != set(FILES):
        raise ValueError("EarthOrbitalMotion report inventory differs")
    files = {}
    for name in FILES:
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("EarthOrbitalMotion report entries must be regular files")
        files[name] = path.read_bytes()
    checksums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        value, name = line.split("  ", 1)
        if name in checksums:
            raise ValueError("duplicate EarthOrbitalMotion report checksum")
        checksums[name] = value
    if checksums != {name: digest(data) for name, data in files.items() if name != "SHA256SUMS"}:
        raise ValueError("EarthOrbitalMotion report checksum mismatch")

    import sys
    sys.path.insert(0, str(CHECKER.parent))
    import check_earth_orbit as checker
    result = json.loads(files["result.json"])
    raw = result.get("raw_driver_record", {})
    verified = checker.verify(raw)
    summary = result.get("finite_catalogue_result", {})
    if (result.get("source_repository_commit") != UPSTREAM_SOURCE_COMMIT or
            result.get("source_file_blob") != checker.UPSTREAM_BLOB or
            result.get("source_file_url") != checker.SOURCE_URL or
            summary.get("complete_plan_count") != checker.PLAN_COUNT or
            summary.get("selected_plan_index") != verified["selected_index"] or
            summary.get("selected_control_indices") != list(checker.decode(verified["selected_index"])) or
            summary.get("selected_block_actions") != [
                list(checker.ACTIONS[i]) for i in checker.decode(verified["selected_index"])] or
            not math.isclose(summary.get("source_reward", math.nan), -verified["objective"],
                             rel_tol=0.0, abs_tol=2e-8) or
            not math.isclose(summary.get("minimum_cost", math.nan), verified["objective"],
                             rel_tol=0.0, abs_tol=2e-8) or
            not math.isclose(summary.get("zero_control_cost", math.nan), verified["zero_objective"],
                             rel_tol=0.0, abs_tol=2e-8) or
            result.get("search", {}).get("all_plan_scores_independently_replayed") is not True):
        raise ValueError("saved EarthOrbitalMotion result evidence differs")
    figure = json.loads(files["figure-data.json"])
    if (figure.get("selected_plan_index") != result["finite_catalogue_result"].get("selected_plan_index") or
            len(figure.get("selected_trajectory", [])) != checker.HORIZON + 1 or
            figure.get("selected_trajectory") != verified["trajectory"] or
            figure.get("zero_control_trajectory") != checker.evaluate((4, 4, 4))[2] or
            figure.get("target") != {"radius_km": checker.TARGET_RADIUS,
                                      "angular_rate_rad_s": checker.target_rate()}):
        raise ValueError("EarthOrbitalMotion figure data differs from the saved result")
    page = files["index.html"].decode("utf-8")
    if (checker.SOURCE_URL not in page or str(checker.PLAN_COUNT) not in page or
            "not an optimum over continuous controls" not in page):
        raise ValueError("EarthOrbitalMotion HTML does not preserve source and scope")
    return files


def stage(source: Path, site: Path) -> str:
    if not site.is_dir() or source.name != "env717-earth-orbit-pilot-v1":
        raise ValueError("unknown EarthOrbitalMotion report source or Pages directory")
    files = verified_bundle(source)
    identity = {"source_repository_commit": UPSTREAM_SOURCE_COMMIT,
                "result_sha256": digest(files["result.json"]),
                "stager_sha256": digest(Path(__file__).read_bytes()),
                "source_files": {name: digest(data) for name, data in sorted(files.items())}}
    route_id = "env717-earth-orbit-" + digest(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())[:20]
    destination, archive_path = site / route_id, site / f"{route_id}.zip"
    if destination.exists() or archive_path.exists():
        raise ValueError("content-addressed EarthOrbitalMotion route already exists")
    index = site / "index.html"
    page = index.read_text(encoding="utf-8")
    if page.count("</ul>") != 1 or route_id in page:
        raise ValueError("Pages index insertion point differs")
    output = dict(files)
    output["index.html"] = files["index.html"].decode().replace(
        "</main>", f'<p>Immutable Pages report <code>{html.escape(route_id)}</code>. '
        '<a href="publication-manifest.json">Publication manifest</a> · '
        f'<a href="../{html.escape(route_id)}.zip">Offline report ZIP</a>.</p></main>').encode()
    output["SHA256SUMS"] = "".join(
        f"{digest(output[name])}  {name}\n" for name in sorted(output) if name != "SHA256SUMS").encode()
    manifest = {"schema": "csl.env717-publication/1", "report_id": route_id,
                "source_report_id": source.name, **identity,
                "published_files": {name: digest(data) for name, data in sorted(output.items())}}
    output["publication-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    route = (f'<li><a href="{route_id}/index.html">EarthOrbitalMotion finite-catalog control pilot</a>'
             f' · <a href="{route_id}/orbit-phase-plane.svg">radius-rate phase plane</a>'
             f' · <a href="{route_id}/result.json">result JSON</a>'
             f' · <a href="{route_id}.zip">offline ZIP</a></li>')
    destination.mkdir()
    for name, data in output.items():
        (destination / name).write_bytes(data)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        offline = (f'<!doctype html><html lang="en"><meta charset="utf-8">'
                   f'<title>Offline EarthOrbitalMotion report</title><a href="{route_id}/index.html">Open report</a></html>').encode()
        for name, data in [("index.html", offline)] + [
                (f"{route_id}/{name}", data) for name, data in sorted(output.items())]:
            item = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data)
    index.write_text(page.replace("</ul>", route + "</ul>"), encoding="utf-8")
    return route_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))


if __name__ == "__main__":
    main()
