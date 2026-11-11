#!/usr/bin/env python3
"""Small independent checks for the three source-bound task adapters."""
from __future__ import annotations

import copy
import json
import math
import sys

import numpy as np

from contracts import canonical_sha256, load_task, manifest_sha256
from task_models import (continuous_jacobian, make_replay_request, objective,
                         physical_dynamics, prediction_receipt, source_scenario,
                         validate_source_binding)


def finite_difference(task, x, u):
    a = np.empty((len(x), len(x))); b = np.empty((len(x), len(u)))
    for j in range(len(x)):
        h = 1e-6 * max(1.0, abs(x[j]))
        plus=x.copy();minus=x.copy();plus[j]+=h;minus[j]-=h
        a[:,j]=(physical_dynamics(task,plus,u)-physical_dynamics(task,minus,u))/(2*h)
    for j in range(len(u)):
        h=1e-6
        plus=u.copy();minus=u.copy();plus[j]+=h;minus[j]-=h
        b[:,j]=(physical_dynamics(task,x,plus)-physical_dynamics(task,x,minus))/(2*h)
    return a,b


def main() -> int:
    cases = {
        "syn-nl-lv-01": (np.array([143.0, 47.0]), np.array([0.017])),
        "syn-nl-fuel-01": (np.array([91.0, 26.0, 1.8, 0.49]), np.array([0.31, 0.67])),
        "earth-orbit": (np.array([7130.0, 0.012, 0.2, 0.0011]), np.array([0.21, -0.17])),
    }
    results=[]
    for key,(x,u) in cases.items():
        task=load_task(key);validate_source_binding(task)
        a,b=continuous_jacobian(task,x,u);fd_a,fd_b=finite_difference(task,x,u)
        assert np.allclose(a,fd_a,rtol=2e-6,atol=2e-8), key+" state Jacobian"
        assert np.allclose(b,fd_b,rtol=2e-6,atol=2e-8), key+" input Jacobian"
        receipt=prediction_receipt(task)
        if key=="earth-orbit":
            assert np.asarray(receipt["physical_coefficients"]["A"]).shape==(4,4)
            assert receipt["model_id"]=="env717-earth-orbit/local-tangent-zoh/1"
            assert task["legacy_source_case"]["schedule"]["plan_count"]==729
            scales=np.asarray([row["scale"] for row in task["model"]["states"]])
            control_scales=np.asarray([max(abs(value) for value in row["bounds"]) for row in task["model"]["controls"]])
            physical=receipt["physical_coefficients"];scaled=receipt["scaled_coefficients"]
            assert np.allclose(scaled["A"],np.asarray(physical["A"])*scales[None,:]/scales[:,None])
            assert np.allclose(scaled["B"],np.asarray(physical["B"])*control_scales[None,:]/scales[:,None])
        else:
            authored=receipt["physical_coefficients"]
            assert len(authored)==task["episode"]["intervals"]
            refs=np.asarray(receipt["state_references"])
            uref=np.asarray(receipt["input_references"])[0]
            source_x=(refs[0]+refs[1])/2 if key=="syn-nl-fuel-01" else refs[0]
            source_u=uref
            point_a,point_b=continuous_jacobian(task,source_x,source_u)
            assert np.allclose(point_a,authored[0]["jacobian_A"],rtol=1e-12,atol=1e-12)
            assert np.allclose(point_b,authored[0]["jacobian_B"],rtol=1e-12,atol=1e-12)
            scaled=receipt["scaled_coefficients"][0]
            state_scale=np.asarray(receipt["state_scale"]);control_scale=np.asarray(receipt["control_scale"])
            assert np.allclose(scaled["A"],np.asarray(authored[0]["A"])*state_scale[None,:]/state_scale[:,None])
            assert np.allclose(scaled["B"],np.asarray(authored[0]["B"])*control_scale[None,:]/state_scale[:,None])
        assert task["control_domains"]["continuous"]["problem_id"] != task["control_domains"]["finite"]["problem_id"]
        assert task["roles"]["policy_trajectory"]=="one-deterministic-policy-trajectory"
        for query in task["roles"]["off_trajectory_query_fixtures"]:
            query_x=np.asarray(query["state"]);query_u=np.asarray(query["control"])
            physical_dynamics(task,query_x,query_u)
        results.append({"task_id":task["task_id"],"task_sha256":manifest_sha256(task),"jacobian":"pass","prediction":"pass"})

    lv=load_task("syn-nl-lv-01")
    x=np.array([s["initial"] for s in lv["model"]["states"]]);u=np.zeros((lv["episode"]["intervals"],1));states=np.tile(x,(len(u)+1,1))
    value=objective(lv,states,u)
    expected=((x[0]-100)/100)**2+((x[1]-80)/80)**2
    assert abs(value["terminal"]-expected)<1e-15 and value["running"]==0
    fuel=load_task("syn-nl-fuel-01")
    assert fuel["coordinate_maps"]["projections"][0]["indices"]==[0,2]
    assert fuel["coordinate_maps"]["projections"][1]["indices"]==[1,3]
    assert fuel["legacy_source_cases"][0]["task_id"]!="syn-nl-fuel-01/continuous-receding/1"
    xf=np.array([s["initial"] for s in fuel["model"]["states"]]);uf=np.zeros((fuel["episode"]["intervals"],2));sf=np.tile(xf,(len(uf)+1,1))
    fuel_value=objective(fuel,sf,uf);fo=fuel["objective"]["source_definition"]
    fuel_terminal=sum(w*((xv-t)/scale)**2 for xv,t,scale,w in zip(xf,fo["terminal_target"],fo["terminal_scale"],fo["terminal_weights"]))
    refs=[]
    for k in range(fuel["episode"]["intervals"]):
        t=(k+.5)*fuel["episode"]["dt"]
        refs.append([2/(3*math.sqrt((100-2*t)/100)),.6/math.sqrt((30-.6*t)/30)])
    fuel_running=fo["running_weight"]/fuel["episode"]["intervals"]*sum(sum(v*v for v in row) for row in refs)
    assert abs(fuel_value["terminal"]-fuel_terminal)<1e-14
    assert abs(fuel_value["running"]-fuel_running)<1e-14
    try:physical_dynamics(fuel,[ -1, 30, 2, .6],[.5,.5])
    except ValueError:pass
    else:raise AssertionError("negative fuel mass was admitted")
    orbit=load_task("earth-orbit")
    xo=np.array([s["initial"] for s in orbit["model"]["states"]]);uo=np.tile([.2,.3],(orbit["episode"]["intervals"],1));so=np.tile(xo,(len(uo)+1,1))
    orbit_value=objective(orbit,so,uo)
    source_mu=6.67448478e-20*5.9726e24
    source_target_rate=math.sqrt(source_mu/6900.0**3)
    assert orbit["objective"]["target"]=={"radius_km":6900.0,"angular_rate_rad_s":source_target_rate}
    orbit_terminal=math.hypot(6900.0-xo[0],100000*(source_target_rate-xo[3]))
    orbit_running=.001*orbit["episode"]["dt"]*(len(uo)-1)*math.hypot(.2,.3)
    assert abs(orbit_value["terminal"]-orbit_terminal)<1e-12
    assert abs(orbit_value["running"]-orbit_running)<1e-12
    last_stage_only=np.zeros_like(uo);last_stage_only[-1]=[.2,.3]
    assert objective(orbit,so,last_stage_only)["running"]==0
    orbit_as_mpc11=copy.deepcopy(source_scenario(lv));orbit_as_mpc11["case_id"]=orbit["model"]["case_id"]
    try:
        import affine
        affine.model(orbit_as_mpc11)
    except ValueError:pass
    else:raise AssertionError("the MPC11 affine builder must reject Earth-orbit")
    try:physical_dynamics(orbit,[0,0,0,.001],[0,0])
    except ValueError:pass
    else:raise AssertionError("nonpositive orbit radius was admitted")
    for field,value in (("objective.target.radius_km",6901.0),("model.states[0].initial",7001.0)):
        changed=copy.deepcopy(orbit)
        if field=="objective.target.radius_km":changed["objective"]["target"]["radius_km"]=value
        else:changed["model"]["states"][0]["initial"]=value
        try:validate_source_binding(changed)
        except ValueError:pass
        else:raise AssertionError("Earth-orbit source association admitted changed "+field)
    for task in (lv,fuel,orbit):
        n=task["episode"]["intervals"];u=np.zeros((n,len(task["model"]["controls"]))).tolist()
        request=make_replay_request(task,u,"fixture-witness")
        assert request["task_sha256"]==manifest_sha256(task)
        assert request["scenario_sha256"]==canonical_sha256(request["scenario"])
        assert len(request["original_controls"])==n
    invalid=copy.deepcopy(lv);invalid["model"]["states"].pop()
    try:
        from contracts import validate_task
        validate_task(invalid)
    except (ValueError,KeyError):pass
    else:raise AssertionError("wrong state dimension was admitted")
    invalid=copy.deepcopy(lv);invalid["model"]["states"][0]["unit"]=""
    try:validate_task(invalid)
    except (ValueError,KeyError):pass
    else:raise AssertionError("missing state units were admitted")
    invalid=copy.deepcopy(lv);invalid["source"]["sha256"]="0"*64
    try:validate_source_binding(invalid)
    except ValueError:pass
    else:raise AssertionError("source association mismatch was admitted")
    try:make_replay_request(lv,[[.1] for _ in range(lv["episode"]["intervals"])],"fixture-witness")
    except ValueError:pass
    else:raise AssertionError("out-of-bounds physical control was admitted")
    print(json.dumps({"status":"pass","checks":results,"physical_objective":"independent LV, fuel and orbit checks pass",
                      "model_domains":"fuel and orbit rejection pass","replay_requests":"three source-bound tasks pass"},indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
