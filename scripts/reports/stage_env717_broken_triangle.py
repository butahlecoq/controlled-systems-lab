"""Verify and publish the BrokenTriangleGame finite minimax pilot."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/env717-broken-triangle-pilot-v1"
CHECKER = ROOT / "scripts/reports/env717/check_broken_triangle.py"
spec = importlib.util.spec_from_file_location("env717_broken_triangle_checker", CHECKER)
checker = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(checker)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stage(source: Path, site: Path) -> str:
    files, result = checker.validate_saved_bundle(source)
    page = files["index.html"].decode("utf-8")
    if (f"{result['open_loop_value']:.12g}" not in page
            or f"{result['causal_value']:.12g}" not in page
            or "finite backward-winning nodes/intersections" not in page):
        raise ValueError("HTML report results differ from the raw record")
    if not site.is_dir() or site.is_symlink():
        raise ValueError("Pages site directory must be a regular directory")
    identity = {"source": source.name, "result": digest(files["result.json"]),
                "renderer": digest(CHECKER.read_bytes()),
                "files": {name: digest(data) for name, data in sorted(files.items())}}
    report_id = "env717-broken-triangle-" + digest(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())[:20]
    destination, archive_path = site / report_id, site / f"{report_id}.zip"
    index = site / "index.html"
    if destination.exists() or archive_path.exists():
        raise ValueError("versioned publication route already exists")
    index_text = index.read_text(encoding="utf-8")
    if index_text.count("</ul>") != 1 or report_id in index_text:
        raise ValueError("Pages index insertion point differs")
    generated = dict(files)
    footer = (f'<p>Immutable report <code>{report_id}</code>. '
              f'<a href="publication-manifest.json">Publication manifest</a> · '
              f'<a href="../{report_id}.zip">Offline ZIP</a>.</p>')
    if generated["index.html"].decode().count("</main>") != 1:
        raise ValueError("report page insertion point differs")
    generated["index.html"] = (generated["index.html"].decode()
                                .replace("</main>", footer + "</main>")).encode()
    generated["SHA256SUMS"] = "".join(
        f"{digest(generated[name])}  {name}\n" for name in sorted(generated)
        if name != "SHA256SUMS").encode("ascii")
    manifest = {"schema": "csl.env717-publication/1", "report_id": report_id,
                "source_report_id": source.name,
                "source_repository_commit": checker.SOURCE_COMMIT,
                "source_commit": result["source_commit"],
                "published_files": {name: digest(data)
                                     for name, data in sorted(generated.items())}}
    generated["publication-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    destination.mkdir()
    for name, data in generated.items():
        (destination / name).write_bytes(data)
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        landing = (f'<!doctype html><html lang="en"><meta charset="utf-8">'
                   f'<title>Offline BrokenTriangleGame report</title>'
                   f'<a href="{report_id}/index.html">Open the report</a></html>').encode()
        for name, data in [("index.html", landing)] + [
                (f"{report_id}/{name}", content) for name, content in sorted(generated.items())]:
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    route = (f'<li><a href="{report_id}/index.html">BrokenTriangleGame reachability and minimax</a>'
             f' · <a href="{report_id}/result.json">result JSON</a>'
             f' · <a href="{report_id}/projections.svg">game geometry</a>'
             f' · <a href="{report_id}.zip">offline ZIP</a></li>')
    index.write_text(index_text.replace("</ul>", route + "</ul>"), encoding="utf-8")
    return report_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))
