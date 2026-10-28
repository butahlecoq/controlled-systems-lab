"""Package and stage the EXP-02 4D simplex hull pilot."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
from pathlib import Path, PurePosixPath
import shutil
import zipfile

REPORT_ID = "exp02-it17-hull-4d-simplex-20261028-r1"
site_spec = importlib.util.spec_from_file_location(
    "exp02_hull4d_site", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(site_spec)
assert site_spec.loader is not None
site_spec.loader.exec_module(site)


def bundle_files(bundle: Path) -> list[Path]:
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("report bundle directory required")
    files = sorted(bundle.rglob("*"))
    if any(path.is_symlink() for path in files):
        raise ValueError("report bundles must not contain symlinks")
    return [path for path in files if path.is_file()]


def package(bundle: Path) -> str:
    if bundle.name != REPORT_ID:
        raise ValueError("unexpected EXP-02 4D bundle ID")
    files = bundle_files(bundle)
    archive_path = bundle / f"{REPORT_ID}.zip"
    manifest_path = bundle / "SHA256SUMS"
    files = [path for path in files if path not in {archive_path, manifest_path}]
    if not files or not (bundle / "index.html").is_file():
        raise ValueError("report bundle is missing its page or payload")
    manifest = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(bundle).as_posix()}\n"
        for path in files
    )
    manifest_path.write_text(manifest, encoding="utf-8")
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in [*files, manifest_path]:
            info = zipfile.ZipInfo(path.relative_to(bundle).as_posix(),
                                   date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return hashlib.sha256(archive_path.read_bytes()).hexdigest()


def verify_bundle(bundle: Path) -> str:
    files = bundle_files(bundle)
    archive_path = bundle / f"{REPORT_ID}.zip"
    manifest_path = bundle / "SHA256SUMS"
    if bundle.name != REPORT_ID or archive_path not in files or manifest_path not in files:
        raise ValueError("4D bundle identity, offline ZIP, or checksum manifest is missing")
    entries: dict[str, str] = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        fields = line.split("  ", 1)
        if len(fields) != 2 or len(fields[0]) != 64:
            raise ValueError("malformed SHA256SUMS entry")
        digest, relative = fields
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or relative in entries:
            raise ValueError("unsafe or duplicate manifest path")
        entries[relative] = digest
    actual = {
        path.relative_to(bundle).as_posix(): path
        for path in files if path not in {archive_path, manifest_path}
    }
    if set(entries) != set(actual):
        raise ValueError("bundle contents differ from SHA256SUMS")
    for relative, path in actual.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != entries[relative]:
            raise ValueError("bundle checksum mismatch: " + relative)
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(actual) | {"SHA256SUMS"}:
            raise ValueError("offline ZIP inventory differs from the source bundle")
        if archive.read("SHA256SUMS") != manifest_path.read_bytes():
            raise ValueError("offline ZIP contains a different checksum manifest")
        for relative, digest in entries.items():
            if hashlib.sha256(archive.read(relative)).hexdigest() != digest:
                raise ValueError("offline ZIP checksum mismatch: " + relative)
    site.OfflineHTML(set(entries) | {"SHA256SUMS", archive_path.name}).feed(
        (bundle / "index.html").read_text(encoding="utf-8"))
    return hashlib.sha256(archive_path.read_bytes()).hexdigest()


def stage(bundle: Path, site_root: Path) -> str:
    bundle, site_root = Path(bundle), Path(site_root)
    if bundle.name != REPORT_ID:
        raise ValueError("unexpected EXP-02 4D report ID")
    archive_sha = verify_bundle(bundle)
    index_path = site_root / "index.html"
    if site_root.is_symlink() or not site_root.is_dir() or index_path.is_symlink():
        raise ValueError("generated Pages site required")
    index = index_path.read_text(encoding="utf-8")
    if index.count("</ul>") != 1 or REPORT_ID in index:
        raise ValueError("Pages index insertion point differs or route already exists")
    route = (
        f'<li><a href="{REPORT_ID}/index.html">EXP-02 4D simplex hull reducer pilot</a>'
        ' — one deterministic 250-point fixture; three of five LP reducers completed, '
        'two exact but incomplete outputs have withheld timings, and no speedup is claimed.'
        f' · <a href="{REPORT_ID}/{REPORT_ID}.zip">offline bundle</a>'
        f' · bundle SHA256 {archive_sha[:12]}</li>'
    )
    site.OfflineHTML({f"{REPORT_ID}/index.html", f"{REPORT_ID}/{REPORT_ID}.zip"}).feed(route)
    destination = site_root / REPORT_ID
    if destination.exists():
        raise ValueError("EXP-02 4D Pages route must be fresh")
    shutil.copytree(bundle, destination, symlinks=False)
    index_path.write_text(index.replace("</ul>", route + "</ul>", 1), encoding="utf-8")
    return REPORT_ID


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    if args.package:
        print(f"{args.package.name} {package(args.package)}")
    if args.source or args.site:
        if not (args.source and args.site):
            parser.error("--source and --site must be used together")
        print(stage(args.source, args.site))


if __name__ == "__main__":
    main()
