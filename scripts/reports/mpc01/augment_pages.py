"""Safely extract the upstream Pages artifact before adding a report route."""
from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import tarfile


def extract_pages_site(downloaded: Path, destination: Path) -> Path:
    if downloaded.is_symlink() or not downloaded.is_dir():
        raise ValueError("Pages artifact download directory is missing or unsafe")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Pages extraction destination must be fresh")
    candidates = list(downloaded.iterdir())
    if len(candidates) != 1 or candidates[0].name != "artifact.tar" or \
            candidates[0].is_symlink() or not candidates[0].is_file():
        raise ValueError("Pages download must contain exactly one regular artifact.tar")

    destination.mkdir(parents=True, exist_ok=False)
    try:
        with tarfile.open(candidates[0], "r:") as archive:
            members = archive.getmembers()
            if not members:
                raise ValueError("Pages artifact is empty")
            files: set[PurePosixPath] = set()
            directories: set[PurePosixPath] = set()
            for member in members:
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts or not path.parts:
                    raise ValueError(f"unsafe Pages artifact path: {member.name!r}")
                if not (member.isdir() or member.isfile()):
                    raise ValueError(f"unsupported Pages artifact entry: {member.name!r}")
                parents = set(path.parents) - {PurePosixPath(".")}
                if parents & files:
                    raise ValueError(f"Pages artifact member is nested under a file: {member.name!r}")
                if member.isfile():
                    if path in files or path in directories or any(
                            path in existing.parents for existing in files | directories):
                        raise ValueError(f"duplicate or conflicting Pages artifact path: {member.name!r}")
                    files.add(path)
                else:
                    if path in directories or path in files:
                        raise ValueError(f"duplicate or conflicting Pages artifact path: {member.name!r}")
                    directories.add(path)
            archive.extractall(destination, filter="data")
        if not (destination / "index.html").is_file() or (destination / "index.html").is_symlink():
            raise ValueError("upstream Pages artifact has no regular root index.html")
    except Exception:
        # Do not leave a partial site that a later run could mistake for a complete extraction.
        import shutil
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    print(extract_pages_site(args.download, args.destination).as_posix())
