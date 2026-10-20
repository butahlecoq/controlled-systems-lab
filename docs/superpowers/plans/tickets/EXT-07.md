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

This ticket is intentionally later than the nominal v1 comparison and may refine model, geometry, strategy, and result contracts. Coordinate with model tickets and the shared outcome contract [SYN-07](https://github.com/butahlecoq/controlled-systems-lab/issues/155) once created. Resolve semantics and capability/evidence claims in a reviewed design update before implementation. Do not silently infer hybrid meaning from finite controls or stage-varying matrices.

## Design gate

The proposed contract is [hybrid-systems.md](../../../contracts/hybrid-systems.md). It defines a known request-selected initial mode/state, stage-indexed invariants and transition timing, existential reset witnesses (without universal physical guarantees), global minimization over explicitly allowed terminal modes, branch-labelled all-optimal families, replaceable reachability/direct-trajectory/verification adapter seams, admission checks, independent oracle requirements, and the unsupported capability boundary. Implementation remains separate until this design gate is reviewed and accepted.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

The implementation now has profile admission, bounded path enumeration, direct
joint-H path programs, branch optimization, solver provenance, and numerical
family verifiers for integral singleton paths, one-step scalar interval
families, a finite-horizon scalar interval profile with exactly one free
bounded control interval, and a separate exactly two-stage scalar profile with
two free bounded control intervals. These verifier profiles require interval
invariants/guards and deterministic exactly representable scalar affine
resets. A raw-graph oracle covers tied two-stage continuous families and a
three-stage regression fixture covers the generalized single-parameter horizon
path; an independent polygon oracle covers the bounded two-parameter case.
General continuous-polytope oracle coverage, arbitrary horizons and broader
multiple-parameter verification remain open. Portfolio builders now preflight
the complete enumerated path inventory for supported direct joint-H
representations and variable/row/matrix resource limits before constructing
any branch relation. The combined verified-program builder also runs each
built-in verifier's bounded-domain preflight; custom bounded verifiers fail
closed until they implement preflight. The fixed-path reachability adapter
currently uses the direct joint-H composer; a separate projected-set
implementation is not yet supplied.

The EXT-07 report set now includes a measured one-step scalar interval case and
a measured bounded two-control case, each with saved raw rows and an offline
bundle. The one-step report's 2D plot shows control against terminal state; it
does not measure the finite-horizon verifier. The two-control report measures
rectangular parameter sets and the complete minimizing faces for a scalar
linear objective. The visual gallery also contains an analytic constant-zero
objective illustration with coupled triangular and quadrilateral feasible
sets. It links to the measured report while describing the distinct geometry
and objective.
These bounded examples are not scalability results or a completion claim. The
main-only Pages URL and live hashes remain pending until publication succeeds.
