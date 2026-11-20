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
    manifest_sha256="e49e8a8fc1603a1c9af5def0301c331edd780b8f6c118cedcf3ee1f40327da63",
    archive_sha256="efce8c403b504a534e5d8b8b5c134ab00f5d9664c758c86489b5b5bd5d943d91",
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


EXACT_SUPPORT = FrozenNativeBundle(
    route="catalogue-exact-support-v1",
    source_commit="e7ebf482480271e0d79ec5e2d5167a27849528f9",
    schema="csl.catalogue-exact-support-capture/1",
    manifest_sha256="82ecc7806d24eef34fdb89b6713530defa914a30937b1908ef956b2ba51b4d77",
    archive_sha256="3ef5d49f03cbd8c0067714cc5145877fbd245709cc473e0f1f4b5ff5661d5e2b",
)


def build_exact_support(
    repository_root: Path,
) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    route = EXACT_SUPPORT.route
    files = {
        f"{route}/{name}": data
        for name, data in read_bundle(repository_root, EXACT_SUPPORT).items()
    }
    entry = {
        "family": "Reachability",
        "title": "Exact support certificates for three catalogue models",
        "status": "saved-data-companion",
        "anchor": route,
        "page": f"{route}/index.html",
        "figure": f"{route}/building-budget-projection.svg",
        "source_page": f"https://github.com/butahlecoq/controlled-systems-lab/blob/{EXACT_SUPPORT.source_commit}/reports/algorithm-results/{route}/exact_support.cpp",
        "raw_record": f"{route}/manifest.json",
    }
    card = (
        f'<article class="saved-figure" id="{route}"><h3><a href="{entry["page"]}">{entry["title"]}</a></h3>'
        f'<a href="{entry["page"]}"><img src="{entry["figure"]}" alt="The building’s initial state and three projections beside the positive support deficits"></a>'
        "<p>Check exact witnesses and upper bounds for 192 sampled supports, including the building’s small control-budget effect.</p>"
        f'<p><a href="{route}/catalogue-exact-support-evidence.zip">Download the C++ producer and certificates</a></p></article>'
    )
    return files, [entry], card


BACKWARD_REACHABILITY = FrozenNativeBundle(
    route="catalogue-backward-reachability-v1",
    source_commit="4e2e332b6dffd697febfd53c3d7fb3a6b20f90ef",
    schema="csl.catalogue-backward-reachability-capture/1",
    manifest_sha256="397c07a65fb01ef3b0f1e657bcb105e3e1f7329647d64c8d5a246b1d8772425e",
    archive_sha256="8895be0afce61cfa0ba6653ab437d2187d65613cb4de79fa01afc61867ebd4a6",
)


def build_backward_reachability(
    repository_root: Path,
) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    route = BACKWARD_REACHABILITY.route
    files = {
        f"{route}/{name}": data
        for name, data in read_bundle(repository_root, BACKWARD_REACHABILITY).items()
    }
    entry = {
        "family": "Reachability",
        "title": "Backward reachability across 35 catalogue models",
        "status": "saved-data-companion",
        "anchor": route,
        "page": f"{route}/index.html",
        "figure": f"{route}/battery-forward-backward.svg",
        "source_page": f"https://github.com/butahlecoq/controlled-systems-lab/blob/{BACKWARD_REACHABILITY.source_commit}/reports/algorithm-results/{route}/predecessor.cpp",
        "raw_record": f"{route}/manifest.json",
    }
    card = (
        f'<article class="saved-figure" id="{route}"><h3><a href="{entry["page"]}">{entry["title"]}</a></h3>'
        f'<a href="{entry["page"]}"><img src="{entry["figure"]}" alt="Four battery stages with forward sets, backward sets, intersections and the terminal-optimal trajectory"></a>'
        "<p>Certify predecessor supports and see the states that can reach the battery target at each stage.</p>"
        f'<p><a href="{route}/catalogue-backward-support-evidence.zip">Download the producer, checker and figures</a></p></article>'
    )
    return files, [entry], card
