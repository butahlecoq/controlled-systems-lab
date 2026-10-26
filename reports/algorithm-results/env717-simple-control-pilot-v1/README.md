# SimpleControlProblem finite-action pilot

This is the first runnable source-attributed slice for issue #717. The source
repository has 23 environment directories; this report covers only its
discrete `SimpleControlProblem` variant. Its equations and parameters are
re-expressed from upstream rather than copied, because the source repository
declares no license.

## Result

The CSL finite-action minimax solver exhausts all 81 four-step control
sequences from `{-1, 0, 1}`. Ten plans have terminal squared error within
absolute objective tolerance `1e-14` of the minimum; their state residuals are
at binary64 roundoff scale. The independent Python check replays every state in
every plan and confirms the complete near-minimizing set. The labelled
time-state figure shows all 81 trajectories, with the ten near-minimizers
highlighted.

One solver-call warmup is excluded. Seven measured calls retain their raw
nanosecond values, median and range in `result.json`. The interval covers the
`finite_action_minimax` call; request construction, numerical replay checks and
JSON/figure export are outside it. No limiter profile was collected, so these
are descriptive timing observations for one tiny fixture, not a performance
claim or comparison.

## Source behavior and pilot changes

Upstream source identity is commit
[`f4d76c60f4003f50954174e96eafd8e514bd5441`](https://github.com/imm-rl-lab/optimal_control/tree/f4d76c60f4003f50954174e96eafd8e514bd5441).
The continuous source declares state `[time, x]`, `dt = 0.05`, terminal time
`2`, initial state `[0, 1]`, and actions in `[-1, 1]`. The discrete variant
provides actions `{-1, 0, 1}` and uses the same `step()` update. Its `step()`
adds reward `-0.5 * dt * u^2` and subtracts terminal `x^2`; the separate
`cost()` method uses `-dt * u^2` for running reward. The source therefore has
two different running-reward coefficients.

To keep exhaustive fixed-plan enumeration small, this pilot changes the
initial scalar state to `x0 = 0.1` and uses four steps (`T = 0.2 s`). Its
objective is terminal `x^2` only; it omits the running reward and fixes the
disturbance at zero. The result is a numerical finite-catalogue solution for
this adapted problem, not a reproduction of the original environment reward or
its default episode.

## Reproduction

With the repository's pinned CMake/Ninja versions:

```sh
TMPDIR="$PWD/build/dev/tmp" mise exec cmake@3.31.6 ninja@1.12.1 -- \
  cmake --preset dev -DCSL_BUILD_ENV717_REPORT=ON -DCMAKE_BUILD_TYPE=Release
TMPDIR="$PWD/build/dev/tmp" mise exec cmake@3.31.6 ninja@1.12.1 -- \
  cmake --build build/dev --target csl_env717_simple_control -j2
python3 scripts/reports/env717/check_smoke.py \
  build/dev/csl_env717_simple_control \
  --output reports/algorithm-results/env717-simple-control-pilot-v1
```

The final command independently checks the saved plan family and regenerates
the standalone HTML and SVG. It also writes PNG when `rsvg-convert` is
available. The result embeds the upstream repository commit and source-file
blob identities, along with the CSL source commit, driver hash, and renderer
hash. `SHA256SUMS` binds the report, raw result, renderer output and figure
files.

## Remaining source candidates

The upstream repository lists these environment directories. None of the
remaining candidates is ported or measured by this pilot:

`Acrobot`, `AirToAirInterception`, `AircraftLanding`, `BrokenTriangleGame`,
`CartPole`, `DubinsCar`, `EarthOrbitalMotion`, `FallingCylinder`, `LunarLander`,
`LunarLanderContinuous`, `MaxCoordinateGame`, `MultiPointCostGame`, `Pendulum`,
`PendulumTerminal`, `PointOnThePlane`, `SphereGame`, `TimeOptimalSphereGame`,
`TwoPointsOnParallelLines`, `UnequalGame`, `UnlimitedBolzaProblem`, `VanDerPol`,
and `Vehicle`.
