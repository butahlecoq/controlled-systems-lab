# Three source-bound single-player task contracts

These files pin the physical plant, objective, time grid, observation timing,
and control-domain identities used by the closed-loop pilot. Each JSON file has
a canonical SHA-256 sidecar. The source hash binds the contract to the existing
MPC11 scenario or the Earth-orbit pilot source.

| Contract | Task identity | Source binding | Cost |
| --- | --- | --- | --- |
| `syn-nl-lv-01.json` | `syn-nl-lv-01/continuous-receding/1` | MPC11 `SYN-NL-LV-01`, physical order `(P,R)` | Existing scaled quadratic terminal cost and all 30 effort terms |
| `earth-orbit.json` | `env717-earth-orbit/continuous-receding/1` | `benchmarks/reporting/env717/earth_orbit.cpp` | Source terminal `hypot` and first 19 Euclidean force-norm terms |
| `syn-nl-fuel-01.json` | `syn-nl-fuel-01/continuous-receding/1` | MPC11 `SYN-NL-FUEL-01`, physical order `(m_ox,m_f,q_ox,q_f)` | Existing scaled quadratic terminal cost and all 40 reference-deviation terms |

The fuel contract records native MPC11 axes `(m_ox,q_ox)` at `(0,2)` and
`(m_f,q_f)` at `(1,3)`, with units `(kg, kg/s)`. For the requested
flow-versus-mass plots, use `(q_ox,m_ox)` at `(2,0)` and `(q_f,m_f)` at
`(3,1)`, with units `(kg/s, kg)`. The archived
`csl.fuel-reachability-model/1` and `fuel-four-state-box-control-demo-v1`
examples are separate source cases: their stock-balance coordinates are not
numerically equivalent to MPC11 absolute propellant mass. Keep their source
hashes, coordinate orders, units, and task identities distinct.

Each contract also names a separate finite-action adaptation. This means a
finite catalogue is never silently compared as the same control domain as the
continuous problem. Orbit's `finite-nine-action-per-step-adaptation` chooses a
catalogue action independently at each 100-second interval. It is separate
from the original `finite-nine-action-three-block-plan` source case, whose
decisions are held for `(7,7,6)` intervals and whose 729 plans remain intact.

The common runtime is `benchmarks/reporting/closed_loop/task_models.py`. It
provides the original physical vector field, physical objective, affine
prediction receipt, and an adapter request for the existing
`CSL::simulation` replay bridge. LV and fuel call the actual MPC11 affine
producer. Orbit uses its own analytic Jacobian and augmented matrix
exponential. Neither predictor is described as a nonlinear enclosure. The
orbit source pilot uses 100 classical RK4 substeps per 100-second hold. The
common replay uses CSL adaptive RK4 step doubling, so the contract records
that execution change and makes no equivalence claim.

After building `csl_mpc11_nonlinear_replay` using the existing MPC11 CMake
instructions, run the same fixture entry point for each task:

```sh
python3 benchmarks/reporting/closed_loop/run_task.py \
  --task syn-nl-lv-01 --control 0 \
  --bridge <BUILD_DIR>/csl_mpc11_nonlinear_replay \
  --output /tmp/lv-fixture.json

python3 benchmarks/reporting/closed_loop/run_task.py \
  --task earth-orbit --control 0,0 \
  --bridge <BUILD_DIR>/csl_mpc11_nonlinear_replay \
  --output /tmp/orbit-fixture.json

python3 benchmarks/reporting/closed_loop/run_task.py \
  --task syn-nl-fuel-01 --control 0,0 \
  --bridge <BUILD_DIR>/csl_mpc11_nonlinear_replay \
  --output /tmp/fuel-fixture.json
```

These are fixed-control trajectory fixtures. They are not optimizer runs,
policy results, reachable sets, or benchmarks. The saved
[MPC11 Lotka–Volterra phase illustration](../../../benchmarks/reporting/mpc11/evidence/figures-629f3edc/syn-nl-lv-01-phase.svg)
is a labelled two-dimensional trajectory example and remains bound to its
original evidence bundle.

Check canonical hashes and source bindings without numerical packages, then run
the Jacobian, scaling, objective, and replay-request checks in the MPC11 Python
environment, which already supplies NumPy and SciPy:

```sh
python3 benchmarks/reporting/closed_loop/validate_contracts.py
python3 benchmarks/reporting/closed_loop/check_contracts.py
python3 -m unittest tests.reporting.test_closed_loop_tasks
python3 benchmarks/reporting/closed_loop/check_replay.py \
  --bridge <BUILD_DIR>/csl_mpc11_nonlinear_replay
```

The common closed-loop convention is one controller, exact full-state
observation, fixed final time, shrinking remaining horizon, first zero-order
held action, shifted primal warm start, zero dual warm start, and stop before
the next action on failure. A deterministic policy trajectory is one
trajectory. Forward reachability means all admissible controls. These source
tasks do not turn their soft objective targets into hard point constraints.
The Lotka and fuel backward-feasibility roles use their physical terminal
state bounds. The orbit role names its positive-radius model domain. Any
reachability output must retain those exact terminal sets. Policy query
fixtures include off-trajectory states in the declared model domain. No
disturbance player or feedback-superiority claim is implied. This change adds
no acados code, dependency, or installation path.
