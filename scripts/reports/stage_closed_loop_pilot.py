#!/usr/bin/env python3
"""Stage the versioned closed-loop pilot report and 2D example from saved records."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import site_design
REPORT_ID = "closed-loop-pilot-v1"
CARD = (
    '<article class="saved-figure" id="closed-loop-pilot-v1">'
    '<p class="eyebrow">Closed-loop control · numerical pilot</p>'
    '<h3>Three source-bound observed-state NMPC trajectories</h3>'
    '<p>Lotka–Volterra, Earth-orbit, and fuel episodes use their complete source horizons, common CSL held-step execution, and independent numerical replay checks. No speed ranking or reachability claim is made.</p>'
    '<p><a href="../closed-loop-pilot-v1/index.html">Open the standalone three-task report →</a> · '
    '<a href="closed-loop-pilot-2d.html">Lotka–Volterra 2D example</a></p></article>'
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_map(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): digest(path.read_bytes())
            for path in sorted(root.rglob("*")) if path.is_file()}


def mutable_example(example: bytes) -> bytes:
    """Frame the saved 2D content as a current mutable learning companion."""
    markup = example.decode("utf-8")
    old_shell = '<body><div class="shell"><aside aria-hidden="true"></aside><main>\n'
    require(old_shell in markup, "saved 2D example shell differs from the known renderer output")
    start = site_design.page_start(
        "Lotka–Volterra observed-state trajectory",
        stylesheet_href="examples.css",
        crumbs=[("Learn", "../index.html"), ("Examples", "../examples/index.html"),
                ("Closed-loop 2D companion", "closed-loop-pilot-2d.html")],
    ).partition("<body>")[2]
    markup = markup.replace(old_shell, "<body>" + start, 1)
    old_end = "</main></div></body></html>"
    require(markup.endswith(old_end), "saved 2D example ending differs from the known renderer output")
    markup = markup[:-len(old_end)] + site_design.page_end() + "</body></html>"
    markup = markup.replace('<p class="muted">', '<p class="eyebrow">')
    markup = markup.replace('class="panel"', '')
    status = ('<p class="note"><strong>Capture-time publication status.</strong> The immutable v1 report records '
              'that review and main-only Pages deployment were pending when its evidence bundle was captured. '
              'That saved status text remains part of the versioned report and does not describe this current '
              'mutable companion.</p>')
    markup = markup.replace('</h1>', '</h1>' + status, 1)
    markup = site_design.focusable_code_blocks(markup, "Saved-report reproduction code")
    return markup.encode("utf-8")


def stage(source: Path, site: Path) -> None:
    source = source.resolve(); site = site.resolve()
    manifest_path = source / "manifest.json"
    require(source.is_dir() and manifest_path.is_file() and not manifest_path.is_symlink(),
            "saved closed-loop pilot report bundle is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("schema") == "csl.closed-loop-published-report/1" and
            manifest.get("report_id") == REPORT_ID, "unsupported closed-loop report manifest")
    for relative, expected in manifest["files"].items():
        path = source / relative
        require(source.resolve() in path.resolve().parents and path.is_file() and not path.is_symlink(),
                "missing or unsafe report asset: " + relative)
        require(digest(path.read_bytes()) == expected, "saved report asset digest differs: " + relative)
    for name in ("index.html", "example-2d.html", "raw/coverage.json"):
        require((source / name).is_file(), "required saved report file is missing: " + name)
    example = (source / "example-2d.html").read_bytes()
    require(b'href="examples.css"' in example, "2D example must use the shared examples stylesheet")
    archive = source.parent / f"{REPORT_ID}.zip"
    require(archive.is_file() and not archive.is_symlink(), "offline closed-loop report ZIP is missing")
    gallery = site / "examples/index.html"
    require(gallery.is_file() and not gallery.is_symlink(), "Pages visual examples gallery is missing")
    html = gallery.read_text(encoding="utf-8")
    marker = '<section id="analytic-illustrations">'
    require(marker in html or 'id="closed-loop-pilot-v1"' in html,
            "visual examples gallery insertion point is missing")
    require('id="closed-loop-pilot-v1"' not in html or CARD in html,
            "closed-loop pilot gallery route collides with existing content")
    route = site / REPORT_ID
    if route.exists():
        require(route.is_dir() and file_map(route) == file_map(source),
                "versioned Pages report route exists with different content")
    else:
        route.mkdir(parents=True)
        for path in sorted(source.rglob("*")):
            if path.is_file():
                target = route / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
    staged_archive = site / f"{REPORT_ID}.zip"
    if staged_archive.exists():
        require(staged_archive.is_file() and digest(staged_archive.read_bytes()) == digest(archive.read_bytes()),
                "versioned Pages offline bundle exists with different content")
    else:
        shutil.copyfile(archive, staged_archive)
    shared_example = site / "examples/closed-loop-pilot-2d.html"
    shared_example_bytes = (mutable_example(example).replace(b'href="index.html"',
        b'href="../closed-loop-pilot-v1/index.html"')
        .replace(b'src="assets/', b'src="../closed-loop-pilot-v1/assets/')
        .replace(b'href="raw/', b'href="../closed-loop-pilot-v1/raw/'))
    if shared_example.exists():
        require(shared_example.is_file() and shared_example.read_bytes() == shared_example_bytes,
                "shared 2D example path exists with different content")
    else:
        shared_example.write_bytes(shared_example_bytes)
    if 'id="closed-loop-pilot-v1"' not in html:
        gallery.write_text(html.replace(marker, CARD + marker, 1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
        default=ROOT / "reports/closed-loop-pilot/closed-loop-pilot-v1")
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    stage(args.source, args.site)


if __name__ == "__main__":
    main()
