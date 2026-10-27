"""Capture and render a source-bound layered 4D fuel reachability example.

Capture computes set geometry. Render reads the saved geometry only.
"""
from __future__ import annotations

import argparse
from itertools import combinations, product
import hashlib
import html
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = ROOT / "docs/examples/fuel-reachability-layers-model.json"
DEFAULT_RECORD = ROOT / "reports/algorithm-results/fuel-reachability-layers-v1/plot-data.json"
DEFAULT_OUTPUT = ROOT / "docs/examples/fuel-reachability-layers"
PAIRS = (("x1", "x2"), ("x3", "x4"), ("x1", "x3"), ("x2", "x4"))
TOL = 1e-8


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _unique(rows: list[np.ndarray]) -> list[np.ndarray]:
    result: list[np.ndarray] = []
    for row in rows:
        if not any(np.allclose(row, prior, rtol=0, atol=TOL) for prior in result):
            result.append(row)
    return result


def _vertices(inequalities: list[tuple[np.ndarray, float]], dimension: int) -> list[np.ndarray]:
    """Enumerate vertices of a small full-dimensional control-space polytope."""
    if dimension == 0:
        if all(0.0 <= bound + TOL for _, bound in inequalities):
            return [np.empty(0)]
        return []
    rows = [np.asarray(row, dtype=float) for row, _ in inequalities]
    bounds = [float(bound) for _, bound in inequalities]
    points: list[np.ndarray] = []
    for selected in combinations(range(len(rows)), dimension):
        matrix = np.vstack([rows[index] for index in selected])
        if np.linalg.matrix_rank(matrix, tol=TOL) != dimension:
            continue
        candidate = np.linalg.solve(matrix, np.asarray([bounds[index] for index in selected]))
        if all(float(np.dot(row, candidate)) <= bound + TOL
               for row, bound in zip(rows, bounds, strict=True)):
            points.append(candidate)
    return _unique(points)


def _state_affine_forward(model: dict, stage: int) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.asarray(model["A"], dtype=float)
    control = np.asarray(model["B"], dtype=float)
    initial = np.asarray(model["initial_state"], dtype=float)
    dimension = len(initial)
    coefficients = np.zeros((dimension, stage))
    for index in range(stage):
        coefficients[:, index] = np.linalg.matrix_power(matrix, stage - 1 - index) @ control
    return np.linalg.matrix_power(matrix, stage) @ initial, coefficients


