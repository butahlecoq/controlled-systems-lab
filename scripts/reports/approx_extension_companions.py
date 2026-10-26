"""Make additive quantitative figure companions from frozen extension records."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import tempfile

import geometry_figures


STAGE_BANDS = ((1, 15, "#D55E00"), (16, 30, "#E69F00"),
               (31, 45, "#0072B2"), (46, 60, "#CC79A7"))


def _render_companion(document: dict, style_path: Path, stem: str) -> dict[str, bytes]:
    """Render a saved planar geometry document as a standalone SVG and PNG."""
    with tempfile.TemporaryDirectory(prefix="csl-geometry-figure-") as directory:
        output = Path(directory) / "figure"
        receipt = geometry_figures.render(document, style_path, output)
        svg = (output / "geometry.svg").read_bytes()
        png = (output / "geometry.png").read_bytes()
    return {stem + ".svg": svg, stem + ".png": png,
            stem + "-export.json": (json.dumps(receipt, indent=2) + "\n").encode()}


def app02_companion(record_path: Path, style_path: Path) -> dict[str, bytes]:
    """Plot the APP-02 diamond's saved input, outer bounds and inner box."""
    record = json.loads(Path(record_path).read_text(encoding="utf-8"))
    outer_input = record["fixtures"]["diamond-rotated-outer"]
    axis_outer = record["fixtures"]["diamond-axis-outer"]
    inner_output = record["fixtures"]["diamond-axis-inner"]["expected_v_vertices"]
    _require(outer_input["input_vertices"] == [[0, 2], [2, 0], [0, -2], [-2, 0]] and
            outer_input["expected_h_rows"] == [[1, 1], [-1, -1], [1, -1], [-1, 1]] and
            outer_input["expected_h_bounds"] == [2, 2, 2, 2],
            "APP-02 saved rotated diamond fixture changed")
    _require(axis_outer["expected_h_rows"] == [[1, 0], [-1, 0], [0, 1], [0, -1]] and
            axis_outer["expected_h_bounds"] == [2, 2, 2, 2],
            "APP-02 saved axis outer box changed")
    _require(inner_output == [[1, 1], [1, -1], [-1, -1], [-1, 1]],
            "APP-02 saved inner box vertices changed")
    document = {"schema": "csl.saved-geometric-plot/1",
                "title": "APP-02 saved diamond approximation geometry",
                "description": ("The blue saved input diamond and rotated outer bound coincide. The orange square is the saved axis outer bound; "
                                "the green square is the saved inner approximation. The plot visualizes archived values and does not trace algorithm steps."),
                "aspect": "equal",
                "axes": {"x": {"label": "x coordinate"}, "y": {"label": "y coordinate"}},
                "series": [
                    {"kind": "polygon", "label": "saved axis outer box", "color": "#D55E00",
                     "fill": True, "alpha": .09, "points": [[-2, -2], [2, -2], [2, 2], [-2, 2]]},
                    {"kind": "polygon", "label": "saved input and rotated outer bound", "color": "#0072B2",
                     "fill": True, "alpha": .16, "points": outer_input["input_vertices"]},
                    {"kind": "polygon", "label": "saved inner box", "color": "#009E73",
                     "points": inner_output},
                ]}
    outputs = _render_companion(document, style_path, "app02-diamond-v1")
    return outputs | {"app02-diamond-v1.html": _companion_page(
        "APP-02 diamond approximations", "app02-diamond-v1", "app02-box-8ff979de60ea9d22",
        "This companion uses the archived diamond input, outer bounds, and inner vertices. The blue rotated outer approximation coincides with the diamond; the orange axis box encloses it, and the green box is the stored inner result. Exact declarations and evidence remain in the saved report.")}


