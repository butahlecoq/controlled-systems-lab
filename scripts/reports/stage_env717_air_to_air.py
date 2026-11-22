"""Validate and publish the immutable AirToAirInterception pilot."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.reports import environment_report_publication as publication
else:
    publication_path = Path(__file__).with_name("environment_report_publication.py")
    publication_spec = importlib.util.spec_from_file_location(
        "environment_report_publication", publication_path
    )
    if publication_spec is None or publication_spec.loader is None:
        raise ImportError(f"cannot load the environment publication helper: {publication_path}")
    publication = importlib.util.module_from_spec(publication_spec)
    publication_spec.loader.exec_module(publication)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/algorithm-results/env717-air-to-air-pilot-v1"
CHECKER = ROOT / "scripts/reports/env717/check_air_to_air.py"
spec = importlib.util.spec_from_file_location("env717_air_to_air_checker", CHECKER)
if spec is None or spec.loader is None:
    raise ImportError("cannot load the environment report dependency")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
FILES = (
    "README.md",
    "capture.json",
    "environment.json",
    "figure-data.json",
    "index.html",
    "projections.svg",
    "result.json",
    "SHA256SUMS",
)
SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
SOURCE_URL = (
    f"https://github.com/imm-rl-lab/optimal_control/blob/{SOURCE_COMMIT}/"
    "Environments/AirToAirInterception/AirToAirInterception.py"
)


class LocalLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("a", "img"):
            for key, value in attrs:
                if key in ("href", "src"):
                    if value is None:
                        raise ValueError("report contains a link without a destination")
                    self.hrefs.append(value)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inputs(source: Path) -> dict[str, bytes]:
    if (
        source.is_symlink()
        or not source.is_dir()
        or {p.name for p in source.iterdir()} != set(FILES)
    ):
        raise ValueError("AirToAir report inventory differs")
    files = {name: (source / name).read_bytes() for name in FILES}
    sums = dict(
        line.split("  ", 1)[::-1] for line in files["SHA256SUMS"].decode("ascii").splitlines()
    )
    if sums != {name: digest(data) for name, data in files.items() if name != "SHA256SUMS"}:
        raise ValueError("AirToAir report checksums differ")
    result = json.loads(files["result.json"])
    if result.get("source_repository_commit") != SOURCE_COMMIT:
        raise ValueError("pinned upstream source commit differs")
    expected = checker.verify(result)
    derived = checker.feedback_sets(expected["value"])

    def projected(layers, i):
        return [
            [
                list(point)
                for point in sorted({tuple(checker.relative(s)[i : i + 2]) for s in layer})
            ]
            for layer in layers
        ]

    expected_data = {
        "schema": "csl.env717-air-to-air-figure-data/1",
        "relative_x_position_velocity": {
            "forward_layers": projected(derived["forward"], 0),
            "winning_layers": projected(derived["winning"], 0),
            "open_loop_threshold_winning_layers": projected(derived["open_loop_winning"], 0),
        },
        "relative_y_position_velocity": {
            "forward_layers": projected(derived["forward"], 2),
            "winning_layers": projected(derived["winning"], 2),
            "open_loop_threshold_winning_layers": projected(derived["open_loop_winning"], 2),
        },
        "selected_worst_case": [list(checker.relative(s)) for s in expected["trajectory"]],
        "open_loop_value": expected["value"],
        "winning_set_threshold_tolerance": checker.WINNING_SET_TOLERANCE,
        "feedback_value": derived["feedback_value"],
    }
    if json.loads(files["figure-data.json"]) != expected_data:
        raise ValueError("saved geometry does not match independent replay")
    if files["projections.svg"].decode() != checker.svg_figure(expected, derived):
        raise ValueError("saved projections do not match replay geometry")
    capture = json.loads(files["capture.json"])
    environment = json.loads(files["environment.json"])
    if capture.get("renderer_sha256") != digest(CHECKER.read_bytes()):
        raise ValueError("renderer identity differs")
    if capture.get("source_commit") != result.get("source_commit"):
        raise ValueError("capture source revision differs")
    host = capture.get("capture_environment")
    measurement = capture.get("measurement")
    if (
        not isinstance(host, dict)
        or not host.get("processor")
        or not host.get("processor_identity_source")
        or not host.get("architecture")
        or not isinstance(host.get("logical_cpus"), int)
    ):
        raise ValueError("capture host metadata is incomplete")
    if (
        not isinstance(measurement, dict)
        or measurement.get("warmup_calls") != 0
        or measurement.get("measured_calls") != 1
        or measurement.get("comparison_claim") is not False
        or measurement.get("worker_threads_requested") != 1
        or measurement.get("worker_threads_actual") != 1
        or measurement.get("native_threads_requested") != 1
        or measurement.get("native_threads_actual") != 1
        or measurement.get("workspace_reuse") != "none"
        or measurement.get("cache_state") != "cold process; no prior solver call"
    ):
        raise ValueError("timing evidence scope differs")
    if (
        environment.get("near_optimal_tolerance") != result.get("near_optimal_tolerance")
        or environment.get("winning_set_threshold_tolerance") != checker.WINNING_SET_TOLERANCE
        or environment.get("source_horizon_seconds") != 2.0
        or environment.get("adapted_horizon_seconds") != checker.HORIZON * checker.DT
    ):
        raise ValueError("solver tolerance or adaptation metadata differs")
    parser = LocalLinks()
    parser.feed(files["index.html"].decode())
    if not parser.hrefs or any(link not in files and link != SOURCE_URL for link in parser.hrefs):
        raise ValueError("report has a missing or nonlocal linked asset")
    return files


def stage(source: Path, site: Path) -> str:
    files = inputs(source)
    result = json.loads(files["result.json"])
    publisher, archived_zip_sha256 = publication.archive_identity(
        source.name, files["SHA256SUMS"], Path(__file__)
    )
    identity = {
        "source_report_id": source.name,
        "result_sha256": digest(files["result.json"]),
        "renderer_sha256": digest(CHECKER.read_bytes()),
        **publisher,
        "source_file_hashes": {key: digest(value) for key, value in sorted(files.items())},
    }
    route = (
        "env717-air-to-air-"
        + digest(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())[:20]
    )
    index = site / "index.html"
    index_text = index.read_text(encoding="utf-8")
    destination, archive_path = site / route, site / (route + ".zip")
    if destination.exists() or archive_path.exists() or index_text.count("</ul>") != 1:
        raise ValueError("Pages destination or insertion point differs")
    generated = dict(files)
    page = generated["index.html"].decode()
    footer = (
        f"<p>Immutable report <code>{escape(route)}</code> · "
        f'<a href="publication-manifest.json">Publication manifest</a> · '
        f'<a href="../{escape(route)}.zip">Offline report ZIP</a>.</p>'
    )
    if page.count("</main>") != 1:
        raise ValueError("report page insertion point differs")
    generated["index.html"] = page.replace("</main>", footer + "</main>").encode()
    generated["SHA256SUMS"] = "".join(
        f"{digest(generated[name])}  {name}\n"
        for name in sorted(generated)
        if name not in ("SHA256SUMS", "publication-manifest.json")
    ).encode()
    manifest = {
        "schema": "csl.env717-publication/1",
        "report_id": route,
        "source_report_id": source.name,
        "source_repository_commit": SOURCE_COMMIT,
        "source_commit": result["source_commit"],
        "result_sha256": digest(files["result.json"]),
        **(publisher if archived_zip_sha256 is None else {}),
        "published_files": {key: digest(value) for key, value in sorted(generated.items())},
    }
    generated["publication-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    landing = f'<!doctype html><meta charset="utf-8"><a href="{route}/index.html">Open AirToAir report</a>'.encode()
    archive_bytes = publication.offline_zip(
        route, landing, generated, expected_sha256=archived_zip_sha256
    )
    destination.mkdir()
    for name, data in generated.items():
        (destination / name).write_bytes(data)
    archive_path.write_bytes(archive_bytes)
    route_link = (
        f'<li><a href="{route}/index.html">AirToAirInterception finite minimax</a>'
        f" — 125 plans × 125 disturbances; stage geometry in two relative phase planes"
        f' · <a href="{route}/result.json">result JSON</a>'
        f' · <a href="{route}/projections.svg">projections</a>'
        f' · <a href="{route}.zip">offline ZIP</a></li>'
    )
    index.write_text(index_text.replace("</ul>", route_link + "</ul>"), encoding="utf-8")
    return route


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))
