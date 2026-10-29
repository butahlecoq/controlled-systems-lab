#!/usr/bin/env python3
"""Replay and render the finite MultiPointCostGame minimax pilot."""
from __future__ import annotations

import argparse
import hashlib
import html
import itertools
import json
import math
import platform
import subprocess
from pathlib import Path

SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
SOURCE_BLOB = "baf126c2074c865f3a758abbaade73686a1dc4bc"
CATALOGUE = (-1.0, 0.0, 1.0)
HORIZON = 4
INNER_DT = 0.02
INNER_STEPS = 50
TOLERANCE = 2e-10
INITIAL = (0.0, 1.0)


def advance(state: tuple[float, float], stage: int, u: float,
            disturbance: float) -> tuple[float, float]:
    time, position, velocity = float(stage), state[0], state[1]
    for _ in range(INNER_STEPS):
        old_time, old_position, old_velocity = time, position, velocity
        time += INNER_DT
        position = old_position + old_velocity * INNER_DT
        velocity = old_velocity + (3.0 * u + (old_time - 2.0) ** 2 * disturbance) * INNER_DT
    return position, velocity


def solve_reference() -> dict:
    layers: list[list[tuple[float, float]]] = [[INITIAL]]
    edges: list[list[list[int]]] = []
    for stage in range(HORIZON):
        next_ids: dict[tuple[float, float], int] = {}
        next_layer: list[tuple[float, float]] = []
        stage_edges: list[list[int]] = []
        for state in layers[stage]:
            action_edges = []
            for u in CATALOGUE:
                destinations = []
                for disturbance in CATALOGUE:
                    nxt = advance(state, stage, u, disturbance)
                    if nxt not in next_ids:
                        next_ids[nxt] = len(next_layer)
                        next_layer.append(nxt)
                    destinations.append(next_ids[nxt])
                action_edges.append(destinations)
            stage_edges.append(action_edges)
        layers.append(next_layer)
        edges.append(stage_edges)

    terminal_values = [p * p + v * v for p, v in layers[-1]]
    values: list[list[float]] = [[] for _ in layers]
    optimal: list[list[list[int]]] = [[] for _ in range(HORIZON)]
    values[-1] = terminal_values
    for stage in range(HORIZON - 1, -1, -1):
        current = []
        actions_at_stage = []
        for transitions in edges[stage]:
            action_values = [max(values[stage + 1][index] for index in successors)
                             for successors in transitions]
            best = min(action_values)
            current.append(best)
            actions_at_stage.append([i for i, value in enumerate(action_values)
                                     if abs(value - best) <= TOLERANCE + TOLERANCE * max(abs(value), abs(best))])
        values[stage] = current
        optimal[stage] = actions_at_stage

    open_plans = []
    for plan_index, plan in enumerate(itertools.product(CATALOGUE, repeat=HORIZON)):
        worst = -math.inf
        worst_state = None
        worst_disturbance = None
        for disturbances in itertools.product(CATALOGUE, repeat=HORIZON):
            state = INITIAL
            for stage, (u, d) in enumerate(zip(plan, disturbances)):
                state = advance(state, stage, u, d)
            cost = state[0] ** 2 + state[1] ** 2
            if cost > worst:
                worst, worst_state, worst_disturbance = cost, state, disturbances
        open_plans.append({"plan_index": plan_index,
                           "control_indices": [CATALOGUE.index(value) for value in plan],
                           "worst_terminal_cost": worst,
                           "maximizing_terminal_state": list(worst_state),
                           "maximizing_disturbance_indices": [CATALOGUE.index(value)
                                                              for value in worst_disturbance]})
    open_value = min(plan["worst_terminal_cost"] for plan in open_plans)
    minimizing = [plan["plan_index"] for plan in open_plans
                  if abs(plan["worst_terminal_cost"] - open_value) <= TOLERANCE]

    feedback_path = [INITIAL]
    feedback_controls: list[float] = []
    feedback_disturbances: list[float] = []
    state_id = 0
    for stage in range(HORIZON):
        action_id = optimal[stage][state_id][0]
        successor_ids = edges[stage][state_id][action_id]
        disturbance_id = max(range(len(CATALOGUE)),
                             key=lambda i: values[stage + 1][successor_ids[i]])
        state_id = successor_ids[disturbance_id]
        feedback_controls.append(CATALOGUE[action_id])
        feedback_disturbances.append(CATALOGUE[disturbance_id])
        feedback_path.append(layers[stage + 1][state_id])
    assert math.isclose(feedback_path[-1][0] ** 2 + feedback_path[-1][1] ** 2,
                        values[0][0], abs_tol=1e-9)

    return {"layers": layers, "edges": edges, "values": values, "optimal": optimal,
            "open_plans": open_plans, "open_value": open_value,
            "open_minimizing": minimizing, "feedback_path": feedback_path,
            "feedback_controls": feedback_controls,
            "feedback_disturbances": feedback_disturbances}


