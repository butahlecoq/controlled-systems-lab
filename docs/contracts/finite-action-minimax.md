# Finite-action fixed-plan minimax reference

Issue #3 adds the public `CSL::finite_action_minimax` module in
[`finite_action_minimax.hpp`](../../include/csl/optimization/finite_action_minimax.hpp).
It composes the EXT-01 fixed-plan disturbance propagation and convex terminal
vertex oracle. The scope is an ordered, stage-invariant finite control catalogue,
fixed open-loop plans, affine discrete dynamics, an independent compact native V
or singleton disturbance set per transition, and a convex terminal `Objective`.
It does not optimize a causal feedback policy, mixed/continuous controls,
nonlinear dynamics, correlated disturbances, or an H-only terminal set.

For horizon `T`, the module visits every ordered index tuple in
`{0,...,m-1}^T`, where `m` is the catalogue length. Duplicate action rows remain
separate plans. Each plan propagates **all** disturbance candidate histories
without clipping them to the safe set. An unsafe successor rejects that plan.
For a robustly feasible plan, the complete generated terminal V description is
scored by `worst_case_vertex`. Convexity and complete compact V semantics imply
that a maximum occurs at one of these rows. The least of those per-plan maxima
is the reported minimax value. The supplied plan and point limits are checked
before any truncated successful result is published.

`FiniteMinimaxOptimal` binds the result to caller-supplied problem and request
IDs. Its ordered `plans` record contains every catalogue tuple: a feasible
record has its computed worst value, a maximizing point, evaluated vertex
count, and immutable terminal V set; a rejected record has its first violating
stage and successor. The `minimizing_plan_indices` address those records. The
`near_optimal_tolerance` is an absolute tolerance in objective units: plans
whose **computed** worst values differ from the computed minimum by no more
than this tolerance are retained. With zero tolerance only binary64 equality
is used. These indices are numerical near-minimizers, not a certified list of
all mathematically tied plans. A feasible terminal set can be replayed through
the public vertex oracle; the plan order and rejection witnesses can be
replayed through fixed-plan propagation. The result does not contain a validated
rounding bound or a stand-alone proof that every generated point equals an
independent source representation.

`FiniteMinimaxInfeasible` is returned only after every indexed plan has a
robust violation. `FiniteMinimaxEmptyCatalogue` distinguishes an empty action
catalogue at positive horizon. `FiniteMinimaxNoScenarios` distinguishes an
empty initial or disturbance description: no terminal worst-case value is
defined for the resulting empty trajectory product. At zero horizon, even an
empty catalogue has the single empty action plan. Invalid dimensions,
unsupported representations, unbounded sets and exhausted caller capacities
return `Unsupported`; cancellation, deadline and numerical arithmetic failure
return `OperationStopped`. Neither carries a partial optimum. All completed
outcomes have `Assurance::numerical`, inherited from objective PSD admission,
binary64 propagation, tolerance-based H membership and objective evaluation.

The public tests include the L19 midpoint counterexample, duplicate-row ties,
all-infeasible safe sets, empty and unsupported input, cancellation, and the
displayed rounded B08 catalogue: 625 plans, each with 256 terminal disturbance
histories, minimum approximately `67.150601101407`, with three numerical ties
at absolute tolerance `1e-8`. This remains a discrete rounded-data reference,
not a reproduction of the published `67.12` nonlinear trajectory or a
validated numerical certificate.
