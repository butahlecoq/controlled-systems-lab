# ADR 0016: Require verified certificates for hull reduction

Date: 2026-11-22
Status: Accepted

## Context

Hull reducers use LP membership queries and phase-one basis data to propose
source points for removal. A tolerance-based membership result can accept a
point that is close to a convex combination but is not an exact combination in
binary64. Basis membership is also only a candidate signal; it does not by
itself prove that removing a source point preserves the hull.

## Decision

- Validate each removal with the exact binary64 convex-combination verifier.
  A certificate whose represented weighted sum differs by even one binary64
  step is rejected; tolerance does not authorize removal.
- Treat phase-one basis points as candidates, not certificates. Use the exact
  verifier before removal, and retain the LP-based reducer as the fallback when
  the provider does not expose optional basis diagnostics.
- In tests, compare the proposed retained set with the baseline in both
  containment directions using independent LP membership queries. Every
  retained point is an original point, so the reverse direction follows from
  source identity. These numerical LP queries are regression evidence, not a
  formal proof of exact containment.

## Consequences

The reducer may retain points that a tolerance-only test would remove. Test
fixtures that exercise a structural interior point in the phase-one basis put
that point first because the fixed Bland phase-one provider deterministically
returns it as a basic structural point. This verifies that candidate generation
does not bypass certificate validation or final hull comparison.
