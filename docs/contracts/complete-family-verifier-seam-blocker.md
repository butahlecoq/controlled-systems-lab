# Complete-family verifier boundary and scientific gate

**Status at main `470ab2e8cc40652a6207bd42222c23e18342a70f`:** the shared fail-closed publication seam described by this file's former blocker is delivered. General numerical coverage evidence remains an open scientific gate. This record tracks that distinction for [#155](https://github.com/butahlecoq/controlled-systems-lab/issues/155) and [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8); it does not approve new assurance claims.

## Delivered boundary

The prepared strategy owns the frozen resolved problem, effective family request, strategy identity/version, and lineage. [`StrategyRegistry::prepare`](../../src/registry/registry.cpp#L208-L230) selects a compiled verifier for established completeness and rejects a missing or unknown verifier before planning. [`VerifiedStrategyWorkspace::solve`](../../src/registry/registry.cpp#L16-L93) checks the proposal against that prepared identity, requires the selected verifier's registered proof payload, calls the verifier, and only then publishes through the verified authority. [`check_family_evidence`](../../src/contracts/synthesis.cpp#L64-L96) rejects unverified complete-family values and checks their binding.

The guard is exercised by the public prepared-strategy regression [“rejects completeness claims without the selected verifier proof”](../../tests/contract/registry/registry_tests.cpp#L1171-L1249). The generic publication seam has a test-only verifier fixture in [compiled_verifier_catalog_tests.cpp](../../tests/synthesis/compiled_verifier_catalog_tests.cpp#L137-L192). These establish the boundary and fail-closed behavior; they do not establish a general coverage theorem.

## Remaining gap

The production catalog currently provides profile-specific analytic verifiers for T-S01 and T-S02 ([`compiled_verifiers.cpp`](../../src/registry/compiled_verifiers.cpp#L308-L410), catalog dispatch at [lines 506–517](../../src/registry/compiled_verifiers.cpp#L506-L517)). They validate those canonical problems, relations, optimum claims, and bounds. They are not a general numerical coverage procedure for arbitrary supported problems or Strategy A/B outputs.

`NumericalCoverageEvidence` is a typed proposal payload, not proof by construction. A residual, tolerance check, solver status, or list of witnesses cannot by itself prove that the published joint relation contains every optimal history. Until a profile's coverage evidence has a reviewed procedure and a compiled verifier that checks it against the frozen request, that profile must fail closed: report the supported candidate/partial result or reject complete-family publication. This is consistent with #155's completeness-guard addendum and the scientific gates in the [class-level architecture](../superpowers/specs/2026-10-12-class-level-system-architecture.md#scientific-gates-before-complete-family-acceptance).

## Scientific decision record

**Recorded decisions:**

- The target in #8 is the full joint state/control argmin relation. A witness set, independent stage marginals, or a near-optimal sublevel set is not an equivalent output.
- Numerical and validated assurance remain distinct. The delivered boundary can verify registered, profile-specific evidence; it does not turn arbitrary symbolic text, a certificate reference, or residual data into coverage evidence.
- No general numerical coverage procedure, arithmetic/rounding model, tolerance values, or acceptance thresholds are approved by this record. No generic Strategy A/B complete-family claim follows from the current T-S01/T-S02 cases.

**Proof obligations before admitting a new numerically supported complete-family profile:**

1. State the supported model/objective assumptions and define the exact joint optimizer relation to be returned, including ties, nonunique terminal minimizers, and distinct histories leading to the same terminal point.
2. Give a reviewed argument connecting the computed relation to that full optimizer relation. Specify whether each construction/conversion is exact or what sound inclusion/error guarantee it supplies; approximation direction must support the claimed coverage.
3. Establish optimum evidence separately from relation coverage. An objective bound or a feasible incumbent can support the value claim but does not show that no optimal histories are missing.
4. Define the arithmetic, rounding, tolerance, and error-accounting policy used by the coverage procedure. Thresholds are profile-specific review decisions; they are intentionally unspecified here.
5. Implement a verifier that checks the evidence against the immutable resolved problem, effective request, ordered joint-coordinate schema, strategy/version, and ordered transformation lineage. It must reject missing, malformed, mismatched, or unsupported proof data.
6. Add independent public-path tests for positive and adversarial cases. Preserve T-S01's `u0 + u1 = 1` dependence and T-S02's constant-objective full feasible set; include ties/degeneracy and any approximation route claimed by the profile. A residual-only or sampled-witness test cannot serve as a coverage oracle.

**Open review decisions:** scientific reviewers and the owner must approve each profile's coverage theorem, supported operations/representations, arithmetic and tolerance policy, and thresholds before its verifier is enabled. These decisions belong to #155/#8 and the strategy reviews #66/#67. This record does not select a numerical method or threshold on their behalf.