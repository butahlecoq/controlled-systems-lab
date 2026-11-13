"""Verify and stage the frozen Buryatia Dim4 lesson for the Pages gallery."""
from __future__ import annotations

import hashlib
from html import escape
from html.parser import HTMLParser
from functools import lru_cache
import json
import math
from pathlib import Path

from report_data import require


ROUTE = "buryatia-dim4-literal-affine-v1"
SOURCE = "136e30f33fca849ec8814747702ab720e76e22bd"
RAW_SHA256 = "d0a8ca600eaa52f9630c87f1e7395c4ca2454c0080d315469e44c06a4403d8ad"
CAPTURE_SHA256 = "70955d039aa581072fc7dbf8d539404b9bf152160f682dfae95712dcbf8932d4"
SCENARIO_SHA256 = "276f1c0d456cf2f27a8fcae827538746670a5f04ae5e86b4b17c9a28db51cd35"
PAGE_SHA256 = "d19e112576d836c45692054319d45edcecd9db0d61a3270762c47273fefda6d6"
BOX_TRACE_PROOF = "buryatia-dim4-box-trace-correction-v1.json"
BOX_TRACE_PROOF_SHA256 = "86ceeb2cc3bb6064dfd16b57c9c62b62e7651afa8ac784b8ffa260057f4cb89a"
SOURCE_VARIANT_SHA256 = "f1b9868dac256a45f144ee5192ec8b789548b34c2be6be094005bcef8dc7293a"
COLOR = {
    "exact_affine_polytope": "#f8f8f2",
    "unreduced_zonotope": "#66d9ef",
    "reduced_zonotope": "#a6e22e",
    "box": "#ae81ff",
    "parallelotope": "#fd971f",
    "ellipsoid": "#f92672",
}
LABEL = {
    "exact_affine_polytope": "Exact affine polytope",
    "unreduced_zonotope": "Unreduced zonotope",
    "reduced_zonotope": "Reduced zonotope",
    "box": "Box",
    "parallelotope": "Parallelotope",
    "ellipsoid": "Factor ellipsoid",
}


def _safe_file(root: Path, relative: str) -> Path:
    path = root
    for part in Path(relative).parts:
        path = path / part
        require(not path.is_symlink(), "Buryatia source asset is symlinked: " + relative)
    require(path.is_file(), "Buryatia source asset is missing: " + relative)
    return path


def _ellipse_points(shape: dict, count: int = 240) -> list[list[float]]:
    factor = shape["factor_row_major"]
    columns = shape["factor_columns"]
    center = shape["center"]
    points = []
    for index in range(count):
        angle = 2.0 * 3.141592653589793 * index / count
        direction = (math.cos(angle), math.sin(angle))
        projected = [sum(factor[row * columns + j] * direction[row] for row in range(2))
                     for j in range(columns)]
        norm = sum(value * value for value in projected) ** 0.5
        if norm == 0.0:
            points.append(list(center))
        else:
            points.append([
                center[row] + sum(factor[row * columns + j] * projected[j] for j in range(columns)) / norm
                for row in range(2)
            ])
    return points


