# Ellipsoid candidate selection for fixed-plan minimax

## Profile

`finite_plan_ellipsoid` propagates one bounded finite-catalogue fixed plan through a discrete-time linear system. It emits a stagewise outer ellipsoid represented by a center and nonnegative axis radii. At each stage, it maps the prior ellipsoid through the state matrix using coordinate support, adds the control and bounded-disturbance contributions, and encloses the resulting coordinate box in a new axis-aligned ellipsoid.

This profile supports positive state dimension, finite bounded initial and disturbance V-sets (reduced to coordinate boxes), finite control catalogs, and universal state constraints. Unsupported safe-set shapes, unbounded sets, and incompatible dimensions return explicit unsupported outcomes. Cancellation and resource limits return explicit stopped outcomes. The result is a numerical outer enclosure; it does not use validated rounding.

`finite_action_ellipsoid_minimax` enumerates every fixed open-loop action plan in the declared finite catalog, scores its terminal ellipsoid for the supported convex objective forms, records scored and failed attempts, and replays the selected plan through every declared disturbance history. The quantifier order is `exists one fixed control plan, for all disturbance histories`. It does not synthesize feedback or reproduce continuous-action RL.

## Score and evidence

The score is an estimate evaluated from the stored binary64 ellipsoid: linear support, a PSD quadratic support expression, or a residual-norm support expression. It is not a validated objective bound, a feasible cost on its own, or a global optimality certificate. The selected control plan and worst-case disturbance witness become a realizable finite-catalogue result only after the separate exact-history replay succeeds.

The independent report checker reconstructs each finite disturbance history with exact rational arithmetic from the recorded binary64 input values and verifies full-dimensional ellipsoid membership at every stage for all candidate plans. It also checks every disturbance history in the selected replay. This is complete evidence for the pinned finite TwoPoints fixture, not a general proof for arbitrary floating-point inputs.

The included planar analytic fixture maps `[-1,1] × [-1,1]` through `diag(2,1)` and checks every exact image corner against the output ellipse. The figure is generated from the saved record. The TwoPoints report retains both player projections `(x1,x2)` and `(x3,x4)`, forward reachable sets, backward-winning sets, intersections where defined, and replayed trajectories.

## Limits

This is a fixed-axis, coordinate-radius enclosure. It can be conservative under rotation and shear. Semiaxis construction and scoring are ordinary binary64 arithmetic. Any runtime measurements are descriptive unless the comparison-program repetition and limiter-profile gates are satisfied. No performance winner follows from this pilot.
