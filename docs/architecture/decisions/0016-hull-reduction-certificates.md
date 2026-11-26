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

## Reducer mechanics (2026-11-26)

These decisions govern how the certified reducers compose certificates, stage
work, and schedule execution. The corresponding functions retain their local
guards against malformed input, unsafe deletion, and observer interference.

- **Certificate composition.** A removal certificate may refer to another
  removed point. Verify a candidate by walking only its reachable certificate
  dependency graph, then accumulating coefficients to final retained support in
  topological order. Use workspace linear in the number of input points; do not
  materialize a dense expansion for every removed point. Reject missing
  certificates, cycles, negative or nonfinite weights, and any nonpositive
  total weight.
- **Out-of-policy restoration.** Compose every removal to the final retained
  set before acceptance. If a composed combination exceeds the numerical
  policy, restore the latest failing support point to the retained set and
  recompose; restoring that point can make earlier dependent certificates valid
  on the next pass. Repeat until every remaining removal composes within
  policy.
- **Grouped staging.** In the grouped reducer, ten consecutive certified
  removals trigger a grouped stage. The tenth redundant candidate is returned
  to the grouped remainder rather than emitted as a streamed certificate; the
  grouped stage reclassifies it against the fixed retained set and nearby
  supports. A stopped or unsupported stream leaves the unclassified suffix for
  the final shared pass, so no candidate is discarded on an uncertain result.
- **ITI-S17 seed order.** For the A44 reducer, seed the retained set with the
  first `k + 1` candidates in farthest-first order from the box center, then
  classify the remainder incrementally. The paper's earlier "increasing
  distance" sentence conflicts with its farthest-first seed description; the
  implementation records the farthest-first reading.
- **Input validation before ordering.** The ordered reducer validates point
  dimensions and finiteness before any comparator runs and delegates malformed
  input to the shared in-order reducer for its established diagnostics. No
  comparator may observe mismatched dimensions or nonfinite values.
- **Recursive concurrency bound.** A recursive subtree is sequential
  internally. Only the caller may run the root's left and right subtrees
  concurrently, bounding active workers at two.
- **Observer isolation.** A child-LP trace observer records invocations without
  altering the reducer's LP execution. Capture failure or record exhaustion
  increments omission state; it must not propagate an exception into the
  reducer.
- **Halfspace redundancy certificate.** For a candidate row `a*x <= b`, solve
  `min(-a*x)` and require a finite optimal lower bound `L` with `-L - b <= 0`
  in strict binary64 comparison. Because `min(-a*x) >= L` implies
  `max(a*x - b) <= -L - b`, tolerances must not turn a positive maximum
  violation into a deletion.
