"""Independently replay and render the finite BrokenTriangleGame pilot."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import platform
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
GAME_BLOB = "91771d55f6f868bb31d871cb0ad8a5d2af521c2a"
RL_BLOB = "2ba6b9d73040caf2c98017ecc7bcee3d41c1be8a"
INITIAL = (-0.75, -1.0)
DT = 0.4
HORIZON = 4
U = (-0.25, 0.25)
V = (-1.0, 1.0)
POLYGON = ((0.0, 4.5), (0.5, -1.0), (3.5, -4.0), (-3.5, -4.0), (-0.5, -1.0))
TOL = 1e-12


def signed_distance(point: tuple[float, float]) -> float:
    distances, signs = [], []
    for index, x in enumerate(POLYGON):
        y = POLYGON[(index + 1) % len(POLYGON)]
        dx, dy = y[0] - x[0], y[1] - x[1]
        length_squared = dx * dx + dy * dy
        rx, ry = point[0] - x[0], point[1] - x[1]
        r = (rx * dx + ry * dy) / length_squared
        if r < 0.0:
            distance = math.hypot(rx, ry)
        elif r > 1.0:
            distance = math.hypot(point[0] - y[0], point[1] - y[1])
        else:
            distance = math.sqrt(max(0.0, rx * rx + ry * ry - r * r * length_squared))
        distances.append(distance)
        signs.append(ry * dx - rx * dy)
    nearest = min(range(len(distances)), key=distances.__getitem__)
    return distances[nearest] * (-1.0 if signs[nearest] < 0.0 else 1.0)


def inside(point: tuple[float, float]) -> bool:
    # Matches the source signed-distance convention: interior is nonpositive.
    return signed_distance(point) <= TOL


def step(point: tuple[float, float], u: float, v: float) -> tuple[float, float]:
    return (round(point[0] + DT * (u + v), 12), round(point[1] + DT * v, 12))


def build_graph():
    layers = [[INITIAL]]
    transitions = []
    for _stage in range(HORIZON):
        next_ids = {}
        next_layer = []
        stage_rows = []
        for point in layers[-1]:
            action_rows = []
            for u in U:
                successors = []
                for v in V:
                    candidate = step(point, u, v)
                    if candidate not in next_ids:
                        next_ids[candidate] = len(next_layer)
                        next_layer.append(candidate)
                    successors.append(next_ids[candidate])
                action_rows.append(successors)
            stage_rows.append(action_rows)
        transitions.append(stage_rows)
        layers.append(next_layer)
    return layers, transitions


def solve_independently():
    layers, transitions = build_graph()
    terminal = [signed_distance(point) for point in layers[-1]]
    values = [None] * (HORIZON + 1)
    values[-1] = terminal
    actions_by_state = [None] * HORIZON
    for stage in range(HORIZON - 1, -1, -1):
        values[stage], actions_by_state[stage] = [], []
        for state_id, action_rows in enumerate(transitions[stage]):
            action_values = [max(values[stage + 1][next_id] for next_id in succ)
                             for succ in action_rows]
            best = min(action_values)
            values[stage].append(best)
            actions_by_state[stage].append([i for i, value in enumerate(action_values)
                                            if abs(value - best) <= TOL])

    winning = [[False] * len(layer) for layer in layers]
    winning[-1] = [inside(point) for point in layers[-1]]
    for stage in range(HORIZON - 1, -1, -1):
        for state_id, action_rows in enumerate(transitions[stage]):
            winning[stage][state_id] = any(
                all(winning[stage + 1][next_id] for next_id in successors)
                for successors in action_rows)

    open_plans = []
    # Match the C++ driver's base-two plan ID convention (stage 0 is the low bit).
    for code in range(2 ** HORIZON):
        digits, us = code, []
        for _ in range(HORIZON):
            us.append(digits % 2)
            digits //= 2
        worst_cost = -math.inf
        worst_vs = None
        worst_path = None
        for vs in itertools.product(range(2), repeat=HORIZON):
            state_id, path = 0, [layers[0][0]]
            for stage, (u_id, v_id) in enumerate(zip(us, vs)):
                state_id = transitions[stage][state_id][u_id][v_id]
                path.append(layers[stage + 1][state_id])
            cost = terminal[state_id]
            if cost > worst_cost + TOL:
                worst_cost, worst_vs, worst_path = cost, list(vs), path
        open_plans.append({"u_indices": list(us), "worst_cost": worst_cost,
                           "worst_v_indices": worst_vs, "worst_path": worst_path})
    open_index = min(range(len(open_plans)), key=lambda i: open_plans[i]["worst_cost"])
    open_plan = open_plans[open_index]

    causal_path, causal_us, causal_vs = [INITIAL], [], []
    state_id = 0
    for stage in range(HORIZON):
        u_id = actions_by_state[stage][state_id][0]
        v_id = max(range(2), key=lambda v: values[stage + 1][transitions[stage][state_id][u_id][v]])
        causal_us.append(u_id)
        causal_vs.append(v_id)
        state_id = transitions[stage][state_id][u_id][v_id]
        causal_path.append(layers[stage + 1][state_id])

    return {"layers": layers, "transitions": transitions, "values": values,
            "actions": actions_by_state, "winning": winning,
            "open_plans": open_plans, "open_plan_id": open_index,
            "open_value": open_plan["worst_cost"],
            "open_u_indices": open_plan["u_indices"],
            "open_worst_v_indices": open_plan["worst_v_indices"],
            "open_path": open_plan["worst_path"],
            "causal_value": values[0][0], "causal_u_indices": causal_us,
            "causal_worst_v_indices": causal_vs, "causal_path": causal_path}


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)


def verify(result: dict) -> dict:
    if result.get("schema") != "csl.env717-broken-triangle-pilot/1":
        raise ValueError("BrokenTriangleGame result schema differs")
    if (result.get("source_repository_commit") != SOURCE_COMMIT
            or result.get("game_file_blob") != GAME_BLOB
            or result.get("rl_notebook_blob") != RL_BLOB):
        raise ValueError("upstream BrokenTriangleGame source identity differs")
    if result.get("state_order") != ["time", "x", "y"] or result.get("initial_state") != [0.0, *INITIAL]:
        raise ValueError("source initial state or state order differs")
    if (result.get("source_dt") != DT or result.get("source_terminal_time") != 1.6
            or result.get("terminal_polygon") != [list(point) for point in POLYGON]
            or result.get("source_u_actions") != list(U)
            or result.get("source_v_actions") != list(V)):
        raise ValueError("source horizon settings differ")
    expected = solve_independently()
    def points(layer): return [[float(x), float(y)] for x, y in layer]
    if result.get("state_catalogues") != [points(layer) for layer in expected["layers"]]:
        raise ValueError("state catalogues differ from independent integer-lattice replay")
    if result.get("state_counts_by_stage") != [len(layer) for layer in expected["layers"]]:
        raise ValueError("state counts differ")
    if result.get("winning_counts_by_stage") != [sum(layer) for layer in expected["winning"]]:
        raise ValueError("backward target counts differ")
    if result.get("feedback_winning_initial") != expected["winning"][0][0]:
        raise ValueError("initial feedback target reachability differs")
    if result.get("open_loop_value") is None or not _close(result["open_loop_value"], expected["open_value"]):
        raise ValueError("open-loop minimax value differs")
    if not _close(result.get("causal_value", math.nan), expected["causal_value"]):
        raise ValueError("causal Bellman value differs")
    expected_keys = {"open_loop_u_indices": "open_u_indices",
                     "open_loop_worst_v_indices": "open_worst_v_indices",
                     "causal_u_indices": "causal_u_indices",
                     "causal_worst_v_indices": "causal_worst_v_indices"}
    for observed_key, expected_key in expected_keys.items():
        if result.get(observed_key) != expected[expected_key]:
            raise ValueError(f"{observed_key} differs")
    for key in ("open_loop_worst_path", "causal_worst_path"):
        observed = result.get(key)
        expected_path = expected["open_path" if key.startswith("open_") else "causal_path"]
        if len(observed or []) != len(expected_path) or any(
                not all(_close(float(a), float(b)) for a, b in zip(got, want))
                for got, want in zip(observed, expected_path)):
            raise ValueError(f"{key} differs")
    saved_layers = result.get("layers")
    if not isinstance(saved_layers, list) or len(saved_layers) != HORIZON + 1:
        raise ValueError("saved layer inventory differs")
    for stage, rows in enumerate(saved_layers):
        if len(rows) != len(expected["layers"][stage]): raise ValueError("layer length differs")
        for state_id, row in enumerate(rows):
            point = expected["layers"][stage][state_id]
            if row.get("id") != state_id or any(not _close(float(a), b)
                                                  for a, b in zip(row.get("xy", []), point)):
                raise ValueError("saved state row differs")
            if row.get("target") != inside(point):
                raise ValueError("target membership annotation differs")
            if row.get("feedback_winning") != expected["winning"][stage][state_id]:
                raise ValueError("finite feedback layer differs")
            if not _close(float(row.get("causal_value", math.nan)), expected["values"][stage][state_id]):
                raise ValueError("saved causal value differs")
            expected_actions = expected["actions"][stage][state_id] if stage < HORIZON else []
            if row.get("optimal_actions") != expected_actions:
                raise ValueError("saved optimal action set differs")
    if len(result.get("open_loop_plans", [])) != 16:
        raise ValueError("open-loop catalogue is incomplete")
    for plan_id, (saved, actual) in enumerate(zip(result["open_loop_plans"], expected["open_plans"])):
        if (saved.get("u_indices") != actual["u_indices"]
                or saved.get("plan_id") != plan_id
                or saved.get("worst_v_indices") != actual["worst_v_indices"]
                or not _close(float(saved.get("worst_cost", math.nan)), actual["worst_cost"])
                or any(not all(_close(float(a), float(b)) for a, b in zip(got, want))
                       for got, want in zip(saved.get("worst_path", []), actual["worst_path"]))
                or len(saved.get("worst_path", [])) != len(actual["worst_path"])):
            raise ValueError("an open-loop plan or adversarial outcome differs")
    expected_adaptation = result.get("adaptation", {})
    if (expected_adaptation.get("horizon") != HORIZON
            or expected_adaptation.get("open_loop_plan_count") != 16
            or expected_adaptation.get("disturbance_sequences_per_plan") != 16
            or expected_adaptation.get("reachability") !=
               "finite forward state catalog and exact finite-feedback predecessor game; no continuous boundary claim"):
        raise ValueError("adaptation scope differs")
    return expected


def figure_data(analysis: dict) -> dict:
    layers = analysis["layers"]
    return {"schema": "csl.env717-broken-triangle-figure/1",
            "coordinate_ids": ["x", "y"],
            "forward_layers": [points(layer) for layer in layers],
            "backward_winning_layers": [
                points([point for point, wins in zip(layer, mask) if wins])
                for layer, mask in zip(layers, analysis["winning"])],
            "forward_backward_intersections": [
                points([point for point, wins in zip(layer, mask) if wins])
                for layer, mask in zip(layers, analysis["winning"])],
            "target_polygon": [list(point) for point in POLYGON],
            "open_loop_worst_path": points(analysis["open_path"]),
            "causal_worst_path": points(analysis["causal_path"]),
            "open_loop_value": analysis["open_value"],
            "causal_value": analysis["causal_value"]}


def points(rows):
    return [[float(x), float(y)] for x, y in rows]


def svg_figure(data: dict) -> str:
    width, height = 980, 805
    left, right, top, bottom = 100.0, 940.0, 75.0, 580.0
    all_points = [point for layer in data["forward_layers"] for point in layer]
    all_points += [point for point in data["target_polygon"]]
    all_points += data["open_loop_worst_path"] + data["causal_worst_path"]
    xmin, xmax = min(p[0] for p in all_points) - .8, max(p[0] for p in all_points) + .8
    ymin, ymax = min(p[1] for p in all_points) - .8, max(p[1] for p in all_points) + .8
    sx = lambda x: left + (x - xmin) * (right - left) / (xmax - xmin)
    sy = lambda y: bottom - (y - ymin) * (bottom - top) / (ymax - ymin)
    colors = ("#2563eb", "#0891b2", "#7c3aed", "#ea580c", "#65a30d")
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
           '<title id="title">BrokenTriangleGame forward and backward finite-game geometry</title>',
           '<desc id="desc">Forward state catalogues, terminal polygon, robust backward-winning nodes, their intersections with the forward catalogue, and open-loop and causal minimax worst-case trajectories.</desc>',
           '<rect width="100%" height="100%" fill="#fbfbfd"/>',
           '<text x="490" y="28" text-anchor="middle" font-family="sans-serif" font-size="20" font-weight="bold">BrokenTriangleGame · finite target game</text>',
           '<text x="490" y="51" text-anchor="middle" font-family="sans-serif" font-size="12">four 0.4-second decisions · state catalogues from the documented RL initial state</text>']
    for i in range(6):
        x = left + i * (right - left) / 5
        value = xmin + i * (xmax - xmin) / 5
        out.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{bottom}" stroke="#e5e7eb"/><text x="{x:.2f}" y="{bottom+22}" text-anchor="middle" font-family="sans-serif" font-size="11">{value:.1f}</text>')
        y = top + i * (bottom - top) / 5
        value = ymax - i * (ymax - ymin) / 5
        out.append(f'<line x1="{left}" y1="{y:.2f}" x2="{right}" y2="{y:.2f}" stroke="#e5e7eb"/><text x="{left-12}" y="{y+4:.2f}" text-anchor="end" font-family="sans-serif" font-size="11">{value:.1f}</text>')
    polygon = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in data["target_polygon"])
    out.append(f'<polygon points="{polygon}" fill="#fecaca" fill-opacity=".45" stroke="#dc2626" stroke-width="2.5"><title>terminal target M</title></polygon>')
    # Forward reachable nodes, stage by stage.
    for stage, layer in enumerate(data["forward_layers"]):
        for x, y in layer:
            out.append(f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="4.2" fill="{colors[stage]}" fill-opacity=".7"><title>R{stage}: ({x:g}, {y:g})</title></circle>')
    # Robust backward-winning nodes coincide with the finite forward graph queried here.
    for stage, layer in enumerate(data["forward_backward_intersections"]):
        for x, y in layer:
            out.append(f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="8" fill="none" stroke="#16a34a" stroke-width="2.5"><title>R{stage} intersect G{stage}: ({x:g}, {y:g})</title></circle>')
    for key, color, dash in (("open_loop_worst_path", "#111827", ""),
                             ("causal_worst_path", "#7c2d12", "8 5")):
        path = data[key]
        encoded = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in path)
        out.append(f'<polyline points="{encoded}" fill="none" stroke="{color}" stroke-width="3" stroke-dasharray="{dash}"/>')
        for stage, (x, y) in enumerate(path):
            out.append(f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="5.5" fill="{color}" stroke="white" stroke-width="1"><title>{key}, stage {stage}</title></circle>')
    out.extend([f'<text x="{(left+right)/2}" y="{bottom+25}" text-anchor="middle" font-family="sans-serif" font-size="14">x position</text>',
                f'<text x="20" y="{(top+bottom)/2}" text-anchor="middle" transform="rotate(-90 20 {(top+bottom)/2})" font-family="sans-serif" font-size="14">y position</text>',
                '<rect x="105" y="620" width="770" height="72" rx="5" fill="#fff" stroke="#d1d5db"/>',
                '<line x1="120" y1="640" x2="148" y2="640" stroke="#111827" stroke-width="3"/><text x="154" y="644" font-family="sans-serif" font-size="12">open-loop minimax worst path</text>',
                '<line x1="355" y1="640" x2="383" y2="640" stroke="#7c2d12" stroke-width="3" stroke-dasharray="8 5"/><text x="389" y="644" font-family="sans-serif" font-size="12">causal minimax worst path</text>',
                '<circle cx="623" cy="640" r="4" fill="#2563eb"/><text x="632" y="644" font-family="sans-serif" font-size="12">forward nodes Rk</text>',
                '<rect x="120" y="660" width="14" height="10" fill="#fecaca" stroke="#dc2626"/><text x="141" y="670" font-family="sans-serif" font-size="12">terminal polygon M</text>',
                '<circle cx="300" cy="665" r="8" fill="none" stroke="#16a34a" stroke-width="2.5"/><text x="314" y="670" font-family="sans-serif" font-size="12">backward-winning nodes Rk ∩ Gk</text>',
                f'<text x="490" y="735" text-anchor="middle" font-family="sans-serif" font-size="12">Minimax terminal costs: open loop {data["open_loop_value"]:.6g} · causal feedback {data["causal_value"]:.6g}.</text>',
                '<text x="490" y="758" text-anchor="middle" font-family="sans-serif" font-size="12">Backward sets are finite-catalogue nodes, not continuous boundaries.</text>', '</svg>'])
    return "\n".join(out) + "\n"


def write_bundle(result: dict, output: Path) -> None:
    analysis = verify(result)
    fig = figure_data(analysis)
    output.mkdir(parents=True, exist_ok=False)
    renderer_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report = {"schema": "csl.env717-broken-triangle-figure/1", **fig}
    svg = svg_figure(fig)
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (output / "figure-data.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output / "projections.svg").write_text(svg, encoding="utf-8")
    (output / "README.md").write_text(
        "# BrokenTriangleGame finite minimax and reachability pilot\n\n"
        "This finite four-stage adaptation uses the source RL notebook's documented initial state, action catalogues, dynamics, and terminal polygon. It is not an RL training reproduction. The report compares a fixed open-loop plan with an exact observed-state causal Bellman policy under the source signed-distance terminal cost. The backward winning nodes answer a separate robust target-reachability question over the finite forward state graph; no continuous boundary is claimed.\n\n"
        "## Findings\n\n"
        f"- Open-loop minimax terminal signed-distance value: `{result['open_loop_value']:.12g}`.\n"
        f"- Causal Bellman terminal signed-distance value: `{result['causal_value']:.12g}`.\n"
        f"- Finite feedback target-winning nodes by stage: `{result['winning_counts_by_stage']}`. The documented initial state is not winning in this four-stage game.\n"
        f"- Forward state catalogue sizes: `{result['state_counts_by_stage']}`.\n\n"
        "## Scope and evidence\n\n"
        "The stage map is the source Euler step with `dt=0.4`, controls `u ∈ {-0.25,+0.25}`, disturbances `v ∈ {-1,+1}`, and four decisions. Open-loop plans are exhaustively checked against all 16 disturbance histories. Causal values are computed by the finite state Bellman recursion. Reachability uses the finite forward catalogue and enumerates the listed disturbance vertices; it does not describe continuous-state boundaries or interior disturbance values. One warmup and one timed minimax solve are recorded; the timing is descriptive for this fixture and supports no performance comparison or scalability claim.\n\n"
        f"Upstream game notebook: <https://github.com/imm-rl-lab/optimal_control/blob/{SOURCE_COMMIT}/Environments/BrokenTriangleGame/BrokenTriangleGame.ipynb> (blob `{GAME_BLOB}`). The separate DCEM notebook is provenance only (blob `{RL_BLOB}`). The upstream repository declares no license in its repository metadata; this bundle contains independently computed result data and does not redistribute notebook contents.\n",
        encoding="utf-8")
    environment = {"schema": "csl.env717-broken-triangle-environment/1",
        "source_repository": result["source_repository"],
        "source_repository_commit": SOURCE_COMMIT, "game_file_blob": GAME_BLOB,
        "rl_notebook_blob": RL_BLOB, "source_license": result["source_license"],
        "state_order": result["state_order"], "source_dt": DT,
        "source_horizon": HORIZON, "source_terminal_time": 1.6,
        "u_catalogue": list(U), "v_catalogue": list(V),
        "source_terminal_reward": result["source_terminal_reward"],
        "adaptation": result["adaptation"]}
    (output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8")
    capture = {"schema": "csl.env717-broken-triangle-capture/1",
        "source_commit": result["source_commit"], "driver_sha256": result["driver_sha256"],
        "algorithm_source_sha256": result["algorithm_source_sha256"],
        "renderer_sha256": renderer_sha, "capture_environment": {
            "compiler": result["compiler"], "compiler_version": result["compiler_version"],
            "build_type": result["build_type"], "architecture": result["architecture"],
            "os": platform.platform(), "python": platform.python_version(),
            "processor": platform.processor() or platform.machine(),
            "logical_cpu_count": os.cpu_count()}}
    (output / "capture.json").write_text(json.dumps(capture, indent=2) + "\n", encoding="utf-8")
    title = "BrokenTriangleGame finite minimax pilot"
    html = ("<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{title}</title><style>body{{max-width:1000px;margin:2rem auto;padding:0 1rem;font:16px/1.5 system-ui;color:#17202a}}svg{{width:100%;height:auto}}pre{{overflow:auto;background:#f4f4f5;padding:1rem}}</style><main><h1>{title}</h1>"
        f"<p>Four finite decisions from the <a href=\"https://github.com/imm-rl-lab/optimal_control/blob/{SOURCE_COMMIT}/Environments/BrokenTriangleGame/BrokenTriangleGame.ipynb\">upstream BrokenTriangleGame example</a>. The source training process is not reproduced. The plot overlays the terminal target, forward state catalogues, finite backward-winning nodes/intersections, and the open-loop and causal minimax worst-case paths.</p>"
        f"<p>Open-loop minimax value <code>{result['open_loop_value']:.12g}</code>; causal Bellman value <code>{result['causal_value']:.12g}</code>. Robust target capture from the documented initial state: <code>{str(result['feedback_winning_initial']).lower()}</code>.</p>{svg}"
        "<p><a href=\"result.json\">raw result</a> · <a href=\"figure-data.json\">figure data</a> · <a href=\"environment.json\">environment inputs</a> · <a href=\"capture.json\">capture provenance</a></p>"
        f"<p>Upstream source commit <code>{SOURCE_COMMIT}</code>; capture commit <code>{result['source_commit']}</code>.</p></main></html>")
    (output / "index.html").write_text(html, encoding="utf-8")
    names = ("README.md", "capture.json", "environment.json", "figure-data.json", "index.html", "projections.svg", "result.json")
    sums = "".join(f"{hashlib.sha256((output / name).read_bytes()).hexdigest()}  {name}\n" for name in names)
    (output / "SHA256SUMS").write_text(sums, encoding="ascii")


def validate_saved_bundle(source: Path) -> tuple[dict[str, bytes], dict]:
    names = ("README.md", "capture.json", "environment.json", "figure-data.json",
             "index.html", "projections.svg", "result.json", "SHA256SUMS")
    if source.is_symlink() or not source.is_dir() or {p.name for p in source.iterdir()} != set(names):
        raise ValueError("report source directory or file inventory differs")
    if any(path.is_symlink() or not path.is_file() for path in source.iterdir()):
        raise ValueError("report files must be regular nonsymlink files")
    files = {name: (source / name).read_bytes() for name in names}
    expected_sums = {name: hashlib.sha256(content).hexdigest()
                     for name, content in files.items() if name != "SHA256SUMS"}
    observed_sums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        sha, name = line.split("  ", 1)
        if name in observed_sums:
            raise ValueError("duplicate checksum entry")
        observed_sums[name] = sha
    if observed_sums != expected_sums:
        raise ValueError("report file checksums differ")
    result = json.loads(files["result.json"])
    analysis = verify(result)
    if json.loads(files["figure-data.json"]) != {"schema": "csl.env717-broken-triangle-figure/1",
                                                     **figure_data(analysis)}:
        raise ValueError("saved figure data differs from independent replay")
    if files["projections.svg"].decode("utf-8") != svg_figure(figure_data(analysis)):
        raise ValueError("saved SVG differs from independent replay")
    capture = json.loads(files["capture.json"])
    if capture.get("renderer_sha256") != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("renderer hash differs")
    page = files["index.html"].decode("utf-8")
    if ("<svg " not in page or "causal Bellman value" not in page
            or "source training process is not reproduced" not in page):
        raise ValueError("HTML report is missing its plot or scope labels")
    return files, result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path, nargs="?")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-bundle", type=Path)
    args = parser.parse_args()
    if args.verify_bundle:
        files, result = validate_saved_bundle(args.verify_bundle)
        print(json.dumps({"verified_files": len(files), "source_commit": result["source_commit"]},
                         sort_keys=True))
        return
    if not args.executable:
        parser.error("an executable is required unless --verify-bundle is used")
    raw = subprocess.run([str(args.executable.resolve(strict=True))], check=True,
                         capture_output=True, text=True).stdout
    result = json.loads(raw)
    verify(result)
    if args.output:
        write_bundle(result, args.output)
    print(json.dumps({"source_commit": result["source_commit"],
        "state_counts_by_stage": result["state_counts_by_stage"],
        "winning_counts_by_stage": result["winning_counts_by_stage"],
        "open_loop_value": result["open_loop_value"], "causal_value": result["causal_value"],
        "feedback_winning_initial": result["feedback_winning_initial"]}, sort_keys=True))


if __name__ == "__main__":
    main()
