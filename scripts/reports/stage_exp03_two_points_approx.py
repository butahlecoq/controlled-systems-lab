"""Publish the frozen EXP-03 TwoPoints approximation report on Pages."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/exp03-two-points-approx-pilot-v1"
REPORTS = {
    "exp03-two-points-approx-pilot-v1": "exp03-two-points-approx-publication-v1",
    "exp03-two-points-approx-pilot-v2": "exp03-two-points-approx-publication-v2",
}
BASE_FILES = (
    "README.md", "check.json", "index.html", "provenance.json",
    "reachability-and-approximations.svg", "reference.json", "run.json",
)
V2_RECORDS = ("comparison-record-projection-0.json", "comparison-record-projection-1.json")
sys.path.insert(0, str(ROOT / "scripts/reports/exp03"))
from build_comparison_records import validate_record


def files_for(source: Path) -> tuple[str, ...]:
    if source.name == "exp03-two-points-approx-pilot-v2":
        return (*BASE_FILES, *V2_RECORDS)
    return BASE_FILES


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_bundle(source: Path) -> dict[str, bytes]:
    if source.is_symlink() or not source.is_dir() or source.name not in REPORTS:
        raise ValueError("unexpected EXP-03 source bundle")
    files_to_read = files_for(source)
    if any((source / name).is_symlink() or not (source / name).is_file()
           for name in (*files_to_read, "SHA256SUMS")):
        raise ValueError("EXP-03 source bundle contains a missing or unsafe file")
    files = {name: (source / name).read_bytes() for name in files_to_read}
    raw_sums = (source / "SHA256SUMS").read_bytes()
    expected = {}
    for line in raw_sums.decode("ascii").splitlines():
        sha, name = line.split("  ", 1)
        if name in expected:
            raise ValueError("duplicate EXP-03 bundle checksum")
        expected[name] = sha
    if expected != {name: digest(data) for name, data in files.items()}:
        raise ValueError("EXP-03 saved bundle checksum mismatch")
    if {path.name for path in source.iterdir()} != set(files_to_read) | {"SHA256SUMS"}:
        raise ValueError("EXP-03 source inventory differs")
    check = json.loads(files["check.json"])
    run = json.loads(files["run.json"])
    reference = json.loads(files["reference.json"])
    provenance = json.loads(files["provenance.json"])
    if (check.get("schema") != "csl.exp03-two-points-approximation-check/1" or
            check.get("status") != "verified" or
            check.get("measurement_coverage", {}).get("status") != "complete" or
            check.get("measurement_coverage", {}).get("count_mismatches") != [] or
            run.get("schema") != "csl.exp03-two-points-approximation-run/1" or
            reference.get("schema") != "csl.exp03-two-points-reference/1" or
            run.get("case_id") != check.get("case_id") or
            reference.get("case_id") != check.get("case_id") or
            provenance.get("schema") != "csl.exp03-two-points-approximation-provenance/1"):
        raise ValueError("EXP-03 evidence identity or saved checker outcome differs")
    if source.name == "exp03-two-points-approx-pilot-v2":
        for name in V2_RECORDS:
            record = json.loads(files[name])
            validate_record(record)
            if len(record["attempts"]) != 40:
                raise ValueError("EXP-03 v2 paired comparison record is missing attempts")
    return files | {"SHA256SUMS": raw_sums}


def stage(source: Path, site: Path) -> str:
    files = read_bundle(source)
    if not site.is_dir() or site.is_symlink():
        raise ValueError("Pages site must be a regular directory")
    report_id = REPORTS[source.name]
    destination = site / report_id
    if destination.exists() or destination.is_symlink():
        raise ValueError("EXP-03 publication route must be fresh")
    index = site / "index.html"
    html = index.read_text(encoding="utf-8")
    if html.count("</ul>") != 1 or report_id in html:
        raise ValueError("Pages landing index insertion point differs")

    published = dict(files)
    source_page = published["index.html"].decode("utf-8")
    if (source_page.count("</head>") != 1 or source_page.count('<figure class="figure">') != 1 or
            source_page.count("</figcaption>") != 1 or source_page.count("</main>") != 1):
        raise ValueError("EXP-03 HTML presentation hooks differ")
    source_page = source_page.replace(
        '<figure class="figure">',
        '<figure class="figure" tabindex="0" role="region" '
        'aria-label="Scrollable combined figure: point 1 and point 2 phase planes">')
    source_page = source_page.replace(
        '<figure class="figure" tabindex=',
        '<p class="note">On narrow screens, swipe or scroll the figure horizontally to view both phase planes. '
        'The panels use independent coordinate ranges and position/velocity units; compare geometry within each panel.</p>'
        '<figure class="figure" tabindex=')
    source_page = source_page.replace(
        "</figcaption>",
        " The panels use independent coordinate ranges and position/velocity units; compare geometry within each panel."
        "</figcaption>")
    source_page = source_page.replace(
        "</head>",
        '<style>@media print{@page{size:landscape;margin:0.45in}'
        '.note{display:none!important}.figure{overflow:visible!important}.figure img{width:auto!important;min-width:0!important;'
        'height:4.7in!important;max-width:100%!important;margin:auto}}'
        '</style></head>')
    published["index.html"] = source_page.encode("utf-8")
    published["SHA256SUMS"] = "".join(
        f"{digest(published[name])}  {name}\n" for name in sorted(published)
        if name != "SHA256SUMS").encode("ascii")

    destination.mkdir()
    for name, data in published.items():
        (destination / name).write_bytes(data)
    manifest = {
        "schema": "csl.exp03-two-points-approx-publication/1",
        "report_id": report_id,
        "source_report_id": source.name,
        "source_bundle_sha256": digest(files["SHA256SUMS"]),
        "published_files": {name: digest(data) for name, data in sorted(published.items())},
    }
    (destination / "publication-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    links = (
        f'<li><a href="{report_id}/index.html">TwoPoints differential-game reachability and approximation figure</a>'
        f' · <a href="{report_id}/reachability-and-approximations.svg">combined phase-plane figure</a>'
        f' · <a href="{report_id}/run.json">raw method results</a>'
        f' · <a href="{report_id}/check.json">independent inclusion checks</a>'
        + (f' · <a href="{report_id}/comparison-record-projection-0.json">(x1,x2) comparison record</a>'
           f' · <a href="{report_id}/comparison-record-projection-1.json">(x3,x4) comparison record</a>'
           if source.name == "exp03-two-points-approx-pilot-v2" else "")
        + "</li>")
    index.write_text(html.replace("</ul>", links + "</ul>"), encoding="utf-8")
    return report_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))


if __name__ == "__main__":
    main()
