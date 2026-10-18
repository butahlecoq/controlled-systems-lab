# Hybrid system profile (proposed)

Status: proposed for review under EXT-07 #156. This document defines a
finite-horizon, discrete-time hybrid profile and its admission boundary. It
does not claim that the current model, synthesis, geometry, or verification
modules implement the profile. The profile is deliberately distinct from the
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
replaceable reachability contract, but not yet an independent projected-set
reachability algorithm. The direct-trajectory API is replaceable through
`HybridDirectTrajectoryAdapter`; its default implementation,
`JointHDirectTrajectoryAdapter`, builds a branch-labelled joint H relation and
optimization program. Each direct adapter declares whether it preserves the
branch-labelled relation, which objective classes it supports, and its
assurance level; the wrapper rejects missing branch or objective capabilities
before dispatch. Injected adapters must preserve that result contract and
return diagnostics or cancellation without publishing a partial portfolio.
The `HybridFamilyVerificationAdapter` boundary consumes the original model,
request, exhaustive path inventory, branch programs, and candidate faces. Its
wrapper checks complete path and report identity coverage. The report carries
per-path feasibility, objective, and continuous-coverage statuses, but it is
inspection data and cannot publish a `synthesis::OptimalFamily`. No concrete
hybrid family verifier or compiled proof authority is implemented yet.

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
recorded separately, and complete-family publication requires a profile-specific
compiled verifier; no such hybrid verifier currently exists.

Operation admission is complete and occurs before any workspace is created:

1. Validate unique nonempty mode/edge IDs, stage counts, coordinate labels,
   coefficient shapes, source/target edge modes, the request-selected initial
   mode/state, and all relation dimensions.
2. Confirm exact support for each mode's flow, every required guard
   intersection, reset relational image/projection, and branch-labelled union
   over the finite transition graph.
3. Validate `Q_T` and the per-mode supported terminal objectives, including
   dimensions, objective policy, shared scalar quantity/units, and global
   minimization semantics; confirm a family verifier for the resulting
   mode-indexed joint relation and all-optimal-branch claim.
4. If any check fails, return a request-scoped unsupported/rejected result
   naming the first unsupported capability and the affected mode/edge/stage;
   do not start an algorithm, create a workspace, or publish partial family
   evidence as complete.

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
execution. The trace records work performed by the current direct composer; it
does not imply that an independent projected-set reachability algorithm or a
compiled hybrid family verifier has been implemented.

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
