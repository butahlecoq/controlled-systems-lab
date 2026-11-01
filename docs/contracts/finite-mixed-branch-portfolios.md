# Finite mixed-control branch portfolios

`solve_finite_mixed_branch_portfolio` evaluates every finite catalogue history
of a supported nominal open-loop mixed-control problem. For each history it
fixes the discrete controls, resolves the remaining continuous problem, and
runs the caller-selected registered synthesis strategy. The first integrated
profile requires a numerical, complete, H-represented branch family that the
selected strategy's compiled verifier accepts.

Successful branches retain their catalogue-index history, verified continuous
family, and an H relation lifted into the original joint coordinates with the
discrete controls fixed. Duplicate catalogue values remain distinct histories.
Preparation, admission, solve, objective-bound, verification, and relation-lift
failures remain in the ordered evaluations. A partial or stopped search never
claims a complete optimum. `enumeration_complete` reports whether all histories
were emitted; `complete` additionally requires a valid objective for every
history. A stop outcome retains all results completed before the stop.

The effective tie tolerance is the requested tolerance plus the largest
branch-optimum interval width. Branches within that distance of the minimum
reported lower bound are retained; wider numerical intervals can therefore
add conservative ties. The API does not claim a sharper ranking than its
branch bounds support.

This initial path covers fixed finite discrete histories with a supported
continuous solver. It does not implement mixed-integer optimization, feedback
policies, convex relaxation of discrete controls, or a global source-level
`OptimalFamily` verifier. The portfolio is the source-level union record: each
component branch family is verified against its own resolved subproblem, and
the fixed discrete coordinates are preserved in the lifted relation.