def app04_companion(record_path: Path, style_path: Path) -> dict[str, bytes]:
    """Plot APP-04 saved square and outer ellipsoid radii."""
    record = json.loads(Path(record_path).read_text(encoding="utf-8"))
    square = record["fixtures"]["square-axis"]["input_vertices"]
    diagonal_fixture = record["fixtures"]["square-diagonal"]
    trials = record["measurement"]["trials"]
    radii = {row["case"]: float(row["radius_x"]) for row in trials
             if row["case"] in {"square-axis", "square-diagonal"}}
    _require(square == [[-1, -1], [1, -1], [1, 1], [-1, 1]] and
             diagonal_fixture["orientation_rows"] == [[1, 1], [1, -1]] and
             set(radii) == {"square-axis", "square-diagonal"},
             "APP-04 saved square or radius trials changed")
    document = {"schema": "csl.saved-geometric-plot/1",
                "title": "APP-04 saved square and enclosing ellipses",
                "description": ("The square comes from the saved input vertices. Circle radii come from saved APP-04 trial values; "
                                "the diagonal-orientation radius is converted to physical x-y coordinates using the recorded orientation. "
                                "This is a display of stored output, not an algorithm trace."),
                "aspect": "equal",
                "axes": {"x": {"label": "x coordinate"}, "y": {"label": "y coordinate"}},
                "series": [
                    {"kind": "circle", "label": "axis orientation · saved radius", "color": "#6A4C93",
                     "center": [0, 0], "radius": radii["square-axis"]},
                    {"kind": "circle", "label": "diagonal orientation · physical radius", "color": "#0072B2",
                     "linestyle": "--", "center": [0, 0], "radius": radii["square-diagonal"] / 2**0.5},
                    {"kind": "polygon", "label": "saved square input", "color": "#D55E00",
                     "fill": True, "alpha": .12, "points": square},
                ]}
    outputs = _render_companion(document, style_path, "app04-square-v1")
    return outputs | {"app04-square-v1.html": _companion_page(
        "APP-04 square and enclosing ellipses", "app04-square-v1", "app04-ellipsoid-fd302c34092f8b19",
        "This companion plots the saved square vertices and two outer ellipse results. The diagonal-orientation radius is converted to physical x-y coordinates using the declared orientation; the circles show the resulting ellipses in this special two-dimensional fixture.")}


def ext05_companion(record_path: Path, style_path: Path) -> dict[str, bytes]:
    """Plot only the archived EXT-05 state samples, without interpolating a path."""
    record = json.loads(Path(record_path).read_text(encoding="utf-8"))
    times = record["model"]["times"]
    states = record["analytic"]["trajectory"]
    _require(record.get("schema") == "csl.ext05-discretization-report/1" and
             times == [0, 1, 3] and states == [[0, 0], [1, 2], [3, 0]],
             "EXT-05 saved sample times or states changed")
    document = {"schema": "csl.saved-geometric-plot/1",
                "title": "EXT-05 saved position–velocity states",
                "description": ("Markers show the three states recorded at physical times 0, 1, and 3. "
                                "The figure does not interpolate between samples or claim to show the continuous trajectory."),
                "aspect": "independent",
                "axes": {"x": {"label": "position state (source units unspecified)"},
                         "y": {"label": "velocity state (source units unspecified)"}},
                "series": [{"kind": "points", "label": "saved states at t = 0, 1, 3",
                            "color": "#D55E00", "points": states, "size": 52, "alpha": 1}]}
    outputs = _render_companion(document, style_path, "ext05-states-v1")
    return outputs | {"ext05-states-v1.html": _companion_page(
        "EXT-05 saved state samples", "ext05-states-v1", "ext05-discretization-a40ba9647cc023dc",
        "This companion plots exactly the archived position–velocity states at physical times 0, 1, and 3. It shows only the saved samples: no line between markers or continuous-time trajectory is inferred.",
        aspect="independent")}


