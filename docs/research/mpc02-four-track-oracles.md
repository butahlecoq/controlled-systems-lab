# MPC-02 four-track exact oracle

This note records the small rational oracle shared by the four authored MPC-02
scenario tracks in [issue #598](https://github.com/butahlecoq/controlled-systems-lab/issues/598).
It is an independent mathematical reference for the [direct joint-program
tests](../../tests/synthesis/strategy_b/direct_joint_tests.cpp); it is not a
timing result and does not replace the saved paired measurement bundle for the
slew case.

## Common model

All four scenarios use the two-stage identity dynamics

\[
x_1=u_0,\qquad x_2=u_1,
\]

from the zero initial state. Their objective is

\[
J=(x_1-1/2)^2+x_2^2.
\]

Thus the unconstrained minimizer is the target `(u0,u1)=(1/2,0)` and the
objective is the squared Euclidean distance to that point.

## Track oracle

| Scenario | Additional admissibility | Exact minimizer | Exact objective |
| --- | --- | --- | --- |
| [`mpc02-unconstrained-2d-v1`](../../examples/scenarios/mpc02-unconstrained-2d.json) | no input rows | `(1/2, 0)` | `0` |
| [`mpc02-stage-box-2d-v1`](../../examples/scenarios/mpc02-stage-box-2d.json) | `|u0|, |u1| ≤ 1` | `(1/2, 0)` | `0` |
| [`mpc02-slew-2d-v1`](../../examples/scenarios/mpc02-slew-2d.json) | `|u1-u0| ≤ 1/4` | `(3/8, 1/8)` | `1/32` |
| [`mpc02-l1-budget-2d-v1`](../../examples/scenarios/mpc02-l1-budget-2d.json) | `|u0|+|u1| ≤ 1/4` | `(1/4, 0)` | `1/16` |

The slew result is the orthogonal projection of `(1/2,0)` onto the active
line `u0-u1=1/4`. For the budget track, the four authored rows are the two
absolute sum/difference bounds; the identity

\[
\max(|u_0+u_1|,|u_1-u_0|)=|u_0|+|u_1|
\]

shows that they are exactly the two-dimensional `L1` ball. The target projects
to its positive `u0` facet at `(1/4,0)`.

## Scope boundary

The exact tests also check the slew-memory lift's coordinate projection and
reconstruction. The current saved measurement report compares the direct
full-history and lifted formulations only for `mpc02-slew-2d-v1`; the other
three tracks still need their measured comparison and the broader temporal
constraint fixtures required by issue #598. No performance ranking follows
from this oracle.