def verify(record: dict) -> dict:
    assert record["schema"] == "csl.env717-multipoint-terminal-pilot/1"
    assert record["environment"] == "MultiPointCostGame"
    assert record["source_repository_commit"] == SOURCE_COMMIT
    assert record["source_file_blob"] == SOURCE_BLOB
    assert record["source_initial_state"] == [0.0, 0.0, 1.0]
    assert record["source_terminal_time"] == 4.0
    adaptation = record["adaptation"]
    assert adaptation["control_catalogue"] == list(CATALOGUE)
    assert adaptation["disturbance_catalogue"] == list(CATALOGUE)
    assert "not included" in adaptation["excluded_source_terms"]
    expected = solve_reference()
    assert len(record["open_loop"]["plans"]) == 81
    assert record["open_loop"]["minimizing_plan_indices"] == expected["open_minimizing"]
    assert math.isclose(record["open_loop"]["value"], expected["open_value"], abs_tol=1e-10)
    for actual, reference in zip(record["open_loop"]["plans"], expected["open_plans"]):
        assert actual["plan_index"] == reference["plan_index"]
        assert actual["control_indices"] == reference["control_indices"]
        assert math.isclose(actual["worst_terminal_cost"], reference["worst_terminal_cost"], abs_tol=1e-9)
        assert all(math.isclose(a, b, abs_tol=1e-9) for a, b in
                   zip(actual["maximizing_terminal_state"], reference["maximizing_terminal_state"]))
    first_optimal = expected["open_plans"][expected["open_minimizing"][0]]
    replay_state = INITIAL
    for stage, (control_id, disturbance_id) in enumerate(zip(
            first_optimal["control_indices"], first_optimal["maximizing_disturbance_indices"])):
        replay_state = advance(replay_state, stage, CATALOGUE[control_id], CATALOGUE[disturbance_id])
    assert math.isclose(replay_state[0] ** 2 + replay_state[1] ** 2,
                        expected["open_value"], abs_tol=1e-9)
    feedback = record["feedback"]
    assert math.isclose(feedback["value"], expected["values"][0][0], abs_tol=1e-9)
    assert feedback["optimal_initial_action_indices"] == expected["optimal"][0][0]
    assert len(feedback["values_by_stage"]) == HORIZON + 1
    for stage, rows in enumerate(feedback["values_by_stage"]):
        assert len(rows) == len(expected["layers"][stage])
        for state_id, row in enumerate(rows):
            assert row["state_id"] == state_id
            assert row["state"] == list(expected["layers"][stage][state_id])
            assert row["feasible"] is True
            assert math.isclose(row["value"], expected["values"][stage][state_id], abs_tol=1e-9)
            if stage < HORIZON:
                assert row["optimal_action_indices"] == expected["optimal"][stage][state_id]
            else:
                assert row["optimal_action_indices"] == []
    timing = record["timing"]
    assert timing["warmup_calls_per_method"] == 1
    assert timing["measured_calls_per_method"] == 7
    for field in ("open_loop_wall_ns", "feedback_wall_ns"):
        samples = timing[field]
        assert len(samples) == 7 and all(type(sample) is int and sample > 0 for sample in samples)
    assert timing["performance_claim"] is False
    assert timing["worker_threads_requested"] == timing["native_threads_requested"] == 1
    assert timing["order"] == "seven measured rounds alternate open-loop/feedback and feedback/open-loop"
    assert timing["scope"].startswith("algorithm solve only;")
    return expected


