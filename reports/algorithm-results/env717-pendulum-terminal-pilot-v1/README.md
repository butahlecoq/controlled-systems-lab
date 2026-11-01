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
source-map finite-catalogue replay.

The Release CLI call took a median `6453882.0` ns
(3121864–7318105 ns)
over 28 calls in
4 capture block(s), with one excluded warmup per block. Block summaries:
block 1: median 6.609 ms, range 3.923–7.233 ms; block 2: median 3.226 ms, range 3.122–3.378 ms; block 3: median 6.498 ms, range 6.391–6.632 ms; block 4: median 7.011 ms, range 3.493–7.318 ms. Each interval includes process launch, affine-plan
enumeration and JSON serialization/capture; it excludes the Python oracle and
report rendering. The block medians vary substantially, so these are descriptive
observations and support no performance conclusion or speedup claim. The CPU limiter is
unestablished because `perf` and `strace` were unavailable. The capture used
AMD Ryzen 5 3550H with Radeon Vega Mobile Gfx on
Linux-7.2.8-9-omarchy-x86_64-with-glibc2.44 with
GNU 16.2.1 in Release mode.

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
