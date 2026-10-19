# GEO-08 Lazy Geometry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish registered lazy affine/projection/sum expressions with numerical support samples and explicit budgeted V materialization.

**Architecture:** Immutable payloads own typed operands. Separate geometry registrations construct expressions and answer support; a conversion registration materializes finite V output with checked growth and caller limits.

**Tech Stack:** C++20, existing CSL `GeometryPort`/`ConversionPort`, CMake, doctest.

**Spec:** `docs/superpowers/specs/2026-10-19-geo08-lazy-geometry-design.md`

## Global Constraints

- Only native V and empty leaves are admitted; no implicit H/V conversion.
- `Assurance::validated` and unsupported guarantees reject before workspace creation.
- Binary64 support samples and materialization do not claim validated inclusion.
- Source handles and operand arrays are owned immutably; cancellation and limits prevent partial publication.
- Do not run benchmarks or label sampled directions as exact set coverage.

## Review Focus

- A forged handle envelope must fail inspection, not inherit another set's claim.
- A positive transformed ray direction must return unbounded support.
- Multiplication of child vertex counts must fail closed on overflow or budget breach.
- A zero-dimensional projection must retain one empty-coordinate vertex for a nonempty source.
- A stopped materialization must retain its request, provider, lineage and growth seen so far.

---

### Task 1: Expression values and admission

**Files:** `include/csl/geometry/lazy.hpp`, `src/geometry/lazy/expression.cpp`, `src/geometry/Module.cmake`, `src/geometry/Tests.cmake`, `tests/contract/geometry/lazy_geometry_tests.cpp`.

**Interfaces:** `make_expression_registration()`, `inspect_expression(const SetHandle&)`, immutable `ExpressionDescription` with operation operands and creation evidence.

- [ ] Write tests for affine, projection and independent-sum construction, nested ownership, operand identity, unsupported operation/assurance, and forged metadata.
- [ ] Configure/build and confirm missing-route failure.
- [ ] Implement expression admission and immutable payload; run the focused tests to green.
- [ ] Commit the expression route.

### Task 2: Lazy support and samples

**Files:** `include/csl/geometry/lazy.hpp`, `src/geometry/lazy/support.cpp`, `tests/contract/geometry/lazy_geometry_tests.cpp`.

**Interfaces:** `make_support_registration()`, `sample_support(const SetHandle&, const std::vector<Vector>&, const GeometryRequestIdentity&, const ExecutionContext&)` returning labelled `SupportSamples` or stop/rejection.

- [ ] Write literal support tests for a transformed square, nested projection, independent sum, empty/ray leaves, and a sampled-direction evidence boundary.
- [ ] Confirm the tests fail on the absent support route.
- [ ] Implement recursive numerical support with finite arithmetic and stop checks; run focused tests to green.
- [ ] Commit support and sampling.

### Task 3: Explicit materialization

**Files:** `include/csl/geometry/lazy.hpp`, `src/geometry/lazy/materialize.cpp`, `tests/contract/geometry/lazy_geometry_tests.cpp`.

**Interfaces:** `MaterializationBudget{max_vertices,max_rays}`, `make_materializer(MaterializationBudget)`, `materialize_expression(const ConversionRequest&, const PreparedProvider<ConversionPort>&, const ExecutionContext&)` returning growth and lineage for success or failure.

- [ ] Write tests for V vertex/ray output, exact row-count growth, budget and overflow rejection, cancellation/deadline, and retained failure provenance.
- [ ] Confirm the tests fail on the absent materializer.
- [ ] Implement checked row accounting and capped recursive enumeration; run focused tests to green.
- [ ] Commit materialization.

### Task 4: Delivery and integration

**Files:** `docs/contracts/lazy-geometry.md`, `docs/architecture/set-representations-and-ellipsoidal-toolbox.md`, `tests/installed/lazy_geometry_client.cpp`, Pages example/staging and reporting tests as appropriate.

**Interfaces:** Installed `CSL::lazy_geometry` target and public headers; discoverable 2D example with inputs, labelled plot and reproduction commands.

- [ ] Add external installed-client and example checks before wiring exports and staging.
- [ ] Verify Windows Release focused and full CTest, installed `find_package` client, reporting tests, and `git diff --check`.
- [ ] Publish PR with release/package impact; request independent specification and standards SubAgent reviews as PR comments.
- [ ] Fix findings, re-review affected scope, wait for exact-head CI, merge, verify Pages, close #52, and clean the branch/worktree.
