"""Expose the checked, source-qualified explicit versus online MPC study."""

from pathlib import Path

from frozen_native_bundle import FrozenNativeBundle, read_bundle

IDENTITY = FrozenNativeBundle(
    route="mpc-crossover-6b7308c4",
    source_commit="6b7308c400824c211b3c803ebb483ffd2b741f08",
    schema="csl.mpc-crossover-capture/1",
    manifest_sha256="e1b08aeb98ef7e553715dfc02ae797a7cd2346ff1889bc7971177e5b68d9d5ed",
    archive_sha256="44eed8810407bea385797bd9dfeca38173fce452a3c04058256f2bf4020882b5",
)


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    route = IDENTITY.route
    files = {
        f"{route}/{name}": data for name, data in read_bundle(repository_root, IDENTITY).items()
    }
    entry = {
        "family": "Predictive control",
        "title": "When does explicit MPC repay its setup cost?",
        "status": "saved-data-companion",
        "anchor": route,
        "page": f"{route}/index.html",
        "figure": f"{route}/feedback-geometry.svg",
        "source_page": f"https://github.com/butahlecoq/controlled-systems-lab/tree/{IDENTITY.source_commit}/benchmarks/reporting/mpc08_explicit",
        "raw_record": f"{route}/manifest.json",
    }
    card = (
        f'<article class="saved-figure" id="{route}"><h3><a href="{entry["page"]}">{entry["title"]}</a></h3>'
        f'<a href="{entry["page"]}"><img src="{entry["figure"]}" alt="Forward, backward and intersected sets alongside the feedback trajectory and critical regions"></a>'
        "<p>Compare offline construction and online quadratic optimization on the same three-step double integrator. Inspect 155 checked states and 25 paired deployment measurements.</p></article>"
    )
    return files, [entry], card
