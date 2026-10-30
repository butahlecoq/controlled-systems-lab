"""Make additive quantitative figure companions from frozen extension records."""
from __future__ import annotations

from html import escape
from itertools import product
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


def app03_companion(record_path: Path, style_path: Path) -> dict[str, bytes]:
    """Plot APP-03's saved planar zonotope and saved axis-cover generators."""
    record = json.loads(Path(record_path).read_text(encoding="utf-8"))
    fixture = record["fixtures"]["diamond-axis-cover"]
    generators = fixture["input_generators"]
    output = fixture["expected_generators"]
    _require(record.get("schema") == "csl.app03-zonotope-reduction/1" and
             record.get("report_id") == "app03-zonotope-4522855018fa9b0b" and
             fixture["center"] == [0, 0] and
             generators == [[1, 0, .5], [0, 1, .5]] and
             output == [[1.5, 0], [0, 1.5]] and
             fixture["relation"] == "outer" and
             fixture["analytic_support_1_minus_1"] == {"input": 2, "output": 3},
             "APP-03 saved zonotope or outer-cover fixture changed")
    signed_points = sorted({
        (sum(generators[0][index] * signs[index] for index in range(len(signs))),
         sum(generators[1][index] * signs[index] for index in range(len(signs))))
        for signs in product((-1, 1), repeat=len(generators[0]))
    })

    def cross(origin: tuple[float, float], first: tuple[float, float],
              second: tuple[float, float]) -> float:
        return ((first[0] - origin[0]) * (second[1] - origin[1]) -
                (first[1] - origin[1]) * (second[0] - origin[0]))

    lower: list[tuple[float, float]] = []
    upper: list[tuple[float, float]] = []
    for point in signed_points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    for point in reversed(signed_points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    hull = lower[:-1] + upper[:-1]
    cover = [(-output[0][0], -output[1][1]), (output[0][0], -output[1][1]),
             (output[0][0], output[1][1]), (-output[0][0], output[1][1])]
    document = {"schema": "csl.saved-geometric-plot/1",
                "title": "APP-03 saved planar zonotope and axis cover",
                "description": ("The input boundary is the convex hull of the eight signed sums formed directly from the three archived generator columns. "
                                "Dark points show those saved-coefficient sums; the orange square uses the recorded outer-cover generators. "
                                "This is a 2D display of one saved fixture, not a new geometry query or a finite error certificate."),
                "aspect": "equal",
                "axes": {"x": {"label": "x coordinate (source units unspecified)"},
                         "y": {"label": "y coordinate (source units unspecified)"}},
                "series": [
                    {"kind": "polygon", "label": "saved outer axis cover", "color": "#D55E00",
                     "fill": True, "alpha": .08, "points": [list(point) for point in cover]},
                    {"kind": "polygon", "label": "input zonotope · saved generators", "color": "#0072B2",
                     "fill": True, "alpha": .18, "points": [list(point) for point in hull]},
                    {"kind": "points", "label": "eight saved-generator sign sums", "color": "#222222",
                     "points": [list(point) for point in signed_points], "size": 26, "alpha": .65},
                ]}
    outputs = _render_companion(document, style_path, "app03-zonotope-v1")
    return outputs | {"app03-zonotope-v1.html": _companion_page(
        "APP-03 saved planar zonotope", "app03-zonotope-v1",
        "app03-zonotope-4522855018fa9b0b",
        "The saved CSL::approximation zonotope-reduction adapter reports method tag generator-axis-cover. Input generators are (1,0), (0,1), (0.5,0.5); the recorded outer-cover generators are (1.5,0), (0,1.5). The signed points are direct sums of archived binary64 coefficients; the blue outline joins their planar convex hull. The fixture reports support 2 for the input and 3 for its axis cover in direction (1, −1). This display does not add a finite approximation-error bound or validated real-arithmetic claim.",
        source_commit=record["source_commit"])}


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


def app01_companion(record_path: Path, style_path: Path, publication_report_id: str) -> dict[str, bytes]:
    """Plot APP-01's archived plan-check medians without collecting new timings."""
    record = json.loads(Path(record_path).read_text(encoding="utf-8"))
    payload = record.get("payload", {})
    summary = payload.get("summary", [])
    expected = {"valid_plan": 189260900, "invalid_plan": 190658800,
                "empty_inner": 127618800}
    _require(record.get("schema") == "csl.app01-plan-report/1" and
             record.get("report_id") == "app01-plan-20261016-22d406fd" and
             isinstance(publication_report_id, str) and publication_report_id.startswith("app01-plan-") and
             payload.get("schema") == "csl.app01-plan-report/1" and
             payload.get("source_commit") == "22d406fd9ea92315ef2a4f6b5703eec74e710d47" and
             [row.get("fixture") for row in summary] == list(expected) and
             all(row.get("median_elapsed_ns") == expected[row["fixture"]] and
                 row.get("trials") == 7 and row.get("batch") == 40000 and
                 row.get("checked_calls") == 280000 and row.get("failures") == 0
                 for row in summary),
             "APP-01 saved fixture timing identities changed")
    colors = {"valid_plan": "#0072B2", "invalid_plan": "#D55E00", "empty_inner": "#009E73"}
    points = {row["fixture"]: [index, row["median_elapsed_ns"] / 1_000_000]
              for index, row in enumerate(summary, start=1)}
    document = {"schema": "csl.saved-geometric-plot/1",
                "title": "APP-01 saved plan-check median times",
                "description": ("Three markers show archived fixture medians: valid plan, invalid plan, and empty inner set. "
                                "Each median summarizes seven measured batches of 40,000 checked calls. "
                                "This descriptive report is not a speed comparison or performance-winner claim."),
                "aspect": "independent",
                "axes": {"x": {"label": "fixture ordinal (1 valid, 2 invalid, 3 empty inner)"},
                         "y": {"label": "median elapsed time per 40,000-call batch (ms)"}},
                "series": [{"kind": "points", "label": f"{name} · {expected[name] / 1_000_000:.3f} ms median",
                            "color": colors[name], "points": [points[name]], "size": 52, "alpha": 1}
                           for name in expected]}
    outputs = _render_companion(document, style_path, "app01-plan-timing-v1")
    return outputs | {"app01-plan-timing-v1.html": _companion_page(
        "APP-01 saved plan-check timings", "app01-plan-timing-v1", publication_report_id,
        f"This companion plots archived medians: valid_plan {expected['valid_plan'] / 1_000_000:.3f} ms, "
        f"invalid_plan {expected['invalid_plan'] / 1_000_000:.3f} ms, and "
        f"empty_inner {expected['empty_inner'] / 1_000_000:.3f} ms. Each median summarizes seven measured "
        "batches of 40,000 checked calls (280,000 calls per fixture). "
        "Exact nanosecond values, trials, configuration, and evidence limits remain in the frozen record. "
        "This is descriptive evidence, not a speed comparison or a performance-winner claim.",
        aspect="fixture-timing", source_commit=payload["source_commit"])}


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


def ext04_observed_replay_companion(record_path: Path, style_path: Path) -> dict[str, bytes]:
    """Plot the frozen EXT-04 measured batch observations."""
    record = json.loads(Path(record_path).read_text(encoding="utf-8"))
    expected = ("partial_noisy_delayed", "post_feedthrough", "no_channel")
    rows = record.get("rows", [])
    measured = [row for row in rows if row.get("warmup") is False]
    _require(record.get("schema") == "csl.ext04-replay-records/1" and
             record.get("report_id") == "ext04-df62c7c6d295e135" and
             len(rows) == 24 and len(measured) == 21 and
             all(record["summary"][name]["successes"] == 7 and
                 record["summary"][name]["failures"] == 0 for name in expected) and
             {row.get("fixture") for row in measured} == set(expected) and
             all(row.get("status") == "passed" and row.get("batch") == 5000 and
                 row.get("checked_calls") == 5000 and 0 <= row.get("round", -1) <= 6
                 for row in measured),
             "EXT-04 saved replay observations changed")
    colors = {"partial_noisy_delayed": "#0072B2", "post_feedthrough": "#D55E00",
              "no_channel": "#009E73"}
    labels = {"partial_noisy_delayed": "partial noisy delayed", "post_feedthrough": "post-decision feedthrough",
              "no_channel": "no observation channel"}
    series = [{"kind": "points", "label": labels[name], "color": colors[name],
               "points": [[row["round"] + 1, row["elapsed_ns"] / 1_000_000]
                          for row in measured if row["fixture"] == name],
               "size": 40, "alpha": .85} for name in expected]
    document = {"schema": "csl.saved-geometric-plot/1",
                "title": "EXT-04 saved observed-replay batch times",
                "description": ("Each marker is one of seven saved 5,000-call batches for a fixed observation fixture. "
                                "The three series are distinct workloads, not competing methods. The plot reads archived "
                                "durations and does not rerun the replay."),
                "aspect": "independent",
                "axes": {"x": {"label": "measured round"},
                         "y": {"label": "duration (ms per 5,000 checked calls)"}},
                "series": series}
    outputs = _render_companion(document, style_path, "ext04-observed-replay-v1")
    medians = "; ".join(f"{labels[name]} {record['summary'][name]['median_batch_ns'] / 1_000_000:.3f} ms"
                         for name in expected)
    return outputs | {"ext04-observed-replay-v1.html": _companion_page(
        "EXT-04 observed-replay batch times", "ext04-observed-replay-v1", record["report_id"],
        f"The three saved medians are {medians}. Each point covers 5,000 fully checked replay calls. "
        "These distinct fixtures are not competing methods; the report makes no performance-winner claim.",
        aspect="batch-timing", source_commit=record["source_commit"],
        image_alt="Seven saved batch durations for each of the partial noisy delayed, post-decision feedthrough, and no-channel replay fixtures.",
        report_route="ext04-observed-replay-eb0b06e560360611d2f2a16fba9b1204e0415b4ba5cd0d5210427c6349963b34")}


def ext04_affine_synthesis_companion(bundle: Path, style_path: Path) -> dict[str, bytes]:
    """Plot the frozen initial/terminal vertices and target box for the EXT-04 policy fixture."""
    bundle = Path(bundle)
    record = json.loads((bundle / "records.json").read_text(encoding="utf-8"))
    result = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    fixture = record.get("fixture", {})
    initial = sorted({tuple(row.get("initial", ())) for row in result.get("generators", [])})
    terminal = [row.get("terminal") for row in result.get("generators", [])]
    target = fixture.get("terminal_bounds", {})
    _require(record.get("schema") == "csl.ext04-affine-synthesis-report/1" and
             record.get("report_id") == "ext04-affine-synthesis-7eadf7c7ecbb2bbd" and
             fixture.get("id") == "ext04-one-stage-noisy-integrator-v1" and
             fixture.get("initial_generators") == [[-1, -.05], [-1, .05], [1, -.05], [1, .05]] and
             result.get("coverage") == "all_joint_uncertainty" and
             result.get("feasibility") == "within_tolerance" and
             result.get("solver_outcome") == "optimal" and len(result.get("generators", [])) == 8 and
             initial == [(-1.0, -.05), (-1.0, .05), (1.0, -.05), (1.0, .05)] and
             all(isinstance(point, list) and len(point) == 2 for point in terminal) and
             all(target["x1"][0] - 1e-12 <= point[0] <= target["x1"][1] + 1e-12 and
                 target["x2"][0] - 1e-12 <= point[1] <= target["x2"][1] + 1e-12
                 for point in terminal),
             "EXT-04 affine-synthesis saved vertices or target changed")
    document = {"schema": "csl.saved-geometric-plot/1",
                "title": "EXT-04 saved robust one-step state vertices",
                "description": ("The pale rectangle is the authored initial state set, the dashed rectangle is the terminal target, "
                                "and each marker is one of eight saved initial/noise generator terminal states under the synthesized policy. "
                                "The plot reads saved replay outcomes; it does not rerun policy synthesis."),
                "aspect": "independent",
                "axes": {"x": {"label": "state x₁"}, "y": {"label": "state x₂"}},
                "series": [
                    {"kind": "polygon", "label": "initial state set", "color": "#0072B2",
                     "fill": True, "alpha": .10,
                     "points": [[-1, -.05], [1, -.05], [1, .05], [-1, .05]]},
                    {"kind": "polygon", "label": "terminal target", "color": "#D55E00",
                     "linestyle": "--", "fill": True, "alpha": .10,
                     "points": [[target["x1"][0], target["x2"][0]],
                                [target["x1"][1], target["x2"][0]],
                                [target["x1"][1], target["x2"][1]],
                                [target["x1"][0], target["x2"][1]]]},
                    {"kind": "points", "label": "eight saved terminal vertices", "color": "#009E73",
                     "points": terminal, "size": 44, "alpha": .95},
                ]}
    outputs = _render_companion(document, style_path, "ext04-affine-synthesis-v1")
    return outputs | {"ext04-affine-synthesis-v1.html": _companion_page(
        "EXT-04 robust one-step synthesis", "ext04-affine-synthesis-v1", record["report_id"],
        "The saved numerical policy maps all eight authored initial/noise generator pairs into the one-step terminal target. "
        "The source report states that coverage applies to this caller-authored joint hull and is not a validated arithmetic certificate.",
        source_commit=record["source_commit"],
        image_alt="Four initial state vertices, a small terminal target rectangle, and eight saved terminal vertices inside the target.",
        report_route=record["report_id"])}


def ext07_hybrid_relation_companion(record_path: Path, style_path: Path) -> dict[str, bytes]:
    """Plot the saved one-control EXT-07 feasible relation and its minimum."""
    record = json.loads(Path(record_path).read_text(encoding="utf-8"))
    scenario = record.get("scenario", {})
    _require(record.get("schema") == "csl.ext07-hybrid-profile-report/1" and
             record.get("report_id") == "ext07-hybrid-51d9ee2e89d240eb" and
             scenario.get("control_interval") == [0, 1] and
             scenario.get("transition_guard") == [0, .5] and
             record.get("analytic", {}).get("feasible_relation") ==
             "x0=0, x_pre1=u0, x1=u0, 0<=u0<=0.5" and
             record["analytic"].get("optimal_family") == "x0=u0=x_pre1=x1=0",
             "EXT-07 saved hybrid relation or analytic answer changed")
    interval = scenario["transition_guard"]
    document = {"schema": "csl.saved-geometric-plot/1",
                "title": "EXT-07 saved feasible control relation",
                "description": ("The feasible relation is x1=u0 over the saved transition guard from zero to one half. "
                                "The marker at the origin is the unique minimum of the terminal state. This is the analytic "
                                "one-step fixture, not a sampled trajectory."),
                "aspect": "equal",
                "axes": {"x": {"label": "control u₀"}, "y": {"label": "terminal state x₁"}},
                "series": [
                    {"kind": "path", "label": "feasible relation x₁ = u₀", "color": "#0072B2",
                     "points": [[interval[0], interval[0]], [interval[1], interval[1]]]},
                    {"kind": "points", "label": "unique terminal minimum", "color": "#D55E00",
                     "points": [[0, 0]], "size": 58, "alpha": 1},
                ]}
    outputs = _render_companion(document, style_path, "ext07-feasible-relation-v1")
    return outputs | {"ext07-feasible-relation-v1.html": _companion_page(
        "EXT-07 feasible control relation", "ext07-feasible-relation-v1", record["report_id"],
        "The saved fixture gives x₁=u₀ on 0≤u₀≤0.5. The terminal objective is x₁, so the unique minimum is the origin.",
        source_commit=record["source_commit"],
        image_alt="The feasible line x1 equals control u0 from zero to one half, with its unique minimum marked at the origin.",
        report_route=record["report_id"])}


def ext07_two_parameter_companion(record_path: Path, style_path: Path) -> dict[str, bytes]:
    """Plot the frozen EXT-07 feasible control polygons and tied minimizing face."""
    record = json.loads(Path(record_path).read_text(encoding="utf-8"))
    scenario = record.get("scenario", {})
    analytic = record.get("analytic", {})
    paths = analytic.get("paths", {})
    _require(record.get("schema") == "csl.ext07-hybrid-two-parameter-report/1" and
             record.get("report_id") == "ext07-hybrid-two-parameter-26f402289a309403" and
             scenario.get("controls") == {"u0": [0, 1], "u1": [0, 1]} and
             {edge.get("id"): edge.get("guard") for edge in scenario.get("edges", [])} ==
             {"enter-half": "0 <= x_pre1 <= 0.5", "enter-full": "universal", "finish": "universal"} and
             analytic.get("global_minimum") == 0 and
             analytic.get("tied_paths") == ["enter-half", "enter-full"] and
             paths.get("enter-half", {}).get("feasible_parameter_set") == "(u0,u1) in [0,0.5] x [0,1]" and
             paths.get("enter-full", {}).get("feasible_parameter_set") == "(u0,u1) in [0,1] x [0,1]",
             "EXT-07 saved two-control regions or minimizing family changed")
    document = {"schema": "csl.saved-geometric-plot/1",
                "title": "EXT-07 feasible control regions and minimizing family",
                "description": ("The dashed outer square is the enter-full path and the half-width rectangle is the enter-half path. "
                                "Both paths share the full minimizing face u0=0 with u1 from zero to one. Polygon boundaries come "
                                "from the archived control bounds and guard, not solver samples."),
                "aspect": "equal",
                "axes": {"x": {"label": "stage 0 control u₀"}, "y": {"label": "stage 1 control u₁"}},
                "series": [
                    {"kind": "polygon", "label": "enter-full feasible square", "color": "#0072B2",
                     "linestyle": "--", "fill": True, "alpha": .08,
                     "points": [[0, 0], [1, 0], [1, 1], [0, 1]]},
                    {"kind": "polygon", "label": "enter-half feasible rectangle", "color": "#009E73",
                     "fill": True, "alpha": .16,
                     "points": [[0, 0], [.5, 0], [.5, 1], [0, 1]]},
                    {"kind": "path", "label": "complete tied minimizing face", "color": "#D55E00",
                     "linewidth": 3, "points": [[0, 0], [0, 1]]},
                ]}
    outputs = _render_companion(document, style_path, "ext07-two-control-family-v1")
    return outputs | {"ext07-two-control-family-v1.html": _companion_page(
        "EXT-07 feasible control regions", "ext07-two-control-family-v1", record["report_id"],
        "The archived enter-full path allows [0,1]². The enter-half path allows [0,0.5]×[0,1]. Both retain the complete minimizing face u₀=0, 0≤u₁≤1.",
        source_commit=record["source_commit"],
        image_alt="The enter-full unit square contains the enter-half rectangle. Both share the complete minimizing line u0 equals zero, with u1 from zero to one.",
        report_route="ext07-hybrid-two-parameter-8ad871b5ea29fc7b")}


def finite_feedback_timing_companion(record_path: Path, style_path: Path) -> dict[str, bytes]:
    """Plot saved finite-feedback median execution times and observed ranges."""
    record = json.loads(Path(record_path).read_text(encoding="utf-8"))
    expected = ("clipping", "branching", "empty-action", "nominal")
    summary = record.get("summary", [])
    _require(record.get("schema") == "csl.finite-feedback-records/2" and
             record.get("report_id") == "finite-feedback-a6e96fd96c7ac7cc" and
             [row.get("scenario") for row in summary] == list(expected) and
             all(row.get("attempts") == row.get("matches") == 7 and row.get("failures") == 0 and
                 row.get("min_ns", 0) <= row.get("median_ns", -1) <= row.get("max_ns", 0)
                 for row in summary),
             "finite-feedback saved timing summary changed")
    colors = ("#0072B2", "#D55E00", "#009E73", "#6A4C93")
    series = []
    for ordinal, (name, row, color) in enumerate(zip(expected, summary, colors), start=1):
        series.append({"kind": "path", "label": name + " observed range", "color": color,
                       "points": [[ordinal, row["min_ns"] / 1000],
                                  [ordinal, row["max_ns"] / 1000]]})
        series.append({"kind": "points", "label": name + " median", "color": color,
                       "points": [[ordinal, row["median_ns"] / 1000]], "size": 50, "alpha": 1})
    document = {"schema": "csl.saved-geometric-plot/1",
                "title": "Finite-feedback saved execution times",
                "description": ("Each median marker and vertical range line summarizes seven saved checked calls for one scenario. "
                                "The x-axis uses scenario ordinals: one clipping, two branching, three empty action, four nominal. "
                                "These are descriptive timings from one adapter, not a comparison."),
                "aspect": "independent",
                "axes": {"x": {"label": "scenario ordinal"},
                         "y": {"label": "duration (μs per checked call)"}},
                "series": series}
    outputs = _render_companion(document, style_path, "finite-feedback-timing-v1")
    medians = "; ".join(f"{row['scenario']} {row['median_ns'] / 1000:g} μs"
                         for row in summary)
    return outputs | {"finite-feedback-timing-v1.html": _companion_page(
        "Finite-feedback saved timings", "finite-feedback-timing-v1", record["report_id"],
        f"The seven-call median durations are {medians}. The vertical lines show each scenario's recorded min-to-max range. "
        "The underlying report states that checked witness cells do not certify the complete action tensor.",
        aspect="call-timing", source_commit=record["source_commit"],
        image_alt="Saved median execution time and min-to-max range for the clipping, branching, empty-action, and nominal scenarios.",
        report_route="finite-feedback-registered-f874133e442eb0fb884b8813a06591cc0f077063ee75ddf627de74656fc11c0f")}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _companion_page(title: str, stem: str, report_id: str, summary: str,
                    aspect: str = "equal", source_commit: str | None = None,
                    image_alt: str | None = None, report_route: str | None = None) -> bytes:
    title = escape(title)
    summary = escape(summary)
    report_id = escape(report_id, quote=True)
    report_route = escape(report_route or report_id, quote=True)
    source_link = (f' · <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/'
                   f'{escape(source_commit, quote=True)}">Source commit {escape(source_commit)} ↗</a>'
                   if source_commit else "")
    if aspect == "equal":
        scaling = "The plot uses equal x-y scales and preserves the archived fixture values."
    elif aspect == "numeric":
        scaling = "Round and elapsed time use separate numeric axes; elapsed time is shown in milliseconds per call."
    elif aspect == "batch-timing":
        scaling = "Measured round and duration use separate numeric axes; duration is milliseconds per 5,000-call batch."
    elif aspect == "call-timing":
        scaling = "Scenario ordinal and duration use separate numeric axes; duration is microseconds per checked call."
    elif aspect == "fixture-timing":
        scaling = "Fixture ordinal and median elapsed time use separate numeric axes; elapsed time is per 40,000-call batch in milliseconds."
    else:
        scaling = "Independent coordinate scales are disclosed."
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{title} · shared axis policy</title><link rel="stylesheet" href="examples.css"></head><body>'
            '<main><p><a href="index.html#saved-report-figures">← Reviewed report figures</a></p>'
            '<p class="eyebrow">Saved-data companion · shared quantitative axes</p>'
            f'<h1>{title}</h1><p>{summary}</p>'
            f'<figure><img src="{stem}.svg" alt="{escape(image_alt or (title + "; saved values on labelled numeric axes"), quote=True)}">'
            '<figcaption>Numeric ticks and major grids follow the shared csl-report-quantitative-v1 policy. '
            + escape(scaling) + '</figcaption></figure>'
            f'<p><a href="{stem}.png">Standalone PNG</a> · <a href="../{report_route}/records.json">Frozen values ↗</a> · '
            f'<a href="../{report_route}/index.html">Original report ↗</a>{source_link}</p></main></body></html>').encode()


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
