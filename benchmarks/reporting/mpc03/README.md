# MPC-03 robust minimax formulation pilot

This bounded two-stage scalar case is a formulation and oracle cross-check for
issue #599. It is a new synthetic case, not a B06/B07/B08 reproduction. The
finite action catalogue is the ordered list `(0, 1, 1)`, so duplicate action
indices remain distinct. Each stage disturbance is independently selected
from `{-1/8, +1/8}`. The model is `x[t+1] = x[t] + u[t] + w[t]`, with
`x[0] = 0`; the terminal objective is to minimize the worst `x[2]`, subject to
`-10 <= x[0], x[1] <= 10` and `1.5 <= x[2] <= 10` for every disturbance
history.

The finite-action reference enumerates all nine control-index plans and all
four disturbance histories. Four plans are tied at value `2.25`; five plans
are rejected by robust terminal safety. The extensive-form MILP has one-hot
control selectors shared across all four histories, separate states for each
history, and one epigraph variable for the worst terminal cost. Its MIP
incumbent, best bound and gap are compared with the exhaustive reference. The
continuous relaxation leaves those same one-hot selectors continuous, giving
a lower bound of `2.0`; the finite optimum supplies the feasible upper bound
`2.25`. The interval `[2.0, 2.25]` is a bound comparison, not an equal-problem
speed ranking.

Run the non-timed smoke check with an optional Release build configured using
`-DCSL_ENABLE_HIGHS=ON -DCSL_BUILD_MPC03_REPORT=ON`; the target is
`csl_mpc03_robust_minimax_report --smoke`. The build reuses the repository's
source-pinned HiGHS 1.11.0 dependency. This pilot adds no installed API or new
dependency.

The labelled 2D state projection at
`docs/examples/mpc03-open-loop-disturbance-tube.svg` shows all four terminal
history points for the finite upper-bound plan, the convex hull of their
endpoints, the robust terminal safety threshold, and the worst-cost history.
It preserves the discrete history identities rather than presenting the hull
as the original finite disturbance set.

This pilot does not yet implement convex quadratic/norm MIQCPs or the full
comparison-record publication/capture workflow. It establishes the first
linear-cost MILP case and its relaxation direction before adding those
remaining acceptance items.