def _svg_thumbnail(record: dict) -> bytes:
    stage = record["records"][-1]
    families = {family["family"]: family for family in stage["families"]}
    points: dict[str, list[list[float]]] = {
        "exact_affine_polytope": stage["exact_reference"]["projections_2d"]["x1_x2"],
        "unreduced_zonotope": stage["exact_reference"]["projections_2d"]["x1_x2"],
    }
    for name in ("reduced_zonotope", "box", "parallelotope"):
        points[name] = families[name]["coordinate_projections_2d"]["x1_x2"]
    points["ellipsoid"] = _ellipse_points(families["ellipsoid"]["coordinate_projections_2d"]["x1_x2"])
    cloud = [point for series in points.values() for point in series]
    min_x, max_x = min(p[0] for p in cloud), max(p[0] for p in cloud)
    min_y, max_y = min(p[1] for p in cloud), max(p[1] for p in cloud)
    x_span, y_span = max(max_x - min_x, 1e-12), max(max_y - min_y, 1e-12)
    scale = min(640 / x_span, 360 / y_span)
    center_x, center_y = (min_x + max_x) / 2, (min_y + max_y) / 2

    def screen(point: list[float]) -> tuple[float, float]:
        return 400 + (point[0] - center_x) * scale, 225 - (point[1] - center_y) * scale

    fragments = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450" role="img" '
        'aria-labelledby="title description"><title id="title">Buryatia Dim4 terminal x1-x2 projection</title>'
        '<desc id="description">Stage seven point projections of six set families from the full four-dimensional model.</desc>'
        '<rect width="800" height="450" fill="#303129"/>',
        '<path d="M80 405H720 M80 45V405" stroke="#92938b" fill="none"/>',
        '<text x="400" y="438" fill="#f8f8f2" text-anchor="middle">deviation x₁</text>',
        '<text x="18" y="225" fill="#f8f8f2" text-anchor="middle" transform="rotate(-90 18 225)">deviation x₂</text>',
    ]
    for name, series in points.items():
        subset = series if len(series) <= 1200 else series[:: max(1, len(series) // 1200)]
        fragments.append(f'<g fill="{COLOR[name]}" fill-opacity=".55" data-family="{name}">')
        fragments.extend(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.4"/>' for x, y in map(screen, subset))
        fragments.append("</g>")
    for index, name in enumerate(points):
        x = 95 + (index % 3) * 230
        y = 28 + (index // 3) * 22
        fragments.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{COLOR[name]}"/>')
        fragments.append(f'<text x="{x + 8}" y="{y + 4}" fill="#f8f8f2" font-size="12">{escape(LABEL[name])}</text>')
    fragments.append('</svg>')
    return ("\n".join(fragments) + "\n").encode()


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.values.extend(value for key, value in attrs if key in {"href", "src"} and value)


@lru_cache(maxsize=1)
def _saved_record() -> dict:
    path = Path(__file__).resolve().parents[2] / "docs/examples" / (ROUTE + "-records.json")
    return json.loads(path.read_text(encoding="utf-8"))


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    repository_root = Path(repository_root)
    docs = repository_root / "docs/examples"
    benchmark = repository_root / "benchmarks/scenarios"
    raw_name = ROUTE + "-records.json"
    capture_name = ROUTE + "-capture.json"
    sums_name = ROUTE + "-SHA256SUMS"
    scenario_name = "buryatia-dim4-matlab-literal-affine-v1.json"
    raw = _safe_file(docs, raw_name).read_bytes()
    capture_bytes = _safe_file(docs, capture_name).read_bytes()
    box_trace_proof = _safe_file(docs, BOX_TRACE_PROOF).read_bytes()
    scenario = _safe_file(benchmark, scenario_name).read_bytes()
    sums = _safe_file(docs, sums_name).read_text(encoding="ascii")
    require(hashlib.sha256(raw).hexdigest() == RAW_SHA256, "Buryatia raw capture hash differs")
    require(hashlib.sha256(capture_bytes).hexdigest() == CAPTURE_SHA256,
            "Buryatia capture receipt hash differs")
    require(hashlib.sha256(box_trace_proof).hexdigest() == BOX_TRACE_PROOF_SHA256,
            "Buryatia box-trace correction proof hash differs")
    require(hashlib.sha256(scenario).hexdigest() == SCENARIO_SHA256,
            "Buryatia source scenario hash differs")
    receipt = json.loads(capture_bytes)
    trace_proof = json.loads(box_trace_proof)
    record = _saved_record()
    scenario_data = json.loads(scenario)
    require(receipt["source_commit"] == SOURCE and receipt["stdout_sha256"] == RAW_SHA256,
            "Buryatia capture receipt source or raw stream differs")
    require(record["schema"] == "csl.buryatia.recursive-approximation-4d/1" and
            record["source_sha256"] == SOURCE_VARIANT_SHA256,
            "Buryatia raw record source identity differs")
    require(scenario_data["case_id"] == record["case_id"],
            "Buryatia scenario and saved record IDs differ")
    require(trace_proof["schema"] == "csl.buryatia.dim4-box-trace-erratum/1" and
            trace_proof["historical_record"]["sha256"] == RAW_SHA256 and
            trace_proof["corrected_native_capture"]["source_commit"] == "00a9e3da45ded30906ca7d79d4d1fff4a63fa347" and
            trace_proof["comparison"]["all_other_json_values_equal"] is True and
            trace_proof["comparison"]["changed_json_values"] == 7,
            "Buryatia box-trace correction proof does not match the immutable source record")
    expected = {
        raw_name: RAW_SHA256,
        capture_name: CAPTURE_SHA256,
        BOX_TRACE_PROOF: BOX_TRACE_PROOF_SHA256,
        "buryatia-dim4-literal-affine.html": PAGE_SHA256,
        "../../benchmarks/scenarios/" + scenario_name: SCENARIO_SHA256,
    }
    parsed = {}
    for line in sums.splitlines():
        digest, relative = line.split("  ", 1)
        parsed[relative] = digest
    require(parsed == expected, "Buryatia source checksum manifest differs")

    page_path = _safe_file(docs, "buryatia-dim4-literal-affine.html")
    page = page_path.read_text(encoding="utf-8")
    page = page.replace('href="examples.css"', 'href="../examples.css"')
    page = page.replace(
        'href="../../benchmarks/scenarios/' + scenario_name + '"',
        'href="' + scenario_name + '"',
    )
    # The source page links the manifest by its published filename; the staged
    # route keeps that same filename next to the page and raw record.
    require('href="../examples.css"' in page and scenario_name in page,
            "Buryatia page links do not resolve in its staged route")
    files = {
        ROUTE + "/index.html": page.encode("utf-8"),
        ROUTE + "/" + raw_name: raw,
        ROUTE + "/" + capture_name: capture_bytes,
        ROUTE + "/" + BOX_TRACE_PROOF: box_trace_proof,
        ROUTE + "/" + scenario_name: scenario,
    }
    thumbnail = _svg_thumbnail(record)
    files[ROUTE + "/terminal-x1-x2.svg"] = thumbnail
    stage_sums = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name.rsplit('/', 1)[-1]}\n"
        for name, content in sorted(files.items()) if name != ROUTE + "/index.html"
    ).encode("ascii")
    files[ROUTE + "/" + sums_name] = stage_sums

    links = _Links()
    links.feed(page)
    for link in links.values:
        if link.startswith(("https://", "http://", "#")):
            continue
        target = ROUTE + "/" + link
        require(target in files or link == "../examples.css",
                "Buryatia staged page link is missing: " + link)
    entry = {
        "family": "Buryatia affine reachability",
        "title": "Buryatia Dim4: six approximations through seven updates",
        "status": "educational-example",
        "anchor": "buryatia-dim4-literal-affine-v1",
        "page": ROUTE + "/index.html",
        "figure": ROUTE + "/terminal-x1-x2.svg",
        "source_page": "https://github.com/butahlecoq/controlled-systems-lab/commit/" + SOURCE,
        "raw_record": ROUTE + "/" + raw_name,
    }
    card = (
        '<article class="saved-figure" id="buryatia-dim4-literal-affine-v1">'
        '<p class="eyebrow">Buryatia · source-qualified affine reachability</p>'
        '<h3><a href="buryatia-dim4-literal-affine-v1/index.html">'
        'Buryatia Dim4: six approximations through seven updates</a></h3>'
        '<a href="buryatia-dim4-literal-affine-v1/index.html">'
        '<img src="buryatia-dim4-literal-affine-v1/terminal-x1-x2.svg" '
        'alt="Terminal x1-x2 projection of six set families from the full four-state model"></a>'
        '<p>Inspect all eight stages of the literal seven-update affine variant. The plot is a two-coordinate view; all propagation is in four state coordinates.</p>'
        '<p><a href="buryatia-dim4-literal-affine-v1/index.html">Open the interactive lesson and saved record →</a></p></article>'
    )
    return files, [entry], card