def ext01_companion(record_path: Path, style_path: Path) -> dict[str, bytes]:
    """Plot the seven archived EXT-01 B08 timing observations."""
    record = json.loads(Path(record_path).read_text(encoding="utf-8"))
    trials = [row for row in record.get("trials", [])
              if row.get("fixture") == "b08_rounded" and not row.get("warmup")]
    _require(record.get("schema") == "csl.ext01-fixed-plan-records/1" and
             record.get("report_id") == "ext01-fixed-plan-20261016-11b7bc74" and
             len(trials) == 7 and
             [row.get("round") for row in trials] == list(range(1, 8)) and
             all(row.get("batch") == row.get("checked_calls") == 1 and
                 row.get("result", {}).get("disturbance_histories") == 160000 and
                 row.get("result", {}).get("plan_count") == 625
                 for row in trials),
             "EXT-01 saved B08 trial identities changed")
    points = [[row["round"], row["elapsed_ns"] / 1_000_000] for row in trials]
    median_ms = next(row["median_elapsed_ns"] for row in record["summary"]
                     if row["fixture"] == "b08_rounded") / 1_000_000
    document = {"schema": "csl.saved-geometric-plot/1",
                "title": "EXT-01 saved B08 timing observations",
                "description": ("Seven markers show saved full-catalogue timing observations for the rounded B08 reference. "
                                "Each marker is one checked public call over 625 plans and 160,000 disturbance histories. "
                                "No line is drawn between rounds; this is descriptive timing evidence, not a comparison or speedup claim."),
                "aspect": "independent",
                "axes": {"x": {"label": "measured round"},
                         "y": {"label": "elapsed time (ms per call)"}},
                "series": [{"kind": "points", "label": "saved B08 calls",
                            "color": "#0072B2", "points": points, "size": 42, "alpha": 1}]}
    outputs = _render_companion(document, style_path, "ext01-b08-timing-v1")
    return outputs | {"ext01-b08-timing-v1.html": _companion_page(
        "EXT-01 B08 full-catalogue timing", "ext01-b08-timing-v1",
        "ext01-fixed-plan-303ad863ca3af58dc6a515844c474fe0e1af9349e55cb8acd1ff1a3f220f1b54",
        f"This companion plots the seven saved measured B08 observations from the frozen EXT-01 record. "
        f"Each point is one checked call over 625 plans and 160,000 disturbance histories; the archived median is {median_ms:.3f} ms. "
        "The points are not connected, and the observation does not establish a speedup or performance winner.",
        aspect="numeric")}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _companion_page(title: str, stem: str, report_id: str, summary: str,
                    aspect: str = "equal") -> bytes:
    title = escape(title)
    summary = escape(summary)
    report_id = escape(report_id, quote=True)
    if aspect == "equal":
        scaling = "The plot uses equal x-y scales and preserves the archived fixture values."
    elif aspect == "numeric":
        scaling = "Round and elapsed time use separate numeric axes; elapsed time is shown in milliseconds per call."
    else:
        scaling = "Independent coordinate scales are disclosed; the saved state coordinates use different physical meanings."
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{title} · shared axis policy</title><link rel="stylesheet" href="examples.css"></head><body>'
            '<main><p><a href="index.html#saved-report-figures">← Reviewed report figures</a></p>'
            '<p class="eyebrow">Saved-data companion · shared quantitative axes</p>'
            f'<h1>{title}</h1><p>{summary}</p>'
            f'<figure><img src="{stem}.svg" alt="{title}; saved values on labelled numeric axes">'
            '<figcaption>Numeric ticks and major grids follow the shared csl-report-quantitative-v1 policy. '
            + escape(scaling) + '</figcaption></figure>'
            f'<p><a href="{stem}.png">Standalone PNG</a> · <a href="../{report_id}/records.json">Frozen values ↗</a> · '
            f'<a href="../{report_id}/index.html">Original report ↗</a></p></main></body></html>').encode()


