# ADR 0003: Numerical input and completeness evidence

Date: 2026-10-18. Status: accepted for the initial architecture under the owner's delegation. This decision records the input semantics and assurance boundary for numerical synthesis; it does not approve a generic Strategy A/B completeness claim or set physical error thresholds.

## Decision

- **Represented model:** when the runtime confirms IEC 60559 binary64, each finite stored `double` in a `ResolvedProblem` denotes the exact dyadic rational represented by its bits for the computational model. The resolved-problem digest binds those stored values. A claim about authored decimal reals, measurements, or a physical nonlinear model is a separate claim and requires explicit conversion, uncertainty, or model-error evidence. A platform without the declared binary64 format is unsupported for this profile.
- **Numerical assurance:** solver status, floating-point residuals, samples, and matching objective values are numerical evidence. None alone proves exact feasibility, global optimality, set equivalence, or complete-family coverage. Exact-dyadic checking can establish properties of stored values; it does not certify the solver, geometry producer, or conversion that created them.
- **Complete-family publication:** a numerically supported complete family may be published only through a selected compiled verifier for an admitted profile. The verifier checks soundness and coverage against a binding of the resolved-problem digest, effective objective and family request (including tolerance-profile identity), ordered joint coordinates, strategy identity/version, and ordered transformation lineage. The verifier, rather than a caller-provided evidence label, decides whether the profile's coverage evidence passes. The current production catalog remains limited to its profile-specific T-S01 and T-S02 verifiers; this decision adds no profile and makes no generic Strategy A/B coverage claim.
- **Tolerance policy:** there is no project-wide numerical acceptance threshold. Each admitted numerical profile defines and versions its own residual quantities, units/scales, requested tolerances, effective backend tolerances, and independent acceptance criteria. Backend defaults are recorded as execution settings and never stand in for scientific acceptance criteria.
- **Unresolved evidence:** when a requested claim lacks a matching verifier, or numerical evidence cannot decide its acceptance conditions, return the supported partial/candidate outcome or an unsupported/undetermined result. Keep run termination separate from mathematical status and evidence status. Validated assurance requires a supported validated arithmetic/model profile and a checker for its certificate; no general validated profile is currently available.

## Implementation update (2026-10-24)

The compiled catalog now includes Strategy A's bounded
`strategy-a.nominal-linear-exact-v1` profile alongside the profile-specific
T-S01/T-S02/T-S03 verifiers. It uses exact dyadic reconstruction of the
represented finite binary64 problem, exact nonempty/boundedness and objective
checks, and two-way inclusion of the proposed optimal relation. It binds the
prepared finite-horizon Strategy A lineage and fails closed on unsupported or
resource-capped cases. The profile remains Strategy A-only; exact checks of
the represented problem do not validate the binary64 forward geometry or
optimization producers and do not establish generic Strategy A/B coverage.

## Consequences

The architecture has a stable, honest default without inventing universal physical tolerances. New numerical profiles still require a reviewed coverage argument, profile-specific acceptance criteria, adversarial tests, and a compiled verifier before they can publish a complete family. The [decision-support report](../../research/issue7-numerical-coverage-policy-options.md) compares the alternatives and source limits; the [complete-family verifier boundary](../../contracts/complete-family-verifier-seam-blocker.md) tracks current implementation status.
