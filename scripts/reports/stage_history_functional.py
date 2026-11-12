"""Stage the affine-history functional evidence and its gallery link."""
import argparse
import hashlib
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]
REPORT = "closed-loop-history-functional"
RECORDS = ("lv-highs-f4", "orbit-ipopt-f4", "fuel-ipopt-3c", "fuel-highs-f4-timeout",
           "lv-box-fd28")
CARD = ('<article class="saved-figure" id="closed-loop-history-functional">'
        '<h3>Continuous affine-history control: functional evidence</h3>'
        '<p>Original-horizon direct and F/B/I box physical episodes, plus a separately retained HiGHS fuel timeout, with source-bound records.</p>'
        '<p><a href="../closed-loop-history-functional/index.html">Open functional evidence →</a></p></article>')


def stage(source: Path, site: Path) -> None:
    source = source.resolve(strict=True)
    site = site.resolve(strict=True)
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
