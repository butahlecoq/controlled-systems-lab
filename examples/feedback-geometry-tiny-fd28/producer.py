"""Capture source-qualified real family geometry and original-cost tiny queries."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(os.environ["CSL_CAPTURE_SOURCE_ROOT"])
binary = Path(os.environ["CSL_CAPTURE_BINARY"])
output = Path(os.environ["CSL_CAPTURE_OUTPUT"])
output.mkdir(exist_ok=False)
sys.path.insert(0, str(root / "benchmarks/reporting/closed_loop"))
import numpy as np
from history_policy import geometry_memberships
from history_norm_solver import solve

request = {"mode": "continuous-history/1", "history_solver": "casadi-ipopt",
    "task_id": "analytic", "task_sha256": "analytic", "problem_id": "analytic",
    "request_id": "analytic", "controller_id": "analytic", "action_profile_id": "continuous",
    "absolute_update_index": 0, "original_horizon": 1, "dt": 1,
    "observed_physical_state": [0, 0],
    "predictor_stages": [{"A": [[1, 0], [0, 1]], "B": [[1, 0], [0, 1]], "c": [0, 0]}],
    "state_bounds": [None, None], "control_bounds": [[-2, 2], [-2, 2]],
    "terminal_objective": {"kind": "quadratic", "Q": [[2, 0], [0, 2]], "linear": [-2, 0], "offset": 1},
    "running_cost": {"objective_id": "analytic-cost", "stages": [
        {"stage": 0, "terms": [{"kind": "quadratic", "reference": [0, 0],
            "scales": [1, 1], "weights": [1, 1], "coefficient": 2}]}]},
    "geometry_max_generators": 1000}
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
results = {}
for family in ("polytope", "box", "zonotope", "parallelotope", "ellipsoid"):
    directory = output / family
    directory.mkdir()
    request["geometry_family"] = family
    request_path = directory / "request.jsonl"
    request_path.write_text(json.dumps(request, separators=(",", ":")) + chr(10))
    process = subprocess.run([str(binary)], input=request_path.read_bytes(), capture_output=True)
    (directory / "response.jsonl").write_bytes(process.stdout)
    (directory / "stderr.txt").write_bytes(process.stderr)
    if process.returncode:
        raise RuntimeError(f"{family} native exit {process.returncode}")
    response = json.loads(process.stdout)
    if response.get("status") != "exported":
        raise RuntimeError(f"{family} native stop: {response}")
    geometry = response["geometry"]
    memberships = geometry_memberships(geometry, family, 2, 1)
    result = solve(response["history_relation"], response["history_objective"],
                   initial=[0]*6, geometry_memberships=memberships)
    (directory / "solver-result.json").write_text(json.dumps(result, indent=2) + chr(10))
    if not result["success"]:
        raise RuntimeError(f"{family} optimizer failed: {result}")
    z = np.asarray(result["primal"])
    h = response["history_relation"]
    lhs = max([0.] + [abs(float(np.dot(row,z))-v) for row,v in zip(h["equalities"], h["equality_values"])])
    violation = max([0.] + [float(np.dot(row,z))-v for row,v in zip(h["inequalities"], h["upper_bounds"])])
    original_cost = float((z[2]-1)**2 + z[3]**2 + 2*(z[4]**2+z[5]**2))
    if (lhs > 1e-7 or violation > 1e-7 or abs(original_cost-result["objective"]) > 1e-7
            or abs(z[2]-1/3) > 1e-5 or abs(z[3]) > 1e-5):
        raise RuntimeError(f"{family} source history or source cost check failed")
    certificate_count = 0
    for stage in geometry["stages"]:
        for member in stage["memberships"]:
            hset = stage[member["role"] + "_h"]
            for cert in member["support_certificates"]:
                if cert["input_set"] != hset["set_id"]:
                    raise RuntimeError("support certificate input ID differs from retained H")
                A = np.asarray(hset["inequalities"], dtype=float).reshape(-1, 2)
                E = np.asarray(hset["equalities"], dtype=float).reshape(-1, 2)
                lam = np.asarray(cert["inequality_multipliers"])
                mu = np.asarray(cert["equality_multipliers"])
                residual = np.asarray(cert["direction"]) - A.T @ lam - E.T @ mu
                replay = (lam @ np.asarray(hset["upper_bounds"]) + mu @ np.asarray(hset["equality_values"])
                    + np.maximum(residual * cert["carrier_lower"], residual * cert["carrier_upper"]).sum())
                if np.any(lam < 0) or replay > cert["bound"] + 1e-9 * (1 + abs(replay)):
                    raise RuntimeError("support certificate replay failed")
                certificate_count += 1
    providers = sorted({call["actual"] for m in memberships for call in m["providers"] if call["actual"]})
    support_providers = sorted({call["actual"] for m in memberships for call in m["support_calls"] if call["actual"]})
    results[family] = {"primal": z.tolist(), "original_cost": original_cost, "max_H_equality": lhs,
        "max_H_inequality": violation, "certificate_count": certificate_count, "geometry_providers": providers,
        "support_providers": support_providers, "geometry_validation": result["geometry_validation"],
        "files": {path.name: digest(path) for path in sorted(directory.iterdir())}}
(output / "independent-audit.json").write_text(json.dumps(results, indent=2) + chr(10))
print(json.dumps({k: {"cost": v["original_cost"], "certificates": v["certificate_count"]}
                  for k,v in results.items()}, indent=2))