def lotka_volterra_companion(record_path: Path, style_path: Path) -> dict[str, bytes]:
    """Render the archived 512 sample paths without re-running their recurrence."""
    record_path = Path(record_path)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    def require(condition: bool, message: str) -> None:
        if not condition:
            raise ValueError(message)
    require(record.get("schema") == "csl.lotka-volterra-sampled-illustration/1",
            "unsupported saved Lotka–Volterra sample record")
    traces = record.get("sampled_states")
    require(isinstance(traces, list) and len(traces) == 512 and
            all(isinstance(trace, list) and len(trace) == 61 for trace in traces),
            "saved Lotka–Volterra histories differ from the reviewed 512 × 61 record")
    require(record["displayed_stages"] == [15, 30, 45, 60],
            "saved Lotka–Volterra stage selection changed")
    require(record["model"]["state_units"] ==
            "not specified in the source; plotted coordinates retain the printed state units",
            "saved Lotka–Volterra unit statement changed")
    series = []
    for first, last, color in STAGE_BANDS:
        points = [trace[stage] for trace in traces for stage in range(first, last + 1)]
        series.append({"kind": "points", "label": f"sample states, stages {first}–{last}",
                       "color": color, "points": points, "size": 4, "alpha": .18})
    series.extend((
        {"kind": "points", "label": "unforced equilibrium (400, 300)", "color": "#222222",
         "points": [[400, 300]], "size": 38, "alpha": 1},
        {"kind": "points", "label": "initial state (410, 300)", "color": "#009E73",
         "points": [record["model"]["initial_state"]], "size": 32, "alpha": 1},
    ))
    document = {"schema": "csl.saved-geometric-plot/1",
                "title": "Lotka–Volterra sampled state cloud by stage band",
                "description": ("30,720 saved state points from 512 seeded control histories are colored by four 15-stage bands. "
                                "The dark and green markers show the unforced equilibrium and common initial state. "
                                "Samples and their plot extent are not the full reachable set and provide no inner or outer certificate."),
                "aspect": "independent",
                "axes": {"x": {"label": "prey state x₁ (source units unspecified)"},
                         "y": {"label": "predator state x₂ (source units unspecified)"}},
                "series": series}
    with tempfile.TemporaryDirectory(prefix="csl-lotka-figure-") as directory:
        output = Path(directory) / "figure"
        receipt = geometry_figures.render(document, style_path, output)
        svg = (output / "geometry.svg").read_bytes()
        png = (output / "geometry.png").read_bytes()
    report_id = escape(record["report_id"], quote=True)
    source_commit = escape(record["source_commit"], quote=True)
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Lotka–Volterra sample geometry · shared axis policy</title>'
            '<link rel="stylesheet" href="examples.css"></head><body><main>'
            '<p><a href="index.html#saved-report-figures">← Reviewed report figures</a></p>'
            '<p class="eyebrow">Saved-data companion · shared quantitative axes</p>'
            '<h1>Lotka–Volterra samples across four stage bands</h1>'
            '<p>This figure reads the frozen record directly; it does not re-run the recurrence. Each colored dot is a saved state '
            'from one of 512 seeded control histories. The four colors divide stages 1–60 into equal bands.</p>'
            '<figure><img src="lotka-volterra-sampled-v1.svg" alt="Saved Lotka–Volterra state samples across four stage bands, with equilibrium and initial state markers">'
            '<figcaption>Independent coordinate scales are disclosed because source units are unspecified. Numeric ticks and major grids use '
            'the shared <code>csl-report-quantitative-v1</code> policy. The samples do not bound the complete reachable set.</figcaption></figure>'
            '<p><a href="lotka-volterra-sampled-v1.png">Standalone PNG</a> · <a href="lotka-volterra-sampled-v1.svg">Standalone SVG</a> · '
            '<a href="../' + report_id + '/records.json">Frozen sampled values ↗</a> · '
            '<a href="../' + report_id + '/index.html">Original report ↗</a> · '
            '<a href="https://github.com/butahlecoq/controlled-systems-lab/blob/' + source_commit +
            '/scripts/reports/lotka_volterra_sampled.py">Source at recorded commit ↗</a></p>'
            '<p class="limits">This is an additive display of the saved sample data, not an exact reachability set, solver result, or historical reproduction.</p>'
            '</main></body></html>').encode()
    return {"lotka-volterra-sampled-v1.svg": svg,
            "lotka-volterra-sampled-v1.png": png,
            "lotka-volterra-sampled-v1.html": page,
            "lotka-volterra-sampled-v1-export.json": (json.dumps(receipt, indent=2) + "\n").encode()}
