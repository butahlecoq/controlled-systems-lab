# ADR 0016: Require verified certificates for hull reduction

Date: 2026-11-22
Status: Accepted

## Context

Hull reducers use LP membership queries and phase-one basis data to identify
source points for removal. A tolerance-based membership result can accept a
point that is close to a convex combination but is not an exact combination in
binary64. In the basis-reuse reducer, structural basis points are retained as
support points; nonbasis points are the removal candidates.

## Decision

- Validate each removal with the exact binary64 convex-combination verifier.
  A certificate whose represented weighted sum differs by even one binary64
  step is rejected; tolerance does not authorize removal.
- In basis reuse, retain structural basis points as supports and consider
  nonbasis points as removal candidates. Use exact certificates before removal;
  basis coordinates alone do not authorize deletion.
- Retain the LP-based reducer as the fallback when the provider does not expose
  optional basis diagnostics.
- In hull-preservation tests, check every original input point for membership
  in the retained hull. The reverse containment follows from retained source
  IDs being a subset of the input. When comparing two reducers' retained sets,
  check membership in both directions; source identity alone cannot establish
  equality between them. The LP queries use numerical tolerances and are
  regression evidence, not a formal proof of exact containment.

## Consequences

The reducer may retain points that a tolerance-only test would remove. The
structural-interior fixture puts that point first because the fixed Bland
phase-one provider deterministically returns it as a basic structural point.
The regression confirms that this point remains retained even though it is not
an extreme point.
