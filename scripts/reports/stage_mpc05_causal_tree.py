"""Validate and stage the saved MPC-05 causal minimax report on Pages."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/mpc05-causal-tree-pilot-v2"
CHECKER_PATH = ROOT / "scripts/reports/mpc05/reference.py"
spec = importlib.util.spec_from_file_location("mpc05_causal_reference", CHECKER_PATH)
reference = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(reference)
FILES = ("README.md", "build.log", "capture.json", "figure-data.json", "index.html",
         "projections.svg", "result.json", "SHA256SUMS")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inputs(source: Path) -> dict[str, bytes]:
    if source.is_symlink() or not source.is_dir() or {p.name for p in source.iterdir()} != set(FILES):
        raise ValueError("MPC-05 report inventory differs")
    files = {name: (source / name).read_bytes() for name in FILES}
    checksums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        value, name = line.split("  ", 1)
        if name in checksums:
            raise ValueError("duplicate report checksum")
        checksums[name] = value
    if checksums != {name: digest(data) for name, data in files.items() if name != "SHA256SUMS"}:
        raise ValueError("MPC-05 report checksum mismatch")
    result = json.loads(files["result.json"])
    figure = reference.verify_result(result)
    capture = json.loads(files["capture.json"])
    if capture.get("highs_version") != result["two_points"]["causal_tree"]["solver"]:
        raise ValueError("MPC-05 capture and numerical record solver differ")
    if not files["build.log"].strip():
        raise ValueError("MPC-05 saved build log is empty")
    with tempfile.TemporaryDirectory(prefix="mpc05-stage-") as temporary:
        generated = Path(temporary)
        input_path = generated / "result.json"
        input_path.write_bytes(files["result.json"])
        reference.render(input_path, generated / "rendered")
        expected = generated / "rendered"
        for name in ("figure-data.json", "projections.svg", "index.html"):
            if files[name] != (expected / name).read_bytes():
                raise ValueError(f"MPC-05 saved renderer output differs: {name}")
    if json.loads(files["figure-data.json"]) != figure:
        raise ValueError("MPC-05 figure data differs from independent reference")
    return files


def stage(source: Path, site: Path) -> str:
    files = inputs(source)
    index = site / "index.html"
    page = index.read_text(encoding="utf-8")
    identity = {name: digest(content) for name, content in sorted(files.items())}
    route = "mpc05-causal-tree-" + digest(json.dumps(identity, sort_keys=True,
                                                     separators=(",", ":")).encode())[:20]
    destination, archive_path = site / route, site / f"{route}.zip"
    if destination.exists() or archive_path.exists() or page.count("</body>") != 1:
        raise ValueError("MPC-05 Pages destination or landing insertion point differs")
    generated = dict(files)
    saved_page = generated["index.html"].decode("utf-8")
    footer = (f'<p>Immutable report <code>{route}</code> · '
              '<a href="publication-manifest.json">Publication manifest</a>.</p>')
    generated["index.html"] = saved_page.replace("</body>", footer + "</body>").encode("utf-8")
    generated["SHA256SUMS"] = "".join(
        f"{digest(generated[name])}  {name}\n" for name in sorted(generated)
        if name != "SHA256SUMS").encode("ascii")
    manifest = {"schema": "csl.mpc05-causal-tree-publication/1", "report_id": route,
                "source_commit": json.loads(files["capture.json"])["source_commit"],
                "source_files": identity,
                "published_files": {name: digest(value) for name, value in sorted(generated.items())}}
    generated["publication-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    destination.mkdir()
    for name, value in generated.items():
        (destination / name).write_bytes(value)
    link = (f'<section><h2>Finite causal minimax on TwoPointsOnParallelLines</h2>'
            f'<p>Compares a finite Bellman solver with an independent HiGHS scenario-tree model. '
            f'The report shows forward reachable sets, terminal sets, backward-winning intersections, '
            f'and the replayed worst-case path in player phase planes <code>(x1,x2)</code> and '
            f'<code>(x3,x4)</code>. It covers a three-stage finite adaptation and makes no continuous '
            f'RL or performance claim. <a href="{route}/index.html">Open the report</a> · '
            f'<a href="{route}.zip">Download the offline report bundle</a>.</p></section>')
    index.write_text(page.replace("</body>", link + "</body>"), encoding="utf-8")
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in sorted(generated.items()):
            item = zipfile.ZipInfo(f"{route}/{name}", date_time=(2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, value)
    return route


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--executable", type=Path,
                        help="optional fresh driver output to compare with the saved record")
    args = parser.parse_args()
    if args.executable:
        actual = json.loads(subprocess.check_output(
            [str(args.executable.resolve()), "--smoke"], text=True))
        saved = json.loads((args.source / "result.json").read_text(encoding="utf-8"))
        if actual != saved:
            raise ValueError("MPC-05 saved result differs from a fresh run of the report driver")
    print(stage(args.source, args.site))
