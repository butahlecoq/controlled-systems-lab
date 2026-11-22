"""Stage the frozen catalogue robust predecessor and causal minimax lesson."""

from pathlib import Path

from frozen_native_bundle import FrozenNativeBundle, read_bundle

IDENTITY = FrozenNativeBundle(
    route="catalogue-disturbance-control-v1",
    source_commit="806738c9d1c8f1d9ebd8885b7bb605b5a698b1af",
    schema="csl.catalogue-disturbance-control-capture/1",
    manifest_sha256="b47e53f86eac0673b975e40dd0aca06401b0d2de6a2e7dac534073cbafcc3997",
    archive_sha256="4abbc5621a2f8e18975fb258ab9c14e326f43fe23473b31bdc9527023ba4a4c9",
)


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    route = IDENTITY.route
    files = {
        f"{route}/{name}": data for name, data in read_bundle(repository_root, IDENTITY).items()
    }
    entry = {
        "family": "Control",
        "title": "Disturbance guarantees and feedback",
        "status": "saved-data-companion",
        "anchor": route,
        "page": f"{route}/index.html",
        "figure": f"{route}/ev-causal-minimax.svg",
        "source_page": f"https://github.com/butahlecoq/csl-sdk/tree/{IDENTITY.source_commit}/src/optimization",
        "raw_record": f"{route}/manifest.json",
    }
    card = (
        f'<article class="saved-figure" id="{route}"><h3><a href="{entry["page"]}">{entry["title"]}</a></h3>'
        f'<a href="{entry["page"]}"><img src="{entry["figure"]}" alt="Finite EV terminal states and worst-case paths under fixed and causal control"></a>'
        "<p>Verify when a fixed plan guarantees its target and when an observed state improves the finite minimax policy, with and without the saved constraints.</p>"
        f'<p><a href="{route}/{route}.zip">Download the lesson and replay</a></p></article>'
    )
    return files, [entry], card
