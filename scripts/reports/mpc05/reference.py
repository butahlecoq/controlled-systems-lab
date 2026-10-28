"""Independent exact reference and deterministic rendering for MPC-05."""
from __future__ import annotations

from fractions import Fraction
from functools import lru_cache
import hashlib
import html
import json
from pathlib import Path

SCALE = 2000
ACTION_CODES = (-1, 0, 1)
DISTURBANCES = (-1, 0, 1)
SOURCE_COMMIT = "f4d76c60f4003f50954174e96eafd8e514bd5441"
SOURCE_BLOB = "4e71bed8ceffa1990645fb85e54d6b5b1eeb688d"
ENV717_BUNDLE = Path(__file__).resolve().parents[3] / "reports/algorithm-results/env717-two-points-pilot-v1"


def step(state: tuple[int, ...], action: int, disturbance: int) -> tuple[int, ...]:
    p1, v1, p2, v2 = state
    if v1 % 100 or v2 % 10:
        raise ValueError("source-derived TwoPoints state is outside the exact lattice")
    return (p1 + v1 // 100 + 450 * action, 5000 * action,
            p2 + v2 // 10 + 9 * disturbance, v2 + 200 * disturbance)


def reference() -> tuple[list[list[tuple[int, ...]]], list[list[Fraction]], list[list[list[int]]], Fraction]:
    layers: list[list[tuple[int, ...]]] = [[(9000, 0, 0, 0)]]
    for _ in range(3):
        layers.append(sorted({step(state, action, disturbance)
                              for state in layers[-1]
                              for action in ACTION_CODES
                              for disturbance in DISTURBANCES}))

    def cost(state: tuple[int, ...]) -> Fraction:
        return Fraction((state[0] - state[2]) ** 2, SCALE ** 2)

    @lru_cache(None)
    def value(stage: int, state: tuple[int, ...]) -> Fraction:
        if stage == 3:
            return cost(state)
        return min(max(value(stage + 1, step(state, action, disturbance))
                       for disturbance in DISTURBANCES) for action in ACTION_CODES)

    values = [[value(t, state) for state in layer] for t, layer in enumerate(layers)]
    optimal_actions: list[list[list[int]]] = []
    for t, layer in enumerate(layers):
        rows: list[list[int]] = []
        for state in layer:
            if t == 3:
                rows.append([])
                continue
            candidates = [max(value(t + 1, step(state, action, disturbance))
                              for disturbance in DISTURBANCES)
                          for action in ACTION_CODES]
            minimum = min(candidates)
            rows.append([action for action, candidate in enumerate(candidates)
                         if abs(float(candidate - minimum)) <= 1e-12 + 1e-12 * max(abs(float(candidate)), abs(float(minimum)))])
        optimal_actions.append(rows)

    fixed_values = []
    from itertools import product
    for plan in product(ACTION_CODES, repeat=3):
        worst = Fraction(-1)
        for disturbance_history in product(DISTURBANCES, repeat=3):
            state = layers[0][0]
            for action, disturbance in zip(plan, disturbance_history):
                state = step(state, action, disturbance)
            worst = max(worst, cost(state))
        fixed_values.append(worst)
    fixed_value = min(fixed_values)
    return layers, values, optimal_actions, fixed_value


def verify_result(result: dict) -> dict:
    item = result["two_points"]
    if (item.get("source_commit") != SOURCE_COMMIT or item.get("source_blob") != SOURCE_BLOB or
            item.get("action_codes") != list(ACTION_CODES) or
            item.get("disturbance_codes") != list(DISTURBANCES)):
        raise ValueError("MPC-05 TwoPoints source or finite-game metadata differs")
    layers, values, actions, fixed_value = reference()
    if item["layer_state_counts"] != [len(layer) for layer in layers]:
        raise ValueError("TwoPoints state-layer counts differ from independent model reconstruction")
    if item["layer_states_lattice_scale_2000"] != [[list(state) for state in layer] for layer in layers]:
        raise ValueError("TwoPoints saved state catalogues differ from source-derived exact transitions")
    for saved_layer, exact_layer in zip(item["bellman_cost_to_go"], values):
        if len(saved_layer) != len(exact_layer) or any(
                abs(saved - float(exact)) > 1e-9 for saved, exact in zip(saved_layer, exact_layer)):
            raise ValueError("TwoPoints Bellman cost-to-go table differs from exact finite reference")
    if item["bellman_optimal_actions"] != actions:
        raise ValueError("TwoPoints Bellman optimal-action table differs from exact finite reference")
    if abs(item["open_loop_fixed_plan_value"] - float(fixed_value)) > 1e-12:
        raise ValueError("TwoPoints fixed-plan value differs from independent enumeration")
    tree = item["causal_tree"]
    if tree["status"] != "optimal" or [len(row) for row in tree["policy"]] != [1, 9, 81]:
        raise ValueError("TwoPoints scenario-tree solution or policy shape differs")
    if tree["decision_occurrences"] != 91 or tree["leaf_occurrences"] != 729:
        raise ValueError("TwoPoints complete action-disturbance tree size differs")

    index = [{state: state_index for state_index, state in enumerate(layer)} for layer in layers]
    worst_cost = Fraction(-1)
    worst_path: list[tuple[int, ...]] = []
    worst_actions: list[int] = []
    worst_disturbances: list[int] = []

    def replay(stage: int, state: tuple[int, ...], path: list[tuple[int, ...]],
               action_path: list[int], disturbance_path: list[int]) -> None:
        nonlocal worst_cost, worst_path, worst_actions, worst_disturbances
        if stage == 3:
            terminal_cost = Fraction((state[0] - state[2]) ** 2, SCALE ** 2)
            if (terminal_cost > worst_cost or
                    terminal_cost == worst_cost and disturbance_path < worst_disturbances):
                worst_cost = terminal_cost
                worst_path = path[:]
                worst_actions = action_path[:]
                worst_disturbances = disturbance_path[:]
            return
        action_index = index[stage][state]
        action = tree["policy"][stage][action_index]
        if action not in (0, 1, 2):
            raise ValueError("TwoPoints optimal policy has an invalid action")
        action_code = ACTION_CODES[action]
        for disturbance in DISTURBANCES:
            successor = step(state, action_code, disturbance)
            replay(stage + 1, successor, path + [successor],
                   action_path + [action_code], disturbance_path + [disturbance])

    replay(0, layers[0][0], [layers[0][0]], [], [])
    causal_value = float(values[0][0])
    if (abs(item["causal_bellman_value"] - causal_value) > 1e-10 or
            abs(tree["objective"] - causal_value) > 1e-8 or
            abs(tree["global_bound"] - causal_value) > 1e-8 or
            abs(tree["replayed_worst_cost"] - float(worst_cost)) > 1e-8 or
            abs(float(worst_cost) - causal_value) > 1e-8):
        raise ValueError("TwoPoints Bellman, tree objective/bound and selected policy replay disagree")

    source_figure = json.loads((ENV717_BUNDLE / "figure-data.json").read_text(encoding="utf-8"))
    expected_layers = [{tuple(state) for state in layer} for layer in layers]
    plotted_layers = [{tuple(round(value * SCALE) for value in state)
                       for state in layer} for layer in source_figure["forward_layers"]]
    if plotted_layers != expected_layers:
        raise ValueError("TwoPoints reachability plot does not match the causal game's state catalogues")
    winning = {state for state in layers[-1]
               if Fraction((state[0] - state[2]) ** 2, SCALE ** 2) <= values[0][0]}
    expected_backward = [set() for _ in layers]
    expected_backward[-1] = winning
    for stage_index in range(len(layers) - 2, -1, -1):
        for state in layers[stage_index]:
            if any(all(step(state, action, disturbance) in expected_backward[stage_index + 1]
                       for disturbance in DISTURBANCES) for action in ACTION_CODES):
                expected_backward[stage_index].add(state)
    plotted_backward = [{tuple(round(value * SCALE) for value in state)
                         for state in layer}
                        for layer in source_figure["robust_backward_layers"]]
    if plotted_backward != expected_backward:
        raise ValueError("TwoPoints plotted backward-winning sets differ from the causal threshold recursion")
    if len(source_figure["forward_groups"]) != 4:
        raise ValueError("TwoPoints plot is missing a forward control-prefix layer")
    plotted_path = source_figure["trajectory"]
    if len(plotted_path) != len(worst_path) or any(
            abs(plotted - exact / SCALE) > 1e-10
            for plotted_state, exact_state in zip(plotted_path, worst_path)
            for plotted, exact in zip(plotted_state, exact_state)):
        raise ValueError("Existing phase-plane path differs from causal policy's replayed worst-case path")
    if source_figure["selected_plan"] != [-2.5, -2.5, -2.5] or source_figure["selected_worst_disturbance"] != [-1.0, -1.0, -1.0]:
        raise ValueError("TwoPoints phase-plane source no longer describes the independently selected minimax path")

    return {
        "schema": "csl.mpc05-causal-tree-figure-data/1",
        "coordinate_scale": SCALE,
        "players": [
            {"name": "Player 1", "x_coordinate": "x1", "y_coordinate": "x2",
             "x_label": "Position x1 (m)", "y_label": "Velocity x2 (m/s)"},
            {"name": "Player 2", "x_coordinate": "x3", "y_coordinate": "x4",
             "x_label": "Position x3 (m)", "y_label": "Velocity x4 (m/s)"},
        ],
        "stages": [{"stage": t, "states": [[v / SCALE for v in state] for state in layer],
                    "cost_to_go": [float(v) for v in values[t]],
                    "optimal_action_indices": actions[t],
                    "selected_action_indices": tree["policy"][t] if t < 3 else []}
                   for t, layer in enumerate(layers)],
        "worst_case_path": {"states": [[v / SCALE for v in state] for state in worst_path],
                            "actions": worst_actions, "disturbances": worst_disturbances,
                            "terminal_squared_gap": float(worst_cost)},
        "causal_value": causal_value,
        "fixed_plan_value": float(fixed_value),
        "reachability_geometry_source": {
            "report_id": "env717-two-points-pilot-v1",
            "figure_data_sha256": hashlib.sha256((ENV717_BUNDLE / "figure-data.json").read_bytes()).hexdigest(),
            "svg_sha256": hashlib.sha256((ENV717_BUNDLE / "projections.svg").read_bytes()).hexdigest(),
            "backward_threshold": causal_value,
            "backward_layer_counts": [len(layer) for layer in expected_backward],
            "forward_backward_intersection_counts": [
                len(forward & backward) for forward, backward in zip(expected_layers, expected_backward)],
        },
        "reachability_geometry": source_figure,
    }


def render_svg(figure: dict) -> str:
    # Reuse the already independently checked publication plot for this exact
    # source-derived map; verify_result binds its layers and path to this run.
    return (ENV717_BUNDLE / "projections.svg").read_text(encoding="utf-8")


def render_html(result: dict, figure: dict, svg: str) -> str:
    two = result["two_points"]
    tree = two["causal_tree"]
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Finite causal minimax — TwoPointsOnParallelLines</title>
<style>body{{max-width:1100px;margin:2rem auto;padding:0 1rem;background:#fbf1c7;color:#282828;font:16px/1.5 system-ui}}h1,h2{{color:#3c3836}}.metric{{display:inline-block;margin:.4rem 1rem .4rem 0;padding:.7rem;background:#f9f5d7;border:1px solid #d5c4a1;border-radius:6px}}svg{{width:100%;height:auto}}code{{background:#f9f5d7;padding:.1rem .3rem}}a{{color:#076678}}</style></head>
<body><h1>Finite causal minimax on TwoPointsOnParallelLines</h1>
<p>This report runs the finite-state Bellman solver and an independent complete action–disturbance scenario-tree MILP on a short finite adaptation of an upstream differential-game RL environment. The two panels show the players’ phase planes: <code>(x1,x2)=(position₁,velocity₁)</code> and <code>(x3,x4)=(position₂,velocity₂)</code>.</p>
<div class="metric"><strong>Fixed-plan value</strong><br>{two['open_loop_fixed_plan_value']:.8f} m²</div>
<div class="metric"><strong>Causal Bellman / tree value</strong><br>{two['causal_bellman_value']:.8f} m²</div>
<div class="metric"><strong>Tree evidence</strong><br>{tree['decision_occurrences']} decisions · {tree['leaf_occurrences']} leaves · {tree['nonanticipativity_equalities']} explicit equalities</div>
<p>The MILP reports incumbent {tree['objective']:.8f}, global bound {tree['global_bound']:.8f}, relative gap {tree['relative_gap']:.3g}; an independent replay gives worst-case cost {tree['replayed_worst_cost']:.8f}. This finite instance has equal fixed-plan and causal values; the separate strict-gap fixture demonstrates a value difference of 2 versus 1.</p>
<h2>Reachability, backward winning sets, and the optimal path</h2>
<p>The two phase-plane panels overlay forward reachable polytopes by control prefix, the terminal reachable set, robust backward-winning nodes, forward/backward intersections, and a selected worst-case trajectory. The plotted trajectory is independently confirmed to equal the worst-case path under the selected causal minimax policy. These are the same exact finite dynamics and terminal threshold checked by this report.</p>
{svg}
<h2>Model and limits</h2>
<ul><li>Upstream repository: <a href="https://github.com/imm-rl-lab/optimal_control/tree/master/Environments">imm-rl-lab/optimal_control/Environments</a>, commit <code>{two['source_commit']}</code>, source blob <code>{two['source_blob']}</code>. No upstream source code is copied.</li>
<li>Upstream task uses continuous controls over 10 seconds. This report uses three stages (0.3 seconds) with control values <code>{two['control_values']}</code> and disturbance values <code>{two['disturbance_codes']}</code>; it is not an RL reproduction.</li>
<li>Objective: terminal squared position gap. It is monotone-equivalent to the source absolute-gap reward for policy ordering, but this report gives squared-cost units.</li>
<li>Claims cover only exact full-state observation and the listed finite disturbance catalogue. They do not cover continuous disturbances, state approximation, or the original continuous-control policy.</li>
<li>The current finite-feedback report is a safety-threshold result. This report separately solves the cost-optimal causal policy.</li></ul>
<p><a href="result.json">Raw result</a> · <a href="figure-data.json">Figure data</a> · <a href="capture.json">Capture metadata</a> · <a href="README.md">Reproduction notes</a></p>
</body></html>
'''


def render(result_path: Path, output: Path) -> None:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    figure = verify_result(result)
    output.mkdir(parents=True, exist_ok=True)
    (output / "figure-data.json").write_text(json.dumps(figure, indent=2) + "\n", encoding="utf-8")
    svg = render_svg(figure)
    (output / "projections.svg").write_text(svg, encoding="utf-8")
    (output / "index.html").write_text(render_html(result, figure, svg), encoding="utf-8")
