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
defined for the resulting empty trajectory product. The first fixed plan's
whole-request admission and stop check run before this status is returned;
an empty later disturbance is still recognized if propagation first finds an
earlier safe-set violation. At zero horizon, even an
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
at absolute tolerance `1e-8` (ordered plan indices 17, 33 and 129). This remains a discrete rounded-data reference,
not a reproduction of the published `67.12` nonlinear trajectory or a
validated numerical certificate.

The [B08 exact-dyadic fixture audit](../research/issue3-b08-dyadic.md)
independently replays the frozen public binary64 inputs, compares every public
per-plan status and objective, and brackets the exact norm for this one saved
fixture. Its a posteriori discrepancy bounds do not upgrade this port's
`Assurance::numerical` or prove a general validated-arithmetic contract.

`worst_case_interval` is a separate bound query for a compact native V set or
singleton. It interprets stored binary64 vertices and objective coefficients
as exact real inputs, obtains a coordinate box for the convex hull, and applies
outward interval evaluation to the objective over that box. A lower bound is
the largest lower endpoint from evaluating authored vertices; an upper bound
encloses every objective value on the coordinate box. The box may make bounds
loose, especially for quadratic objectives with repeated coordinates. The
result binds the caller's problem/request IDs and source `SetId`; it is an
outward range for that stored-set/objective query, not a certificate that
binary64 reachability or a geometry conversion produced the intended source
set. Empty input has its own outcome; unbounded, unsupported and over-capacity
inputs do not publish bounds. This function does not replace the numerical
`worst_case_vertex` or upgrade finite-action feasibility and minimizer claims.

## Report and modular integration gates

The versioned EXT-01 fixed-plan report measures direct fixed-plan and vertex
calls; it does not measure this whole-catalogue function. Before delivery of
issue #3, prepare a separate optional `CSL_BUILD_ISSUE3_REPORT` harness,
`benchmarks/reporting/issue3/finite_catalogue_driver.cpp`, modeled on the
existing EXT-01 driver. Its JSONL `--smoke` route must call the public
`finite_action_minimax` interface once per fixture and check the L19
two-action endpoint value, all-infeasible per-plan rejection, empty/unsupported/
cancelled statuses, and the B08 625-plan, 160,000-terminal-row reference with
indices 17, 33 and 129. The saved rows must retain input/fixture hashes,
identity, status, limits, objective convention, assurance, plan and row counts,
and expected-versus-observed checks. No test elapsed time is a measurement.

Review the fixed source and harness first. Then measure a **clean Release**
commit, recording compiler/build graph, OS/hardware, numerical settings,
warmups and raw repeated trials. For B08, time the public whole-catalogue call
and literal result checks as one declared interval; smaller cases need recorded
batch counts so the measured work is not dominated by the clock. Keep failures
and unavailable counters. Use the existing report tooling separation:
collection writes versioned raw JSONL/JSON and build evidence, rendering reads
only saved records, and schema-3 catalogue registration stages standalone HTML,
offline ZIP and immutable GitHub Pages paths. Review raw/HTML consistency and
visual layout, then verify the live URL and record the measured source commit
on PR #351 and issue #3. No measurements or publication URL are claimed by
this source PR yet.

The existing registry ports do not accept this result without changing its
meaning. `StrategyPort` requires a `SynthesisOutcome` containing a joint
optimal-family relation; this module returns a scalar value and per-plan
numerical records. LP, convex and geometry ports have separate mathematical
requests. [Issue #353](https://github.com/butahlecoq/controlled-systems-lab/issues/353)
tracks a typed oracle port and registration with capability/provenance tests.
An eventual complete finite optimal-plan family needs its own representation
and verifier before any `StrategyPort` claim.

## Typed numerical oracle registration

`CSL::finite_action_minimax_port` installs the separate
`<csl/optimization/finite_action_minimax_port.hpp>` interface. Its
`FiniteActionMinimaxQuery` freezes the complete request and caller limits.
`csl.optimization.finite-action-minimax@1.0.0` registers an exclusive
workspace under `FiniteActionMinimaxPort`; clients select it through
`Registry<FiniteActionMinimaxPort>` with the
`csl.optimization.finite-action-minimax.value` output representation and
binary64 numerical assurance. Preparation retains requested and actual
method/version provenance, and a workspace runs only its prepared query.
The port verifies the problem/request identity and numerical assurance of
completed optimal or infeasible results before returning them.

Capability admission covers the declared affine `LinearSystem`, immutable
convex terminal `Objective`, compact native V, singleton, or empty initial
and independent disturbance sets, and H, singleton, universal, or empty safe
sets. Admission also checks request identities, dimensions, finite action rows,
the near-optimal tolerance, point and plan limits, and the objective/output
assurance match before creating a workspace. Execution-context numerical
settings, cancellation, deadlines, and arithmetic failures remain run-time
checks. Consequently registration rejection is distinct from the admitted
oracle's `Unsupported` outcome. The returned `FiniteActionMinimaxOutcome` preserves
optimal, all-infeasible, empty-catalogue, no-scenario, unsupported, and
stopped variants; no branch publishes an optimal-family relation or validated
arithmetic assurance.

The scientific next step is a separately reviewed representation and verifier
for a finite optimal-plan relation. Its scope must define whether the objects
are index tuples, state-control trajectories, or policies, and prove the
membership and completeness claim against the admissible scenarios and
objective. Only after that contract exists can reviewers decide whether a
verified relation has the joint-family semantics required by `StrategyPort`.
The scalar oracle and its near-minimizer indices do not authorize that mapping.
