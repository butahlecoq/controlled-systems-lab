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
family verifiers for integral singleton paths, one-step scalar interval
families, a finite-horizon scalar interval profile with exactly one free bounded
control interval, and a finite-horizon scalar polygon profile with exactly two
free control parameters at distinct stages. All other controls must be
singletons. Invariants and guards are intervals and resets are exact scalar
affine relations. Separate raw-graph and polygon-geometry checks cover tied
two-stage continuous families; a three-stage regression places the two free
controls at stages zero and two with a fixed-control stage between them. These
bounded profiles do not establish a verifier
for higher-dimensional continuous polytopes or horizons with more than two free
controls, so those acceptance requirements remain open. Portfolio builders
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
inventory. Full provider/resource aggregation remains open.

Trajectory-adapter objective-type support is checked for every allowed
terminal mode, including modes with no enumerated path, before any branch
program is built. Adapter-specific objective-policy semantics beyond
assurance/tolerance validation, provider-operation admission at other seams,
and general continuous-family support remain open.

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

The EXT-07 report set now contains a one-step scalar interval case and a
two-stage/two-control scalar polygon case, each exercised through path
construction, HiGHS optimization, and family verification. The published
profile summary lists respectively `(state, control, horizon, modes, edges,
paths) = (1, 1, 1, 2, 1, 1)` and `(1, 1, 2, 3, 3, 2)`, using each report's
supported-case description for the scalar dimensions. The first report plots
control against terminal state; the second plots both feasible control
polygons and their tied minimizing faces. These fixed numerical examples do
not establish higher-dimensional scalability or complete the capability-report
acceptance across broader dimensions and mode counts. Main-only Pages URLs and
live hashes remain pending until publication succeeds.
