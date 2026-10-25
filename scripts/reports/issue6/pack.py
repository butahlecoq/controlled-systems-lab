#!/usr/bin/env python3
"""Create a deterministic offline ZIP from a saved B06 report bundle."""
import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: pack.py RESULT_DIRECTORY")
    candidate = Path(sys.argv[1])
    if candidate.is_symlink():
        raise SystemExit("result directory must be a real directory")
    root = candidate.resolve()
    if not root.is_dir():
        raise SystemExit("result directory must be a real directory")
    files = {}
    for path in sorted(root.iterdir()):
        if path.name in {"manifest.json"} or path.name.endswith(".manifest.sha256"):
            continue
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"unexpected report entry: {path.name}")
        files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"schema": "csl.issue6-b06-files/1", "files": files}
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (root / "manifest.json").write_bytes(manifest_bytes)
    sidecar = root.parent / (root.name + ".manifest.sha256")
    sidecar.write_text(hashlib.sha256(manifest_bytes).hexdigest() + "  manifest.json\n")
    archive = root.parent / (root.name + ".zip")
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as output:
        for path in sorted(root.iterdir()):
            if path.name.endswith(".manifest.sha256"):
                continue
            if not path.is_file() or path.is_symlink():
                raise SystemExit(f"unexpected report entry: {path.name}")
            entry = ZipInfo(f"{root.name}/{path.name}", (1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            output.writestr(entry, path.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)
    print(archive)


if __name__ == "__main__":
    main()