def svg_figure(record: dict, replay: dict) -> str:
    width, height = 1000, 805
    x0, y0, pw, ph = 110, 105, 800, 540
    states = [state for layer in replay["layers"] for state in layer]
    xmin, xmax = min(s[0] for s in states), max(s[0] for s in states)
    ymin, ymax = min(s[1] for s in states), max(s[1] for s in states)
    padx, pady = max((xmax-xmin)*0.08, 0.2), max((ymax-ymin)*0.08, 0.2)
    xmin, xmax, ymin, ymax = xmin-padx, xmax+padx, ymin-pady, ymax+pady
    sx = lambda value: x0 + pw * (value-xmin)/(xmax-xmin)
    sy = lambda value: y0 + ph * (ymax-value)/(ymax-ymin)
    colors = ["#f4f1e8", "#38bdf8", "#34d399", "#a78bfa", "#fbbf24"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
           '<title id="title">MultiPointCostGame minimax and reachable states</title>',
           '<desc id="desc">Position-velocity phase plane, forward reachable states at all five times, the minimizing open-loop worst-case path, and a causal feedback path against a greedy worst-case disturbance.</desc>',
           '<rect width="100%" height="100%" fill="#111820"/>',
           '<text x="48" y="42" fill="#f4f1e8" font-family="sans-serif" font-size="25" font-weight="700">MultiPointCostGame · position–velocity plane</text>',
           f'<text x="{x0}" y="78" fill="#bac6ce" font-family="sans-serif" font-size="14">4 one-second decisions · 81 fixed control plans × 81 disturbance sequences · terminal values: open-loop {replay["open_value"]:.6g}, causal feedback {replay["values"][0][0]:.6g}</text>',
           f'<rect x="{x0}" y="{y0}" width="{pw}" height="{ph}" fill="#18232c" stroke="#53616c"/>',
           f'<defs><clipPath id="plane"><rect x="{x0}" y="{y0}" width="{pw}" height="{ph}"/></clipPath></defs>']
    for stage, layer in reversed(list(enumerate(replay["layers"]))):
        color = colors[stage]
        for position, velocity in layer:
            radius = 4.4 if stage == 0 else (3.1 if stage == 1 else 2.2)
            opacity = 0.92 if stage < 2 else 0.26
            out.append(f'<circle clip-path="url(#plane)" cx="{sx(position):.2f}" cy="{sy(velocity):.2f}" r="{radius}" fill="{color}" fill-opacity="{opacity}"><title>t={stage}s, position={position:.6g}, velocity={velocity:.6g}</title></circle>')
    for path, color, label, dash in ((replay["open_path"], "#fb7185", "open-loop", ""),
                                     (replay["feedback_path"], "#ffffff", "causal feedback (greedy worst-case disturbance)", "stroke-dasharray=\"8 5\"")):
        points = " ".join(f"{sx(p):.2f},{sy(v):.2f}" for p, v in path)
        out.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="4" {dash}><title>{label}</title></polyline>')
        for i, (p, v) in enumerate(path):
            out.append(f'<circle cx="{sx(p):.2f}" cy="{sy(v):.2f}" r="5" fill="{color}" stroke="#111820" stroke-width="1"><title>{label}, t={i}s</title></circle>')
    out.extend([f'<text x="{x0+pw/2}" y="{y0+ph+36}" text-anchor="middle" fill="#cbd5dc" font-family="sans-serif" font-size="16">Position</text>',
                f'<text x="35" y="{y0+ph/2}" transform="rotate(-90 35 {y0+ph/2})" text-anchor="middle" fill="#cbd5dc" font-family="sans-serif" font-size="16">Velocity</text>'])
    for stage, color in enumerate(colors):
        lx = x0 + stage * 135
        out.append(f'<circle cx="{lx}" cy="700" r="4" fill="{color}"/><text x="{lx+12}" y="705" fill="#d6dee3" font-family="sans-serif" font-size="13">reachable t={stage}s</text>')
    out.extend(['<line x1="110" y1="738" x2="140" y2="738" stroke="#fb7185" stroke-width="4"/><text x="148" y="743" fill="#d6dee3" font-family="sans-serif" font-size="13">open-loop plan under worst disturbance</text>',
                '<line x1="490" y1="738" x2="520" y2="738" stroke="#ffffff" stroke-width="4" stroke-dasharray="8 5"/><text x="528" y="743" fill="#d6dee3" font-family="sans-serif" font-size="13">causal feedback under worst-case disturbance</text>',
                '<text x="110" y="780" fill="#9eabb4" font-family="sans-serif" font-size="12">Feedback path uses the first minimizing action and a disturbance maximizing next-state value at each step. No target set or backward winning set is defined here.</text>',
                '</svg>'])
    return "\n".join(out)


def figure_data(record: dict, replay: dict) -> dict:
    return {"schema": "csl.env717-multipoint-figure/1", "projection_pairs": [[0, 1]],
            "projection_labels": [["position", "velocity"]],
            "stages": [{"time_seconds": stage, "reachable_states": [list(state) for state in layer]}
                       for stage, layer in enumerate(replay["layers"])],
            "open_loop_path": [list(state) for state in replay["open_path"]],
            "open_loop_controls": replay["open_controls"],
            "open_loop_worst_disturbances": replay["open_disturbances"],
            "feedback_path": [list(state) for state in replay["feedback_path"]],
            "feedback_controls": replay["feedback_controls"],
            "feedback_worst_disturbances": replay["feedback_disturbances"],
            "open_loop_value": replay["open_value"], "feedback_value": replay["values"][0][0],
            "terminal_only_adaptation": record["adaptation"]["excluded_source_terms"]}


def processor_identity() -> str:
    if platform.system() == "Linux":
        try:
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition(":")
                if separator and key.strip() in ("model name", "Hardware") and value.strip():
                    return value.strip()
        except OSError:
            pass
    return platform.processor() or platform.uname().processor or "unavailable"


