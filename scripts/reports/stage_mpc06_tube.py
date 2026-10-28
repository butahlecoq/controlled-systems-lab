"""Validate and stage the saved exact tube-MPC report on Pages."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/mpc06-nilpotent-tube-pilot-v1"
CHECKER_PATH = ROOT / "scripts/reports/mpc06/check_tube.py"
RENDERER_PATH = ROOT / "scripts/reports/mpc06/render_tube.py"
spec = importlib.util.spec_from_file_location("mpc06_tube_checker", CHECKER_PATH)
checker = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(checker)
render_spec = importlib.util.spec_from_file_location("mpc06_tube_renderer", RENDERER_PATH)
renderer = importlib.util.module_from_spec(render_spec)
assert render_spec.loader is not None
render_spec.loader.exec_module(renderer)
FILES = ("README.md", "capture.json", "figure-data.json", "index.html",
         "projection.svg", "result.json", "scenario.json", "SHA256SUMS")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inputs(source: Path) -> dict[str, bytes]:
    if source.is_symlink() or not source.is_dir() or {p.name for p in source.iterdir()} != set(FILES):
        raise ValueError("MPC-06 report inventory differs")
    files = {name: (source / name).read_bytes() for name in FILES}
    checksums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        value, name = line.split("  ", 1)
        if name in checksums:
            raise ValueError("duplicate report checksum")
        checksums[name] = value
    if checksums != {name: digest(data) for name, data in files.items() if name != "SHA256SUMS"}:
        raise ValueError("MPC-06 report checksum mismatch")
    record = json.loads(files["result.json"])
    capture = json.loads(files["capture.json"])
    if not re.fullmatch(r"[0-9a-f]{40}", record.get("source_commit", "")):
        raise ValueError("MPC-06 source commit is invalid")
    if (capture.get("source_commit") != record["source_commit"] or
            capture.get("driver_sha256") != record.get("driver_sha256") or
            capture.get("checker_sha256") != record.get("checker_sha256") or
            capture.get("scenario_sha256") != record.get("scenario_sha256")):
        raise ValueError("MPC-06 capture and result provenance differ")
    if digest(CHECKER_PATH.read_bytes()) != record["checker_sha256"]:
        raise ValueError("MPC-06 checker identity differs")
    checker.check_record(record)
    with tempfile.TemporaryDirectory(prefix="mpc06-stage-") as temporary:
        generated = Path(temporary)
        input_path = generated / "result.json"
        input_path.write_bytes(files["result.json"])
        renderer.render(input_path, generated / "rendered")
        expected_dir = generated / "rendered"
        for name in ("figure-data.json", "projection.svg", "index.html"):
            if files[name] != (expected_dir / name).read_bytes():
                raise ValueError(f"MPC-06 saved renderer output differs: {name}")
    return files


def stage(source: Path, site: Path) -> str:
    files = inputs(source)
    index = site / "index.html"
    page = index.read_text(encoding="utf-8")
    identity = {name: digest(content) for name, content in sorted(files.items())}
    route = "mpc06-tube-" + digest(json.dumps(identity, sort_keys=True,
                                              separators=(",", ":")).encode())[:20]
    destination, archive_path = site / route, site / f"{route}.zip"
    if destination.exists() or archive_path.exists() or page.count("</body>") != 1:
        raise ValueError("MPC-06 Pages destination or landing insertion point differs")
    generated = dict(files)
    saved_page = generated["index.html"].decode("utf-8")
    footer = (f'<p>Immutable report <code>{route}</code> · '
              '<a href="publication-manifest.json">Publication manifest</a>.</p>')
    generated["index.html"] = saved_page.replace("</main>", footer + "</main>").encode("utf-8")
    generated["SHA256SUMS"] = "".join(
        f"{digest(generated[name])}  {name}\n" for name in sorted(generated)
        if name != "SHA256SUMS").encode("ascii")
    manifest = {"schema": "csl.mpc06-tube-publication/1", "report_id": route,
                "source_commit": json.loads(files["result.json"])["source_commit"],
                "source_files": identity,
                "published_files": {name: digest(value) for name, value in sorted(generated.items())}}
    generated["publication-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    destination.mkdir()
    for name, value in generated.items():
        (destination / name).write_bytes(value)
    link = (f'<section><h2>Exact tube-MPC feasibility pilot</h2>'
            f'<p>Nilpotent two-state tube, exact RPI inclusion, support tightenings, and an independent '
            f'eight-path disturbance reference. <a href="{route}/index.html">Open the report</a> · '
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
    args = parser.parse_args()
    print(stage(args.source, args.site))
