"""Independent floating-point check of the discrete B08 formulation in L04.
Requires NumPy. Does not reproduce the nonlinear plant or MATLAB runtime.
"""
import itertools
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
T = 4
A = np.array([[1., 0., 0., 0.], [-25., 1., 0., 0.],
              [0., 0., 1., 0.], [0., 0., -25., 1.]])
B = np.array([20.073, 0., -10.473, 0.])
E = np.array([[1., 0.], [0., 0.], [0., -1.], [0., 0.]])
x0 = np.array([1182.074, 119560., 459.832, 45260.])
target = np.array([1200., 0., 450., 0.])
actions = [0.6, 0.3, 0., -0.3, -0.6]
generators = np.concatenate([
    np.linalg.matrix_power(A, T-1-t) @ E @
    np.diag([0.1+0.1*t, 0.1+0.3*t]) for t in range(T)
], axis=1)
signs = np.array(list(itertools.product([-1., 1.], repeat=2*T)))
offsets = signs @ generators.T
plans = np.array(list(itertools.product(actions, repeat=T)))
centers = np.repeat(x0[None, :], len(plans), axis=0)
for t in range(T):
    centers = centers @ A.T + plans[:, t, None] * B
scores = np.linalg.norm(centers[:, None, :] + offsets[None, :, :]
                        - target, axis=2).max(axis=1)
best = int(np.argmin(scores))
published_plan = [0.6, 0.6, -0.3, 0.]
published_idx = next(i for i,p in enumerate(plans)
                     if np.allclose(p, published_plan, rtol=0., atol=1e-12))
nonlinear_display = np.array([1200.139, -2.294, 450.406, -16.254])
adaptive_display = np.array([60., 20.3, 24., 4.5])
report = {
    "kind": "independent floating-point reference from transcribed discrete model",
    "baseline": "B08", "source": "L04 PDF pages 12-13",
    "method": "enumerate all finite plans and all box-corner images; convex norm attains maximum on a box at a corner",
    "numpy": np.__version__, "plans": len(plans),
    "disturbance_box_corner_images_per_plan": len(signs),
    "best_plan": plans[best].tolist(),
    "computed_discrete_minimax": float(scores[best]),
    "tie_absolute_tolerance": 1e-8,
    "plans_tied_within_tolerance": plans[scores <= scores[best]+1e-8].tolist(),
    "reported_discrete_minimax": 67.12,
    "reported_plan": published_plan,
    "computed_cost_of_reported_plan": float(scores[published_idx]),
    "nonlinear_displayed_state_euclidean_cost": float(np.linalg.norm(nonlinear_display-target)),
    "reported_nonlinear_cost": 14.048,
    "L13_adaptive_displayed_state_euclidean_cost": float(np.linalg.norm(adaptive_display-[60.,0.,24.,0.])),
    "L13_reported_adaptive_cost": 22.657,
    "limitations": [
        "Uses rounded displayed matrices/state, not original MATLAB arrays.",
        "No validated rounding enclosure; mathematical exhaustive formulation, floating arithmetic.",
        "Does not reproduce nonlinear dynamics, plots, historical runtime, or other article versions."
    ]
}
out = ROOT / "docs/research/reference-b08.json"
out.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
print(json.dumps(report, indent=2))
