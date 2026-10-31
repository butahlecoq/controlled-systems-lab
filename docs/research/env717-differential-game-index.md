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
separate `TwoPoints` feedback bundle is linked from the report and records the
causal finite-state reachability result.

`SimpleControlProblem`, `TwoParticleGame`, and the time-sphere nominal pilot
are retained in the archive as additional control/replay examples, but are not
counted as members of the nine-environment differential-game list above.

Every listed report is a finite, explicitly scoped adaptation. The finite
catalogues, shortened horizons, information pattern, and any state
discretization remain part of each report's evidence boundary.