def _state_affine_backward(model: dict, stage: int, terminal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.asarray(model["A"], dtype=float)
    control = np.asarray(model["B"], dtype=float)
    inverse = np.linalg.inv(matrix)
    future_count = model["horizon"] - stage
    coefficients = np.zeros((len(terminal), future_count))
    for index in range(future_count):
        coefficients[:, index] = -np.linalg.matrix_power(inverse, index + 1) @ control
    return np.linalg.matrix_power(inverse, future_count) @ terminal, coefficients


def _control_box(dimension: int, bounds: list[float]) -> list[tuple[np.ndarray, float]]:
    lower, upper = map(float, bounds)
    result = []
    for index in range(dimension):
        row = np.zeros(dimension); row[index] = 1.0
        result.extend(((row.copy(), upper), (-row.copy(), -lower)))
    return result


def _state_bound_inequalities(model: dict, affine: tuple[np.ndarray, np.ndarray],
                              dimension: int, offset: int = 0) -> list[tuple[np.ndarray, float]]:
    center, local_coefficients = affine
    coefficients = np.zeros((len(center), dimension))
    coefficients[:, offset:offset + local_coefficients.shape[1]] = local_coefficients
    result: list[tuple[np.ndarray, float]] = []
    for state_id, coordinate in (("x1", 0), ("x3", 2)):
        lower, upper = map(float, model["state_bounds"][state_id])
        row = coefficients[coordinate]
        result.extend(((row.copy(), upper - center[coordinate]),
                       (-row.copy(), center[coordinate] - lower)))
    return result


def _objective(state: np.ndarray) -> float:
    x1, x2, x3, x4 = map(float, state)
    return (30.0 - x1) ** 2 + x2**2 + (20.0 - x3) ** 2 + x4**2 + (x2 - x4) ** 2


def _optimal_controls(model: dict) -> tuple[np.ndarray, np.ndarray, float]:
    center, coefficients = _state_affine_forward(model, model["horizon"])
    q = np.array([[1, 0, 0, 0], [0, 2, 0, -1], [0, 0, 1, 0], [0, -1, 0, 2]], dtype=float)
    linear = np.array([-30.0, 0.0, -20.0, 0.0])
    hessian = coefficients.T @ q @ coefficients
    gradient_center = coefficients.T @ (q @ center + linear)
    lo, hi = map(float, model["control_bounds"])
    best: tuple[float, np.ndarray, np.ndarray] | None = None
    for statuses in product((-1, 0, 1), repeat=coefficients.shape[1]):
        fixed = np.asarray([index for index, value in enumerate(statuses) if value != 0], dtype=int)
        free = np.asarray([index for index, value in enumerate(statuses) if value == 0], dtype=int)
        controls = np.zeros(coefficients.shape[1])
        for index in fixed:
            controls[index] = lo if statuses[index] == -1 else hi
        if len(free):
            rhs = -gradient_center[free]
            if len(fixed):
                rhs -= hessian[np.ix_(free, fixed)] @ controls[fixed]
            controls[free] = np.linalg.solve(hessian[np.ix_(free, free)], rhs)
        if np.any(controls < lo - TOL) or np.any(controls > hi + TOL):
            continue
        states = [np.asarray(model["initial_state"], dtype=float)]
        for value in controls:
            states.append(np.asarray(model["A"], dtype=float) @ states[-1] +
                          np.asarray(model["B"], dtype=float) * value)
        if any(not _in_state_bounds(model, state) for state in states):
            continue
        terminal = states[-1]
        score = _objective(terminal)
        if best is None or score < best[0] - TOL:
            best = score, controls, terminal
    if best is None:
        raise ValueError("no feasible terminal-objective minimizer found")
    return best[1], best[2], best[0]


def _in_state_bounds(model: dict, state: np.ndarray) -> bool:
    for coordinate, state_id in ((0, "x1"), (2, "x3")):
        lower, upper = map(float, model["state_bounds"][state_id])
        if state[coordinate] < lower - TOL or state[coordinate] > upper + TOL:
            return False
    return True


def _hull(points: list[list[float]]) -> list[list[float]]:
    rows = sorted(set((float(point[0]), float(point[1])) for point in points))
    if len(rows) <= 2:
        return [list(point) for point in rows]

    def cross(origin, first, second):
        return ((first[0] - origin[0]) * (second[1] - origin[1]) -
                (first[1] - origin[1]) * (second[0] - origin[0]))

    lower: list[tuple[float, float]] = []
    for point in rows:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= TOL:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(rows):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= TOL:
            upper.pop()
        upper.append(point)
    return [list(point) for point in lower[:-1] + upper[:-1]]


def _set_vertices(model: dict, stage: int, direction: str, terminal: np.ndarray | None = None) -> list[list[float]]:
    if direction == "forward":
        affine = _state_affine_forward(model, stage)
        inequalities = _control_box(stage, model["control_bounds"])
        for constrained_stage in range(1, stage + 1):
            local = _state_affine_forward(model, constrained_stage)
            inequalities.extend(_state_bound_inequalities(model, local, stage))
    else:
        assert terminal is not None
        affine = _state_affine_backward(model, stage, terminal)
        future_count = model["horizon"] - stage
        inequalities = _control_box(future_count, model["control_bounds"])
        for constrained_stage in range(stage, model["horizon"]):
            local = _state_affine_backward(model, constrained_stage, terminal)
            inequalities.extend(_state_bound_inequalities(
                model, local, future_count, constrained_stage - stage))
    controls = _vertices(inequalities, affine[1].shape[1])
    states = [affine[0] + affine[1] @ control for control in controls]
    if not states:
        raise ValueError(f"{direction} set at R{stage} has no vertices")
    return [list(map(float, state)) for state in _unique(states)]


def _intersection_vertices(model: dict, stage: int, terminal: np.ndarray) -> list[list[float]]:
    """Compute Rk ∩ Gk in full state space through shared control variables."""
    horizon = model["horizon"]
    forward = _state_affine_forward(model, stage)
    backward = _state_affine_backward(model, stage, terminal)
    equality = np.zeros((len(terminal), horizon))
    equality[:, :stage] = forward[1]
    equality[:, stage:] = -backward[1]
    right_hand_side = backward[0] - forward[0]
    particular, *_ = np.linalg.lstsq(equality, right_hand_side, rcond=None)
    if not np.allclose(equality @ particular, right_hand_side, rtol=0, atol=TOL):
        return []
    _, singular_values, right_vectors = np.linalg.svd(equality, full_matrices=True)
    rank = int(np.sum(singular_values > TOL))
    nullspace = right_vectors[rank:].T

    inequalities = _control_box(horizon, model["control_bounds"])
    for constrained_stage in range(1, stage + 1):
        local = _state_affine_forward(model, constrained_stage)
        inequalities.extend(_state_bound_inequalities(model, local, horizon))
    for constrained_stage in range(stage, horizon):
        local = _state_affine_backward(model, constrained_stage, terminal)
        inequalities.extend(_state_bound_inequalities(model, local, horizon, constrained_stage))

    reduced = [(nullspace.T @ row, bound - float(np.dot(row, particular))
                ) for row, bound in inequalities]
    free_controls = _vertices(reduced, nullspace.shape[1])
    states = []
    for free in free_controls:
        all_controls = particular + nullspace @ free
        from_forward = forward[0] + forward[1] @ all_controls[:stage]
        from_backward = backward[0] + backward[1] @ all_controls[stage:]
        if np.allclose(from_forward, from_backward, rtol=0, atol=TOL):
            states.append(from_forward)
    return [list(map(float, state)) for state in _unique(states)]


def capture(model_path: Path, output_path: Path) -> dict:
    model = json.loads(model_path.read_text(encoding="utf-8"))
    source_path = ROOT / model["source"]
    source_available = source_path.is_file()
    source_hash = _sha256(source_path) if source_available else model["source_sha256"]
    if source_available and source_hash != model["source_sha256"]:
        raise ValueError(f"source hash mismatch for {source_path}")
    controls, terminal, score = _optimal_controls(model)
    states = [np.asarray(model["initial_state"], dtype=float)]
    for value in controls:
        states.append(np.asarray(model["A"], dtype=float) @ states[-1] +
                      np.asarray(model["B"], dtype=float) * value)
    if not np.allclose(states[-1], terminal, rtol=0, atol=TOL):
        raise ValueError("optimal trajectory does not reach its saved terminal point")

    stages = []
    for stage in range(model["horizon"] + 1):
        forward = _set_vertices(model, stage, "forward")
        backward = _set_vertices(model, stage, "backward", terminal)
        intersection = _intersection_vertices(model, stage, terminal)
        if not intersection:
            raise ValueError(f"forward/backward intersection is empty at R{stage}")
        point = list(map(float, states[stage]))
        if not _contains_projected_state(model, stage, states[stage], controls):
            raise ValueError(f"trajectory state at R{stage} is outside a forward/backward set")
        projections = {}
        for first, second in model["coordinate_pairs"]:
            i, j = model["state_order"].index(first), model["state_order"].index(second)
            projections[f"{first}-{second}"] = {
                "forward": _hull([[row[i], row[j]] for row in forward]),
                "backward": _hull([[row[i], row[j]] for row in backward]),
                "intersection": _hull([[row[i], row[j]] for row in intersection]),
                "trajectory": [point[i], point[j]],
            }
        stages.append({"stage": stage, "forward_vertices": forward,
                       "backward_vertices": backward, "intersection_vertices": intersection,
                       "projections": projections})
    record = {
        "schema": "csl.fuel-reachability-layers/1",
        "assurance": "numerical",
        "source": {"path": model["source"], "sha256": source_hash,
                   "source_file_available_in_checkout": source_available,
                   "model_sha256": _sha256(model_path), "script_sha256": _sha256(Path(__file__))},
        "semantics": {
            "forward": "Rk: all states reachable from the singleton initial state in k steps under the continuous control interval and state constraints",
            "backward": "Gk: all states from which some admissible control sequence reaches the selected optimal terminal state, with state constraints enforced at each stage",
            "intersection": "Rk intersect Gk in full four-dimensional state space, computed by solving the shared prefix/suffix control equations; the set may contain multiple states",
            "trajectory": "one minimizing open-loop trajectory; not the full optimal family",
            "disturbance": "none; deterministic model",
            "historical_claim": False,
        },
        "model": model,
        "optimal": {"controls": list(map(float, controls)), "terminal_state": list(map(float, terminal)),
                    "objective": score, "controllability_rank": int(np.linalg.matrix_rank(
                        _state_affine_forward(model, model["horizon"])[1], tol=TOL))},
        "stages": stages,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def _contains_projected_state(model: dict, stage: int, state: np.ndarray,
                              controls: np.ndarray) -> bool:
    forward = _state_affine_forward(model, stage)
    forward_state = forward[0] + forward[1] @ controls[:stage]
    trajectory = [np.asarray(model["initial_state"], dtype=float)]
    for value in controls:
        trajectory.append(np.asarray(model["A"], dtype=float) @ trajectory[-1] +
                          np.asarray(model["B"], dtype=float) * value)
    backward_state, backward_map = _state_affine_backward(model, stage, trajectory[-1])
    backward_state = backward_state + backward_map @ controls[stage:]
    lower, upper = map(float, model["control_bounds"])
    return (np.allclose(forward_state, state, rtol=0, atol=TOL) and
            np.allclose(backward_state, state, rtol=0, atol=TOL) and
            np.all(controls >= lower - TOL) and np.all(controls <= upper + TOL) and
            _in_state_bounds(model, state))


def _draw_shape(axis, points: list[list[float]], color: str, *, linestyle: str,
                alpha: float, label: str | None = None, edgecolor: str | None = None,
                zorder: int = 2):
    if not points:
        return
    values = np.asarray(points, dtype=float)
    edgecolor = edgecolor or color
    if len(values) == 1:
        axis.scatter(values[:, 0], values[:, 1], color=color, edgecolors=edgecolor,
                     s=42, marker="o", label=label, zorder=zorder)
    elif len(values) == 2:
        axis.plot(values[:, 0], values[:, 1], color=edgecolor, linestyle=linestyle,
                  linewidth=2.8, alpha=alpha, label=label, zorder=zorder)
    else:
        closed = np.vstack((values, values[0]))
        axis.fill(closed[:, 0], closed[:, 1], color=color, edgecolor=edgecolor, alpha=alpha * .18,
                  linewidth=0, label=label if label else None, zorder=zorder)
        axis.plot(closed[:, 0], closed[:, 1], color=edgecolor, linestyle=linestyle,
                  linewidth=2.2, alpha=alpha, zorder=zorder + 1)


def render(record_path: Path, output_dir: Path) -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from shutil import copyfile

    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("schema") != "csl.fuel-reachability-layers/1":
        raise ValueError("unsupported saved fuel reachability schema")
    if output_dir.exists():
        allowed = {"index.html", "plot-data.json", "fuel-reachability-layers-model.json",
                   "fuel-reachability-layers.svg", "fuel-reachability-layers.png"}
        for pair in PAIRS:
            allowed.update((f"fuel-reachability-{pair[0]}-{pair[1]}.svg",
                            f"fuel-reachability-{pair[0]}-{pair[1]}.png"))
        unexpected = {item.name for item in output_dir.iterdir()} - allowed
        if not output_dir.is_dir() or unexpected:
            raise FileExistsError(f"output directory contains unrelated files: {output_dir}")
    else:
        output_dir.mkdir(parents=True)
    model = record["model"]
    states = model["state_order"]
    labels = {item: f"{item} {model['state_names'][i]} ({model['state_units'][i]})"
              for i, item in enumerate(states)}
    colors = ("#2f6bff", "#38a169", "#e07a2d", "#9b51e0")
    output_dir = output_dir.resolve()
    figure_files: list[Path] = []
    primary_cards = []
    supplementary_cards = []
    pair_titles = {
        "x1-x2": "Oxidizer projection · flow x₁ vs stock balance x₂",
        "x3-x4": "Fuel projection · flow x₃ vs stock balance x₄",
        "x1-x3": "Supplementary projection · oxidizer vs fuel flow",
        "x2-x4": "Supplementary projection · oxidizer vs fuel stock balance",
    }
    for pair in model["coordinate_pairs"]:
        figure, axis = plt.subplots(figsize=(9, 7))
        key = "-".join(pair)
        figure.suptitle(f"{pair_titles[key]}\n"
                        "Forward/backward sets, intersections and a minimizing path",
                        fontsize=15, weight="bold")
        for stage_data in record["stages"]:
            stage = stage_data["stage"]
            color = colors[stage]
            projection = stage_data["projections"][key]
            _draw_shape(axis, projection["forward"], color, linestyle="-", alpha=.85,
                        label=f"R{stage} forward")
            _draw_shape(axis, projection["backward"], color, linestyle="--", alpha=.9,
                        label=f"G{stage} backward")
        path = np.asarray([stage["projections"][key]["trajectory"] for stage in record["stages"]])
        axis.plot(path[:, 0], path[:, 1], color="#171717", linewidth=2.3, marker="o",
                  markersize=5, zorder=8, label="Selected minimizing trajectory")
        axis.scatter([path[0, 0], path[-1, 0]], [path[0, 1], path[-1, 1]],
                     color="#171717", marker="*", s=100, zorder=9)
        axis.annotate("R0 initial", path[0], xytext=(7, 9), textcoords="offset points",
                      fontsize=9, color="#111111", weight="bold")
        axis.annotate("RT final", path[-1], xytext=(7, -17), textcoords="offset points",
                      fontsize=9, color="#111111", weight="bold")
        target = model["target"]
        target_point = [target[states.index(pair[0])], target[states.index(pair[1])]]
        axis.scatter([target_point[0]], [target_point[1]], marker="X", s=80,
                     color="#c72e45", edgecolors="white", linewidths=.7,
                     zorder=10, label="Objective target")
        for i, point in enumerate(path[:-1]):
            if i + 1 < len(path):
                axis.annotate("", xy=path[i + 1], xytext=point,
                              arrowprops={"arrowstyle": "->", "color": "#171717", "lw": 1.5})
        for stage_data in record["stages"]:
            _draw_shape(axis, stage_data["projections"][key]["intersection"], "#f3d547",
                        linestyle="-", alpha=1.0, edgecolor="#171717", zorder=10,
                        label="Full-state intersection Rk ∩ Gk"
                        if stage_data["stage"] == 0 else None)
        axis.set_title(f"Projection ({pair[0]}, {pair[1]})", weight="bold")
        axis.set_xlabel(labels[pair[0]])
        axis.set_ylabel(labels[pair[1]])
        axis.grid(True, color="#b6c3d1", alpha=.45)
        if model["state_units"][states.index(pair[0])] == model["state_units"][states.index(pair[1])]:
            axis.set_aspect("equal", adjustable="datalim")
        axis.margins(.16)
        stage_handles = [Patch(facecolor=colors[i], edgecolor="#222", label=f"Stage R{i}/G{i}")
                         for i in range(model["horizon"] + 1)]
        shape_handles = [
            Line2D([0], [0], color="#333", lw=2, label="Forward set · solid"),
            Line2D([0], [0], color="#333", lw=2, ls="--", label="Backward set · dashed"),
            Patch(facecolor="#f3d547", edgecolor="#171717", alpha=.8,
                  label="Full-state intersection Rk ∩ Gk"),
            Line2D([0], [0], color="#171717", lw=2, marker="*",
                   label="Selected minimizing trajectory"),
            Line2D([0], [0], color="#c72e45", lw=0, marker="X", markersize=8,
                   label="Objective target"),
        ]
        figure.legend(handles=stage_handles + shape_handles, loc="lower center",
                      bbox_to_anchor=(.5, .015), ncol=4, frameon=False, fontsize=8)
        figure.tight_layout(rect=(0, .13, 1, .9))
        stem = f"fuel-reachability-{pair[0]}-{pair[1]}"
        svg, png = output_dir / f"{stem}.svg", output_dir / f"{stem}.png"
        figure.savefig(svg, metadata={"Date": None, "Creator": "CSL fuel reachability layers"})
        figure.savefig(png, dpi=180, metadata={"Software": "CSL fuel reachability layers"})
        plt.close(figure)
        figure_files.extend((svg, png))
        card = f'''<section><h2>{html.escape(pair_titles[key])}</h2><figure><a href="{svg.name}"><img src="{png.name}" alt="Forward and backward fuel reachable sets at every stage, full-state intersections, and one selected minimizing trajectory projected onto {pair[0]} and {pair[1]}"></a><figcaption><a href="{svg.name}">SVG</a> · <a href="{png.name}" download>PNG</a></figcaption></figure></section>'''
        (primary_cards if key in {"x1-x2", "x3-x4"} else supplementary_cards).append(card)
    html_path = output_dir / "index.html"
    html_path.write_text(f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fuel reachability layers</title><style>body{{max-width:1100px;margin:2rem auto;padding:0 1rem;font:16px/1.55 system-ui;color:#18212b}}img{{width:100%;height:auto}}section{{border-top:1px solid #ccd3db;padding:1rem 0;break-inside:avoid}}.note{{padding:1rem;background:#f2f5f8;border-left:4px solid #2f6bff}}a{{color:#174ea6}}@media print{{img{{max-height:8.5in;object-fit:contain}}}}</style><main><h1>Forward and backward fuel reachable sets</h1><p class="note">The main plots are the oxidizer flow/stock projection (x₁,x₂) and fuel flow/stock projection (x₃,x₄). Two cross-coordinate projections follow as supplementary views. The figures use deterministic linear model parameters transcribed from local source <code>papers/Minimax/Constrained/ReachableSets.m</code> (SHA-256 recorded in the model and geometry records); the source file is not redistributed. Each 2D plot shows stage-labelled forward sets R0…RT, backward sets G0…GT leading to the selected minimizing terminal point, their full-state intersections, and one selected minimizing open-loop trajectory. Intersections are computed in full 4D before projection. Degenerate projections remain points or line segments; no artificial area is added. This is not the B06/L09 minimax run, a historical figure reproduction, or a claim about disturbance-robust or complete optimal families.</p><p>Selected controls: {html.escape(', '.join(f'{value:.6g}' for value in record['optimal']['controls']))}. Terminal objective: {record['optimal']['objective']:.9g}. <a href="plot-data.json" download>Saved geometry and provenance</a> · <a href="fuel-reachability-layers-model.json" download>Model input</a>.</p><h2>Oxidizer and fuel state projections</h2>{''.join(primary_cards)}<h2>Supplementary cross-coordinate projections</h2>{''.join(supplementary_cards)}</main></html>''', encoding="utf-8")
    saved_data = output_dir / "plot-data.json"
    saved_data.write_text(record_path.read_text(encoding="utf-8"), encoding="utf-8")
    model_copy = output_dir / "fuel-reachability-layers-model.json"
    copyfile(ROOT / "docs/examples/fuel-reachability-layers-model.json", model_copy)
    return [*figure_files, html_path]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture_parser = subparsers.add_parser("capture", help="compute and save stage geometry")
    capture_parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    capture_parser.add_argument("--out", type=Path, default=DEFAULT_RECORD)
    render_parser = subparsers.add_parser("render", help="render a saved geometry record only")
    render_parser.add_argument("--input", type=Path, default=DEFAULT_RECORD)
    render_parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "capture":
            record = capture(arguments.model, arguments.out)
            print(f"saved geometry: {arguments.out.resolve()}")
            print(f"terminal objective: {record['optimal']['objective']:.12g}")
            print(f"optimal controls: {record['optimal']['controls']}")
        else:
            outputs = render(arguments.input, arguments.out_dir)
            for output in outputs:
                print(output.resolve())
        return 0
    except (OSError, ValueError, np.linalg.LinAlgError, json.JSONDecodeError) as error:
        print(f"fuel reachability {arguments.command} failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
