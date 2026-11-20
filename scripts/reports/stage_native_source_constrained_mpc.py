"""Stage the checked matched open-loop and MPC catalogue evidence."""

from pathlib import Path

from frozen_native_bundle import FrozenNativeBundle, read_bundle

IDENTITY = FrozenNativeBundle(
    route="native-source-constrained-mpc-v1",
    source_commit="d6561f1ee36fca39beb9593e8cf6982f962856b8",
    schema="csl.native-source-constrained-mpc/1",
    manifest_sha256="17f05844930453454536f3158e8b8fac0d2980065732ae30f461d3c1b9fad85e",
    archive_sha256="47c04cfb692a362112d7154af42c777e7eb23d8c29b015c0112cc137316998aa",
)


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    route = IDENTITY.route
    files = {
        f"{route}/{name}": data for name, data in read_bundle(repository_root, IDENTITY).items()
    }
    entry = {
        "family": "Predictive control",
        "title": "Open loop and MPC under the same constraints",
        "status": "saved-data-companion",
        "anchor": route,
        "page": f"{route}/index.html",
        "figure": f"{route}/platoon.svg",
        "source_page": f"{route}/source/catalogue_episode.cpp",
        "raw_record": f"{route}/independent-audit.json",
    }
    card = (
        f'<article class="saved-figure" id="{route}"><h3><a href="{entry["page"]}">'
        f'{entry["title"]}</a></h3><a href="{entry["page"]}"><img src="{entry["figure"]}" '
        'alt="Checked last-car trajectories and minimum headway margins for two policies"></a>'
        "<p>Compare a plan solved once with a policy that replans from each observation. "
        "The ten-car example illustrates the checked outcomes across 35 catalogue models.</p></article>"
    )
    return files, [entry], card
