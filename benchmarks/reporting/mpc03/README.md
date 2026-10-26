# MPC-03 robust minimax formulation pilot

This bounded two-stage scalar case is a formulation and oracle cross-check for
issue #599. It is a new synthetic case, not a B06/B07/B08 reproduction. The
finite action catalogue is the ordered list `(0, 1, 1)`, so duplicate action
indices remain distinct. Each stage disturbance ranges over the full interval
`[-1/8, +1/8]`. The finite oracle and MILP check the four endpoint products.
This is sufficient for this fixture because every state and safety inequality
is affine in the disturbance vector, and the terminal objective is linear;
the extrema over each disturbance box occur at endpoint products. This
vertex-sufficiency argument is specific to this affine, polyhedral case. The
model is `x[t+1] = x[t] + u[t] + w[t]`, with
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

The verified output is saved in
`reports/algorithm-results/mpc03-open-loop-pilot-v1/`, with the raw result,
build provenance, and a standalone English HTML report. The existing report
workflow stages a versioned route, adds it to the archive index and links it
from the examples gallery; the live Pages URL is pending merge and deployment.
The report records numerical outcomes only; it makes no performance claim.

Run the non-timed smoke check with an optional Release build configured using
`-DCSL_ENABLE_HIGHS=ON -DCSL_BUILD_MPC03_REPORT=ON`; the target is
`csl_mpc03_robust_minimax_report --smoke`. The build reuses the repository's
source-pinned HiGHS 1.11.0 dependency. This pilot adds no installed API or new
dependency.

The labelled 2D state projection at
`docs/examples/mpc03-open-loop-disturbance-tube.svg` shows all four terminal
history points for the finite upper-bound plan, the convex hull of their
endpoints, the robust terminal safety threshold, and the worst-cost history.
It preserves endpoint-history identities while representing the full
continuous disturbance box through vertex sufficiency; the hull is a
visual projection, not the disturbance set itself.

This pilot does not yet implement convex quadratic/norm MIQCPs or the full
comparison-record publication/capture workflow. It establishes the first
linear-cost MILP case and its relaxation direction before adding those
remaining acceptance items.
