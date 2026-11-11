"""Common physical model, cost, prediction, and replay request adapters."""
from __future__ import annotations

import json
import hashlib
import math
import sys

from contracts import ROOT, canonical_sha256, source_sha256

MPC11 = ROOT / "benchmarks/reporting/mpc11"
if str(MPC11) not in sys.path:
    sys.path.insert(0, str(MPC11))

def source_scenario(task: dict) -> dict:
    if task["source"]["kind"] != "mpc11-scenario":
        raise ValueError("task has no MPC11 source scenario")
    return json.loads((ROOT / task["source"]["path"]).read_text())


def _ids(task: dict) -> tuple[str, str]:
    return task["model"]["case_id"], task["model"]["model_id"]


def physical_dynamics(task: dict, state, control) -> np.ndarray:
    import numpy as np
    x = np.asarray(state, dtype=float)
    u = np.asarray(control, dtype=float)
    model = task["model"]
    if x.shape != (len(model["states"]),) or u.shape != (len(model["controls"]),):
        raise ValueError("state or control dimension differs from task coordinates")
    if not np.isfinite(x).all() or not np.isfinite(u).all():
        raise ValueError("state and control values must be finite")
    case, _ = _ids(task)
    p = {name: row["value"] for name, row in model["parameters"].items()}
    if case == "SYN-NL-LV-01":
        prey, predator = x
        return np.array([(p["a"] - p["b"] * predator - u[0]) * prey,
                         (p["d"] * prey - p["c"]) * predator])
    if case == "SYN-NL-FUEL-01":
        mox, mf, qox, qf = x
        if mox < 0 or mf < 0:
            raise ValueError("fuel model domain requires nonnegative propellant masses")
        return np.array([-qox, -qf,
                         (p["Q_ox"] * u[0] * math.sqrt(mox / p["m_ox0"]) - qox) / p["tau_ox"],
                         (p["Q_f"] * u[1] * math.sqrt(mf / p["m_f0"]) - qf) / p["tau_f"]])
    if case == "ENV717-EARTH-ORBIT-CONTINUOUS-01":
        radius, radial_velocity, _, angular_rate = x
        if radius <= 0:
            raise ValueError("orbit model domain requires positive radius")
        mu = p["G"] * p["M_earth"]
        mass = p["m_vehicle"]
        return np.array([radial_velocity,
                         radius * angular_rate**2 - mu / radius**2 + u[0] / (1000 * mass),
                         angular_rate,
                         -2 * angular_rate * radial_velocity / radius + u[1] / (1000 * mass * radius)])
    raise ValueError(f"unsupported physical model {case}")


def continuous_jacobian(task: dict, state, control) -> tuple[np.ndarray, np.ndarray]:
    import numpy as np
    x = np.asarray(state, dtype=float)
    u = np.asarray(control, dtype=float)
    f = physical_dynamics(task, x, u)
    case, _ = _ids(task)
    p = {name: row["value"] for name, row in task["model"]["parameters"].items()}
    if case == "SYN-NL-LV-01":
        prey, predator = x
        a = np.array([[p["a"] - p["b"] * predator - u[0], -p["b"] * prey],
                      [p["d"] * predator, p["d"] * prey - p["c"]]])
        b = np.array([[-prey], [0.0]])
    elif case == "SYN-NL-FUEL-01":
        mox, mf, qox, qf = x
        a = np.zeros((4, 4)); b = np.zeros((4, 2))
        a[0, 2] = a[1, 3] = -1
        a[2, 0] = p["Q_ox"] * u[0] / (2 * p["tau_ox"] * p["m_ox0"] * math.sqrt(mox / p["m_ox0"]))
        a[2, 2] = -1 / p["tau_ox"]
        b[2, 0] = p["Q_ox"] * math.sqrt(mox / p["m_ox0"]) / p["tau_ox"]
        a[3, 1] = p["Q_f"] * u[1] / (2 * p["tau_f"] * p["m_f0"] * math.sqrt(mf / p["m_f0"]))
        a[3, 3] = -1 / p["tau_f"]
        b[3, 1] = p["Q_f"] * math.sqrt(mf / p["m_f0"]) / p["tau_f"]
    elif case == "ENV717-EARTH-ORBIT-CONTINUOUS-01":
        r, v, _, omega = x
        mu = p["G"] * p["M_earth"]; mass = p["m_vehicle"]
        a = np.array([[0, 1, 0, 0],
                      [omega**2 + 2 * mu / r**3, 0, 0, 2 * r * omega],
                      [0, 0, 0, 1],
                      [2 * omega * v / r**2 - u[1] / (1000 * mass * r**2), -2 * omega / r, 0, -2 * v / r]])
        b = np.array([[0, 0], [1 / (1000 * mass), 0], [0, 0], [0, 1 / (1000 * mass * r)]])
    else:
        raise ValueError(f"unsupported Jacobian for {case}")
    if not np.isfinite(f).all() or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("model or Jacobian is nonfinite in the declared domain")
    return a, b


