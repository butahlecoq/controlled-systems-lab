"""Stage the frozen five-representation fixed-plan reachability study."""

from pathlib import Path

from frozen_native_bundle import FrozenNativeBundle, read_bundle

IDENTITY = FrozenNativeBundle(
    route="catalogue-external-fixed-plan-v1",
    source_commit="85ffb925a902cf5f47d36d2cfb0e10089ad70fc7",
    schema="csl.catalogue-external-fixed-plan-capture/1",
    manifest_sha256="7efa9221e4a75246f3e980eb304e40547393eead9a3e3cd6b49a538349e232d3",
    archive_sha256="3127019f9693a112e90c491f2857382928d6c767fea82104927f85131fc05954",
)


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    route = IDENTITY.route
    files = {
        f"{route}/{name}": data for name, data in read_bundle(repository_root, IDENTITY).items()
    }
    entry = {
        "family": "Reachability",
        "title": "Fixed-plan reachability with external disturbances",
        "status": "saved-data-companion",
        "anchor": route,
        "page": f"{route}/index.html",
        "figure": f"{route}/queue-outer-projections.svg",
        "source_page": f"https://github.com/butahlecoq/csl-sdk/tree/{IDENTITY.source_commit}/src/reachability",
        "raw_record": f"{route}/manifest.json",
    }
    card = (
        f'<article class="saved-figure" id="{route}"><h3><a href="{entry["page"]}">{entry["title"]}</a></h3>'
        f'<a href="{entry["page"]}"><img src="{entry["figure"]}" alt="Five reachable set representations for a queue model at three stages"></a>'
        "<p>Compare five representations on the same fixed plan for 35 models. "
        "The queue example shows where the outer sets extend beyond the enumerated hull.</p>"
        f'<p><a href="{route}/{route}.zip">Download the C++ example and data</a></p></article>'
    )
    return files, [entry], card
