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
claims a complete optimum. `history_enumeration_complete` reports whether the
cursor emitted every history, including stopped attempts. The portfolio's
`enumeration_complete` is true only if every history was evaluated without a
budget, cancellation, or deadline stop; `complete` additionally requires a
valid objective for every history. A stop outcome retains all results completed
before the stop.

`FiniteMixedBranchLimits` bounds the aggregate retained output, not just one
cursor page. Defaults allow 256 evaluated histories, 100,000 combined rows
across retained continuous/source H-relations, and 10,000,000 stored numeric
matrix/right-hand-side scalars across those relations. Reaching a limit returns
`StopReason::resource_limit`, preserves earlier outcomes, and leaves the
portfolio incomplete. If every history was emitted but a branch relation could
not be retained, enumeration may be complete while the solved portfolio is
still incomplete. The result reports retained row and scalar counts.

These are structural accounting limits, not a native heap/RSS limit. A selected
strategy may transiently materialize one branch family before its returned H
relation is charged against the aggregate budget. Per-branch
`FamilyRequest::materialization_limit` remains part of the selected strategy
request; strategies that do not support it refuse the branch instead of
silently ignoring it. Cancellation/deadline still bound work cooperatively, and
no claim of hard process-memory enforcement follows.

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