def objective(task: dict, states, controls) -> dict:
    import numpy as np
    x = np.asarray(states, dtype=float)
    u = np.asarray(controls, dtype=float)
    n = task["episode"]["intervals"]
    nx, nu = len(task["model"]["states"]), len(task["model"]["controls"])
    if x.shape != (n + 1, nx) or u.shape != (n, nu):
        raise ValueError("objective requires a complete state and control history")
    if not np.isfinite(x).all() or not np.isfinite(u).all():
        raise ValueError("objective inputs must be finite")
    case, _ = _ids(task)
    if case in {"SYN-NL-LV-01", "SYN-NL-FUEL-01"}:
        import affine as mpc11_affine
        source = source_scenario(task)
        spec = source["objective"]
        target = np.asarray(spec["terminal_target"])
        scale = np.asarray(spec["terminal_scale"])
        weights = np.asarray(spec["terminal_weights"])
        terminal = float(np.sum(weights * ((x[-1] - target) / scale) ** 2))
        references = np.asarray(mpc11_affine.model(source)["reference_commands"])
        running = float(spec["running_weight"] / n * np.sum(((u - references) / spec["running_scale"]) ** 2))
    elif case == "ENV717-EARTH-ORBIT-CONTINUOUS-01":
        target = task["objective"]["target"]
        terminal = math.hypot(target["radius_km"] - x[-1, 0],
                              100000 * (target["angular_rate_rad_s"] - x[-1, 3]))
        running = 0.001 * task["episode"]["dt"] * float(np.linalg.norm(u[:n - 1], axis=1).sum())
    else:
        raise ValueError(f"unsupported objective for {case}")
    return {"terminal": terminal, "running": running, "total": terminal + running}


