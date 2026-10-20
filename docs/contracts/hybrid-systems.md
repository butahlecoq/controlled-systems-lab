# Hybrid system profile

Status: accepted design contract. Exact-head specification and standards
reviews cleared this contract in [PR #471](https://github.com/butahlecoq/controlled-systems-lab/pull/471)
at `7632a4c`; it merged as `5e4f174`. Implementation is tracked separately in
[EXT-07 #156](https://github.com/butahlecoq/controlled-systems-lab/issues/156)
and [PR #472](https://github.com/butahlecoq/controlled-systems-lab/pull/472)
and remains incomplete. The implementation-status notes below identify the
supported subset and gaps. The profile is deliberately distinct from the
finite/mixed control domains and observation-based policy profiles.

## Hybrid automaton data

A hybrid model has a finite ordered catalogue of mode identities and a finite
ordered catalogue of directed transition-edge identities. Each mode `q` owns:

- a state dimension `n_q` and a continuous-control dimension `m_q`;
- mode-local affine flow coefficients `A[q,k]`, `B[q,k]`, and `a[q,k]` for
  `x⁻_(k+1) = A[q,k] x_k + B[q,k] u_k + a[q,k]` while `q` is active;
- a control-admissibility set `U[q,k]` in that mode's control coordinates and
  state-admissibility sets in its state coordinates.

Every coefficient and relation carries explicit source and target dimensions.
An edge `e: q → r` has fixed source and destination modes, with a guard
`G[e,k]` in the source mode's state coordinates and a reset relation
`R[e,k] ⊆ R^(n_q) × R^(n_r)` for each transition stage `k`. Both arrays contain
exactly `T` entries; a time-invariant guard or reset is authored by repeating
its value for every stage. A reset can therefore change state dimension. An
affine reset map is the functional special case
`x⁺ = M[e] x⁻ + b[e]`; a general relation can retain multiple post-reset
states. The reset input is the guard-satisfying pre-reset state `x⁻`, and its
output is the post-reset state `x⁺` in the destination coordinates. Coordinate
labels identify each mode's state and control spaces; equal dimensions do not
imply equal physical meaning.

The first executable profile requires one request-selected initial mode `q_0`
and one known initial state `x_0` of dimension `n_q0`. The finite mode catalogue
may contain any number of modes, but the request must name its initial mode; it
is never inferred from state coordinates. Uncertain initial states or initial
mode alternatives need an explicit policy/quantifier contract and are rejected
until coordinated with EXT-04.

## Stage and transition timing

For horizon `T`, the state/mode stages are `0..T`, and flow/control stages are
`0..T-1`. At the start of stage `k`, `(x_k,q_k)` is the post-reset state and
active mode. The mode `q_k` governs `u_k`, `U[q_k,k]`, and the flow producing
`x⁻_(k+1)`. A permitted outgoing edge from `q_k` is selected for the transition
event. Its guard is tested on `x⁻_(k+1)`; only then may its reset relation
produce `x_(k+1)` and its target become `q_(k+1)`. The terminal pair
`(x_T,q_T)` is checked after the final reset. A self-transition is represented
by an explicit edge; there is no implicit stay-in-mode transition. At `T=0`
there is one initial/terminal pair and no flow, control, guard, or reset event.

For this profile, the complete mode/edge sequence and continuous control
history form one open-loop plan selected before execution. A planned edge is an
existential choice in that plan; the model does not add an adversarial edge
quantifier or allow the plan to observe a runtime guard outcome. A guard that
fails makes that planned branch infeasible. Switching policies that choose an
edge from observations or state feedback require a separate information-pattern
contract.

Thus the indexed objects are unambiguous:

```text
(x_k, q_k) -- mode-q flow with u_k --> x⁻_(k+1)
             -- enabled edge guard --> reset relation --> (x_(k+1), q_(k+1))
```

For every mode `q`, provide a state invariant `I[q,k]` in that mode's state
coordinates for every state stage `k=0..T`. An unconstrained invariant is
written explicitly as `UniversalSet`; a missing entry is invalid, and
`EmptySet` is valid input that can make a branch infeasible. At each transition
`q_k → q_(k+1)`, require `x_k ∈ I[q_k,k]` and the pre-reset flow result
`x⁻_(k+1) ∈ I[q_k,k+1]`, then separately require the edge guard and reset
relation, and require `x_(k+1) ∈ I[q_(k+1),k+1]`. Thus the source-mode
invariant is checked on the pre-reset state and the destination-mode invariant
on the post-reset state; guards are additional conditions, not substitutes for
invariants. At termination, `q_T` must be in the explicit allowed terminal-mode
set `Q_T` and `x_T ∈ I[q_T,T]`. For `T=0`, check the initial/terminal
invariant once and require `q_0 ∈ Q_T`; there are no transition-stage checks.
There is no post-reset control at stage `k` and no pre-reset observation timing
in this profile.

## Complete hybrid family and identity

A hybrid trajectory retains states, controls, intermediate pre-reset states,
mode identities, and transition-edge identities in their stage order. A mode
path is the ordered mode sequence; a branch identity additionally includes the
ordered transition-edge sequence, since distinct parallel edges may share the
same source and target modes while having different guards or resets. The
request supplies a nonempty allowed terminal-mode set `Q_T` and exactly one
terminal objective per allowed mode. Each objective is one of the supported
minimized terminal forms (`LinearTerminal`, `QuadraticTerminal`, or
`ResidualNormTerminal`), has the dimension required by that mode, and is
validated under the existing objective policy. All mode-indexed objectives
must represent the same scalar quantity in the same units. Modes outside `Q_T`
are not terminal outcomes; a feasible path ending outside `Q_T` is excluded.
The objective is minimized globally over the union of feasible branch
relations ending in `Q_T`, including its per-mode objective offset. An empty
`Q_T`, missing objective, incompatible dimension, unsupported objective or
provider, or inconsistent quantity/units is rejected before workspace
creation. For `T=0`, the same terminal-mode and objective rules apply to the
initial state.

The feasible/optimal result is a finite union of branch-labelled joint
relations. It must preserve every admitted optimal mode/edge branch and the
continuous family within that branch. It must not convexify across distinct
branches, replace a family with sampled trajectories, or discard a tie because
another branch has the same objective. Repeated discovery of the same complete
edge sequence denotes the same branch and must not duplicate its relation;
different edge sequences remain separate even if their mode sequences match.
The branch record carries mode/edge provenance and provider/version/resource
provenance for every flow, guard, reset, and composition operation.

## Replaceable adapter boundaries

The profile keeps three adapter seams independent of the public hybrid request
and family meaning:

- A reachability adapter composes mode-local flows, invariants, guards, and
  reset relations. It may project intermediate variables internally, but it
  must retain a reconstruction relation sufficient to recover the full
  branch-labelled joint relation and may not merge distinct edge paths.
- A direct-trajectory adapter formulates the full-horizon joint relation for a
  fixed mode/edge path. Its output uses the same logical branch payload and
  identity as reachability composition; neither adapter may downgrade the
  continuous family to witnesses or samples.
- A verification adapter consumes the original request and a candidate family
  from either producer. It independently checks feasibility and objective
  claims, and must establish that all feasible optimal branch identities and
  their continuous relations are covered before certifying family completeness.
  Producer status flags or finite point checks alone are insufficient.

At these seams, each branch exposes the ordered mode and edge identities, the
joint coordinates `(x_k, u_k, x⁻_(k+1), x_(k+1))`, the defining constraints or
an equivalent exact relation with a reconstruction map, the per-branch
objective, and provenance for the operations and providers used. Adapter
implementations can differ in representation and algorithms, but must preserve
this logical payload and the same existential trajectory semantics. Operation
capabilities and assurance remain explicit per adapter; a missing composition,
reconstruction, or completeness capability is rejected before workspace
creation. The fixed-path reachability API is replaceable through
`HybridReachabilityAdapter` and returns a path-labelled joint relation with the
configured limits and ordered operation trace. Its default implementation,
`JointHReachabilityAdapter`, currently wraps the same full joint-H composer; it
does not project intermediate coordinates or merge paths. This provides a
replaceable reachability contract. A separate
`ProjectedStateHybridReachabilityAdapter` independently assembles the full
one-transition relation and projects its terminal state through a registered
geometry provider. It currently admits scalar source and target states, one
scalar bounded non-singleton source-control interval, scalar interval or
universal invariants and guard (including equally scaled opposite H normals),
and a deterministic scalar affine reset encoded
by one H equality. It returns the labelled joint relation alongside the H
terminal set, provider provenance, and input/output row counts. Its row limit
is configured into the registered projection provider and bounds input,
intermediate, and terminal H rows. This narrow implementation does not establish
multi-stage projected reachability or general-dimensional continuous coverage.
The result also retains the provider's complete projection `GeometryEvidence`.
For the registered binary64 H-projection implementation, set-relation support
is `Unestablished`; the projected terminal set is not coverage-certified and
has no numerical error-bound certificate. Consumers must preserve and inspect
that evidence when interpreting the terminal set.
Each reachability adapter must preflight its supported
operations and limits for the fixed path before the wrapper queries capabilities
or starts composition. The default preflight fails closed; the built-in joint-H
adapter uses the structural set-representation and joint-relation-limit checks.
Built-in joint-H structural failures retain path and stage context. The
reachability, direct-trajectory, and family-verification preflight hooks have
default implementations. Derived adapters that do not override a hook remain
source compatible; adapters that override a preflight must match its declared
result type. A reachability adapter must override its fail-closed default to be
usable; a direct-trajectory adapter using a representation other than joint-H
must override the structural joint-H default. These public virtual additions
change adapter vtables; downstream prebuilt adapters must be rebuilt. CSL does
not promise a stable C++ binary/plugin ABI.
The direct-trajectory API is replaceable through
`HybridDirectTrajectoryAdapter`; each adapter preflights its complete fixed-path
inventory and relation limits before capability queries or branch builds.
Every adapter preflight rejection carries a requested path, the configured
relation limits, and one primary diagnostic for the preflight failure; the
wrapper checks that evidence before returning the rejection. Empty path
inventories are rejected before adapter preflight because they have no branch
to identify. A malformed adapter report is replaced with a
request-scoped evidence-mismatch failure. The failure may also retain built-in
relation-operation records. Request-wide validation errors remain diagnostics.
The default adapter, `JointHDirectTrajectoryAdapter`, builds a
branch-labelled joint H relation and optimization program. Each direct adapter
declares whether it preserves the
branch-labelled relation, which objective classes it supports, and its
assurance level; the wrapper rejects missing branch or objective capabilities
before dispatch. Injected adapters must preserve that result contract and
return diagnostics or cancellation without publishing a partial portfolio.
The `HybridFamilyVerificationAdapter` boundary consumes the original model,
request, exhaustive path inventory, branch programs, and candidate faces. Its
wrapper checks complete path and report identity coverage and attaches each
program's relation limits and ordered relation-operation/resource trace, plus
any candidate face's solver-provider provenance, to that path's verification
record. The report carries per-path feasibility, objective, and continuous-
coverage statuses, but it is inspection data and cannot publish a
`synthesis::OptimalFamily`.
Portfolio construction enumerates the complete path inventory and calls the
trajectory adapter's exact-operation and resource preflight before its
capabilities or any branch build. The default joint-H adapter checks structural
set representations and joint variable, row, or matrix-element limits across
every path; unsupported operations and limits are reported with affected path
and stage before any branch relation is constructed. Adapters using another
exact representation may implement their own operation preflight within the
same result contract. It also checks the adapter's
declared assurance, branch-relation support, and linear/convex terminal-objective
support for every path before dispatching any path. Unsupported objective
support identifies the candidate path and terminal stage. When a verifier is
requested during construction, use `build_hybrid_portfolio_programs_with_verifier`;
after trajectory operation preflight it calls the verifier adapter's `preflight`,
then checks trajectory-adapter capabilities across the same inventory. The built-in
path and portfolio builders reject unknown assurance values and non-finite or
negative tolerances before calling injected adapter methods. Validated objective
assurance is unsupported because the hybrid objective path currently supports
numerical assurance only. The single-path wrapper checks policy before querying
trajectory capabilities; the verified portfolio builder checks it before
querying verifier capabilities or running verifier preflight. The built-in
singleton and scalar interval verifiers check each enumerated path; a custom
bounded verifier must implement preflight, and the default implementation fails
closed. These admission checks supplement later relation, candidate, and report
validation.
`ExactSingletonHybridFamilyVerifier` independently enumerates edge paths and
reconstructs trajectories using checked integer arithmetic. It supports only
integral initial states, singleton controls, singleton-representation resets,
universal/singleton/empty invariants and guards, and linear terminal
objectives. For optimal branches it checks that the supplied program and
candidate relations are the same singleton, using exact full-rank integer
equality checks for H representations. Continuous, nonintegral, overflowing,
or otherwise unsupported cases return unsupported status. Independent path
enumeration is bounded by the admitted inventory and a one-million-node
traversal ceiling; exceeding either returns unsupported. This bounded
numerical verifier is not a compiled proof authority and does not certify
general continuous branch coverage.

`OneStepScalarIntervalHybridFamilyVerifier` adds a separate numerical domain for
one-stage paths with scalar source/target states, a scalar control, bounded
feasible control intervals, scalar interval guards/invariants, deterministic
scalar affine H-relation resets, and a linear terminal objective. It independently
reconstructs each path's feasible control interval and objective, checks the
full program relation against the reconstructed affine line, and checks each
optimal-face candidate against the complete minimizing interval. It can certify
ties whose continuous intervals differ. It rejects other horizons, dimensions,
nondeterministic or non-scalar reset relations, unbounded feasible intervals,
and unsupported set forms; H
relation row and matrix limits are enforced. The verifier uses floating-point
policy tolerances for candidate anchors, while equality rank is established
using only exact binary floating-point row operations; if those operations
cannot establish rank exactly, coverage is unsupported. It requires represented
relation equalities and projected interval endpoints to match exactly as
computed, and checks represented inequalities without tolerance expansion.
Flow, reset-map, and objective arithmetic must be exactly representable in
binary floating point. Inexact sums, overflow, and products whose exactness cannot be
established (including possible underflow of the product residual) return
unsupported. Global objective ties therefore require exact equality of exactly
represented values. Near ties, contradictory relations, and near-equal
candidate intervals are rejected instead of expanded by tolerance. It is
limited to this domain; it does not establish general continuous-polytope
family coverage or validated assurance.

`SingleParameterScalarIntervalHybridFamilyVerifier` adds a finite-horizon
numerical domain with scalar states and controls, exactly one bounded
non-singleton control interval across the horizon, singleton controls at every
other stage, interval invariants and guards, deterministic exactly representable
scalar affine H-relation resets, and a scalar linear terminal objective. It
independently propagates the shared control parameter through every flow and
reset, reconstructs each path's feasible parameter interval and objective,
checks the complete `(1 + 3H)`-coordinate path relation, and checks every
optimal candidate against that path's minimizing subset. Distinct continuous
families on globally tied paths are retained. The verifier rejects unsupported
dimensions, relation forms, resource limits, and arithmetic whose exactness it
cannot establish. An independently infeasible path is certified only when its
supplied relation is explicitly represented as empty; otherwise the portfolio
result is unsupported. This verifier supports exactly one free control
parameter; it does not cover general continuous polytope families or validated
assurance. The two-parameter verifier below covers one bounded two-stage case
with two free controls; broader multivariate domains remain unsupported. The
`TwoStageScalarIntervalHybridFamilyVerifier` remains as a two-stage adapter and
preserves its existing report identifier.

`TwoParameterScalarPolytopeHybridFamilyVerifier` adds a separate finite-horizon
slice for exactly two stages, scalar states and controls, one bounded
non-singleton interval control at each stage, interval invariants and guards,
and deterministic exactly representable scalar affine resets. It propagates
both control parameters through the complete joint tuple, clips their bounded
rectangle by exact half-planes, checks the supplied joint H-relation's affine
hull as well as its projected polygon, and applies the same checks to each
globally optimal face. Exact global ties retain their distinct path families.
The implementation bounds both the cumulative interval rows and cumulative
half-plane clips per path (4096 each), as well as polygon vertices (4096). It
rejects degenerate feasible control polygons and unsupported H-representations,
and fails closed when exact binary64 arithmetic cannot be established. This
profile does not cover arbitrary horizons, more than two free controls,
non-interval admissible sets, nondeterministic resets, or validated assurance.

`ExactLinearHHybridFamilyVerifier` independently enumerates allowed mode/edge paths and reconstructs each path's joint H-relation from the raw model. It supports finite horizons and admitted state/control dimensions when the relevant relations are H-representations, singletons, empty sets, or universal sets and the terminal objective is linear. It minimizes each branch objective with exact dyadic arithmetic, compares path minima as exact rationals, and verifies supplied optimal-face relations in both inclusion directions, including candidate anchors. Variable, row, integer-bit, generated-row, and operation budgets apply; unsupported arithmetic, unbounded-below branches, and nonattained infima fail closed. The verifier reports numerical assurance only. Its Fourier-Motzkin resource growth limits practical scale, and this bounded implementation does not replace the independent exhaustive oracle required by EXT-07.
## Initial supported profile and rejection boundary

The first profile is finite-horizon and discrete-time, with mode-specific
affine flows, continuous controls, finite modes/edges, and exact polyhedral
state/control/guard/reset relations. A trajectory is a witness in one joint
feasibility relation: mode and edge sequence, controls, intermediate flow
states, and reset outputs are existential variables. The profile represents all
feasible tuples and, when optimizing, all globally optimal tuples under that
relation. A nonfunctional reset therefore represents alternative feasible
post-reset states; it does not promise that a physical system with nondeterministic
reset behavior succeeds for every possible outcome. Requests for universal
reset-outcome guarantees or robust success are unsupported and rejected. It
must use an exact polyhedral relation operation supported by the selected provider.
"Exact" describes the set operation: no geometric approximation or
cross-branch convexification is introduced. It does not promise validated
arithmetic or prove a numerical provider's result. Provider assurance is
recorded separately. The implementation includes an exact integral singleton verifier, one-step and finite-horizon scalar interval verifiers, the bounded two-stage `TwoParameterScalarPolytopeHybridFamilyVerifier`, and the bounded `ExactLinearHHybridFamilyVerifier` described above. The scalar verifiers retain their documented interval/polygon domains; the exact H verifier admits broader relation dimensions and forms only within its exact arithmetic and resource limits. None of these finite profiles establishes the full EXT-07 acceptance contract.

## Required request-admission contract

A conforming implementation must admit the complete requested operation before
creating a provider workspace or running an algorithm:

1. Validate unique nonempty mode/edge IDs, stage counts, coordinate labels,
   coefficient shapes, source/target edge modes, the request-selected initial
   mode/state, and all relation dimensions.
2. Confirm exact support for each mode's flow, every required guard
   intersection, reset relational image/projection, and branch-labelled union
   over the finite transition graph.
3. Validate `Q_T` and the per-mode supported terminal objectives, including
   dimensions, objective policy, shared scalar quantity/units, and global
   minimization semantics; confirm that a family verifier covers the complete
   requested relation and all-optimal-branch claim.
4. If any check fails, return a request-scoped unsupported/rejected result
   naming the first unsupported capability and the affected mode/edge/stage;
   do not start an algorithm, create a workspace, or publish partial family
   evidence as complete.

The current implementation does not yet satisfy this full admission contract.
Portfolio builders preflight the complete enumerated path set for supported
direct joint-H representations and relation resource limits before branch
construction. The verified builder additionally preflights the verifier domain.
Other provider operations, terminal-policy coverage, and general
continuous-family support remain EXT-07 acceptance work.

The initial profile does not infer support from the presence of lower-level
types. It rejects, before workspace creation, nonempty temporal couplings until
EXT-03 supplies compatible memory lifts; finite/mixed controls until EXT-02
defines joint action/branch semantics; observation-dependent policies and
correlated initial/external quantifiers until EXT-04 defines their game and
information semantics; and nonlinear flows or approximate geometry without a
separate error/coverage contract. Validated assurance is unavailable unless
selected operations and the family checker provide matching validated
certificates. Numerical residuals or a finite test suite alone cannot certify
complete coverage of continuous hybrid families.

Finite mode/edge count bounds path enumeration only. It is not a general
scalability guarantee: the number of paths can grow exponentially with `T`,
and relational projection can grow the polyhedral representation. Reports
must disclose dimensions, mode/edge counts, reachable path counts, generated
and retained branch counts, provider identities, resource limits/observations,
and rejected capabilities. Any pruning requires a reviewed proof that it
preserves all optimal branches and their continuous relations.

The current model-level `HybridCapabilityReport` reports the requested horizon,
mode and transition counts, each mode's state/control dimensions, maxima across
the mode catalogue, profile-admission diagnostics, caller path/horizon limits,
and a complete allowed-path count only when enumeration finishes within those
limits. A missing count means path enumeration did not complete; a reported
count is request-scoped and does not imply that relation composition, solver
execution, or family verification is supported or scalable. Per-operation
provider/resource observations and generated/retained branch counts remain
responsibilities of the synthesis and adapter reports.

The direct joint composer exposes an operation trace, and every
`HybridPathProgram` retains that trace with the relation limits used. Each
record binds an initial-state, mode invariant, flow, control set, transition
guard, or reset relation to its stage and mode/edge identity, identifies the
composer implementation and version, and records joint-variable, added-row,
cumulative-row, and cumulative matrix-element counts. Both successful and
failed composition reports retain the configured limits and the operation
records completed before a diagnostic or cancellation; path-program and
portfolio builders propagate those failure reports without dropping the path
identity. Solver-provider provenance remains attached to each branch
execution. The default reachability adapter wraps this same direct joint-H
composer. The separate projected-state adapter independently builds and
projects a one-transition scalar relation; multi-stage and general-dimensional
projected reachability remain unsupported. The compiled verifiers cover integral singleton paths,
one-step scalar interval families, and the bounded finite-horizon
single-parameter scalar interval profile described above, plus the separate
two-stage/two-parameter scalar polygon profile. They do not cover general
continuous polytope families. These verifier domains reject unsupported input
when verification runs; `build_hybrid_portfolio_programs_with_verifier` also
rejects unsupported verifier domains and declared trajectory objective
capabilities before building branch programs. Validated objective assurance
remains unsupported; adapter-specific objective-policy semantics, broader
provider-operation admission, general projected-set reachability, and broader
multiple-parameter verifier coverage remain incomplete.

## Independent test oracle requirements

The exhaustive oracle independently enumerates every permitted mode/edge
sequence for tiny fixtures, then formulates the corresponding full
state/control/pre-reset joint relation directly. It compares feasible branches,
objective values, and all optimal branch identities with the composed hybrid
result. It must include at least:

- a guard that admits exactly one of two outgoing edges;
- one flow that enters an edge guard and another that exits it, checking that
  the guard is evaluated after the flow and before reset;
- a reset with different source and destination dimensions;
- a forbidden edge and an empty guarded branch;
- parallel edges with one mode path, plus duplicate enumeration of one edge
  path;
- tied optimal edge paths whose continuous families differ;
- cancellation before workspace creation and cancellation during branch work;
- path and polyhedral resource limits, with no unsupported/limited branch
  promoted to a complete result.

The oracle must not call the production path enumerator, guard/reset composer,
or verifier. Tiny exact fixtures use rational coefficients and literal expected
relations so that rounding tolerance cannot turn a missing branch into a pass.

## Coordination boundary

EXT-04 owns initial-set quantifiers and information/observation-based policies;
EXT-03 owns temporal coupling and its memory augmentation; EXT-02 owns finite
and mixed action identity and tie semantics. This proposed EXT-07 contract
shares none of those unsupported meanings: it uses one request-selected known
initial mode/state, existential reset witnesses (not universal guarantees),
continuous open-loop controls, and no temporal or observation coupling in its
first executable profile. Integrations with those
extensions require a separately reviewed contract revision and capability
combination; their semantics must not be guessed from hybrid mode paths.

