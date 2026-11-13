"""Authenticate and publish the saved Buryatia 2D lesson without numerical execution."""

from __future__ import annotations

import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

MANIFEST = "buryatia-volterra-affine-2d-manifest.json"
MANIFEST_SHA256 = "530e085cdcec35f6ad67ff4ce35109fec9f65d80cd5a5c567443a613178d7988"
SOURCE = "35a708df541409bd8d7c0bddaeafcda60c26dbae"
VARIANT = "buryatia-volterra-literal-script-affine/1"
SOURCE_SHA256 = "c26fc2424fa8b3325a864d1afbc67920ba1c05665bfdf4562bed79548b60a4f1"
PAGE = "buryatia-volterra-affine-2d.html"
ASSETS = (
    MANIFEST,
    PAGE,
    "buryatia-volterra-affine-2d-records.json",
    "buryatia-volterra-affine-2d-terminal.svg",
    "buryatia-volterra-affine-2d-records-superseded-v1.json",
    "buryatia-volterra-affine-2d-superseded-v1.html",
    "buryatia-volterra-affine-2d-terminal-superseded-v1.svg",
    "buryatia-volterra-affine-2d-manifest-superseded-v1.json",
)


def asset_paths() -> list[str]:
    return list(ASSETS)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _file(repository_root: Path, name: str) -> Path:
    path = repository_root
    for part in ("docs", "examples", name):
        _require(not path.is_symlink(), "Buryatia source is symlinked")
        path /= part
    _require(not path.is_symlink(), "Buryatia source member is symlinked: " + name)
    _require(path.is_file(), "Buryatia source member is missing: " + name)
    return path


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.values.extend(value for key, value in attrs if key in {"href", "src"} and value)


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    root = Path(repository_root)
    raw_manifest = _file(root, MANIFEST).read_bytes()
    _require(
        hashlib.sha256(raw_manifest).hexdigest() == MANIFEST_SHA256,
        "Buryatia publication manifest identity differs",
    )
    manifest = json.loads(raw_manifest)
    _require(
        manifest["schema"] == "csl.buryatia.2d-artifact-manifest/2"
        and manifest["source_variant_id"] == VARIANT
        and manifest["source_sha256"] == SOURCE_SHA256
        and manifest["native_build"]["git_revision"] == SOURCE,
        "Buryatia saved native producer identity differs",
    )
    records = manifest["artifacts"] + manifest["superseded_artifacts"]
    paths = [record["path"] for record in records]
    expected = {"docs/examples/" + name for name in ASSETS if name != MANIFEST}
    _require(
        len(paths) == len(expected) and set(paths) == expected, "Buryatia asset identity differs"
    )
    outputs = {MANIFEST: raw_manifest}
    for record in records:
        name = Path(record["path"]).name
        content = _file(root, name).read_bytes()
        _require(
            hashlib.sha256(content).hexdigest() == record["sha256"],
            "Buryatia source asset digest differs: " + name,
        )
        outputs[name] = content
    raw = json.loads(outputs["buryatia-volterra-affine-2d-records.json"])
    _require(
        raw["native_build"] == manifest["native_build"]
        and raw["case_id"] == manifest["case_id"]
        and raw["source_variant_id"] == VARIANT
        and raw["source_sha256"] == SOURCE_SHA256
        and raw["intervals"] == 60,
        "Buryatia saved record identity differs from its manifest",
    )
    for name in (PAGE, "buryatia-volterra-affine-2d-superseded-v1.html"):
        parser = _Links()
        parser.feed(outputs[name].decode("utf-8"))
        for value in parser.values:
            link = urlsplit(value)
            if not link.scheme and not link.netloc and link.path:
                _require(
                    link.path in outputs or link.path == "examples.css",
                    "Buryatia published relative link is missing: " + value,
                )
    entry = {
        "family": "Buryatia affine reachability",
        "title": "Buryatia Lotka–Volterra: six tracks through 60 updates",
        "status": "educational-example",
        "anchor": "buryatia-volterra-affine-2d",
        "page": PAGE,
        "figure": "buryatia-volterra-affine-2d-terminal.svg",
        "source_page": "https://github.com/butahlecoq/controlled-systems-lab/tree/" + SOURCE,
        "raw_record": "buryatia-volterra-affine-2d-records.json",
    }
    card = (
        '<article class="saved-figure" id="buryatia-volterra-affine-2d">'
        '<p class="eyebrow">Buryatia · source-qualified affine reachability</p>'
        f'<h3><a href="{PAGE}">{entry["title"]}</a></h3>'
        f'<a href="{PAGE}"><img src="{entry["figure"]}" '
        'alt="Terminal deviation-plane overlay of six recursively propagated set tracks"></a>'
        "<p>Inspect all 61 saved state stages, exact affine sets, recursive outer approximations "
        "and numerical support diagnostics. This is separate from the canonical nonlinear control task.</p>"
        "<p>The current corrected drawing and all superseded-v1 assets retain their original bytes "
        "and native producer identities; no historical timing or nonlinear enclosure claim.</p>"
        f'<p><a href="{PAGE}">Explore all stages and download the raw evidence →</a></p></article>'
    )
    return outputs, [entry], card