def prediction_receipt(task: dict) -> dict:
    import numpy as np
    import scipy
    case, _ = _ids(task)
    if case in {"SYN-NL-LV-01", "SYN-NL-FUEL-01"}:
        import affine as mpc11_affine
        scenario = source_scenario(task)
        authored = mpc11_affine.model(scenario)
        return {"schema": "csl.closed-loop.prediction-receipt/1", "task_sha256": manifest_sha256(task),
                "model_id": authored["model_id"], "producer": "benchmarks/reporting/mpc11/affine.py:model",
                "discretization_method": scenario["affine"]["discretization"],
                "physical_coefficients": authored["physical_coefficients"],
                "scaled_coefficients": authored["scaled_coefficients"],
                "jacobians": [{"A": row["jacobian_A"], "B": row["jacobian_B"]} for row in authored["physical_coefficients"]],
                "state_references": authored["reference_states"], "input_references": authored["reference_commands"],
                "state_scale": authored["state_scale"], "control_scale": authored["control_scale"],
                "validity": task["prediction"]["validity"], "coefficient_assurance": authored["coefficient_assurance"],
                "linearization_receipt": {"method": scenario["affine"]["linearization"],
                    "state_reference": authored["reference_states"], "input_reference": authored["reference_commands"],
                    "validity": task["prediction"]["validity"]},
                "discretization_receipt": {"method": scenario["affine"]["discretization"],
                    "scipy_version": scipy.__version__, "sample_period": scenario["time"]["dt"],
                    "control_hold": "zero-order hold", "affine_offset_construction": scenario["affine"]["offset_coordinates"]},
                "source_model_sha256": task["source"]["sha256"]}
    x = np.asarray([s["initial"] for s in task["model"]["states"]], dtype=float)
    u = np.zeros(len(task["model"]["controls"]))
    dt = task["episode"]["dt"]
    a, b = continuous_jacobian(task, x, u)
    f = physical_dynamics(task, x, u)
    c = f - a @ x - b @ u
    augmented = np.zeros((len(x) + len(u) + 1, len(x) + len(u) + 1))
    augmented[:len(x), :len(x)] = a
    augmented[:len(x), len(x):len(x) + len(u)] = b
    augmented[:len(x), -1] = c
    from scipy.linalg import expm
    discrete = expm(dt * augmented)
    ad = discrete[:len(x), :len(x)]; bd = discrete[:len(x), len(x):len(x) + len(u)]; cd = discrete[:len(x), -1]
    scales = np.asarray([s["scale"] for s in task["model"]["states"]])
    control_scales = np.asarray([max(abs(v) for v in c["bounds"]) for c in task["model"]["controls"]])
    return {"schema": "csl.closed-loop.prediction-receipt/1", "task_sha256": manifest_sha256(task),
            "model_id": task["prediction"]["affine_model_id"], "producer": task["prediction"]["producer"],
            "discretization_method": "scipy.linalg.expm augmented zero-order-hold matrix exponential",
            "physical_coefficients": {"A": ad.tolist(), "B": bd.tolist(), "c": cd.tolist()},
            "continuous_jacobian_A": a.tolist(), "continuous_jacobian_B": b.tolist(), "affine_offset": c.tolist(),
            "scaled_coefficients": {"A": (ad * scales[None, :] / scales[:, None]).tolist(),
                                    "B": (bd * control_scales[None, :] / scales[:, None]).tolist(),
                                    "c": (cd / scales).tolist()},
            "linearization_state": x.tolist(), "linearization_input": u.tolist(), "discretization_dt": dt,
            "reference_states": [x.tolist()], "reference_inputs": [u.tolist()],
            "validity": task["prediction"]["validity"], "coefficient_assurance": "binary64 numerical matrix exponential; no validated enclosure",
            "linearization_receipt": {"method": "analytic continuous vector-field Jacobian",
                "state_reference": x.tolist(), "input_reference": u.tolist(), "validity": task["prediction"]["validity"]},
            "discretization_receipt": {"method": "augmented zero-order-hold matrix exponential",
                "scipy_version": scipy.__version__, "sample_period": dt, "control_hold": "zero-order hold",
                "linearization_point": "initial physical state and zero input", "linearization_scope": "local tangent only"},
            "source_model_sha256": task["source"]["sha256"]}


def _validate_control(task: dict, control) -> list[float]:
    try:
        u = [float(value) for value in control]
    except (TypeError, ValueError):
        raise ValueError("control coordinates must be finite numbers") from None
    fields = task["model"]["controls"]
    if len(u) != len(fields) or not all(math.isfinite(value) for value in u):
        raise ValueError("control has wrong dimension or a nonfinite coordinate")
    for value, field in zip(u, fields):
        if field["bounds"] is not None and not field["bounds"][0] <= value <= field["bounds"][1]:
            raise ValueError(f"control {field['name']} is outside its physical bounds")
    return u


