"""Stage the independently replayed Gym Pendulum finite-action pilot."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/env717-pendulum-pilot-v1"
CHECKER = ROOT / "scripts/reports/env717/check_pendulum.py"
FILES = ("README.md", "capture.json", "figure-data.json", "index.html",
         "phase-plane.svg", "result.json", "SHA256SUMS")
SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verified_bundle(source: Path) -> dict[str, bytes]:
    if source.is_symlink() or not source.is_dir() or {p.name for p in source.iterdir()} != set(FILES):
        raise ValueError("Pendulum report inventory differs")
    files = {}
    for name in FILES:
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Pendulum report entries must be regular files")
        files[name] = path.read_bytes()
    checksums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        value, name = line.split("  ", 1)
        if name in checksums:
            raise ValueError("duplicate Pendulum report checksum")
        checksums[name] = value
    if checksums != {name: digest(data) for name, data in files.items() if name != "SHA256SUMS"}:
        raise ValueError("Pendulum report checksum mismatch")

    import sys
    sys.path.insert(0, str(CHECKER.parent))
    import check_pendulum as checker
    result = json.loads(files["result.json"])
    checker.verify_result_and_bundle(result, source)
    return files


def stage(source: Path, site: Path) -> str:
    if not site.is_dir() or source.name != "env717-pendulum-pilot-v1":
        raise ValueError("unknown Pendulum report source or Pages directory")
    files = verified_bundle(source)
    identity = {"source_repository_commit": SOURCE_COMMIT,
                "result_sha256": digest(files["result.json"]),
                "stager_sha256": digest(Path(__file__).read_bytes()),
                "source_files": {name: digest(data) for name, data in sorted(files.items())}}
    route_id = "env717-pendulum-" + digest(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())[:20]
    destination, archive_path = site / route_id, site / f"{route_id}.zip"
    if destination.exists() or archive_path.exists():
        raise ValueError("content-addressed Pendulum route already exists")
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
    route = (f'<li><a href="{route_id}/index.html">Gym Pendulum finite-action control pilot</a>'
             f' · <a href="{route_id}/phase-plane.svg">phase plane</a>'
             f' · <a href="{route_id}/result.json">result JSON</a>'
             f' · <a href="{route_id}.zip">offline ZIP</a></li>')
    destination.mkdir()
    for name, data in output.items():
        (destination / name).write_bytes(data)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        offline = (f'<!doctype html><html lang="en"><meta charset="utf-8">'
                   f'<title>Offline Pendulum report</title><a href="{route_id}/index.html">Open report</a></html>').encode()
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
