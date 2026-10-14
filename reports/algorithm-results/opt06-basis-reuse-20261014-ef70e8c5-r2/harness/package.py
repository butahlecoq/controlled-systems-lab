"""Create deterministic OPT-06 evidence manifests and bundle ZIP."""
from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(directory: Path) -> None:
    rows = []
    own_manifest = directory / "manifest.sha256"
    for path in sorted(p for p in directory.rglob("*") if p.is_file() and p != own_manifest):
        rows.append(f"{digest(path)}  {path.relative_to(directory).as_posix()}")
    (directory / "manifest.sha256").write_text("\n".join(rows) + "\n", encoding="ascii")


def main() -> None:
    # Every evidence subtree is independently verifiable. Parent manifests bind
    # nested manifests as ordinary files, making edits detectable at each level.
    for directory in sorted((p for p in ROOT.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        write_manifest(directory)

    for name in ("bundle.zip", "bundle.zip.sha256"):
        (ROOT / name).unlink(missing_ok=True)
    write_manifest(ROOT)
    manifest = ROOT / "manifest.sha256"
    archive_path = ROOT / "bundle.zip"
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and p.name not in {"bundle.zip", "bundle.zip.sha256"})
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in files:
            name = f"{ROOT.name}/{path.relative_to(ROOT).as_posix()}"
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    archive_digest = digest(archive_path)
    (ROOT / "bundle.zip.sha256").write_text(f"{archive_digest}  bundle.zip\n", encoding="ascii")

    external = ROOT.parent / f"{ROOT.name}.source.zip"
    external.write_bytes(archive_path.read_bytes())
    (ROOT.parent / f"{external.name}.sha256").write_text(f"{archive_digest}  {external.name}\n", encoding="ascii")
    print(f"packaged {len(files)} files; bundle SHA-256 {archive_digest}")


if __name__ == "__main__":
    main()
