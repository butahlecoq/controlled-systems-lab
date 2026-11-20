"""Stage the source-qualified three-step forward reachability sweep."""

from pathlib import Path

from frozen_native_bundle import FrozenNativeBundle, read_bundle

IDENTITY = FrozenNativeBundle(
    route="catalogue-forward-reachability-v1",
    source_commit="dc6801dc5f02c4000b4f1272361752581a55873a",
    schema="csl.catalogue-forward-reachability-capture/1",
    manifest_sha256="2c7c693ba743bed906d96d1a6b641733cddd0313980c369dcd407429006abca7",
    archive_sha256="cf2453e49bb92be77a4d96e0308b12e075900d02b3a07db2ce472932fbe03c67",
)


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    route = IDENTITY.route
    files = {
        f"{route}/{name}": data for name, data in read_bundle(repository_root, IDENTITY).items()
    }
    entry = {
        "family": "Reachability",
        "title": "Forward reachability across 35 discrete models",
        "status": "saved-data-companion",
        "anchor": route,
        "page": f"{route}/index.html",
        "figure": f"{route}/platoon-forward.svg",
        "source_page": f"https://github.com/butahlecoq/csl-sdk/blob/{IDENTITY.source_commit}/include/csl/geometry/generators.hpp",
        "raw_record": f"{route}/manifest.json",
    }
    card = (
        f'<article class="saved-figure" id="{route}"><h3><a href="{entry["page"]}">{entry["title"]}</a></h3>'
        f'<a href="{entry["page"]}"><img src="{entry["figure"]}" alt="Position and velocity reachable sets for the final car, shown in physical and centred coordinates"></a>'
        "<p>Propagate three steps of independent box controls and reproduce the checked support values. "
        "The 30-state platoon illustrates how projection reveals narrow reachable sets.</p>"
        f'<p><a href="{route}/{route}.zip">Download the offline example</a></p></article>'
    )
    return files, [entry], card


FEASIBLE_HISTORY = FrozenNativeBundle(
    route="catalogue-feasible-history-v1",
    source_commit="dc6801dc5f02c4000b4f1272361752581a55873a",
    schema="csl.catalogue-feasible-history-capture/1",
    manifest_sha256="483aa1f432dd0d2ce9b30852c4acb1094f8ff1cbfbe0080dfb3bd7823f3d5c64",
    archive_sha256="0ed715cf6721d9b2651e46ce16257eceda6c67485e760a901a344c610728729c",
)


def build_feasible_history(
    repository_root: Path,
) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    route = FEASIBLE_HISTORY.route
    files = {
        f"{route}/{name}": data
        for name, data in read_bundle(repository_root, FEASIBLE_HISTORY).items()
    }
    entry = {
        "family": "Reachability",
        "title": "How constraints change reachable sets",
        "status": "saved-data-companion",
        "anchor": route,
        "page": f"{route}/index.html",
        "figure": f"{route}/battery-history-projections.svg",
        "source_page": f"https://github.com/butahlecoq/csl-sdk/blob/{FEASIBLE_HISTORY.source_commit}/include/csl/controllers/discrete_mpc.hpp",
        "raw_record": f"{route}/manifest.json",
    }
    card = (
        f'<article class="saved-figure" id="{route}"><h3><a href="{entry["page"]}">{entry["title"]}</a></h3>'
        f'<a href="{entry["page"]}"><img src="{entry["figure"]}" alt="Full-constraint and interval-only projections for a two-battery model, overlaid by stage"></a>'
        "<p>Compare three-step feasible histories across 35 models. "
        "See how state constraints change the battery energy projections.</p>"
        f'<p><a href="{route}/catalogue-feasible-history-evidence.zip">Download the C++ example and data</a></p></article>'
    )
    return files, [entry], card