def report_page(record: dict, svg: str, capture: dict) -> str:
    timing = record["timing"]
    timing_summary = []
    for label, field in (("open-loop", "open_loop_wall_ns"),
                         ("causal feedback", "feedback_wall_ns")):
        samples = sorted(timing[field])
        timing_summary.append(f"{label}: median {samples[len(samples)//2]} ns, range {samples[0]}–{samples[-1]} ns")
    timing_text = "; ".join(timing_summary)
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MultiPointCostGame minimax pilot</title><style>body{{margin:0;background:#111820;color:#f4f1e8;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:2rem}}svg{{width:100%;height:auto}}.note{{border-left:4px solid #f4a261;padding:.7rem 1rem;background:#1a252e}}a{{color:#8bd3f7}}</style><main><h1>MultiPointCostGame: reachable states and minimax</h1><p>All forward reachable states are shown in the position–velocity plane at each of the five decision times. The two highlighted paths show a minimizing fixed open-loop plan under its worst disturbance sequence and a causal policy under a locally worst-case disturbance.</p><div>{svg}</div><p class="note"><strong>Adaptation:</strong> the source RL task has checkpoint costs at t=1 and t=3 and a terminal cost at t=4. This pilot preserves its source Euler dynamics and terminal cost, but omits both checkpoint costs. It uses four one-second decisions and catalogues {{−1, 0, 1}} for control and disturbance. This is a finite terminal-only minimax comparison, not a reproduction of the RL training run. No target or backward winning set is defined.</p><p>Values: open-loop {record['open_loop']['value']:.9g}; causal feedback {record['feedback']['value']:.9g}. Solver-call observations after one warmup: {timing_text}. They describe different information patterns and are not a speed comparison. <a href="result.json">Result JSON</a> · <a href="figure-data.json">Figure data</a> · <a href="capture.json">Capture environment</a> · <a href="projections.svg">Standalone SVG</a></p><p>Upstream source: <a href="https://github.com/imm-rl-lab/optimal_control/blob/{SOURCE_COMMIT}/Environments/MultiPointCostGame/MultiPointCostGame.py">MultiPointCostGame.py</a> at <code>{SOURCE_COMMIT}</code>. CSL measured source: <a href="https://github.com/butahlecoq/controlled-systems-lab/tree/{record['source_commit']}"><code>{record['source_commit']}</code></a>. Runtime: {html.escape(record['capture_environment']['compiler'])} {html.escape(record['capture_environment']['compiler_version'])}, {html.escape(capture['os'])}.</p></main></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    record = json.loads(subprocess.check_output([str(args.executable.resolve())], text=True))
    replay = verify(record)
    open_plan = replay["open_plans"][replay["open_minimizing"][0]]
    open_controls = [CATALOGUE[i] for i in open_plan["control_indices"]]
    open_disturbances = [CATALOGUE[i] for i in open_plan["maximizing_disturbance_indices"]]
    open_path = [INITIAL]
    for stage, (u, d) in enumerate(zip(open_controls, open_disturbances)):
        open_path.append(advance(open_path[-1], stage, u, d))
    replay.update(open_path=open_path, open_controls=open_controls,
                  open_disturbances=open_disturbances)
    if args.output:
        output = args.output
        output.mkdir(parents=True, exist_ok=False)
        svg = svg_figure(record, replay) + "\n"
        capture = {"schema": "csl.env717-capture/1",
                   "renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   "capture_environment": {"os": platform.platform(),
                       "processor": processor_identity(),
                       "processor_identity_source": "Linux /proc/cpuinfo or platform metadata",
                       "logical_cpus": __import__("os").cpu_count() or 1}}
        fig = figure_data(record, replay)
        (output / "result.json").write_text(json.dumps(record, separators=(",", ":")) + "\n", encoding="utf-8")
        (output / "figure-data.json").write_text(json.dumps(fig, separators=(",", ":")) + "\n", encoding="utf-8")
        (output / "projections.svg").write_text(svg, encoding="utf-8")
        (output / "capture.json").write_text(json.dumps(capture, indent=2) + "\n", encoding="utf-8")
        (output / "index.html").write_text(report_page(record, svg, capture["capture_environment"]), encoding="utf-8")
        (output / "README.md").write_text("# MultiPointCostGame pilot\n\nFinite terminal-only minimax adaptation of the upstream RL environment. See `index.html`; source evidence is in `result.json`.\n", encoding="utf-8")
        rows = sorted(path.name for path in output.iterdir() if path.name != "SHA256SUMS")
        (output / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256((output / name).read_bytes()).hexdigest()}  {name}\n"
            for name in rows), encoding="ascii")
        print(f"verified report written to {output}")
    else:
        print(f"verified: open-loop={replay['open_value']:.12g}; feedback={replay['values'][0][0]:.12g}; layer sizes={[len(x) for x in replay['layers']]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
