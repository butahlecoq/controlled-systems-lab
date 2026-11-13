"""Stage the affine-history functional evidence and its gallery link."""
import argparse
import hashlib
from pathlib import Path
import shutil
import zipfile

import history_warm_gap_report

ROOT = Path(__file__).resolve().parents[2]
REPORT = "closed-loop-history-functional"
RECORDS = ("lv-highs-f4", "orbit-ipopt-f4", "fuel-ipopt-3c", "fuel-highs-f4-timeout",
           "lv-box-fd28", "fuel-box-a800", "orbit-box-a800-incomplete", "orbit-box-aeac-incomplete",
           "lv-zonotope-b78", "lv-parallelotope-b78", "lv-ellipsoid-b78", "lv-box-warm-a488", "orbit-box-warm-a488-incomplete",
           "warm-tiny-a488", "lv-box-warm-a488-execution-failure", "orbit-box-warm-a488-execution-failure")
CARD = ('<article class="saved-figure" id="closed-loop-history-functional">'
        '<h3>Continuous affine-history control: functional evidence</h3>'
        '<p>Original-horizon direct and selected F/B/I family physical episodes, plus a separately retained HiGHS fuel timeout, with source-bound records.</p>'
        '<p><a href="../closed-loop-history-functional/index.html">Open functional evidence →</a></p></article>')


def stage(source: Path, site: Path) -> None:
    source = source.resolve(strict=True)
    site = site.resolve(strict=True)
    warm_gap = source / "warm-gap-9540-v1"
    if warm_gap.exists():
        history_warm_gap_report.validate(warm_gap)
    for record in RECORDS:
        directory = source / record
        checksums = directory / "SHA256SUMS"
        if not checksums.is_file() or checksums.is_symlink():
            raise ValueError("Missing or unsafe checksums: " + record)
        for line in checksums.read_text(encoding="utf-8").splitlines():
            expected, name = line.split("  ", 1)
            path = directory / name
            if path.is_symlink() or path.resolve().parent != directory.resolve() or not path.is_file():
                raise ValueError("Unsafe evidence member: " + name)
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError("Evidence digest differs: " + name)
        with zipfile.ZipFile(directory / "raw.zip") as archive:
            if archive.testzip() is not None:
                raise ValueError("Evidence ZIP CRC failure: " + record)
    for name in ("lv-box-stages-fd28", "lv-box-overlay-fd28", "fuel-box-overlay-a800", "lv-box-warm-overlay-a488"):
        directory = source / name
        sums = directory / "SHA256SUMS"
        if not sums.is_file() or sums.is_symlink():
            raise ValueError("Missing or unsafe figure checksums: " + name)
        for line in sums.read_text(encoding="utf-8").splitlines():
            expected, member = line.split("  ", 1)
            path = directory / member
            if (path.is_symlink() or path.resolve().parent != directory.resolve() or not path.is_file()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
                raise ValueError("Unsafe or changed figure member: " + member)
    files = [path for path in sorted(source.rglob("*")) if path.is_file()]
    if any(path.is_symlink() or source not in path.resolve().parents for path in files):
        raise ValueError("Unsafe source path")
    gallery = site / "examples/index.html"
    if not gallery.is_file() or gallery.is_symlink():
        raise ValueError("Gallery missing or unsafe")
    html = gallery.read_text(encoding="utf-8")
    marker = '<section id="analytic-illustrations">'
    if marker not in html and CARD not in html:
        raise ValueError("Gallery insertion point missing")
    route = site / REPORT
    for path in files:
        target = route / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and (target.is_symlink() or target.read_bytes() != path.read_bytes()):
            raise ValueError("Existing route differs: " + str(target))
        if not target.exists():
            shutil.copyfile(path, target)
    if CARD not in html:
        gallery.write_text(html.replace(marker, CARD + marker, 1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "reports" / REPORT)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    stage(args.source, args.site)


if __name__ == "__main__":
    main()
