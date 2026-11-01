# PendulumTerminal local-linear finite-action pilot

The source is pinned to [f4d76c60f4003f50954174e96eafd8e514bd5441](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/PendulumTerminal/PendulumTerminal.py) and blob
`4c3ef514524fa98fab53b2de18dfa9127316263f`. Its dynamics and parameters are re-expressed here; upstream
source code is not copied. The repository metadata declares no license.

The source task randomizes its reset and runs for five seconds. This pilot fixes
the initial state to `(theta, theta_dot) = (0.25 rad, 0 rad/s)`, uses four
0.05-second steps and the action catalogue `[-1, 0, 1]`, and plans on a local
affine model linearized at the upright equilibrium. The planner minimizes the
terminal surrogate `theta_T^2 + 0.1 theta_dot_T^2`, not the source running cost.
Its unique finite-catalogue minimizer is `[-1.0, -1.0, -1.0, 0.0]` with surrogate
value `0.0459731001717`.

The selected plan is replayed on the source nonlinear semi-implicit Euler map.
An independent exhaustive oracle checks all 81 source-map action sequences
using the source running cost. The selected plan costs
`0.254058925319`; the best sequence in that same
finite catalogue is `[-1.0, -1.0, 0.0, 0.0]` at
`0.244113074455`. This gap describes the surrogate on this
pilot only. It is not a continuous-action or full-horizon optimality result.

The phase-plane plot shows every affine forward-reachable point for the finite
catalogue, the selected affine prediction, its nonlinear replay and the best
source-map finite-catalogue replay. No runtime or performance comparison is
reported.

Reproduce from a clean checkout:

```sh
cmake -S . -B build/env717 -DCMAKE_BUILD_TYPE=Release \
  -DCSL_BUILD_ENV717_REPORT=ON
cmake --build build/env717 --config Release --target csl_env717_pendulum_terminal
python3 scripts/reports/env717/check_pendulum_terminal.py \
  build/env717/csl_env717_pendulum_terminal \
  --output reports/algorithm-results/env717-pendulum-terminal-pilot-v1
```

The raw record binds the upstream source, driver and algorithm source hashes.
The current source commit is `a1d628cda977cefce7747ca8ea56678b967bd0bb`.
