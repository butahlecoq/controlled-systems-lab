# GEO-02 Sound Candidate Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development for implementation and review.

**Goal:** Apply hull-reducer candidate deletions only when exact dyadic arithmetic proves each stored binary64 convex combination reconstructs its removed point, and publish measured candidate-count evidence.

**Architecture:** Keep the LP reducer replaceable and use its primal vector only as a candidate certificate. A small internal exact verifier checks nonnegative binary64 weights, exact unit sum, and exact coordinate reconstruction over the original represented coordinates; uncertainty keeps the full cloud. The affine/sum boundary independently validates the certificate before applying retained indices, then the report records generated and materialized candidate counts and an explicit reduction status.

**Tech Stack:** C++20, existing LP and geometry providers, doctest, current GEO-02 report tooling.

**Spec:** GitHub issue #168; `docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md` requirements ALG-02/03/04 and T-G01/T-G02.

## Global Constraints

- Never authorize deletion from floating-point tolerance or residual evidence alone.
- The returned set relation remains `equivalent` only when each deletion has an exact supported convex-combination proof.
- Unsupported, malformed, stopped, underflow-sensitive, or inexact proof attempts preserve all unproved candidates.
- Preserve original point indices, labels, empty/singleton behavior, and finite-action semantics.
- Reports use independent analytic support oracles and raw trial records; do not claim a speedup or general scalability from microfixtures.

## Review Focus

- Duplicate and interior points with exact binary weights must be removable; verify analytic support values.
- Near-extreme points under loose tolerances must remain; prove no positive displacement is rounded into authorization.
- Subnormal products must not disappear in the exact verifier; compare exact dyadic sums.
- True extreme points must remain even when LP residuals are within tolerance.
- Failed or incomplete reducer results must not cause an equivalent but altered result; test the public GeometryPort path.

### Task 1: Exact convex-combination certificate

**Files:**
- Modify: `src/geometry/hull_reducer.cpp`
- Test: `tests/unit/geometry/hull_reducer_test.cpp`

**Interfaces:** Keep the public HullReducer contract unchanged; certificate construction becomes stricter and authorizes only exact dyadic equality for stored weights and coordinates.

- [ ] Add failing tests for exact duplicate and midpoint/interior removal, non-exact near-interior refusal, true extremes, and subnormal-sensitive equations.
- [ ] Verify RED against the current tolerance-based implementation.
- [ ] Implement an exact binary64 sum/product comparison without external dependencies; fail closed on capacity/unsupported cases.
- [ ] Verify focused unit tests and existing reducer tests.

### Task 2: Apply only independently verified retained indices

**Files:**
- Modify: `src/geometry/affine_sum.cpp`
- Test: `tests/contract/geometry/affine_sum_tests.cpp`

**Interfaces:** Preserve `GeometryPort`; validate every removal certificate with the same exact predicate before selecting retained candidate rows.

- [ ] Add failing public-operation cases for exact redundant clouds, approximate certificates, malformed indices, and support preservation.
- [ ] Verify RED against current behavior (all candidates retained / candidate not applied).
- [ ] Apply the retained candidate indices only after the full reduction proof passes; otherwise preserve the entire generated cloud.
- [ ] Verify analytic affine-image and Minkowski support identities, metadata, and existing tests.

### Task 3: Report candidate reduction and numerical evidence

**Files:**
- Modify: `reports/algorithm-results/tooling/geo02/affine_sum_driver.cpp`
- Create: one new immutable `reports/algorithm-results/geo02-*` publication bundle via the repository report collector.

- [ ] Record generated candidate count, materialized output point count, and status (`reduced` / `preserved`) in raw records and HTML.
- [ ] Add a deterministic redundant-point fixture with a literal support oracle.
- [ ] Run warmups and repeated trials from a clean build; retain raw records/provenance and avoid speedup claims.

### Final verification

- [ ] Run the complete relevant unit/contract suite and full CTest matrix available locally.
- [ ] Run clean build, report collection, and `git diff --check` on exact final HEAD.
- [ ] Obtain separate Standards and Spec reviews; post actionable comments and fixes on the PR, then scoped re-reviews.
- [ ] Merge only after required hosted CI and reviews pass; close #168 only if every acceptance criterion is demonstrated.
