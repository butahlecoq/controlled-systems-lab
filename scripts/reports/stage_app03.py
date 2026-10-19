"""Stage one reviewed content-bound APP-03 report and its 2D example."""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "app03_saved_renderer", ROOT / "scripts/reports/app03/render_saved.py")
report = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(report)
site_spec = importlib.util.spec_from_file_location(
    "app03_site_validator", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(site_spec)
assert site_spec.loader is not None
site_spec.loader.exec_module(site)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def catalog_entry(bundle: Path) -> dict:
    report.render(bundle, check=True)
    record = report.validate(bundle)
    expected = set(report.expected_files(bundle))
    report.collect.require({path.name for path in bundle.iterdir()} == expected,
                           "APP-03 saved inventory differs")
    site.OfflineHTML(expected).feed((bundle / "index.html").read_text(encoding="utf-8"))
    site.OfflineHTML(expected).feed((bundle / "example-2d.html").read_text(encoding="utf-8"))
    return {"report_id": record["report_id"], "source_commit": record["source_commit"],
            "schema": record["schema"],
            "manifest_sha256": sha((bundle / "manifest.json").read_bytes()),
            "zip_sha256": sha((bundle / "bundle.zip").read_bytes()),
            "renderer_sha256": sha((ROOT / "scripts/reports/app03/render_saved.py").read_bytes()),
            "stager_sha256": sha(Path(__file__).read_bytes())}


def example(record: dict) -> bytes:
    report_id = record["report_id"]
    fixture = record["fixtures"]["diamond-axis-cover"]
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>APP-03 planar zonotope example</title><style>
body{{background:#272822;color:#f8f8f2;font:16px/1.55 system-ui,sans-serif;max-width:800px;margin:2rem auto;padding:0 1.5rem}}a{{color:#66d9ef}}img{{max-width:100%}}code{{color:#fd971f}}</style></head><body><h1>APP-03: a planar zonotope cover</h1>
<p>This example uses the saved output of <a href="../{report_id}/index.html">the APP-03 numerical report</a> at <a href="https://github.com/butahlecoq/controlled-systems-lab/tree/{record['source_commit']}">source commit <code>{record['source_commit']}</code></a>. The coordinate labels are x and y.</p>
<h2>Complete minimal input</h2><p>The center is <code>{escape(str(fixture['center']))}</code>, the three generator columns are <code>(1,0)</code>, <code>(0,1)</code> and <code>(0.5,0.5)</code>, factor IDs are <code>{escape(str(fixture['input_factor_ids']))}</code>, and the generator budget is <code>{fixture['budget']}</code>. Request a numerical outer <code>csl.zonotope</code> cover through <code>csl.geometry.zonotope.axis-cover</code>.</p>
<figure><img src="zonotope-2d.svg" alt="Labelled x-y plot of input signed generator sums and outer axis square"><figcaption>The blue hull joins signed generator sums. Orange is the admitted outer cover; white points include interior signed sums. This drawing illustrates saved shapes, not intermediate algorithm steps.</figcaption></figure>
<h2>Check by hand</h2><p>Each source x coordinate is within [−1.5,1.5], and so is each y coordinate. The cover's generator rows are <code>{escape(str(fixture['expected_generators']))}</code>, giving precisely that axis square. In direction (1,−1), source support is 2 while cover support is 3. The registered policy independently verifies the stored-binary64 outer inclusion.</p>
<h2>Reproduce</h2><p>At the linked commit, configure CMake in Release with <code>BUILD_TESTING=OFF</code>, <code>CSL_ENABLE_HIGHS=OFF</code>, <code>CSL_ENABLE_QHULL=OFF</code> and <code>CSL_BUILD_APP03_REPORT=ON</code>; build <code>csl_app03_zonotope_report</code> and run <code>smoke</code>. The complete fixture, hashes and measured results are in the <a href="../{report_id}/records.json">raw record</a>; the <a href="../{report_id}/bundle.zip">offline bundle</a> includes the source and a standalone example.</p></body></html>\n'''.encode()


def stage(catalog: Path, site_dir: Path) -> str:
    data = json.loads(catalog.read_text(encoding="utf-8"))
    report.collect.require(data.get("schema") == "csl.app03-publications/1" and
                           isinstance(data.get("reports"), list) and len(data["reports"]) == 1,
                           "APP-03 publication catalog differs")
    report_id = data["reports"][0]["report_id"]
    report.collect.require(report_id.startswith("app03-zonotope-") and
                           len(report_id) == len("app03-zonotope-") + 16,
                           "Unsafe APP-03 report ID")
    bundle = catalog.parent / report_id
    report.collect.require(data["reports"][0] == catalog_entry(bundle),
                           "APP-03 catalog differs from saved evidence")
    destination = site_dir / report_id
    example_dir = site_dir / "app03-example"
    report.collect.require(site_dir.is_dir() and not site_dir.is_symlink() and
                           not destination.exists() and not example_dir.exists(),
                           "APP-03 routes must be fresh")
    destination.mkdir()
    for path in bundle.iterdir():
        (destination / path.name).write_bytes(path.read_bytes())
    example_dir.mkdir()
    record = report.validate(bundle)
    example_html = example(record)
    (example_dir / "index.html").write_bytes(example_html)
    (example_dir / "zonotope-2d.svg").write_bytes((bundle / "zonotope-2d.svg").read_bytes())
    site.OfflineHTML({"zonotope-2d.svg", "../" + report_id + "/index.html",
                      "../" + report_id + "/records.json",
                      "../" + report_id + "/bundle.zip"}).feed(example_html.decode())
    index_path = site_dir / "index.html"
    index = index_path.read_text(encoding="utf-8")
    report.collect.require(index.count("</ul>") == 1 and report_id not in index,
                           "APP-03 site insertion point differs")
    link = ('<li><a href="' + escape(report_id) + '/index.html">APP-03 zonotope reduction report</a>'
            ' — three planar cases and 2,100 verified measured calls'
            ' · <a href="app03-example/index.html">2D visual example</a>'
            ' · <a href="' + escape(report_id) + '/records.json">raw JSON</a>'
            ' · <a href="' + escape(report_id) + '/bundle.zip">offline ZIP</a></li>')
    site.OfflineHTML({report_id + "/index.html", "app03-example/index.html",
                      report_id + "/records.json", report_id + "/bundle.zip"}).feed(link)
    index_path.write_text(index.replace("</ul>", link + "</ul>"), encoding="utf-8")
    return report_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.source is not None and args.catalog is None and args.site is None:
        print(json.dumps({"schema": "csl.app03-publications/1",
                          "reports": [catalog_entry(args.source)]}, sort_keys=True, indent=2))
    elif args.source is None and args.catalog is not None and args.site is not None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("Use --source alone, or --catalog and --site")
