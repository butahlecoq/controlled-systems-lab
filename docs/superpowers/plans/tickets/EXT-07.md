# EXT-07: Define and implement hybrid-system profiles

GitHub: [#156](https://github.com/butahlecoq/controlled-systems-lab/issues/156).

Test oracle: T-EXT07 (defined in the [master test specification](../../specs/2026-10-11-controlled-systems-master-design.md)).

## Purpose and scope

Track the future hybrid-system extension explicitly. Hybrid systems are reserved as a future model class in the architecture, but their discrete mode semantics are not covered by the finite/mixed-action or observation-feedback tickets. This is a later profile, not part of the initial nominal affine discrete comparison.

Read the [class-level system architecture](../../specs/2026-10-12-class-level-system-architecture.md), [hybrid-system contract](../../../contracts/hybrid-systems.md), and coordinate with [#68](https://github.com/butahlecoq/controlled-systems-lab/issues/68), [#73](https://github.com/butahlecoq/controlled-systems-lab/issues/73), and [#76](https://github.com/butahlecoq/controlled-systems-lab/issues/76). These are coordination points, not native blockers for the design ticket.

## Acceptance criteria

- [ ] Specify finite mode identities, mode-specific affine dynamics and admissible continuous controls, initial-mode semantics, and the stage at which a mode is active.
- [ ] Specify stage-indexed mode invariants, transition guards, permitted transitions, and reset relations with explicit pre/post-transition timing and dimension rules.
- [ ] Preserve the joint relation among state, continuous control, and mode sequence. Retain every optimal mode branch and ties; never replace a hybrid family with a convex hull or an unlabelled sample cloud.
- [ ] Declare supported exact operations and any approximation guarantee for guard intersection, reset images, and mode-branch composition. Reject unsupported operation plans before execution.
- [ ] Keep reachability, direct-trajectory, and verification adapters replaceable and record per-mode/per-transition provenance and resource use.
- [ ] Add unit and contract tests for guard entry/exit, reset maps, forbidden transitions, empty branches, duplicate mode paths, tied optimal branches, cancellation, and resource limits. Compare tiny instances with an independently implemented exhaustive mode-sequence oracle.
- [ ] Provide a capability profile and report for dimensions/mode counts; do not claim general scalability from finite fixtures.

## Dependencies and review

This ticket is intentionally later than the nominal v1 comparison and may refine model, geometry, strategy, and result contracts. Coordinate with model tickets and the shared outcome contract [SYN-07](https://github.com/butahlecoq/controlled-systems-lab/issues/155) once created. Follow the accepted contract for semantics and capability/evidence claims; any refinement requires a reviewed design update. Do not silently infer hybrid meaning from finite controls or stage-varying matrices.

## Design gate

The accepted contract is [hybrid-systems.md](../../../contracts/hybrid-systems.md), reviewed and merged in [PR #471](https://github.com/butahlecoq/controlled-systems-lab/pull/471). It defines a known request-selected initial mode/state, stage-indexed invariants and transition timing, existential reset witnesses (without universal physical guarantees), global minimization over explicitly allowed terminal modes, branch-labelled all-optimal families, replaceable reachability/direct-trajectory/verification adapter seams, admission checks, independent oracle requirements, and the unsupported capability boundary. Implementation is tracked separately in this ticket and remains subject to its full acceptance criteria.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

The implementation now has profile admission, bounded path enumeration, direct
joint-H path programs, branch optimization, solver provenance, and numerical
family verifiers for integral singleton paths, scalar interval families, and a
finite-horizon scalar polygon profile with two free controls at distinct
stages. `ExactLinearHHybridFamilyVerifier` now independently reconstructs
general-dimensional finite-horizon H-relations, minimizes linear objectives
with exact dyadic arithmetic, and checks complete optimal-face relations under
bounded Fourier-Motzkin resources. Regression coverage includes a bounded
continuous path, a flat objective, an unbounded branch, forged faces, and tied
paths whose objective values use different binary scales. The generalized
verifier supports broader continuous domains, but exhaustive independent
relation/objective oracle coverage, resource-scale evidence, and publication
gates remain open. Portfolio builders
now preflight the complete enumerated path inventory for supported direct
joint-H representations and variable/row/matrix resource limits before
constructing any branch relation. The combined verified-program builder also
runs each built-in verifier's bounded-domain preflight; custom bounded verifiers
fail closed until they implement preflight. Fixed-path reachability now has both
the direct joint-H adapter, a bounded one-transition scalar adapter that
independently assembles and projects its path relation, and a general projected
adapter that composes and projects the full joint-H relation for admitted finite
horizons and dimensions. Both projected adapters retain the full branch relation
and provider/row evidence; the general adapter preflights the complete path row
inventory. The new portfolio wrapper enumerates and preflights all allowed paths
before any provider workspace is created, returns each projected branch
separately, and aggregates per-operation resource maxima plus projection-provider
input/output row totals and maxima by provider identity. A two-edge contract
fixture independently checks projections `[0, 0.5]` and `[0, 1]`, aggregate row
counts, and rejection of the second provider admission with zero workspace
creation. Per-path traces remain authoritative; provider-internal resource use
not reported by the provider and broader resource-scale evidence remain open.

Independent continuous-oracle coverage now includes a guarded two-control
two-stage fixture whose two tied paths are each checked against literal
seven-coordinate feasible H-relations, and a one-step two-dimensional-state,
two-dimensional-control box fixture checked against a literal eight-coordinate
relation and complete optimal face. A one-step three-dimensional control-box
case also checks the literal twelve-coordinate relation and complete face while
leaving two tied control directions free. These are named finite cases, not
complete exhaustive coverage across the supported general H profile; broader
independent continuous cases and resource-scale evidence remain open.

Trajectory-adapter objective-type support is checked for every allowed
terminal mode, including modes with no enumerated path, before any branch
program is built. The direct-trajectory preflight contract now states that the
framework checks numerical assurance and finite nonnegative tolerances, while
each adapter must admit or reject its additional tolerance policy before
capability queries or program construction. A custom-adapter regression checks
both accepted and rejected policies at that boundary. Validated objective
assurance remains unsupported, and provider-operation admission at other seams
remains open. General continuous-family verification now has a bounded exact
H-relation implementation, but its independent exhaustive oracle acceptance
work remains open.

The direct-trajectory full-inventory regression now covers three allowed
terminal paths with target dimensions 1, 2, and 3. It checks the ordered
joint-relation dimensions 3, 4, and 5, and verifies that an adapter rejecting
the third path receives the complete inventory before any capability query or
branch build. This remains a small admission fixture, not resource-scale
evidence.

Both projected-state adapters ask their selected geometry provider to admit the
actual terminal projection request during preflight. The one-transition adapter
assembles its independent four-coordinate relation and the general adapter
composes its complete joint-H relation; each request includes coefficients,
labels, equality/inequality partition, metadata, and terminal-coordinate
indices. Provider preparation creates no workspace. Each adapter assembles or
composes the relation again for execution and prepares the request before
workspace creation. Provider admission at other adapter seams and runtime
resource rejection remain open work.

The public API contract tests at
`tests/contract/synthesis/hybrid_reachability_contract.cpp` exercise both the
one-step and general finite-horizon projected adapters. They check one-step
reachability against the guarded terminal interval and verify that an injected
provider rejection occurs before workspace creation. A two-stage 1→2→1 case
checks the complete eight-coordinate joint H relation, terminal projection,
and per-operation stage, mode/edge, implementation, and row/matrix resource
trace. Its injected provider also checks the exact joint relation during
preflight. These public contract cases complement, but do not replace, the
independent raw-graph mode-sequence oracle in the hybrid unit suites.

The public general-projection contract suite now also checks a two-stage scalar
case against the raw-model identity `y = u + v`, with both stage controls in
`[0, 1]`, so the exact terminal set is `[0, 2]`. The test checks interior and
endpoint membership, tight lower and upper bounds, rejection outside the
interval, and projection input/output row evidence against the retained
relation and operation trace. This adds an independent projected-set oracle;
it does not establish higher-dimensional continuous projection coverage or
resource-scale behavior.

The general projected-state contract suite also checks an existential
set-valued reset across a 1→2→1 state-dimension path. With the initial state and
first control fixed at zero, the first reset imposes `p = x_pre` while allowing
an existential `q ∈ [0, 1]`; identity middle flow and the second reset
`y = p + q` give the independently derived terminal set `[0, 1]`. The test
checks the reset's literal H rows, joint-coordinate labels, interval endpoints
and exterior rejection, and provider/operation row evidence. This single
bounded fixture strengthens continuous projection coverage for rectangular
set-valued resets; it does not establish broader polytope or resource scaling.

The exact linear-H family-verifier tests now also include a one-step scalar
continuous reset family. With `u ∈ [0, 1]`, `x_pre = x0 = 0`, and existential
reset constraint `0 ≤ y - x_pre ≤ 1`, minimizing `y` leaves the full optimal
face `y = 0`, `u ∈ [0, 1]`. The exact verifier establishes this literal face
and refutes a feasible candidate that incorrectly fixes `u = 0`, exercising
continuous completeness across a nonfunctional reset. This remains a bounded
one-step oracle rather than exhaustive coverage of the admitted H domain.

A second bounded continuous oracle combines a two-dimensional coupled control
polytope with an existential reset. The raw constraints are `u,v ≥ 0`,
`1 ≤ u+v ≤ 2`, `x_pre = u+v`, and `x_pre ≤ y ≤ x_pre+1`. Minimizing `y`
gives the complete slanted face `u+v=1`, `u,v ≥ 0`, with `x_pre=y=1`.
The exact verifier establishes a literal H representation of that segment and
refutes the feasible optimal subset that adds `u ≤ 0.5`, while retaining
established branch feasibility and objective optimality. This exercises a
coupled two-control polytope and nonfunctional reset together, but remains a
single small oracle rather than exhaustive validation over the admitted H
domain.

The exact H verifier now also has a one-step three-control simplex oracle with
an existential reset. The controls satisfy `u,v,w ≥ 0` and `u+v+w ≤ 1`,
`x_pre=u+v+w`, and `0 ≤ y ≤ x_pre`. Minimizing `y` leaves the full
three-dimensional simplex optimal, with `y=0`. The literal six-coordinate H
candidate is established, while a feasible optimal candidate with the added
facet `u≤0.5` is refuted for incomplete continuous coverage. This directly
exercises a three-free-control optimal family, but does not exhaustively
validate the general finite-horizon H domain.

A second one-step oracle uses the non-simplex control polytope `[0,1]^3` clipped
by `u+v+w≤2`, with the same existential reset and objective. Its complete
optimal family is the three-dimensional truncated cube at `y=0`; the exact H
verifier establishes the full literal face and refutes its feasible `u≤0.5`
subset. This checks a non-simplex three-control polytope, while broader
polytope/oracle coverage and resource-scale evidence remain open.

A third one-step family oracle has four free controls in the simplex
`u,v,w,z≥0`, `u+v+w+z≤1`, flow `x_pre=u+v+w+z`, and existential reset
`0≤y≤x_pre`. The exact H verifier establishes the full 4D simplex optimal face
at `y=0` and refutes its feasible `u≤0.125` subset. The candidate uses dyadic
witness coordinates so the flow equality is exact. This advances the free-
control dimension evidence to four while broader verifier-domain and
resource-scale coverage remain open.

The [EXT-07 capability profile and fixture report](../../../research/ext07-capability-profile.md)
records the declared adapter/verifier domains and named dimensions, horizons,
mode counts, edge counts, path counts, and relation widths. It separates saved
measurements from correctness-only oracle fixtures and makes no scalability
claim. A four-mode, four-edge branching fixture now independently checks its
two allowed paths and exercises a five-variable joint relation at the exact
three-row/fifteen-matrix-element budget, plus rejection at a two-row cap.
Broader resource-scale and higher-mode-count evidence remains open.

The EXT-07 report set now contains a one-step scalar interval case and a
two-stage/two-control scalar polygon case, each exercised through path
construction, HiGHS optimization, and family verification. The published
profile summary lists respectively `(state, control, horizon, modes, edges,
paths) = (1, 1, 1, 2, 1, 1)` and `(1, 1, 2, 3, 3, 2)`, using each report's
supported-case description for the scalar dimensions. The first report plots
control against terminal state; the second plots both feasible control
polygons and their tied minimizing faces. These fixed numerical examples do
not establish higher-dimensional scalability or complete the capability and
resource evidence across broader mode counts. Main-only Pages URLs and live
hashes remain pending until publication succeeds.
