"""Stage the reviewed issue #4 candidate certificate in the Pages index."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "issue4_volterra_renderer", ROOT / "scripts/reports/issue4_volterra/render.py")
report = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(report)

site_spec = importlib.util.spec_from_file_location("issue4_site", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(site_spec)
assert site_spec.loader is not None
site_spec.loader.exec_module(site)


def stage(source: Path, site_root: Path) -> str:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("bundle directory required")
    report_id, generated = report.render(
        (source / "records.json").read_bytes(),
        (ROOT / "scripts/reports/issue4_volterra/render.py").read_bytes(),
    )
    if source.name != report_id or {p.name for p in source.iterdir()} != set(generated):
        raise ValueError("saved bundle inventory or report identity differs")
    for name, content in generated.items():
        if (source / name).read_bytes() != content:
            raise ValueError("saved bundle bytes differ: " + name)
    site.OfflineHTML(set(generated)).feed(generated["index.html"].decode("utf-8"))
    destination = site_root / report_id
    if not site_root.is_dir() or destination.exists():
        raise ValueError("site must exist and route must be fresh")
    index = site_root / "index.html"
    index_text = index.read_text(encoding="utf-8")
    if index_text.count("</ul>") != 1 or report_id in index_text:
        raise ValueError("site index insertion point differs")
    link = (
        f'<li><a href="{report_id}/index.html">Issue 4 candidate Volterra model-error certificate</a>'
        f' — 60-stage validated 2D same-control bound'
        f' · <a href="{report_id}/records.json">raw JSON</a>'
        f' · <a href="{report_id}/{report_id}.zip">offline ZIP</a></li>'
    )
    site.OfflineHTML({f"{report_id}/index.html", f"{report_id}/records.json",
                      f"{report_id}/{report_id}.zip"}).feed(link)
    destination.mkdir()
    for name, content in generated.items():
        (destination / name).write_bytes(content)
    index.write_text(index_text.replace("</ul>", link + "</ul>"), encoding="utf-8")
    return report_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))
