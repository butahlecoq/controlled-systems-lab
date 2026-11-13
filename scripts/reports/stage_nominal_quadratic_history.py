"""Stage the analytic 2D running-state cost lesson and its source check."""

from __future__ import annotations

import hashlib
import json
from html import escape
from pathlib import Path

import report_data
import site_design

SOURCE = "c16a19dd900bc5e186273008f610a712dc177981"
SOURCE_URL = "https://github.com/butahlecoq/controlled-systems-lab/tree/" + SOURCE
CPP_SOURCE = (
    "https://github.com/butahlecoq/controlled-systems-lab/blob/"
    + SOURCE
    + "/examples/nominal_quadratic_history_2d.cpp"
)
API_SOURCE = (
    "https://github.com/butahlecoq/controlled-systems-lab/blob/"
    + SOURCE
    + "/include/csl/optimization/nominal_quadratic_history.hpp"
)
CPP_BINARY_SHA256 = "0b4ef226ecb460e435769589facbdcdad38be88e873d18ad9bd6980811acb98b"
PAGE = "nominal-quadratic-history-2d.html"
FIGURE = "nominal-quadratic-history-2d.svg"
CSV = "nominal_quadratic_history_2d.csv"
OUTPUT = "nominal_quadratic_history_2d-output.txt"
RECORD = "nominal-quadratic-history-2d.json"
REPRODUCTION_COMMAND = "\n".join(
    (
        "cmake --preset highs",
        "cmake --build --preset highs",
        "cmake --install build/highs --prefix build/highs/install",
        "cmake -S examples -B build/examples -DCMAKE_PREFIX_PATH=build/highs/install",
        "cmake --build build/examples --target nominal_quadratic_history_2d",
        "./build/examples/nominal_quadratic_history_2d",
    )
)

EXPECTED_CSV = (
    b"case,first_control,stage1_x,stage1_y\n"
    b"control_only,0.000000,0.000000,0.000000\n"
    b"interior_state_quadratic,0.454545,0.454545,0.454545\n"
)
EXPECTED_OUTPUT = (
    "Interior-state penalty changes first control from 0.000000 to 0.454545; "
    "baseline_x1=(0.000000,0.000000); tracking_x1=(0.454545,0.454545)\n"
).encode("ascii")


def _read(root: Path, relative: str) -> bytes:
    path = root
    report_data.require(not path.is_symlink(), "nominal history lesson root is symlinked")
    for part in Path(relative).parts:
        path /= part
        report_data.require(
            not path.is_symlink(), "nominal history lesson path is symlinked: " + relative
        )
    report_data.require(
        path.is_file(), "nominal history lesson asset is missing or symlinked: " + relative
    )
    return path.read_bytes()


def _record() -> dict:
    return {
        "schema": "csl.educational-example.nominal-quadratic-history-2d/1",
        "source_commit": SOURCE,
        "source_path": "examples/nominal_quadratic_history_2d.cpp",
        "illustration_only": True,
        "inputs": {
            "state_dimension": 2,
            "control_dimension": 1,
            "horizon_stages": 2,
            "initial_state": [0, 0],
            "dynamics": "x[k+1] = u[k](1,1)",
            "control_bounds": [-1, 1],
            "input_cost_each_stage": "0.2 u[k]^2",
            "running_state_cost_at_stage_1": "||x[1]-(1,0)||^2",
            "terminal_cost": 0,
        },
        "answer": {
            "reachable_stage_1_states": "x[1]=(u[0],u[0])",
            "control_only_first_control": "0",
            "interior_state_cost_first_control": "5/11",
            "interior_state_cost_state": "(5/11,5/11)",
            "derivation": "(u-1)^2+u^2+0.2u^2 has derivative 4.4u-2, so u=5/11",
        },
        "reproduction_command": REPRODUCTION_COMMAND,
        "evidence": {
            "classification": "analytic illustration plus a source-bound native example check",
            "svg_provenance": "hand-authored diagram of the exact reachable line and analytic points; not solver-generated",
            "csv_provenance": "six-decimal table transcribed from the native example stdout; not raw solver response data",
            "native_example_binary_sha256": CPP_BINARY_SHA256,
            "native_example_stdout": EXPECTED_OUTPUT.decode("ascii").rstrip("\n"),
            "native_check": "the example checks the two numerical optima and their compiled-program residuals; its interior-state control must be within 1e-7 of 5/11",
            "captured_stdout_sha256": hashlib.sha256(EXPECTED_OUTPUT).hexdigest(),
        },
    }


