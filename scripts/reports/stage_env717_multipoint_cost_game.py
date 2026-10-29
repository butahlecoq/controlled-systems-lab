"""Verify and publish the MultiPointCostGame terminal-only pilot."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/env717-multipoint-cost-game-pilot-v1"
CHECKER = ROOT / "scripts/reports/env717/check_multipoint_cost_game.py"
FILES = ("README.md", "capture.json", "figure-data.json", "index.html",
         "projections.svg", "result.json", "SHA256SUMS")
spec = importlib.util.spec_from_file_location("env717_multipoint_checker", CHECKER)
checker = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(checker)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inputs(source: Path) -> tuple[dict[str, bytes], dict]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("report source must be a regular directory")
    if {p.name for p in source.iterdir()} != set(FILES):
        raise ValueError("report source inventory differs")
    for path in source.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValueError("report files must be regular, nonsymlink files")
    files = {name: (source / name).read_bytes() for name in FILES}
    sums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        sha, name = line.split("  ", 1)
        if name in sums:
            raise ValueError("duplicate checksum entry")
        sums[name] = sha
    if sums != {name: digest(content) for name, content in files.items()
                if name != "SHA256SUMS"}:
        raise ValueError("report file checksum mismatch")
    result = json.loads(files["result.json"])
    replay = checker.verify(result)
    open_plan = replay["open_plans"][replay["open_minimizing"][0]]
    controls = [checker.CATALOGUE[i] for i in open_plan["control_indices"]]
    disturbances = [checker.CATALOGUE[i] for i in open_plan["maximizing_disturbance_indices"]]
    path = [checker.INITIAL]
    for stage, (u, d) in enumerate(zip(controls, disturbances)):
        path.append(checker.advance(path[-1], stage, u, d))
    replay.update(open_path=path, open_controls=controls, open_disturbances=disturbances)
    figure = json.loads(files["figure-data.json"])
    if figure != checker.figure_data(result, replay):
        raise ValueError("saved projection data differs from independent replay")
    capture = json.loads(files["capture.json"])
    if capture.get("renderer_sha256") != digest(CHECKER.read_bytes()):
        raise ValueError("renderer identity differs")
    svg = checker.svg_figure(result, replay) + "\n"
    if files["projections.svg"].decode("utf-8") != svg:
        raise ValueError("saved SVG differs from independently replayed figure")
    page = checker.report_page(result, svg, capture["capture_environment"]).encode()
    if files["index.html"] != page:
        raise ValueError("saved page differs from result and figure")
    return files, result


def stage(source: Path, site: Path) -> str:
    files, result = inputs(source)
    if not site.is_dir():
        raise ValueError("Pages site directory does not exist")
    identity = {"source": source.name, "result": digest(files["result.json"]),
                "renderer": digest(CHECKER.read_bytes()),
                "files": {name: digest(data) for name, data in sorted(files.items())}}
    report_id = "env717-multipoint-" + digest(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())[:20]
    destination, archive_path = site / report_id, site / f"{report_id}.zip"
    if destination.exists() or archive_path.exists():
        raise ValueError("versioned route already exists")
    index = site / "index.html"
    index_text = index.read_text(encoding="utf-8")
    if index_text.count("</ul>") != 1 or report_id in index_text:
        raise ValueError("Pages index insertion point differs")
    generated = dict(files)
    page = generated["index.html"].decode("utf-8")
    if page.count("</main>") != 1:
        raise ValueError("report page insertion point differs")
    page_footer = (f'<p>Immutable report <code>{report_id}</code>. '
                   f'<a href="publication-manifest.json">Publication manifest</a> · '
                   f'<a href="../{report_id}.zip">Offline ZIP</a>.</p>')
    generated["index.html"] = page.replace("</main>", page_footer + "</main>").encode()
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
    for name, content in generated.items():
        (destination / name).write_bytes(content)
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        landing = (f'<!doctype html><html lang="en"><meta charset="utf-8">'
                   f'<title>Offline MultiPointCostGame report</title>'
                   f'<a href="{report_id}/index.html">Open the report</a></html>').encode()
        for archive_name, content in [("index.html", landing)] + [
                (f"{report_id}/{name}", data) for name, data in sorted(generated.items())]:
            info = zipfile.ZipInfo(archive_name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    route = (f'<li><a href="{report_id}/index.html">MultiPointCostGame reachability and minimax</a>'
             f' · <a href="{report_id}/result.json">result JSON</a>'
             f' · <a href="{report_id}/projections.svg">phase plane</a>'
             f' · <a href="{report_id}.zip">offline ZIP</a></li>')
    index.write_text(index_text.replace("</ul>", route + "</ul>"), encoding="utf-8")
    return report_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))