def replay_scenario(task: dict) -> dict:
    if task["source"]["kind"] == "mpc11-scenario":
        return source_scenario(task)
    model = task["model"]; episode = task["episode"]
    n = episode["intervals"]
    return {"schema": "csl.mpc11.scenario/1", "case_id": model["case_id"], "model_id": model["model_id"],
            "states": [{"name": x["name"], "unit": x["unit"], "initial": x["initial"], "scale": x["scale"]} for x in model["states"]],
            "controls": [{"name": u["name"], "unit": u["unit"], "physical_bounds": u["bounds"]} for u in model["controls"]],
            "parameters": model["parameters"], "time": {"unit": episode["time_unit"], "dt": episode["dt"],
                "intervals": n, "final": episode["final_time"], "grid": [k * episode["dt"] for k in range(n + 1)]},
            "independent_replay": {"report_subintervals_per_hold": 20, "step_attempts_per_hold_interval": 100000,
                "scaled_abstol": 1e-10, "reltol": 1e-9, "sensitivity": {"scaled_abstol": 1e-11, "reltol": 1e-10}},
            "objective": {"target": task["objective"]["target"]}}


def make_replay_request(task: dict, controls, witness_sha256: str, *, sensitivity=False) -> dict:
    n = task["episode"]["intervals"]
    values = [_validate_control(task, row) for row in controls]
    if len(values) != n:
        raise ValueError("replay requires one control per fixed physical interval")
    source = replay_scenario(task)
    settings = source["independent_replay"]
    tol = settings["sensitivity"] if sensitivity else settings
    sub = settings["report_subintervals_per_hold"]
    grid = source["time"]["grid"]
    times = [grid[k] + (grid[k + 1] - grid[k]) * j / sub for k in range(n) for j in range(sub)] + [grid[-1]]
    repeated = [row for row in values for _ in range(sub)]
    scenario_hash = canonical_sha256(source)
    return {"schema": "csl.mpc11.nonlinear-request/1", "scenario": source,
            "scenario_sha256": scenario_hash, "task_sha256": manifest_sha256(task),
            "witness_sha256": witness_sha256, "controls_sha256": canonical_sha256(values),
            "hold": "constant-on-original-interval", "original_controls": values, "controls": repeated, "times": times,
            "initial_scaled": [x["initial"] / x["scale"] for x in task["model"]["states"]],
            "abstol": tol["scaled_abstol"], "reltol": tol["reltol"],
            "max_attempts": settings["step_attempts_per_hold_interval"] // sub,
            "report_subintervals_per_hold": sub}


def manifest_sha256(task: dict) -> str:
    return canonical_sha256(task)


