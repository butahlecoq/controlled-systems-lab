"""Validate and stage frozen native model examples; no model computation runs here."""
from __future__ import annotations

import hashlib
import json
import zipfile
from html import escape
from io import BytesIO
from pathlib import Path, PurePosixPath

from report_data import require

ROUTE = "native-model-catalogue-v1"
SOURCE = "19d32a3c37b6860dbf881996da1bf5e2b3f92353"
MANIFEST_SHA256 = "4c1c25872414f9ac7c12fa3fdfb9c9cff24b43174f462ac7f72a795889b0e3ad"
ARCHIVE_SHA256 = "f2c3576403cd367a78d4a81fbdca59db970da43094ad456070561c8ce49bbf30"


def _file(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative)
    require(bool(relative) and not parts.is_absolute() and
            all(part not in {".", ".."} for part in parts.parts) and
            parts.as_posix() == relative and "\\" not in relative,
            "native catalogue asset path is unsafe")
    path = root
    require(not path.is_symlink(), "native catalogue root is symlinked")
    for part in parts.parts:
        path = path / part
        require(not path.is_symlink(), "native catalogue asset is symlinked")
    require(path.is_file(), "native catalogue asset is missing: " + relative)
    return path


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    repository_root = Path(repository_root)
    root = repository_root / "reports/algorithm-results" / ROUTE
    # Check every ancestor before any resolution can erase a symbolic link.
    current = repository_root
    for part in ("reports", "algorithm-results", ROUTE):
        current = current / part
        require(not current.is_symlink(), "native catalogue ancestor is symlinked")
    raw_manifest = _file(root, "manifest.json").read_bytes()
    require(hashlib.sha256(raw_manifest).hexdigest() == MANIFEST_SHA256,
            "native catalogue manifest differs from the frozen publication identity")
    manifest = json.loads(raw_manifest)
    require(manifest["schema"] == "csl.native-model-catalogue-functional/1" and
            manifest["source_commit"] == SOURCE, "native catalogue source differs")
    records = manifest["files_sha256"]
    require(isinstance(records, dict) and records, "native catalogue digest list is empty")
    files = {"manifest.json": raw_manifest}
    for name, digest in records.items():
        content = _file(root, name).read_bytes()
        require(hashlib.sha256(content).hexdigest() == digest,
                "native catalogue digest differs: " + name)
        files[name] = content
    archive_name = ROUTE + ".zip"
    archive_path = _file(root, archive_name)
    archive_bytes = archive_path.read_bytes()
    require(hashlib.sha256(archive_bytes).hexdigest() == ARCHIVE_SHA256,
            "native catalogue archive differs from frozen publication identity")
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        require(len(archive.namelist()) == len(files) and
                set(archive.namelist()) == set(files) and archive.testzip() is None,
                "native catalogue archive members differ")
        for name, content in files.items():
            require(archive.read(name) == content, "native catalogue archive bytes differ: " + name)
    files[archive_name] = archive_bytes
    sidecar = _file(root, archive_name + ".sha256").read_bytes()
    require(sidecar == (ARCHIVE_SHA256 + "  " + archive_name + "\n").encode("ascii"),
            "native catalogue archive checksum differs")
    files[archive_name + ".sha256"] = sidecar
    paths = list(root.rglob("*"))
    require(all(not path.is_symlink() for path in paths), "native catalogue contains a symlink")
    actual = {path.relative_to(root).as_posix() for path in paths if path.is_file()}
    require(actual == set(files), "native catalogue contains unlisted files")
    outputs = {ROUTE + "/" + name: content for name, content in files.items()}
    entries, cards = [], []
    lessons = (
        ("native-model-catalogue", "Three-state native model: seven or eight transitions",
         "three-state/stages-8-x1-x2-screen.svg",
         "Two source-qualified horizon variants, independently checked in all three coordinates.",
         "All stages of the three-state reachable sets projected onto x1 and x2"),
        ("native-four-state-reachability", "Four-state reachable sets through fifteen transitions",
         "four-state/stages-x1-x2-screen.svg",
         "Full four-state generator propagation with independent support checks and both paired projections.",
         "All sixteen four-state reachable sets projected onto x1 and x2"),
    )
    for anchor, title, image, summary, alt in lessons:
        page = anchor + ".html"
        outputs[page] = _file(repository_root / "docs/examples", page).read_bytes()
        figure = ROUTE + "/" + image
        require(figure in outputs, "native catalogue lesson figure is missing")
        entries.append({"family": "Native mathematical models", "title": title,
                        "status": "educational-example", "anchor": anchor, "page": page,
                        "figure": figure,
                        "source_page": "https://github.com/butahlecoq/controlled-systems-lab/tree/" + SOURCE,
                        "raw_record": ROUTE + "/manifest.json"})
        cards.append(f'<article class="saved-figure" id="{anchor}">'
                     '<p class="eyebrow">Native C++ · forward reachability</p>'
                     f'<h3><a href="{page}">{escape(title)}</a></h3>'
                     f'<a href="{page}"><img src="{figure}" alt="{escape(alt)}"></a>'
                     f'<p>{escape(summary)}</p><p><a href="{page}">Matrices, all-stage figures and reproduction →</a></p></article>')
    return outputs, entries, "".join(cards)
