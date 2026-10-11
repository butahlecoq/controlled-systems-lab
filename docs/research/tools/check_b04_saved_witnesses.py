"""Check one registered archived FIG; never execute MATLAB or publish its arrays."""
import argparse
import hashlib
from io import BytesIO
import itertools
import json
from pathlib import Path
import sys


RESEARCH = Path(__file__).resolve().parents[1]
VARIANT = "b04-saved-witness-replay-v1"


def read_sources(arguments):
    register = json.loads((RESEARCH / "archive-selected-sources.json").read_text(encoding="utf-8"))
    records = {entry["id"]: entry for entry in register["selected_sources"]}
    inputs = [("A39", arguments.figure), ("A40", arguments.kernel),
              ("A01", arguments.driver), ("A41", arguments.article), ("A42", arguments.image)]
    if arguments.output:
        for _, path in inputs:
            if path is not None and (arguments.output.resolve() == path.resolve() or
                    (arguments.output.exists() and path.exists() and arguments.output.samefile(path))):
                raise ValueError("output must not replace an input source; choose a separate JSON file")
    integrity, figure_bytes = [], None
    for source_id, path in inputs:
        if path is None:
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ValueError(f"cannot read {source_id}; supply its private original with the named CLI option: {exc}") from exc
        record = records[source_id]
        digest = hashlib.sha256(data).hexdigest()
        if digest != record["sha256"] or len(data) != record["bytes"]:
            raise ValueError(f"{source_id} SHA-256 mismatch or byte-count mismatch; supply the registered original")
        integrity.append({"source_id": source_id, "sha256": digest, "bytes": len(data)})
        if source_id == "A39":
            figure_bytes = data
    return figure_bytes, integrity


