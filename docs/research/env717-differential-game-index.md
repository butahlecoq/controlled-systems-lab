# ENV-717 differential-game report index

Issue [#717](https://github.com/butahlecoq/controlled-systems-lab/issues/717)
started from the `imm-rl-lab/optimal_control/Environments` suite. The saved
reports below are source-attributed finite adaptations; they are not claims to
reproduce RL training or the original continuous-action horizons.

## Differential-game reports

| Environment | Saved report | Geometry/use |
| --- | --- | --- |
| `AirToAirInterception` | [report](../../reports/algorithm-results/env717-air-to-air-pilot-v1/README.md) | finite minimax and causal feedback |
| `BrokenTriangleGame` | [report](../../reports/algorithm-results/env717-broken-triangle-pilot-v1/README.md) | finite game pilot |
| `MaxCoordinateGame` | [report](../../reports/algorithm-results/env717-max-coordinate-pilot-v1/README.md) | finite minimax pilot |
| `MultiPointCostGame` | [report](../../reports/algorithm-results/env717-multipoint-cost-game-pilot-v1/README.md) | finite game pilot |
| `PointOnThePlane` | [report](../../reports/algorithm-results/env717-point-on-plane-pilot-v1/README.md) | finite minimax pilot |
| `SphereGame` | [report](../../reports/algorithm-results/env717-sphere-game-pilot-v1/README.md) | finite-action minimax |
| `TimeOptimalSphereGame` | [report](../../reports/algorithm-results/env717-time-sphere-minimax-v1/README.md) | finite minimax/time pilot |
| `TwoPointsOnParallelLines` | [fixed-plan report](../../reports/algorithm-results/env717-two-points-pilot-v1/README.md) | 4D phase-plane geometry |
| `UnequalGame` | [report](../../reports/algorithm-results/env717-unequal-game-pilot-v1/README.md) | finite minimax pilot |

The clearest reachability/minimax figure is the
[`TwoPointsOnParallelLines` report](../../reports/algorithm-results/env717-two-points-pilot-v1/README.md):
it uses the physical coordinates `(x1,x2)` and `(x3,x4)` as the two player
position–velocity planes and retains forward layers, backward-winning
intersections, and an independently replayed worst-case trajectory. The
separate [`TwoPoints` feedback bundle](../../reports/algorithm-results/env717-two-points-feedback-v1/README.md)
records the causal finite-state reachability result.

`SimpleControlProblem`, `TwoParticleGame`, and the time-sphere nominal pilot
are retained in the archive as additional control/replay examples, but are not
counted as members of the nine-environment differential-game list above.

## Supplementary source-suite control reports

| Environment | Saved report | Scope |
| --- | --- | --- |
| `PendulumTerminal` | [report](../../reports/algorithm-results/env717-pendulum-terminal-pilot-v1/README.md) | finite catalogue, local affine selection, nonlinear source-map replay |
| `UnlimitedBolzaProblem` | [report](../../reports/algorithm-results/env717-unlimited-bolza-pilot-v1/README.md) | analytic double-integrator reference and exact finite-catalogue search |

These single-controller reports supplement the game examples. The Bolza result
uses an authored nonzero initial state and bounded finite action catalogue;
it does not solve the source's unbounded-control problem. The differential-game
reachability/minimax showcase remains `TwoPointsOnParallelLines` above.

Every listed report is a finite, explicitly scoped adaptation. The finite
catalogues, shortened horizons, information pattern, and any state
discretization remain part of each report's evidence boundary.

## Additional nonlinear control pilots

These are single-controller examples from the same upstream environment suite,
not differential games:

| Environment | Saved report | Scope |
| --- | --- | --- |
| `DubinsCar_Terminal` | [report](../../reports/algorithm-results/env717-dubins-car-pilot-v1/README.md) | finite open-loop terminal-control catalogue |
| `PendulumTerminal` | [report](../../reports/algorithm-results/env717-pendulum-terminal-pilot-v1/README.md) | finite-action terminal-control pilot |
| `VanDerPol` | [report](../../reports/algorithm-results/env717-vanderpol-pilot-v1/README.md) | equation-replayed finite-action oscillator pilot; upstream `step()` raises `NameError` |
| `Pendulum` | [report](../../reports/algorithm-results/env717-pendulum-pilot-v1/README.md) | Gym v0.21.0 source-qualified finite-action open-loop pilot; exact only over the authored 5-action, 10-step catalogue |
| `EarthOrbitalMotion` | [report](../../reports/algorithm-results/env717-earth-orbit-pilot-v1/README.md) | source-equation RK4 replay over 20 stages; exhaustive 729-plan, three-block action catalog with radius-rate projection |

The Van der Pol artifact is not a direct execution of the upstream class: it
re-expresses the pinned equations because the source's return tuple references
an undefined variable. Its source note and report state this limitation.
