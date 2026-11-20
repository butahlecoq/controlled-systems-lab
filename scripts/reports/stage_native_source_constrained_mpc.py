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


CONVEX_BACKENDS = FrozenNativeBundle(
    route="native-catalogue-convex-backends-v1",
    source_commit="4bec054f8012b04a2a7108bb14dcdd83cab329ee",
    schema="csl.native-catalogue-convex-backends/1",
    manifest_sha256="bad14baa9aad250e15f620f44a4448d2da73694622ac05cb16e0f11ea98a84f4",
    archive_sha256="52b7b7e07cf594e033fbd01ce1123bed1c95c340ac6cae08c1214ad83f5352da",
)


def build_convex_backends(
    repository_root: Path,
) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    route = CONVEX_BACKENDS.route
    files = {
        f"{route}/{name}": data
        for name, data in read_bundle(repository_root, CONVEX_BACKENDS).items()
    }
    entry = {
        "family": "Predictive control",
        "title": "Convex solvers for the same catalogue control tasks",
        "status": "saved-data-companion",
        "anchor": route,
        "page": f"{route}/index.html",
        "figure": f"{route}/twenty-zone-ipopt.svg",
        "source_page": "https://github.com/butahlecoq/csl-sdk/blob/"
        "f53e770462e323f9e0ff3c844e6fa3882fd82966/src/adapters/convex/ipopt.cpp",
        "raw_record": f"{route}/installed-ipopt-audit.json",
    }
    card = (
        f'<article class="saved-figure" id="{route}"><h3><a href="{entry["page"]}">'
        f'{entry["title"]}</a></h3><a href="{entry["page"]}"><img src="{entry["figure"]}" '
        'alt="Open-loop and MPC trajectories in two state planes of the twenty-zone thermal model"></a>'
        "<p>See which catalogue episodes completed when the controller switched from released "
        "HiGHS to bounded row scaling or the installed Ipopt provider.</p></article>"
    )
    return files, [entry], card