def calculate(figure_bytes):
    import numpy as np
    import scipy
    from scipy.io import loadmat

    figure = loadmat(BytesIO(figure_bytes), simplify_cells=True)["hgS_070000"]

    def pair(children, count):
        oxidizer = figure["children"][0]["children"][children[0]]["properties"]
        fuel = figure["children"][2]["children"][children[1]]["properties"]
        values = np.array([oxidizer["XData"], oxidizer["YData"],
                           fuel["XData"], fuel["YData"]], dtype=float).T
        if values.shape != (count, 4) or not np.isfinite(values).all():
            raise ValueError(f"A39 unexpected array shape/nonfinite values at object pair {children}")
        return values

    nominal = [pair(indices, 17) for indices in ((3, 51), (55, 52), (56, 53))]
    nonlinear = [pair(indices, 10000) for indices in ((4, 54), (57, 55), (58, 56))]
    frozen = pair((5, 57), 17)

    def objective(state):
        terms = np.array([(1200-state[0])**2, state[1]**2, 64/9*(450-state[2])**2,
                          64/9*state[3]**2, (state[1]-8/3*state[3])**2])
        return float(np.sqrt(terms.sum()))

    def flows(total):
        ratio = 8/3
        mixture = ratio + 0.04*8/3 + 0.04*8/3*total
        # Preserve the audited source's subtraction and evaluation order.
        delta = mixture-ratio
        pressure = 132000*4 + (-1685+10)*4*delta**2 + (2242+8)*4*delta
        impulse = 320 - 15*delta**2 - 12*delta
        fuel = pressure/impulse/(1+mixture)
        return np.array([fuel*mixture, fuel])

    def replay(increments):
        states = np.empty((10000, 4))
        total = 0.0
        first = flows(total)
        states[0] = [first[0], 119500, first[1], 45300]
        for index in range(1, 10000):
            if index % 625 == 0:
                total += increments[index//625-1]
            if index == 9999:
                total += increments[-1]
            flow = flows(total)
            states[index] = [flow[0], states[index-1, 1]-0.01*states[index-1, 0],
                             flow[1], states[index-1, 3]-0.01*states[index-1, 2]]
        return states

    step = 6.25
    b = np.array([2208/110, 0, -1152/110, 0])
    a = np.array([[1, 0, 0, 0], [-step, 1, 0, 0], [0, 0, 1, 0], [0, 0, -step, 1]])
    controls = [np.diff(states[:, 0])/b[0] for states in nominal]
    replays = [replay(control) for control in controls]
    witnesses = []
    for number, (states, saved, control, replayed) in enumerate(zip(nominal, nonlinear, controls, replays), 1):
        recurrence = states[1:]-(states[:-1]@a.T+control[:, None]*b)
        stock_difference = np.diff(states[:, [1, 3]], axis=0)+step*states[:-1, [0, 2]]
        inferred_steps = -np.diff(states[:, 1])/states[:-1, 0]
        witnesses.append({
            "id": number, "nominal_states": len(states), "nonlinear_samples": len(saved),
            "initial_state": states[0].tolist(), "nominal_terminal": states[-1].tolist(),
            "nonlinear_terminal": saved[-1].tolist(), "first_inferred_action": float(control[0]),
            "inferred_action_range": [float(control.min()), float(control.max())],
            "control_channel_error": float(np.max(np.abs(control-np.diff(states[:, 2])/b[2]))),
            "recurrence_max_absolute": float(np.max(np.abs(recurrence))),
            "algebraic_stock_difference_max": float(np.max(np.abs(stock_difference))),
            "inferred_step_range": [float(inferred_steps.min()), float(inferred_steps.max())],
            "flow_ranges": [[float(states[:, i].min()), float(states[:, i].max())] for i in (0, 2)],
            "nominal_objective": objective(states[-1]), "nonlinear_objective": objective(saved[-1]),
            "replay_error_by_coordinate": np.max(np.abs(replayed-saved), axis=0).tolist(),
            "initial_stock_invariant": float(12*(states[0, 1]-100*states[0, 0])+23*(states[0, 3]-100*states[0, 2])),
            "terminal_stock_invariant": float(12*states[-1, 1]+23*states[-1, 3]),
        })
    matrix = [[float(np.max(np.abs(replayed-saved))) for saved in nonlinear] for replayed in replays]
    printed_frozen = np.array([1190.4, 101.7, 455.12, -72.817])
    half_units = np.array([0.05, 0.05, 0.005, 0.0005])
    corners = np.array([printed_frozen+half_units*np.array(signs)
                        for signs in itertools.product((-1, 1), repeat=4)])
    corner_objectives = [objective(corner) for corner in corners]
    # Gradients of Phi^2 are affine. Fixed signs at all box corners imply
    # fixed signs throughout, so objective extrema occur at corners.
    gradients = np.array([[2*(x[0]-1200), 4*x[1]-16/3*x[3],
                           128/9*(x[2]-450), 256/9*x[3]-16/3*x[1]] for x in corners])
    fixed_signs = bool(np.all(np.logical_or(gradients.min(axis=0) > 0, gradients.max(axis=0) < 0)))
    frozen_result = {"terminal": frozen[-1].tolist(), "initial": frozen[0].tolist(),
                     "objective": objective(frozen[-1]), "printed_objective": 368.45,
                     "objective_from_printed_coordinates": objective(printed_frozen),
                     "rounding_box_objective_range": [min(corner_objectives), max(corner_objectives)],
                     "rounding_box_gradient_signs_fixed": fixed_signs,
                     "first_stock_offset_divided_by_first_flow": [
                         float((119500-frozen[0, 1])/frozen[0, 0]),
                         float((45300-frozen[0, 3])/frozen[0, 2])]}
    no_last = controls[0].copy()
    no_last[-1] = 0
    last_effect = (replays[0][-1]-replay(no_last)[-1]).tolist()
    free_terminal = np.linalg.matrix_power(a, 16)@nominal[0][0]
    moment_map = np.array([[b[0], 0], [0, -step*b[0]], [b[2], 0], [0, -step*b[2]]])
    weights = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 8/3, 0],
                        [0, 0, 0, 8/3], [0, 1, 0, -8/3]])
    weighted_map = weights@moment_map
    moments = np.linalg.solve(weighted_map.T@weighted_map,
                              -weighted_map.T@weights@(free_terminal-np.array([1200, 0, 450, 0])))
    ideal = free_terminal+moment_map@moments
    conditional = {"assumption": "Fixed saved x0, sourced B, inferred h=6.25; no admissibility certificate",
                   "moments": moments.tolist(), "terminal": ideal.tolist(), "objective": objective(ideal),
                   "observed_terminal_errors": [(x[-1]-ideal).tolist() for x in nominal],
                   "observed_objective_differences": [objective(x[-1])-objective(ideal) for x in nominal]}

    def within_rounding(actual, printed, half_width):
        return bool(np.all(np.abs(np.array(actual)-printed) <= half_width))

    nominal_rounding = all(within_rounding(x[-1], [1200.7, -22.929, 450.2, -7.709],
                                         [0.05, 0.0005, 0.05, 0.0005]) for x in nominal)
    nonlinear_rounding = all(within_rounding(x[-1], printed, widths) for x, printed, widths in zip(
        nonlinear, [[1200.5, -2.695, 449.72, 10.556], [1200.5, 0.50887, 449.72, 17.561],
                    [1200.5, -6.366, 449.72, -1.475]],
        [[0.05, 0.0005, 0.005, 0.0005], [0.05, 0.000005, 0.005, 0.0005], [0.05, 0.0005, 0.005, 0.0005]]))
    # Operational regression tolerances, not validated numerical enclosures.
    checks = {
        "nominal_recurrence": all(w["recurrence_max_absolute"] <= 1e-10 for w in witnesses),
        "independent_control_channels": all(w["control_channel_error"] <= 1e-12 for w in witnesses),
        "inferred_stock_step": all(abs(v-step) <= 1e-12 for w in witnesses for v in w["inferred_step_range"]),
        "all_sample_replay": all(matrix[i][i] <= 2e-12 for i in range(3)),
        "distinct_pairings": all(matrix[i][j] > 500 for i in range(3) for j in range(3) if i != j),
        "optimal_coordinates_round_to_table": nominal_rounding and nonlinear_rounding,
        "optimal_objectives_round_to_table": all(abs(w["nominal_objective"]-30.899) <= 0.0005 and
            abs(w["nonlinear_objective"]-printed) <= 0.0005 for w, printed in zip(witnesses, [41.855, 65.874, 7.922])),
        "frozen_coordinates_round_to_table": within_rounding(frozen[-1], printed_frozen, half_units),
        "frozen_printed_objective_excluded": fixed_signs and min(corner_objectives) > 368.455,
        "last_increment_leaves_terminal_stocks_unchanged": last_effect[1] == 0 and last_effect[3] == 0,
        "conditional_minimum_agrees_at_floating_precision": all(abs(v) <= 1e-8 for v in conditional["observed_objective_differences"]),
    }
    checks["all_passed"] = all(checks.values())
    events = [{"matlab_sample": i*625+1, "time_seconds": i*6.25, "increment_number": i} for i in range(1, 16)]
    events.append({"matlab_sample": 10000, "time_seconds": 99.99, "increment_number": 16})
    return {"variant_id": VARIANT, "scope": "saved-witness/replay evidence", "executable_scenario": False,
            "numerical_status": "floating calculations; not a validated certificate or constrained optimizer",
            "scalar_samples_compared": 120000, "witnesses": witnesses,
            "replay_pair_max_error_matrix": matrix, "replay_events": events,
            "frozen": frozen_result, "last_increment_effect_on_final_sample": last_effect,
            "zero_increment_replay_terminal": replay(np.zeros(16))[-1].tolist(),
            "zero_increment_replay_objective": objective(replay(np.zeros(16))[-1]),
            "conditional_affine_minimum": conditional, "checks": checks,
            "environment": {"python": sys.version.split()[0], "numpy": np.__version__, "scipy": scipy.__version__}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("figure", "kernel", "driver"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("article", "image", "output"):
        parser.add_argument("--" + name, type=Path)
    arguments = parser.parse_args()
    try:
        figure, integrity = read_sources(arguments)
        result = calculate(figure)
        result["source_integrity"] = integrity
        rendered = json.dumps(result, indent=2, allow_nan=False) + "\n"
        if arguments.output:
            arguments.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    except ImportError as exc:
        parser.error(f"install NumPy and SciPy in the active Python environment: {exc}")
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        parser.error(str(exc))
    return 0 if result["checks"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
