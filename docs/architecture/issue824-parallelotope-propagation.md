# Fixed-frame parallelotope propagation for issue 824

## Decision

Represent each stage by a fixed invertible dyadic frame `Q` and a coordinate
box `l <= y <= u`, where physical states are `x = Q y`. Use the same
non-axis-aligned frame at every stage. The pinned `TwoPointsOnParallelLines`
transition is singular, so an evolving frame based on `A Q` cannot be inverted
in general. A fixed frame handles that case without an LP dependency.

For each stage, enclose the initial and disturbance V sets in frame coordinates
and propagate intervals through

`y' = Q^-1 A Q y + Q^-1 B v + Q^-1 E w + Q^-1 c`.

All interval arithmetic rounds outwards. Each represented state set is a
parallelotope and contains the exact real-arithmetic image of the prior
enclosure under the supplied binary64 dynamics and finite input sets. This is
a stagewise outer relation; it does not establish optimizer completeness or
make an enclosure score a realizable control plan.

## Bounds and unsupported cases

Support finite binary64 matrices and bounded nonempty V sets or singletons,
universal state constraints, and finite open-loop controls/disturbances. Return
typed unsupported or stopped outcomes on invalid dimensions, non-finite values,
overflow, unsupported set forms, or configured work limits. Do not accept rays,
H representations, empty sets, or claim predecessor/feedback support.

The first integration is propagation of the selected fixed plan from the
existing finite TwoPoints minimax selector. Keep its exact finite-history
replay and objective separate. Validate enclosure inclusion using an
independently reconstructed low-dimensional fixture with exact dyadic
arithmetic; report the four-dimensional trace as an outer enclosure only.

## Alternatives

- Evolving basis `Q[k+1] = A[k] Q[k]`: rejected because the pinned transition
  has a zero row and is singular.
- Support LP in a fixed orientation: deferred because it adds an optional
  solver dependency and needs its own outward certification contract.
- Zonotope propagation: already implemented; its independent factors retain
  orientation but can grow with the horizon. This parallelotope path instead
  trades tighter stage shape for a fixed frame and coordinate interval
  over-approximation.

## Deliberate limits

No ellipsoid or closed-loop claim is made. The fixed frame is a selected
orientation, not an optimizer over orientations. Scores from its terminal
parallelotope are descriptive candidate scores until an independent bound
contract is implemented.
