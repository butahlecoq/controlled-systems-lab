"""Stage one content-bound APP-02 report and its separate 2D example."""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("app02_saved_renderer", ROOT / "scripts/reports/app02/render_saved.py")
report = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(report)
site_spec = importlib.util.spec_from_file_location("app02_site_validator", Path(__file__).with_name("site.py"))
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
                           "APP-02 source inventory differs")
    site.OfflineHTML(expected).feed((bundle / "index.html").read_text(encoding="utf-8"))
    return {"report_id": record["report_id"], "source_commit": record["source_commit"],
            "schema": record["schema"],
            "manifest_sha256": sha((bundle / "manifest.json").read_bytes()),
            "zip_sha256": sha((bundle / "bundle.zip").read_bytes()),
            "renderer_sha256": sha((ROOT / "scripts/reports/app02/render_saved.py").read_bytes()),
            "stager_sha256": sha(Path(__file__).read_bytes())}


def example(record: dict) -> str:
    report_id = record["report_id"]
    source = record["source_commit"]
    diamond = record["fixtures"]["diamond-rotated-outer"]
    inner = record["fixtures"]["diamond-axis-inner"]
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>APP-02 planar approximation example</title><style>
body{{background:#272822;color:#f8f8f2;font:16px/1.55 system-ui,sans-serif;max-width:950px;margin:2rem auto;padding:0 1.5rem}}a{{color:#66d9ef}}h1,h2{{color:#a6e22e}}code{{color:#fd971f}}img{{max-width:100%}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}
</style></head><body><h1>APP-02: a diamond and two boxes</h1>
<p>This small two-dimensional example uses the reviewed saved output of <a href="../{report_id}/index.html">the APP-02 numerical report</a> at <a href="https://github.com/butahlecoq/controlled-systems-lab/tree/{source}">source commit <code>{source}</code></a>. Coordinates are x and y.</p>
<h2>Complete minimal input</h2><p>The input V polygon has ordered vertices <code>{escape(str(diamond['input_vertices']))}</code>, no rays and primitive budget 4. For the rotated outer parallelotope, use orientation rows <code>{escape(str(diamond['orientation_rows']))}</code>. The inner axis box uses the H diamond with rows <code>{escape(str(inner['input_h_rows']))}</code>, upper bounds <code>{escape(str(inner['input_h_bounds']))}</code>, and proposed corners <code>{escape(str(inner['ordered_corners']))}</code>.</p>
<figure><img src="polygons.svg" alt="Diamond vertices, outer axis box, rotated outer bound and inner axis box on labelled x and y axes"><figcaption>The figure draws saved geometric shapes, not intermediate algorithm steps.</figcaption></figure>
<h2>Check by hand</h2><p>Every input vertex satisfies −2 ≤ x ≤ 2 and −2 ≤ y ≤ 2, so the orange axis box contains the diamond. The rotated rows (1,1) and (1,−1) each have extrema ±2 at those vertices, giving the blue bounds |x+y| ≤ 2 and |x−y| ≤ 2. Their intersection is the diamond. Each green corner (±1,±1) satisfies the four input H inequalities at bound 2, so its convex hull lies inside the diamond. CSL's registered path independently checks these stored binary64 inclusion relations before returning an enclosure.</p>
<h2>Reproduce</h2><p>Checkout the linked source commit. Configure with <code>python -m cmake -S . -B build/app02 -DBUILD_TESTING=OFF -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF -DCSL_BUILD_APP02_REPORT=ON</code>; build <code>csl_app02_approximation_report</code> in Release; run the executable with <code>smoke</code>. The full authored inputs, literal output rows/corners and hashes are in <a href="../{report_id}/records.json">the saved record</a>; <a href="../{report_id}/smoke.csv">smoke results</a> and <a href="../{report_id}/bundle.zip">the offline bundle</a> are also available.</p></body></html>\n'''


def stage(catalog: Path, site_dir: Path) -> str:
    data = json.loads(catalog.read_text(encoding="utf-8"))
    report.collect.require(data.get("schema") == "csl.app02-publications/1" and
                           isinstance(data.get("reports"), list) and len(data["reports"]) == 1,
                           "APP-02 extension catalog differs")
    report_id = data["reports"][0]["report_id"]
    report.collect.require(report_id.startswith("app02-box-") and
                           len(report_id) == len("app02-box-") + 16,
                           "Unsafe APP-02 report ID")
    bundle = catalog.parent / report_id
    report.collect.require(data["reports"][0] == catalog_entry(bundle),
                           "APP-02 catalog differs from saved source")
    destination = site_dir / report_id
    example_dir = site_dir / "app02-example"
    report.collect.require(site_dir.is_dir() and not site_dir.is_symlink() and
                           not destination.exists() and not example_dir.exists(),
                           "APP-02 public route must be fresh")
    destination.mkdir()
    for path in bundle.iterdir():
        (destination / path.name).write_bytes(path.read_bytes())
    example_dir.mkdir()
    record = report.validate(bundle)
    example_html = example(record).encode()
    (example_dir / "index.html").write_bytes(example_html)
    (example_dir / "polygons.svg").write_bytes((bundle / "polygons.svg").read_bytes())
    site.OfflineHTML({"polygons.svg", "../" + report_id + "/index.html",
        "../" + report_id + "/records.json", "../" + report_id + "/smoke.csv",
        "../" + report_id + "/bundle.zip"}).feed(example_html.decode())
    index_path = site_dir / "index.html"
    index = index_path.read_text(encoding="utf-8")
    report.collect.require(index.count("</ul>") == 1 and report_id not in index,
                           "APP-02 site catalogue insertion point differs")
    link = ('<li><a href="' + escape(report_id) + '/index.html">APP-02 box and parallelotope report</a>'
            ' — five exact stored-binary64 examples and 3,500 verified measured calls'
            ' · <a href="app02-example/index.html">2D visual example</a>'
            ' · <a href="' + escape(report_id) + '/records.json">raw JSON</a>'
            ' · <a href="' + escape(report_id) + '/bundle.zip">offline ZIP</a></li>')
    site.OfflineHTML({report_id + "/index.html", report_id + "/records.json",
                      report_id + "/bundle.zip", "app02-example/index.html"}).feed(link)
    index_path.write_text(index.replace("</ul>", link + "</ul>"), encoding="utf-8")
    return report_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.source is not None and args.catalog is None and args.site is None:
        print(json.dumps({"schema": "csl.app02-publications/1",
                          "reports": [catalog_entry(args.source)]}, sort_keys=True, indent=2))
    elif args.source is None and args.catalog is not None and args.site is not None:
        print(stage(args.catalog, args.site))
    else:
        parser.error("Use --source alone, or --catalog and --site")
