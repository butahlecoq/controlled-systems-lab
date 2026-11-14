"""Stage a source-bound 2D illustration of matched open-loop and observed-state MPC."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from html import escape
from io import StringIO
from pathlib import Path

import report_data
import site_design

SOURCE = "27922d674f0c341517fc5c8b99d1bb2cd2597ab7"
SOURCE_URL = "https://github.com/butahlecoq/controlled-systems-lab/tree/" + SOURCE
CPP_SOURCE = (
    "https://github.com/butahlecoq/controlled-systems-lab/blob/"
    + SOURCE
    + "/examples/discrete_mpc_2d.cpp"
)
API_SOURCE = (
    "https://github.com/butahlecoq/controlled-systems-lab/blob/"
    + SOURCE
    + "/include/csl/controllers/discrete_mpc.hpp"
)
CPP_BINARY_SHA256 = "7816899ee75c59a5db1b0aaf47751ef8b6b829e57c6a80d99591e3a93d64b20b"
CSV_SHA256 = "1d5b20418ea1ee532fadd1c3f265a2b8c31e52b513ef769a0dcd05fe002b10c9"
STDOUT_SHA256 = "7bd083c126514c692c72c7a48e6a6a3497cd26c0cec2a35ef4cc4660a6e2ca91"

PAGE = "discrete-mpc-2d.html"
FIGURE = "discrete-mpc-2d.svg"
CSV = "discrete_mpc_2d-output.csv"
OUTPUT = "discrete_mpc_2d-output.txt"
RECORD = "discrete-mpc-2d.json"

REPRODUCTION_COMMAND = "\n".join(
    (
        "cmake --preset highs",
        "cmake --build --preset highs",
        "cmake --install build/highs --prefix build/highs/install",
        "cmake -S examples -B build/examples -DCMAKE_PREFIX_PATH=build/highs/install",
        "cmake --build build/examples --target discrete_mpc_2d",
        "rm -rf build/examples/discrete-mpc-2d-output",
        "./build/examples/discrete_mpc_2d build/examples/discrete-mpc-2d-output",
    )
)


def _read(root: Path, relative: str) -> bytes:
    path = Path(root)
    report_data.require(not path.is_symlink(), "discrete MPC lesson root is symlinked")
    for part in Path(relative).parts:
        path /= part
        report_data.require(
            not path.is_symlink(), "discrete MPC lesson path is symlinked: " + relative
        )
    report_data.require(
        path.is_file(), "discrete MPC lesson asset is missing or symlinked: " + relative
    )
    return path.read_bytes()


def _parse_capture(data: bytes) -> dict[tuple[str, str, str, int], tuple[float, ...]]:
    try:
        rows = list(csv.DictReader(StringIO(data.decode("ascii"))))
    except (UnicodeDecodeError, csv.Error):
        raise ValueError("native MPC capture must be an ASCII CSV table") from None
    report_data.require(
        len(rows) == 68, "native MPC capture must contain all four complete episode traces"
    )
    parsed: dict[tuple[str, str, str, int], tuple[float, ...]] = {}
    for row in rows:
        try:
            key = (row["scenario"], row["policy"], row["kind"], int(row["stage"]))
            raw_values = row["state"] if row["kind"] == "state" else row["control"]
            values = tuple(float(value) for value in raw_values.split(";"))
        except (KeyError, TypeError, ValueError):
            raise ValueError("native MPC capture contains a malformed row") from None
        report_data.require(
            all(math.isfinite(value) for value in values),
            "native MPC capture contains a nonfinite value",
        )
        report_data.require(key not in parsed, "native MPC capture has duplicate stage rows")
        parsed[key] = values

    scenarios = ("forecast-matched", "forecast-zero-replay-disturbed")
    policies = ("open-loop", "observed-mpc")
    for scenario in scenarios:
        for policy in policies:
            for stage in range(9):
                report_data.require(
                    (scenario, policy, "state", stage) in parsed,
                    "native MPC capture is missing a state stage",
                )
                report_data.require(
                    len(parsed[(scenario, policy, "state", stage)]) == 2,
                    "native MPC state rows must retain both coordinates",
                )
            for stage in range(8):
                report_data.require(
                    (scenario, policy, "control", stage) in parsed,
                    "native MPC capture is missing an action stage",
                )
                report_data.require(
                    len(parsed[(scenario, policy, "control", stage)]) == 2,
                    "native MPC action rows must retain both coordinates",
                )

    for kind, stage_count in (("state", 9), ("control", 8)):
        for stage in range(stage_count):
            open_loop = parsed[("forecast-matched", "open-loop", kind, stage)]
            mpc = parsed[("forecast-matched", "observed-mpc", kind, stage)]
            report_data.require(
                all(abs(left - right) <= 1e-7 for left, right in zip(open_loop, mpc, strict=True)),
                "matched nominal episode paths must agree within the native example tolerance",
            )
    action_differences = [
        stage
        for stage in range(1, 8)
        if abs(
            parsed[("forecast-zero-replay-disturbed", "open-loop", "control", stage)][0]
            - parsed[("forecast-zero-replay-disturbed", "observed-mpc", "control", stage)][0]
        )
        > 1e-7
    ]
    report_data.require(
        action_differences and action_differences[0] == 4,
        "declared replay example must first change an action at stage 4",
    )
    return parsed


def _record(
    capture: dict[tuple[str, str, str, int], tuple[float, ...]], stdout_bytes: bytes
) -> dict:
    return {
        "schema": "csl.educational-example.discrete-mpc-2d/1",
        "source_commit": SOURCE,
        "source_path": "examples/discrete_mpc_2d.cpp",
        "illustration_only": True,
        "source_model": {
            "id": "catalogue-2026/model-7/1",
            "states": 2,
            "controls": 2,
            "source_initial_state": [5.0, -2.0],
            "source_A": [[0.88, 0.05], [0.07, 0.84]],
            "source_B": [[0.35, -0.08], [0.05, 0.22]],
            "source_E": [[0.1, -0.12], [0.08, -0.15]],
            "source_state_bounds": [-20, 20],
            "source_control_bounds": [0, 10],
        },
        "authored_task_choices": {
            "profile_id": "catalogue-model-7-source-bounds-v1",
            "objective_id": "authored-zero-reference-quadratic-v1",
            "horizon_id": "authored-fixed-eight-stage-v1",
            "final_stage": 8,
            "running_state_hessian": [[2.0, 0.0], [0.0, 1.0]],
            "running_control_hessian": [[0.5, 0.0], [0.0, 0.0]],
            "terminal_state_hessian": [[4.0, 0.0], [0.0, 2.0]],
            "reference": [0.0, 0.0],
            "forecast": "zero external input at every decision stage",
            "replay_cases": {
                "forecast-matched": "zero external input at every stage",
                "forecast-zero-replay-disturbed": "external input (-3,4) at every stage",
            },
            "observation": "ideal full-state observation at each MPC decision",
        },
        "answer": {
            "matched_nominal_paths": "open-loop and observed-state MPC agree within 1e-7",
            "first_disturbed_replay_action_divergence_stage": 4,
            "open_loop_first_control_coordinate": capture[
                ("forecast-zero-replay-disturbed", "open-loop", "control", 4)
            ][0],
            "observed_mpc_first_control_coordinate": capture[
                ("forecast-zero-replay-disturbed", "observed-mpc", "control", 4)
            ][0],
            "interpretation": "Observed-state replanning responds to this declared replay path; this is not a robustness guarantee.",
        },
        "reproduction_command": REPRODUCTION_COMMAND,
        "evidence": {
            "classification": "actual native HiGHS episode capture; SVG rendered from the committed native CSV",
            "native_example_binary_sha256": CPP_BINARY_SHA256,
            "native_example_csv_sha256": CSV_SHA256,
            "native_example_stdout_sha256": STDOUT_SHA256,
            "native_example_stdout": stdout_bytes.decode("ascii").rstrip("\n"),
            "provider": "csl.convex.highs@1.0.0+highs.1.11.0",
            "build_scope": "Installed consumer linked a fresh csl_controllers archive and generated target export metadata over a byte-copied complete installed SDK; this is component-consumer evidence, not a fresh full-SDK install qualification.",
            "actual_replay_csv_is_solver_output": True,
            "realized_objectives_independently_recomputed_from_executed_states_and_actions": True,
            "svg_provenance": "Generated only from the committed native state/action CSV; no optimizer or simulated-policy code runs in the stager.",
        },
    }


def _svg(capture: dict[tuple[str, str, str, int], tuple[float, ...]]) -> bytes:
    width, height = 920, 470
    left = (70, 80, 350, 300)
    right = (520, 80, 340, 300)
    dark, blue, orange = "#1d3557", "#2878b5", "#d36135"

    def point(panel, x, y, xmin, xmax, ymin, ymax):
        px, py, pw, ph = panel
        return px + (x - xmin) * pw / (xmax - xmin), py + ph - (y - ymin) * ph / (ymax - ymin)

    def path_for(panel, values, xmin, xmax, ymin, ymax):
        return " ".join(
            ("M" if index == 0 else "L") + f"{point(panel, x, y, xmin, xmax, ymin, ymax)[0]:.2f},"
            f"{point(panel, x, y, xmin, xmax, ymin, ymax)[1]:.2f}"
            for index, (x, y) in enumerate(values)
        )

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Source model 7: observed-state MPC follows a declared replay disturbance</title>',
        '<desc id="desc">The left panel plots both state coordinates for matched and disturbed replay episodes. The right panel shows the first control coordinate; the disturbed observed-state MPC changes it at stage four while open loop continues its original plan.</desc>',
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<g font-family="sans-serif" fill="#18212b">',
        '<text x="245" y="35" text-anchor="middle" font-size="19" font-weight="700">State path (x₁, x₂)</text>',
        '<text x="690" y="35" text-anchor="middle" font-size="19" font-weight="700">First control coordinate u₁</text>',
    ]

    for panel, x_ticks, y_ticks, xmin, xmax, ymin, ymax, xlabel, ylabel in (
        (left, range(-4, 7, 2), range(-4, 3, 2), -4, 6, -4, 2, "x₁", "x₂"),
        (right, range(0, 8, 1), range(0, 4, 1), 0, 7, 0, 3, "stage k", "u₁[k]"),
    ):
        px, py, pw, ph = panel
        for tick in x_ticks:
            x, y = point(panel, tick, ymin, xmin, xmax, ymin, ymax)
            parts.append(f'<path d="M{x:.2f},{py} V{py + ph}" stroke="#e1e6eb"/>')
            parts.append(
                f'<text x="{x:.2f}" y="{py + ph + 22}" text-anchor="middle" font-size="12">{tick}</text>'
            )
        for tick in y_ticks:
            x, y = point(panel, xmin, tick, xmin, xmax, ymin, ymax)
            parts.append(f'<path d="M{px},{y:.2f} H{px + pw}" stroke="#e1e6eb"/>')
            parts.append(
                f'<text x="{px - 10}" y="{y + 4:.2f}" text-anchor="end" font-size="12">{tick}</text>'
            )
        parts.append(
            f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" fill="none" stroke="#56616d"/>'
        )
        parts.append(
            f'<text x="{px + pw / 2}" y="{py + ph + 48}" text-anchor="middle" font-size="14">{xlabel}</text>'
        )
        parts.append(
            f'<text transform="translate({px - 50} {py + ph / 2}) rotate(-90)" text-anchor="middle" font-size="14">{ylabel}</text>'
        )

    matched = [capture[("forecast-matched", "open-loop", "state", stage)] for stage in range(9)]
    disturbed_open = [
        capture[("forecast-zero-replay-disturbed", "open-loop", "state", stage)]
        for stage in range(9)
    ]
    disturbed_mpc = [
        capture[("forecast-zero-replay-disturbed", "observed-mpc", "state", stage)]
        for stage in range(9)
    ]
    for values, color, dash in (
        (matched, dark, ""),
        (disturbed_open, blue, ""),
        (disturbed_mpc, orange, ""),
    ):
        coords = [(row[0], row[1]) for row in values]
        parts.append(
            f'<path d="{path_for(left, coords, -4, 6, -4, 2)}" fill="none" stroke="{color}" stroke-width="3"{dash}/>'
        )
        for x, y in coords:
            px, py = point(left, x, y, -4, 6, -4, 2)
            parts.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="3.1" fill="{color}"/>')

    action_rows = (
        ("forecast-matched", "open-loop", dark, ""),
        ("forecast-zero-replay-disturbed", "open-loop", blue, ""),
        ("forecast-zero-replay-disturbed", "observed-mpc", orange, ""),
    )
    for scenario, policy, color, dash in action_rows:
        values = [capture[(scenario, policy, "control", stage)][0] for stage in range(8)]
        coords = [(stage, value) for stage, value in enumerate(values)]
        parts.append(
            f'<path d="{path_for(right, coords, 0, 7, 0, 3)}" fill="none" stroke="{color}" stroke-width="3"{dash}/>'
        )
        for x, y in coords:
            px, py = point(right, x, y, 0, 7, 0, 3)
            parts.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="3.1" fill="{color}"/>')

    legend = (
        (dark, "forecast-matched: open-loop and MPC overlap"),
        (blue, "disturbed replay: open-loop"),
        (orange, "disturbed replay: observed-state MPC"),
    )
    for index, (color, label) in enumerate(legend):
        x = 90 + index * 275
        parts.append(f'<path d="M{x},{430} h28" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<text x="{x + 36}" y="434" font-size="12">{escape(label)}</text>')
    parts.append("</g></svg>")
    return ("".join(parts) + "\n").encode("utf-8")


def _page(record: dict) -> str:
    crumbs = (("Learn", "../index.html"), ("Examples", "index.html"), ("Finite MPC", ""))
    parts = [
        site_design.page_start(
            "Observed-state MPC on a 2D source model", stylesheet_href="examples.css", crumbs=crumbs
        )
    ]
    parts.append('<p class="eyebrow">Nominal finite-horizon control · native source example</p>')
    parts.append("<h1>When a new state observation changes the next action</h1>")
    parts.append(
        "<p>This example uses the source data for catalogue model 7: two states, two control coordinates, "
        "initial state <code>(5,−2)</code>, and the published linear transition matrices. The source bounds are "
        "<code>−20≤xᵢ≤20</code> and <code>0≤uᵢ≤10</code>. The zero-reference objective and eight-stage horizon "
        "are explicitly authored by this example, not read from the model catalogue.</p>"
    )
    parts.append(
        f'<figure><img src="{FIGURE}" alt="State-plane trajectories and first-control time series compare nominal open loop with observed-state MPC under matched and disturbed replay inputs">'
        "<figcaption>Every point and action in this figure comes from the committed native HiGHS episode CSV. "
        "With the zero forecast and zero replay, the two policies agree within <code>1e−7</code>. When replay "
        "instead applies <code>w=(−3,4)</code> at every step while the forecast remains zero, observed-state MPC "
        "replans from the measured state and first changes its first control coordinate at stage 4: "
        f"<code>{record['answer']['open_loop_first_control_coordinate']:.6f}</code> open loop versus "
        f"<code>{record['answer']['observed_mpc_first_control_coordinate']:.6f}</code> MPC.</figcaption></figure>"
    )
    parts.append(
        '<section><h2>What the two policies solve</h2><div class="math-input"><p>Both use the same fixed final stage '
        "<code>T=8</code>, source bounds, authored cost and zero forecast. At stage <code>k</code>, MPC observes the full "
        "two-state vector and compiles the remaining stages <code>[k,T]</code>; the open-loop policy solves once at "
        "<code>k=0</code> and applies that plan. The running objective is</p>"
        "<p><strong><code>Σₖ₌₀⁷ (½ x[k]ᵀQx[k] + ½ u[k]ᵀRu[k]) + ½ x[8]ᵀQᴺx[8]</code></strong>,</p>"
        "<p>with <code>Q=diag(2,1)</code>, <code>R=diag(0.5,0)</code>, and <code>Qᴺ=diag(4,2)</code>. "
        "The same compiled running-state, control and terminal costs are retained at every replan; QP prediction "
        "objectives are not summed to obtain the realized episode objective.</p></div>"
        "<p>The changed action demonstrates the effect of observing this specified replay. It does not establish "
        "robustness to arbitrary disturbances, uncertainty bounds, or a physical calibration.</p></section>"
    )
    parts.append(
        "<section><h2>Source data and authored choices</h2><table><thead><tr><th>Source model facts</th><th>Task choices for this example</th></tr></thead><tbody>"
    )
    parts.append(
        "<tr><td><code>A=((0.88,0.05),(0.07,0.84))</code><br><code>B=((0.35,−0.08),(0.05,0.22))</code><br><code>E=((0.10,−0.12),(0.08,−0.15))</code><br><code>x₀=(5,−2)</code></td><td>Zero-reference diagonal quadratic objective<br>Eight fixed transitions ending at <code>T=8</code><br>Zero nominal forecast<br>Replay either zero or <code>(−3,4)</code><br>Ideal full-state observation semantics</td></tr></tbody></table>"
    )
    parts.append(
        "<p>When model data lacks source bounds, the native API requires named authored intervals; discrete domains, arrival timing, and the model-30 positive-part budget are also explicit admission limits. This one example does not claim that all catalogue task choices are supplied.</p></section>"
    )
    parts.append(
        '<p>Browse the <a href="native-discrete-models.html">native catalogue source data for all 35 models</a>.</p>'
    )
    parts.append("<section><h2>Reproduce the native check</h2>")
    parts.append(
        site_design.code_block(
            record["reproduction_command"], "Build and run the installed native MPC example"
        )
    )
    parts.append(
        f'<p><a href="{CSV}">Actual episode states and actions (CSV)</a> · <a href="{OUTPUT}">Native run summary</a> · <a href="{RECORD}">Source and task record (JSON)</a></p>'
    )
    parts.append(
        f'<p><a href="{CPP_SOURCE}">Native executable source</a> · <a href="{API_SOURCE}">Public discrete MPC API</a> · <a href="{SOURCE_URL}">Source commit {SOURCE}</a></p>'
    )
    parts.append(
        '<p>The <a href="nominal-quadratic-history-2d.html">running-state cost example</a> isolates how an interior-state term changes a history QP solution. This page exercises its native controller execution boundary with the catalogue model and explicit forecast/replay schedules.</p>'
    )
    parts.append("</section>")
    parts.append(site_design.page_end())
    return "".join(parts)


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    root = Path(repository_root)
    csv_bytes = _read(root, "examples/discrete_mpc_2d-output.csv")
    stdout_bytes = _read(root, "examples/discrete_mpc_2d-output.txt")
    report_data.require(
        hashlib.sha256(csv_bytes).hexdigest() == CSV_SHA256,
        "native discrete MPC capture differs from source-qualified output",
    )
    report_data.require(
        hashlib.sha256(stdout_bytes).hexdigest() == STDOUT_SHA256,
        "native discrete MPC stdout differs from source-qualified output",
    )
    report_data.require(
        stdout_bytes.decode("ascii")
        == (
            "Matched open-loop/MPC episodes agree; declared replay disturbance changes a later observed-state MPC action. "
            "first_action=0.000000 first_divergence_stage=4 open_loop_action=0.000000 mpc_action=1.050202 "
            "provider=csl.convex.highs@1.0.0+highs.1.11.0\n"
        ),
        "native discrete MPC summary differs from the checked episode",
    )
    capture = _parse_capture(csv_bytes)
    record = _record(capture, stdout_bytes)
    figure = _svg(capture)
    record_bytes = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    page = _page(record).encode("utf-8")
    outputs = {
        PAGE: page,
        FIGURE: figure,
        CSV: csv_bytes,
        OUTPUT: stdout_bytes,
        RECORD: record_bytes,
    }
    inventory = [
        {
            "family": "Nominal finite-horizon control",
            "title": "Observed-state MPC responds to the declared replay",
            "status": "educational-example",
            "anchor": "discrete-mpc-2d",
            "page": PAGE,
            "figure": FIGURE,
            "source_page": CPP_SOURCE,
            "raw_record": RECORD,
        }
    ]
    card = (
        '<article class="saved-figure" id="discrete-mpc-2d">'
        '<p class="eyebrow">Native C++ · nominal finite-horizon control</p>'
        f'<h3><a href="{PAGE}">Observed-state MPC responds to the declared replay</a></h3>'
        f'<a href="{PAGE}"><img src="{FIGURE}" alt="State paths and first-control traces for matched and replay-disturbed open-loop and observed-state MPC"></a>'
        "<p>One explicit two-state task compares a fixed open-loop plan with repeated state observations and suffix replans. Its CSV is the actual native episode output.</p>"
        f'<p><a href="{PAGE}">Read the derivation and reproduction steps →</a> · <a href="{RECORD}">Source/task record</a></p></article>'
    )
    return outputs, inventory, card
