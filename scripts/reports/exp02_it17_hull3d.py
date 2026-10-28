"""Package and stage the EXP-02 3D hull pilot reports."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
from pathlib import Path, PurePosixPath
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PRIMARY_ID = "exp02-it17-hull-3d-simplex-20261028-r1"
INITIAL_ID = "exp02-it17-hull-3d-halton-cloud-20261028-r1"
REPORTS = ROOT / "reports/algorithm-results"
site_spec = importlib.util.spec_from_file_location("exp02_report_site", Path(__file__).with_name("site.py"))
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
    if bundle.name not in {PRIMARY_ID, INITIAL_ID}:
        raise ValueError("unexpected EXP-02 bundle ID")
    files = bundle_files(bundle)
    archive_path = bundle / f"{bundle.name}.zip"
    if archive_path in files:
        files.remove(archive_path)
    manifest_path = bundle / "SHA256SUMS"
    files = [path for path in files if path != manifest_path]
    if not files or not (bundle / "index.html").is_file():
        raise ValueError("report bundle is missing its page or payload")
    manifest = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(bundle).as_posix()}\n"
        for path in files
    )
    manifest_path.write_text(manifest, encoding="utf-8")
    archived = [*files, manifest_path]
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in archived:
            name = path.relative_to(bundle).as_posix()
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return hashlib.sha256(archive_path.read_bytes()).hexdigest()


def verify_bundle(bundle: Path) -> str:
    files = bundle_files(bundle)
    archive_path = bundle / f"{bundle.name}.zip"
    manifest_path = bundle / "SHA256SUMS"
    if archive_path not in files or manifest_path not in files:
        raise ValueError("offline ZIP and SHA256SUMS are required")
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
        expected = set(actual) | {"SHA256SUMS"}
        if len(names) != len(set(names)) or set(names) != expected:
            raise ValueError("offline ZIP inventory differs from the source bundle")
        if archive.read("SHA256SUMS") != manifest_path.read_bytes():
            raise ValueError("offline ZIP contains a different checksum manifest")
        for relative, digest in entries.items():
            if hashlib.sha256(archive.read(relative)).hexdigest() != digest:
                raise ValueError("offline ZIP checksum mismatch: " + relative)
    for path in (bundle / "index.html",):
        allowed = set(entries) | {"SHA256SUMS", f"{bundle.name}.zip"}
        if bundle.name == PRIMARY_ID:
            allowed.add(f"../{INITIAL_ID}/index.html")
        site.OfflineHTML(allowed).feed(path.read_text(encoding="utf-8"))
    return hashlib.sha256(archive_path.read_bytes()).hexdigest()


def stage(primary: Path, initial: Path, site_root: Path) -> str:
    primary, initial, site_root = map(Path, (primary, initial, site_root))
    if primary.name != PRIMARY_ID or initial.name != INITIAL_ID:
        raise ValueError("unexpected EXP-02 report IDs")
    primary_sha = verify_bundle(primary)
    initial_sha = verify_bundle(initial)
    index_path = site_root / "index.html"
    if site_root.is_symlink() or not site_root.is_dir() or index_path.is_symlink():
        raise ValueError("generated Pages site required")
    index = index_path.read_text(encoding="utf-8")
    if index.count("</ul>") != 1 or PRIMARY_ID in index or INITIAL_ID in index:
        raise ValueError("Pages index insertion point differs or route already exists")
    routes = (
        f'<li><a href="{PRIMARY_ID}/index.html">EXP-02 3D hull reducers: tetrahedron with exact interior redundancy</a>'
        ' — one deterministic 250-point fixture; three of five LP reducers completed, and no speedup is claimed.'
        f' · <a href="{PRIMARY_ID}/{PRIMARY_ID}.zip">offline bundle</a>'
        f' · <a href="{INITIAL_ID}/index.html">initial pure-Halton attempt</a>'
        f' · <a href="{INITIAL_ID}/{INITIAL_ID}.zip">raw exploratory bundle</a>'
        f' · bundle SHA256 {primary_sha[:12]} / {initial_sha[:12]}</li>'
    )
    site.OfflineHTML({f"{PRIMARY_ID}/index.html", f"{PRIMARY_ID}/{PRIMARY_ID}.zip",
                      f"{INITIAL_ID}/index.html", f"{INITIAL_ID}/{INITIAL_ID}.zip"}).feed(routes)
    primary_destination, initial_destination = site_root / PRIMARY_ID, site_root / INITIAL_ID
    if primary_destination.exists() or initial_destination.exists():
        raise ValueError("EXP-02 Pages routes must be fresh")
    shutil.copytree(initial, initial_destination, symlinks=False)
    shutil.copytree(primary, primary_destination, symlinks=False)
    index_path.write_text(index.replace("</ul>", routes + "</ul>", 1), encoding="utf-8")
    return PRIMARY_ID


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, action="append", default=[])
    parser.add_argument("--primary", type=Path)
    parser.add_argument("--initial", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    for bundle in args.package:
        print(f"{bundle.name} {package(bundle)}")
    if args.primary or args.initial or args.site:
        if not (args.primary and args.initial and args.site):
            parser.error("--primary, --initial, and --site must be used together")
        print(stage(args.primary, args.initial, args.site))


if __name__ == "__main__":
    main()