def _page(record: dict) -> str:
    crumbs = (
        ("Learn", "../index.html"),
        ("Examples", "index.html"),
        ("Interior-state quadratic cost", ""),
    )
    parts = [
        site_design.page_start(
            "Interior-state quadratic cost in a 2D history QP",
            stylesheet_href="examples.css",
            crumbs=crumbs,
        )
    ]
    parts.append(
        '<p class="eyebrow">Nominal optimization · analytic illustration with native source check</p>'
    )
    parts.append("<h1>Why an interior-state cost changes the first control</h1>")
    parts.append(
        "<p>Consider a two-state system with one scalar control over two stages. From "
        "<code>x₀=(0,0)</code>, the dynamics are <code>x[k+1]=u[k](1,1)</code> and "
        "<code>u[k]∈[−1,1]</code>. Each stage has input cost <code>0.2u[k]²</code>. "
        "The terminal cost is zero.</p>"
    )
    parts.append(
        f'<figure><img src="{FIGURE}" alt="{escape("The reachable stage-one states form x one equals y one. The control-only optimum is (0,0); adding an interior quadratic penalty toward (1,0) selects (5/11,5/11).", quote=True)}">'
        "<figcaption>The dashed diagonal is the full reachable set at stage one. The target "
        "<code>(1,0)</code> is off that line. The diagram uses exact analytic points and is "
        "not a plot generated by the solver.</figcaption></figure>"
    )
    parts.append(
        '<section><h2>Derive the answer</h2><div class="math-input">'
        "<p>At the interior stage, <code>x₁=(u₀,u₀)</code>. Add the stage-one tracking "
        "term <code>‖x₁−(1,0)‖²</code>. The part of the total objective that depends on "
        "<code>u₀</code> is</p><p><strong><code>(u₀−1)² + u₀² + 0.2u₀²</code></strong>.</p>"
        "<p>Its derivative is <code>4.4u₀−2</code>, so <code>u₀=5/11</code>. The "
        "corresponding reachable state is <code>x₁=(5/11,5/11)</code>. Without the "
        "state term, the input penalty is minimized at <code>u₀=0</code>.</p></div>"
        "<p>The SVG and CSV are explanatory derivatives of the exact calculation and "
        "the source example output. The native C++ example separately solves both "
        "compiled QPs with HiGHS and checks that the state-cost solution is within "
        "<code>1e−7</code> of <code>5/11</code>, with feasible program residuals.</p>"
    )
    parts.append(
        "<table><thead><tr><th>Task-authored cost</th><th>First control</th><th>Interior state</th></tr></thead>"
        "<tbody><tr><td>Input penalty only</td><td>0</td><td>(0,0)</td></tr>"
        "<tr><td>Input and stage-one state penalty</td><td>5/11 ≈ 0.454545</td>"
        "<td>(5/11,5/11) ≈ (0.454545,0.454545)</td></tr></tbody></table>"
    )
    parts.append("</section><section><h2>Reproduce the native check</h2>")
    parts.append(
        site_design.code_block(
            record["reproduction_command"], "Rebuild and run the native 2D history example"
        )
    )
    parts.append(
        f'<p><a href="{CSV}">Rounded output table (CSV)</a> · '
        f'<a href="{OUTPUT}">Captured native example stdout</a> · '
        f'<a href="{RECORD}">Analytic inputs, answer and evidence classification (JSON)</a></p>'
    )
    parts.append(
        '<p>The previous <a href="history-cost-2d-v1/index.html">full-history cost lesson</a> '
        "uses a different objective fixture and compiler path; its frozen page and records "
        "remain unchanged.</p>"
    )
    parts.append("</section><section><h2>Source</h2><ul>")
    parts.append(
        f'<li>Compiler and example source: <a href="{CPP_SOURCE}">2D native example at {SOURCE[:8]}</a>.</li>'
    )
    parts.append(
        f'<li>Reusable API: <a href="{API_SOURCE}">public nominal history compiler header</a>.</li>'
    )
    parts.append(f'<li>Source tree: <a href="{SOURCE_URL}">{SOURCE}</a>.</li>')
    parts.append(
        '</ul><p class="limits">This is a nominal discrete convex QP example. It is not a physical calibration, benchmark, or claim about all 35 catalogue models.</p></section>'
    )
    parts.append(site_design.page_end())
    return "".join(parts)


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    root = Path(repository_root)
    figure = _read(root, "examples/nominal_quadratic_history_2d.svg")
    csv = _read(root, "examples/nominal_quadratic_history_2d.csv")
    stdout = _read(root, "examples/nominal_quadratic_history_2d-output.txt")
    report_data.require(csv == EXPECTED_CSV, "nominal history rounded output table changed")
    report_data.require(stdout == EXPECTED_OUTPUT, "nominal history native example stdout changed")
    record = _record()
    record_bytes = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    page = _page(record).encode("utf-8")
    outputs = {PAGE: page, FIGURE: figure, CSV: csv, OUTPUT: stdout, RECORD: record_bytes}
    inventory = [
        {
            "family": "Nominal optimization · running-state costs",
            "title": "Interior-state cost changes the first control",
            "status": "analytic-illustration",
            "anchor": "nominal-quadratic-history-2d",
            "page": PAGE,
            "figure": FIGURE,
            "source_page": CPP_SOURCE,
            "raw_record": RECORD,
        }
    ]
    card = (
        '<article class="saved-figure" id="nominal-quadratic-history-2d">'
        '<p class="eyebrow">Nominal optimization · running-state cost</p>'
        f'<h3><a href="{PAGE}">Interior-state cost changes the first control</a></h3>'
        f'<a href="{PAGE}"><img src="{FIGURE}" alt="Reachable stage-one states lie on x one equals y one; adding a state cost moves the selected state from the origin to (5/11,5/11)."></a>'
        "<p>A two-state, one-control, two-stage quadratic task. The exact derivation is "
        "paired with a source-bound native HiGHS example check; the plotted figure is analytic.</p>"
        f'<p><a href="{PAGE}">Read the mathematical example →</a> · '
        f'<a href="{RECORD}">Inputs and evidence classification</a></p></article>'
    )
    return outputs, inventory, card