def validate_source_binding(task: dict) -> None:
    if task["source"]["sha256"] != source_sha256(task):
        raise ValueError("source changed since task contract was authored")
    source = source_scenario(task) if task["source"]["kind"] == "mpc11-scenario" else None
    if source is not None:
        expected = task["model"]
        actual_states = [{"name": x["name"], "unit": x["unit"], "initial": x["initial"], "scale": x["scale"], "bounds": x["physical_bounds"]} for x in source["states"]]
        actual_controls = [{"name": x["name"], "unit": x["unit"], "bounds": x["physical_bounds"]} for x in source["controls"]]
        if (expected["case_id"] != source["case_id"] or expected["model_id"] != source["model_id"] or
                expected["equations"] != source["equations"] or expected["parameters"] != source["parameters"] or
                expected["states"] != actual_states or expected["controls"] != actual_controls):
            raise ValueError("task coordinates or equations differ from the pinned source manifest")
        ep = task["episode"]
        if (ep["time_unit"], ep["dt"], ep["intervals"], ep["final_time"]) != (
                source["time"]["unit"], source["time"]["dt"], source["time"]["intervals"], source["time"]["final"]):
            raise ValueError("task time grid differs from the pinned source manifest")
        if task["objective"]["source_definition"] != source["objective"]:
            raise ValueError("task objective differs from the pinned source manifest")
        if (task["objective"]["objective_id"] != source["objective_id"] or
                task["source"]["objective_id"] != source["objective_id"] or
                task["prediction"]["affine_model_id"] != source["affine"]["model_id"]):
            raise ValueError("task objective or predictor identity differs from the pinned source")
        if task["control_domains"]["continuous"]["bounds"] != [c["physical_bounds"] for c in source["controls"]]:
            raise ValueError("continuous control bounds differ from the pinned source")
        for legacy in task.get("legacy_source_cases", []):
            legacy_path=ROOT / legacy["source_path"]
            if hashlib.sha256(legacy_path.read_bytes()).hexdigest() != legacy["source_sha256"]:
                raise ValueError("legacy fuel source case hash mismatch")
            legacy_source=json.loads(legacy_path.read_text())
            if legacy["task_id"]=="csl.fuel-reachability-model/1":
                if (legacy_source["schema"]!=legacy["task_id"] or legacy["state_order"]!=["x1","x2","x3","x4"] or
                        legacy["state_names"]!=legacy_source["state_names"] or legacy["state_units"]!=legacy_source["state_units"] or
                        legacy["control_dimension"]!=1):
                    raise ValueError("linear fuel source identity or coordinates changed")
            elif (legacy["task_id"]!="fuel-four-state-box-control-demo-v1" or
                  legacy["source_path"]!="benchmarks/reporting/stage-projection/examples/fuel-four-state.json" or
                  legacy_source["run_id"]!=legacy["task_id"] or legacy["state_order"]!=["x1","x2","x3","x4"] or
                  legacy["state_names"]!=legacy_source["state_names"] or legacy["state_units"]!=legacy_source["state_units"] or legacy["control_dimension"]!=1):
                raise ValueError("stage-projection linear fuel source identity or coordinates changed")
        if task["model"]["case_id"] == "SYN-NL-FUEL-01":
            if task["coordinate_maps"]["raw_mpc11_state_order"] != ["m_ox", "m_f", "q_ox", "q_f"]:
                raise ValueError("MPC11 nonlinear fuel coordinate order changed")
            pairs = task["coordinate_maps"]["projections"]
            if [(p["indices"], p["names"], p["units"]) for p in pairs] != [
                    ([0, 2], ["m_ox", "q_ox"], ["kg", "kg/s"]),
                    ([1, 3], ["m_f", "q_f"], ["kg", "kg/s"])]:
                raise ValueError("fuel mass/flow projection order or units changed")
            requested = task["coordinate_maps"]["requested_physical_planes"]
            if [(p["indices"], p["names"], p["units"], p["native_mpc11_plane"]) for p in requested] != [
                    ([2, 0], ["q_ox", "m_ox"], ["kg/s", "kg"], "oxidizer-mass-flow"),
                    ([3, 1], ["q_f", "m_f"], ["kg/s", "kg"], "fuel-mass-flow")]:
                raise ValueError("requested fuel flow/mass plane order or units changed")
            note = task["coordinate_maps"]["projection_comparison_note"]
            if "not numerically equivalent" not in note or "absolute propellant mass" not in note:
                raise ValueError("fuel source-case coordinate distinction is missing")
    else:
        raw = (ROOT / task["source"]["path"]).read_text()
        expected_equations = ["dr/dt=v", "dv/dt=r*omega^2-G*M/r^2+u_r/(1000*m_vehicle)",
                              "dtheta/dt=omega", "domega/dt=-2*omega*v/r+u_t/(1000*m_vehicle*r)"]
        expected_parameters = {"G": {"value": 6.67448478e-20, "unit": "km^3 kg^-1 s^-2"},
                               "M_earth": {"value": 5.9726e24, "unit": "kg"},
                               "m_vehicle": {"value": 50.0, "unit": "kg"}}
        if task["model"]["equations"] != expected_equations or task["model"]["parameters"] != expected_parameters:
            raise ValueError("orbit equations or parameters differ from the source-derived contract")
        source_tokens = ["constexpr double sample_period_seconds = 100.0;", "constexpr std::size_t horizon = 20;",
                         "constexpr std::array<std::size_t, 3> block_lengths{7, 7, 6};",
                         "constexpr std::size_t inner_steps = 100;", "constexpr std::array<Action, 9> actions{{",
                         "constexpr double initial_radius_km = 7000.0;", "constexpr double required_orbit_km = 6900.0;",
                         "constexpr double running_action_cost = 0.001;", "std::hypot(action[0], action[1])",
                         "if(stage + 1 == horizon) objective += terminal_cost(state);",
                         "100000.0 * (target_rate - state[3])"]
        if any(token not in raw for token in source_tokens):
            raise ValueError("pinned Earth-orbit source no longer contains the contracted constants or cost")
        if (task["episode"]["dt"], task["episode"]["intervals"], task["episode"]["final_time"]) != (100.0, 20, 2000.0):
            raise ValueError("Earth-orbit task grid differs from its source profile")
        mu = expected_parameters["G"]["value"] * expected_parameters["M_earth"]["value"]
        initial_rate = math.sqrt(mu / 7000.0**3)
        target_rate = math.sqrt(mu / 6900.0**3)
        expected_states = [
            {"name": "r", "unit": "km", "initial": 7000.0, "scale": 1000.0, "bounds": None},
            {"name": "v", "unit": "km/s", "initial": 0.0, "scale": 1.0, "bounds": None},
            {"name": "theta", "unit": "rad", "initial": 0.0, "scale": 1.0, "bounds": None},
            {"name": "omega", "unit": "rad/s", "initial": initial_rate, "scale": 0.001, "bounds": None},
        ]
        expected_controls = [{"name": name, "unit": "N", "bounds": [-0.5, 0.5]} for name in ("u_r", "u_t")]
        if task["model"]["states"] != expected_states or task["model"]["controls"] != expected_controls:
            raise ValueError("orbit state order, units, initial state, or force bounds differ from the source profile")
        if task["objective"]["target"] != {"radius_km": 6900.0, "angular_rate_rad_s": target_rate}:
            raise ValueError("orbit objective target differs from the source pilot")
        if task["objective"]["objective_id"] != "env717-earth-orbit/source-cost-continuous/1":
            raise ValueError("orbit cost identity differs from the source pilot")
        if (task["objective"]["running_formula"] != "0.001*100 seconds*hypot(u_r,u_t) for stages 0 through 18; zero running term at stage 19" or
                task["objective"]["terminal_formula"] != "hypot(6900-r_N,100000*(omega_target-omega_N))" or
                task["objective"]["units"] != "source scalar score; radius contribution km and rate contribution scaled by 100000 s"):
            raise ValueError("orbit objective formula or units differ from the source cost")
        if task["control_domains"]["continuous"]["bounds"] != [[-0.5, 0.5], [-0.5, 0.5]]:
            raise ValueError("orbit continuous force bounds changed")
        expected_actions = [[x, y] for x in (-0.5, 0.0, 0.5) for y in (-0.5, 0.0, 0.5)]
        if task["control_domains"]["finite"]["actions"] != expected_actions:
            raise ValueError("orbit finite per-step catalogue differs from the source force set")
        if task["legacy_source_case"]["schedule"] != {"block_lengths": [7, 7, 6], "decision_count": 3, "plan_count": 729}:
            raise ValueError("Earth-orbit legacy block-plan identity has drifted")
        target_rate = math.sqrt(6.67448478e-20 * 5.9726e24 / 6900.0**3)
        if task["objective"]["objective_id"] != "env717-earth-orbit/source-cost-continuous/1" or task["objective"]["target"]["angular_rate_rad_s"] != target_rate:
            raise ValueError("Earth-orbit terminal target or source objective identity changed")
        if (task["objective"]["running_stage_range"] != [0, 18] or
                task["source"]["execution_profile"] != {"method": "classical fixed-step RK4", "substeps_per_source_hold": 100, "source_hold_seconds": 100.0}):
            raise ValueError("Earth-orbit source running stages or integrator profile changed")
