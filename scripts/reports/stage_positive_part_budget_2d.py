"""Stage the exact 2D positive-part budget lesson and native check."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import report_data
import site_design

SOURCE = "6b1fd35f3afe72fc06207742b6ef2f890100caad"
ROUTE = "positive-part-budget-2d"
PAGE = ROUTE + ".html"
FIGURE = ROUTE + ".svg"
RECORD = ROUTE + ".json"
VERTICES = "positive_part_budget_2d_vertices.csv"
SOLUTION = "positive_part_budget_2d_native-solution.csv"
RUN = "positive_part_budget_2d_run.txt"
STDOUT = "positive_part_budget_2d_native-example.stdout"

CPP_SOURCE = f"https://github.com/butahlecoq/controlled-systems-lab/blob/{SOURCE}/examples/positive_part_budget_2d.cpp"
API_SOURCE = f"https://github.com/butahlecoq/controlled-systems-lab/blob/{SOURCE}/include/csl/optimization/nominal_quadratic_history.hpp"

EXPECTED_VERTICES = b"u0,u1\n-0.2,-0.2\n0.1,-0.2\n0.1,0\n0,0.1\n-0.2,0.1\n"


def _read(root: Path, relative: str) -> bytes:
    path = root
    report_data.require(not path.is_symlink(), "positive-part lesson root is symlinked")
    for part in Path(relative).parts:
        path /= part
        report_data.require(
            not path.is_symlink(), "positive-part lesson path is symlinked: " + relative
        )
    report_data.require(path.is_file(), "positive-part lesson asset is missing: " + relative)
    return path.read_bytes()


def _record(binary: str, stdout: bytes, solution: bytes, run: bytes) -> dict:
    return {
        "schema": "csl.educational-example.positive-part-budget-2d/1",
        "source_commit": SOURCE,
        "source_path": "examples/positive_part_budget_2d.cpp",
        "task": {
            "state_dimension": 1,
            "control_dimension": 2,
            "horizon_stages": 1,
            "state_equation": "x[1] = x[0], with x[0]=0",
            "control_bounds": [-0.2, 0.2],
            "authored_objective": "0.5*((u0-0.2)^2 + (u1+0.2)^2)",
            "positive_part_budget": "max(u0,0)+max(u1,0)<=0.1",
        },
        "answer": {
            "feasible_set_vertices": "(-0.2,-0.2), (0.1,-0.2), (0.1,0), (0,0.1), (-0.2,0.1)",
            "net_sum_surrogate_counterexample": "(0.2,-0.2) has net sum 0 but positive-part sum 0.2",
            "native_solution": "(0.1,-0.2)",
            "native_positive_part_sum": 0.1,
            "literal_objective": 0.005,
        },
        "epigraph": [
            "p0>=u0",
            "p0>=0",
            "p1>=u1",
            "p1>=0",
            "p0+p1<=0.1",
        ],
        "evidence": {
            "classification": "analytic feasible-set construction plus source-bound native HiGHS QP check",
            "vertices_provenance": "analytically derived from the control box and exact positive-part budget; not solver-generated",
            "native_solution_provenance": "captured from the example binary identified below",
            "native_example_binary_sha256": binary,
            "native_example_stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "native_example_stdout": stdout.decode("ascii").rstrip("\n"),
            "native_solution_sha256": hashlib.sha256(solution).hexdigest(),
            "run_record_sha256": hashlib.sha256(run).hexdigest(),
            "assurance": "numerical feasibility and objective check; no robustness or policy claim",
        },
    }


def _check_native_capture(solution: bytes, run: bytes, stdout: bytes) -> None:
    try:
        lines = solution.decode("ascii").splitlines()
        run_text = run.decode("ascii")
        stdout_text = stdout.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("positive-part native capture is not ASCII") from error
    report_data.require(
        lines[:1] == ["coordinate,target,solution,lower,upper"] and len(lines) == 4,
        "positive-part native solution table has the wrong shape",
    )
    rows = [[float(value) for value in line.split(",")[1:]] for line in lines[1:]]
    report_data.require(
        lines[1].startswith("u0,")
        and lines[2].startswith("u1,")
        and lines[3].startswith("positive_part_budget,"),
        "positive-part native solution table has unexpected row identities",
    )
    u0, u1 = rows[0][1], rows[1][1]
    positive_sum = max(u0, 0.0) + max(u1, 0.0)
    objective = 0.5 * ((u0 - 0.2) ** 2 + (u1 + 0.2) ** 2)
    report_data.require(
        all(
            math.isclose(actual, expected, abs_tol=1e-9)
            for row, expected in zip(
                rows,
                ((0.2, u0, -0.2, 0.2), (-0.2, u1, -0.2, 0.2), (0.1, positive_sum, 0.0, 0.1)),
                strict=True,
            )
            for actual, expected in zip(row, expected, strict=True)
        )
        and math.isclose(u0, 0.1, abs_tol=1e-7)
        and math.isclose(u1, -0.2, abs_tol=1e-7)
        and math.isclose(rows[2][1], positive_sum, abs_tol=1e-9)
        and positive_sum <= 0.1 + 1e-9
        and math.isclose(objective, 0.005, abs_tol=1e-7),
        "positive-part native solution does not satisfy its independently recomputed task",
    )
    match = re.fullmatch(
        r"Positive-part budget QP: u=\(([^,]+),([^)]*)\); "
        r"sum\(max\(u,0\)\)=([^;]+); literal objective=([^\n]+)\n",
        stdout_text,
    )
    if match is None:
        raise ValueError("positive-part native stdout has an unexpected format")
    printed = tuple(float(match.group(index)) for index in range(1, 5))
    report_data.require(
        all(
            math.isclose(actual, expected, abs_tol=1e-7)
            for actual, expected in zip(printed, (u0, u1, positive_sum, objective), strict=True)
        )
        and "source_constraint=sum(max(u_i,0))<=0.1" in run_text
        and "net_sum_surrogate_admits_target=true" in run_text,
        "positive-part run details and captured stdout disagree with the checked solution",
    )


def _page(record: dict) -> str:
    crumbs = (("Learn", "../index.html"), ("Examples", "index.html"), ("Positive-part budgets", ""))
    parts = [
        site_design.page_start(
            "Positive-part control budgets in a 2D QP",
            stylesheet_href="examples.css",
            crumbs=crumbs,
        )
    ]
    parts.extend(
        (
            '<p class="eyebrow">Nominal convex optimization · exact epigraph and native check</p>',
            "<h1>A positive-part budget cuts a pentagon</h1>",
            "<p>For one stage with two controls, keep the box <code>−0.2≤u₀,u₁≤0.2</code> and add "
            "the source-shaped constraint <code>max(u₀,0)+max(u₁,0)≤0.1</code>. A net-sum row "
            "<code>u₀+u₁≤0.1</code> is weaker: it admits <code>(0.2,−0.2)</code>, whose net sum "
            "is zero while its positive-part sum is <code>0.2</code>.</p>",
            f'<figure><img src="{FIGURE}" alt="The box control domain cut by the positive-part budget is a pentagon; the target (0.2,-0.2) is outside it and the native optimum (0.1,-0.2) lies on its slanted edge."><figcaption>The pentagon vertices are derived analytically from the box and budget. The dot is the checked HiGHS solution to the authored quadratic task.</figcaption></figure>',
            '<section><h2>Why the epigraph is exact</h2><div class="math-input">',
            "<p>Introduce witnesses <code>p₀,p₁</code> and require <code>pᵢ≥uᵢ</code>, "
            "<code>pᵢ≥0</code>, and <code>p₀+p₁≤0.1</code>. For any fixed controls, the smallest "
            "feasible witness is <code>pᵢ=max(uᵢ,0)</code>; therefore a control vector has a "
            "feasible witness exactly when it satisfies the original positive-part budget.</p></div>",
            "<p>The example minimizes <code>0.5((u₀−0.2)²+(u₁+0.2)²)</code>. Its target "
            "<code>(0.2,−0.2)</code> violates the budget, and the nearest feasible point is "
            "<code>(0.1,−0.2)</code>. At <code>u₁=−0.2</code>, the second coordinate uses no "
            "positive budget, so feasibility caps the first coordinate at <code>u₀=0.1</code>. "
            "The quadratic therefore keeps <code>u₁</code> at its target and moves <code>u₀</code> "
            "to that cap, giving objective <code>0.005</code>. The C++ example compiles "
            "the epigraph into the public nominal history QP API, solves it with HiGHS, checks the "
            "solver result, then independently recomputes the literal source constraint and cost.</p>",
            "<table><thead><tr><th>Control point</th><th>Net sum</th><th>Positive-part sum</th><th>Budget result</th></tr></thead><tbody>"
            "<tr><td>(0.2,−0.2), target</td><td>0</td><td>0.2</td><td>violates</td></tr>"
            "<tr><td>(0.1,−0.2), native optimum</td><td>−0.1</td><td>0.1</td><td>active</td></tr></tbody></table>",
            "</section><section><h2>Native output and reproduction</h2>",
            site_design.code_block(
                record["evidence"]["native_example_stdout"],
                "Captured output from the checked native example",
            ),
            f'<p><a href="{VERTICES}">Analytic polygon vertices (CSV)</a> · <a href="{SOLUTION}">Native solution (CSV)</a> · <a href="{RUN}">Run details</a> · <a href="{STDOUT}">Captured stdout</a> · <a href="{RECORD}">Inputs, derivation and provenance (JSON)</a></p>',
            f'<p>Source: <a href="{CPP_SOURCE}">native example</a> · <a href="{API_SOURCE}">public history-QP API</a> · <a href="https://github.com/butahlecoq/controlled-systems-lab/tree/{SOURCE}">source commit {SOURCE}</a>.</p>',
            '<p class="limits">This is an authored two-control illustration of the exact convex constraint. It is separate from the 30-control source model episode test; it does not redefine that source model or claim a general policy guarantee.</p>',
            "</section>",
            site_design.page_end(),
        )
    )
    return "".join(parts)


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    root = Path(repository_root)
    vertices = _read(root, "examples/positive_part_budget_2d/vertices.csv")
    solution = _read(root, "examples/positive_part_budget_2d/native-solution.csv")
    run = _read(root, "examples/positive_part_budget_2d/run.txt")
    stdout = _read(root, "examples/positive_part_budget_2d/native-example.stdout")
    binary = _read(root, "examples/positive_part_budget_2d/binary.sha256").decode("ascii").strip()
    report_data.require(vertices == EXPECTED_VERTICES, "positive-part analytic vertices changed")
    report_data.require(
        len(binary) == 64 and all(c in "0123456789abcdef" for c in binary),
        "invalid native binary hash",
    )
    _check_native_capture(solution, run, stdout)
    record = _record(binary, stdout, solution, run)
    files = {
        PAGE: _page(record).encode("utf-8"),
        FIGURE: _read(root, "examples/positive_part_budget_2d/feasible-set.svg"),
        RECORD: (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
        VERTICES: vertices,
        SOLUTION: solution,
        RUN: run,
        STDOUT: stdout,
    }
    inventory = [
        {
            "family": "Nominal optimization · convex stage constraints",
            "title": "A positive-part budget cuts a pentagon",
            "status": "saved-data-illustration",
            "anchor": ROUTE,
            "page": PAGE,
            "figure": FIGURE,
            "source_page": CPP_SOURCE,
            "raw_record": RECORD,
        }
    ]
    card = (
        f'<article class="saved-figure" id="{ROUTE}"><p class="eyebrow">Nominal optimization · exact convex budget</p>'
        f'<h3><a href="{PAGE}">A positive-part budget cuts a pentagon</a></h3>'
        f'<a href="{PAGE}"><img src="{FIGURE}" alt="Pentagonal feasible set for a two-control positive-part budget, with the checked optimum marked"></a>'
        "<p>An exact epigraph reformulation, an independently checked native HiGHS optimum, and an explicit counterexample to the net-sum surrogate.</p>"
        f'<p><a href="{PAGE}">Read the derivation and native evidence →</a> · <a href="{RECORD}">Inputs and provenance</a></p></article>'
    )
    return files, inventory, card
