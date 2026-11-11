#!/usr/bin/env python3
"""Compare the CSL replay bridge with an independent fixed-step RK4 replay."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import tempfile

from contracts import load_task, manifest_sha256
from task_models import make_replay_request


def derivative(case: str, parameters: dict, x: list[float], u: list[float]) -> list[float]:
    if case == "SYN-NL-LV-01":
        p, r = x
        q = {k: v["value"] for k, v in parameters.items()}
        return [(q["a"] - q["b"] * r - u[0]) * p, (q["d"] * p - q["c"]) * r]
    if case == "SYN-NL-FUEL-01":
        mox, mf, qox, qf = x
        q = {k: v["value"] for k, v in parameters.items()}
        return [-qox, -qf,
                (q["Q_ox"] * u[0] * math.sqrt(mox / q["m_ox0"]) - qox) / q["tau_ox"],
                (q["Q_f"] * u[1] * math.sqrt(mf / q["m_f0"]) - qf) / q["tau_f"]]
    r, v, theta, omega = x
    q = {k: p["value"] for k, p in parameters.items()}
    mu = q["G"] * q["M_earth"]
    mass = q["m_vehicle"]
    return [v, r * omega * omega - mu / (r * r) + u[0] / (1000 * mass), omega,
            -2 * omega * v / r + u[1] / (1000 * mass * r)]


def add(x, dx, scale):
    return [a + scale * b for a, b in zip(x, dx)]


def rk4_step(case, params, x, u, h):
    k1 = derivative(case, params, x, u)
    k2 = derivative(case, params, add(x, k1, h / 2), u)
    k3 = derivative(case, params, add(x, k2, h / 2), u)
    k4 = derivative(case, params, add(x, k3, h), u)
    return [v + h * (a + 2 * b + 2 * c + d) / 6 for v, a, b, c, d in zip(x, k1, k2, k3, k4)]


def independent_cost(task, states, controls, source):
    case=task["model"]["case_id"];n=task["episode"]["intervals"]
    if case in {"SYN-NL-LV-01","SYN-NL-FUEL-01"}:
        objective=source["objective"];x=states[-1]
        terminal=sum(w*((v-target)/scale)**2 for w,v,target,scale in zip(
            objective["terminal_weights"],x,objective["terminal_target"],objective["terminal_scale"]))
        refs=[]
        if case=="SYN-NL-LV-01":refs=[[0.0] for _ in controls]
        else:
            p={k:v["value"] for k,v in source["parameters"].items()};dt=task["episode"]["dt"]
            for k in range(n):
                t=(k+.5)*dt
                refs.append([2/(p["Q_ox"]*math.sqrt((100-2*t)/p["m_ox0"])),
                             .6/(p["Q_f"]*math.sqrt((30-.6*t)/p["m_f0"]))])
        running=objective["running_weight"]/n*sum(
            ((u[i]-refs[k][i])/objective["running_scale"][i])**2
            for k,u in enumerate(controls) for i in range(len(u)))
    else:
        x=states[-1]
        source_mu=6.67448478e-20*5.9726e24
        target_rate=math.sqrt(source_mu/6900.0**3)
        terminal=math.hypot(6900.0-x[0],100000*(target_rate-x[3]))
        running=.001*task["episode"]["dt"]*sum(math.hypot(*u) for u in controls[:-1])
    return {"terminal":terminal,"running":running,"total":terminal+running}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge", required=True, type=Path)
    args = parser.parse_args()
    fixture_controls = {"syn-nl-lv-01": [0.025], "syn-nl-fuel-01": [0.5, 0.5], "earth-orbit": [0.1, -0.2]}
    rows=[]
    for name, control in fixture_controls.items():
        task=load_task(name);source=None;n=task["episode"]["intervals"];sub=20
        controls=[control[:] for _ in range(n)]
        task_hash=manifest_sha256(task)
        request=make_replay_request(task,controls,manifest_sha256({"task":task_hash,"controls":controls}))
        source=request["scenario"]
        with tempfile.TemporaryDirectory(prefix="csl-task-check-") as directory:
            request_path=Path(directory)/"request.json"
            request_path.write_text(json.dumps(request,allow_nan=False))
            actual=json.loads(subprocess.run([str(args.bridge),str(request_path)],check=True,capture_output=True,text=True).stdout)
        assert actual["status"]=="complete",(name,actual["status"])
        x=[s["initial"] for s in task["model"]["states"]];expected=[x[:]]
        inner=100;h=task["episode"]["dt"]/inner
        for u in controls:
            for _ in range(inner):x=rk4_step(task["model"]["case_id"],source["parameters"],x,u,h)
            expected.append(x[:])
        for k,reference in enumerate(expected):
            observed=actual["physical_states"][k*sub]
            for a,b in zip(reference,observed):
                assert abs(a-b)<=2e-7*max(1.0,abs(a)),(name,k,a,b)
        costs=independent_cost(task,actual["physical_states"],controls,source)
        assert abs(costs["terminal"]-actual["terminal_objective"])<=1e-12*max(1.0,abs(costs["terminal"])),name+" terminal cost"
        rows.append({"task_id":task["task_id"],"status":"independent-RK4-replay-matched",
                     "hold_endpoints_checked":len(expected),"physical_objective":costs,"task_sha256":task_hash})
    print(json.dumps({"status":"pass","checks":rows},indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
