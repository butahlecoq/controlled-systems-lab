# SYN-07 T-S01 midpoint partial-family design

## Scope

Add one reviewed live publication profile for the exact T-S01 nominal two-step
integrator. The published inner relation is the singleton in canonical joint
coordinates `(x0,x1,x2,u0,u1) = (0,1/2,1,1/2,1/2)`, explicitly scoped by
`s=1/2`. This does not claim complete-family coverage, and it does not enable
other partial-family profiles.

The checker admits only the resolved discrete model with `x0=0`, `A=B=1`, zero
offset and external map, independent closed controls `[0,1]`, no temporal or
additional state restrictions, and the resolved quadratic objective
`(x2-1)^2` represented by the exact canonical coefficients. Every scalar is
compared to its exactly representable binary64 literal; no tolerance or
solver-produced residual participates in proof acceptance.

## Authority flow

The strategy returns a `PartialFamilyProposal`, never a trusted
`OptimalFamily`. The prepared `StrategyRegistry` freezes problem, effective
request, coordinates, strategy/version and ordered lineage. Its boundary
compares those fields against the proposal, calls only the selected compiled
`PartialFamilyVerifier`, and invokes `FamilyPublisher::publish_verified_partial`
with a private authority bound to both strategy/version and verifier/version.
Complete-family publication keeps its existing verifier and authority path.
Candidate-family publication does not use either new authority.

The compiled T-S01 midpoint verifier checks the exact resolved profile, the
canonical singleton H-representation, zero optimum bounds, the exact symbolic
membership argument, and the literal scope `s=1/2`. Generic numerical evidence,
arbitrary `SymbolicArgument` payloads, serialized claims and other relation
payload types cannot establish this profile. The public unchecked publisher
continues to reject partial-family claims.

## Tests and risks

The public registry test must run through `PreparedStrategy::create()` and
`StrategyPort::run()`, then inspect the published partial target, relation,
scope, identity and bounds. Adversarial verifier tests change objective,
request, strategy, lineage, relation payload, scope and membership evidence.
An ambiguous result containing both complete and partial proposals is rejected.
Existing complete and candidate tests remain the compatibility guard.

The mathematics is an exact-real argument over the stated profile. The
implementation relies on exact comparisons of canonical binary64 inputs, all
of which are exactly representable here; this must not be generalized to
arbitrary decimal coefficients. This is a singleton inner subset only. It
does not prove that the optimal set consists only of this point, certify a
larger subset, or grant validated-arithmetic assurance. The current run
statistics v4 format still cannot serialize live T-S01 relation capabilities,
so artifact export remains unsupported until a separately reviewed wire
contract is added.
