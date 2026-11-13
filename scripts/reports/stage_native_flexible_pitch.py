"""Validate and stage the frozen synthetic flexible-pitch native capture."""
from __future__ import annotations

import hashlib
from html import escape
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

from report_data import require

ROUTE = "native-flexible-pitch-v1"
SOURCE = "b8c884a0cbca8c5195f82383d4e2bea39a805edc"
MANIFEST_SHA256 = "59f52235c9f9e31cb24c8bec3df8e861a281beb13a242741d81dc85cb973d596"


def _file(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative)
    require(bool(relative) and not parts.is_absolute() and
            all(part not in {".", ".."} for part in parts.parts) and
            parts.as_posix() == relative and "\\" not in relative,
            "flexible pitch asset path is unsafe")
    path = root
    require(not path.is_symlink(), "flexible pitch root is symlinked")
    for part in parts.parts:
        path = path / part
        require(not path.is_symlink(), "flexible pitch asset is symlinked")
    require(path.is_file(), "flexible pitch asset is missing: " + relative)
    return path


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    repository_root = Path(repository_root)
    root = repository_root
    for part in ("reports", "algorithm-results", ROUTE):
        root = root / part
        require(not root.is_symlink(), "flexible pitch ancestor is symlinked")
    raw_manifest = _file(root, "manifest.json").read_bytes()
    require(hashlib.sha256(raw_manifest).hexdigest() == MANIFEST_SHA256,
            "flexible pitch manifest differs from the frozen publication identity")
    manifest = json.loads(raw_manifest)
    require(manifest["schema"] == "csl.synthetic-flexible-pitch-functional/1" and
            manifest["producer_source_commit"] == SOURCE and
            manifest["case_ids"] == [f"flexible-pitch/synthetic-{n}-state/1" for n in (8, 12, 16)],
            "flexible pitch producer or physical cases differ")
    records = manifest["files_sha256"]
    require(isinstance(records, dict) and records, "flexible pitch digest list is empty")
    files = {"manifest.json": raw_manifest}
    for name, digest in records.items():
        content = _file(root, name).read_bytes()
        require(hashlib.sha256(content).hexdigest() == digest,
                "flexible pitch digest differs: " + name)
        files[name] = content
    for name, digest in manifest["producer_source_files_sha256"].items():
        exported = files.get("source/" + name)
        require(exported is not None and hashlib.sha256(exported).hexdigest() == digest,
                "flexible pitch exported source differs: " + name)
        captured = subprocess.run(["git", "show", SOURCE + ":" + name],
                                  cwd=repository_root, capture_output=True, check=False)
        require(captured.returncode == 0,
                "flexible pitch capture source is unavailable; use a full-history checkout")
        require(captured.stdout == exported, "flexible pitch export differs from its captured Git source: " + name)
    protocol = manifest["invocation_protocol_source_commit"]
    require(protocol == "9d91edfe10eaad48e1801cda732fa516d074f152",
            "flexible pitch invocation/checker source differs")
    for name, digest in manifest["invocation_protocol_files_sha256"].items():
        exported = files.get("source/" + name)
        require(exported is not None and hashlib.sha256(exported).hexdigest() == digest,
                "flexible pitch protocol export differs: " + name)
        captured = subprocess.run(["git", "show", protocol + ":" + name],
                                  cwd=repository_root, capture_output=True, check=False)
        require(captured.returncode == 0,
                "flexible pitch protocol source is unavailable; use a full-history checkout")
        require(captured.stdout == exported, "flexible pitch protocol export differs from Git: " + name)
    process = json.loads(files["process-receipt.json"])
    require(process["producer_source_commit"] == SOURCE and process["returncode"] == 0 and
            process["executable_sha256"] == manifest["producer_binary_sha256"] and
            process["stdout_sha256"] == hashlib.sha256(files["native.stdout"]).hexdigest() and
            process["stderr_sha256"] == hashlib.sha256(files["native.stderr"]).hexdigest(),
            "flexible pitch process receipt differs")
    require(b"support_checks=4920 projection_checks=47232" in files["native.stdout"] and
            b"independent amplitude inputs, no stabilization objective" in files["native.stdout"],
            "flexible pitch actual native check result differs")
    installed = json.loads(files["installed-validation.json"])
    require(installed["producer_source_commit"] == SOURCE and installed["returncode"] == 0 and
            installed["consumer_isolated_from_source_tree"] is True,
            "flexible pitch installed consumer differs")
    archive_name = ROUTE + ".zip"
    archive_path = _file(root, archive_name)
    with zipfile.ZipFile(archive_path) as archive:
        require(len(archive.namelist()) == len(files) and
                set(archive.namelist()) == set(files) and archive.testzip() is None,
                "flexible pitch archive members differ")
        for name, content in files.items():
            require(archive.read(name) == content, "flexible pitch archive bytes differ: " + name)
    files[archive_name] = archive_path.read_bytes()
    sidecar = _file(root, archive_name + ".sha256").read_bytes()
    require(sidecar.decode("ascii").strip() ==
            hashlib.sha256(files[archive_name]).hexdigest() + "  " + archive_name,
            "flexible pitch archive checksum differs")
    files[archive_name + ".sha256"] = sidecar
    paths = list(root.rglob("*"))
    require(all(not path.is_symlink() for path in paths), "flexible pitch contains a symlink")
    require({path.relative_to(root).as_posix() for path in paths if path.is_file()} == set(files),
            "flexible pitch contains unlisted files")
    outputs = {ROUTE + "/" + name: content for name, content in files.items()}
    page = "native-flexible-pitch.html"
    outputs[page] = _file(repository_root / "docs/examples", page).read_bytes()
    figure = ROUTE + "/8-state-plane-0.svg"
    title = "Synthetic flexible pitch: eight, twelve and sixteen physical states"
    entries = [{"family": "Native mathematical models", "title": title,
                "status": "educational-example", "anchor": "native-flexible-pitch", "page": page,
                "figure": figure,
                "source_page": "https://github.com/butahlecoq/controlled-systems-lab/tree/" + SOURCE,
                "raw_record": ROUTE + "/manifest.json"}]
    card = ('<article class="saved-figure" id="native-flexible-pitch">'
            '<p class="eyebrow">Native C++ · synthetic flexible pitch · forward reachability</p>'
            f'<h3><a href="{page}">{escape(title)}</a></h3>'
            f'<a href="{page}"><img src="{figure}" alt="All 41 stages of the eight-state synthetic flexible-pitch set in the physical pitch plane"></a>'
            '<p>Coupled descriptor assembly, full-state generator propagation, every paired plane and independent numerical support checks. Independent amplitude inputs; no stabilization objective.</p>'
            f'<p><a href="{page}">Equations, synthetic choices, all-stage figures and installed reproduction →</a></p></article>')
    return outputs, entries, card
