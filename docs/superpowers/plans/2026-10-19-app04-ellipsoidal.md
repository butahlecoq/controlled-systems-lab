# APP-04 Directional Ellipsoidal Approximation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a reviewed native directional ellipsoid enclosure for bounded planar V sets, explicit finite-family semantics, and published low-dimensional evidence.

**Architecture:** A new immutable payload defines the ellipsoid through center, invertible orientation rows and nonnegative radii. A registered approximation workspace constructs candidate outputs; the existing approximation policy independently checks complete V-vertex inclusion using exact dyadic comparisons before admitting the outer relation. A separate family builder retains intersection/union semantics without pretending one ellipsoid represents a finite family.

**Tech Stack:** C++20, CMake, doctest, Python saved-report tools and GitHub Pages. No MATLAB, ET, solver, or new package dependency.

**Spec:** `docs/superpowers/specs/2026-10-19-app04-ellipsoidal-design.md`

## Global Constraints

- Only nonempty bounded native 2D V inputs and numerical assurance are admitted by the native producer.
- Stored binary64 coefficients define the mathematical sets; no validated rounding, global error bound, ET equivalence, speedup or historical reproduction claim.
- Native output size is one ellipsoid; finite families retain every member and its relation.
- Preserve a clean frozen source commit for capture and publish immutable saved raw records, 2D HTML/SVG, exact-byte manifest and offline ZIP through the allowlisted Pages workflow.

## Review Focus

- A forged `SetHandle` envelope or payload must not pass import or structural admission (Task 1/2 tests).
- A singular or near-singular orientation must refuse without converting a line to a full-dimensional ellipsoid (Task 1/2 tests).
- Rounding, overflow and underflow in projected bounds and radii must refuse or round outward; no false outer claim (Task 2 tests).
- A zero-width direction must remain an equality and yield a PSD degenerate set (Task 1/2 tests).
- A finite family must reject mixed references, mixed relations and unsupported inner claims; no accidental single-ellipsoid collapse (Task 3 tests).

---

### Task 1: Immutable planar ellipsoid representation

**Files:** Create `include/csl/geometry/ellipsoidal.hpp`, `src/geometry/approximation/ellipsoidal_set.cpp`, `tests/contract/geometry/ellipsoidal_set_tests.cpp`; modify `src/geometry/Module.cmake` and `src/geometry/Tests.cmake`.

**Interfaces:** `make_ellipsoid(EllipsoidInput) -> variant<EllipsoidSet,Diagnostics>`, `from_ellipsoid_handle(SetHandle) -> variant<EllipsoidSet,Diagnostics>`, `EllipsoidSet::as_handle()`, accessors for ID, center, orientation, projected bounds, radii and labels; numerical `support(Vector) -> variant<double,Diagnostics>`. The input carries two coordinates, a `2×2` finite invertible orientation, nonnegative projected bounds/radii satisfying exact `r_i²≥2m_i²` or zeros, and unique labels. The implicit shape is PSD by construction.

- [ ] Write contract tests for the literal square `c=(0,0), B=I, m=(1,1), r=(√2 rounded upward,√2 rounded upward)`, finite support, point and line degeneracy, malformed shape, bad labels and forged envelopes.
- [ ] Configure a backend-disabled Release build and confirm the new test target fails before the public type exists.
- [ ] Implement the immutable payload and boundary validation; use exact binary64 determinant and radius inequality checks, and refuse nonfinite support evaluation.
- [ ] Build and run the new contract target, then commit the representation and tests.

### Task 2: Directional adapter and independent inclusion gate

**Files:** Create `src/geometry/approximation/ellipsoidal.cpp`, `tests/contract/geometry/ellipsoidal_approximation_tests.cpp`; modify `include/csl/geometry/approximation.hpp`, `src/geometry/approximation/policy.cpp`, `src/geometry/Module.cmake`, `src/geometry/Tests.cmake`.

**Interfaces:** `make_directional_ellipsoid_registration(registry::Method,SetId,Matrix)` offers `ApproximationPort` output `csl.ellipsoid.directional2d`, `SetRelation::outer`, numerical assurance. Unique method IDs allow multiple orientation registrations. Add `StructuralBasis::v_ellipsoid_containment` and budget recognition to policy. Adapter computes center from V coordinate bounds, each projected maximum by exact dyadic arithmetic and outward conversion, and each finite radius by upward binary64 adjustment until exact `r_i²≥2m_i²`; policy independently checks all V rows and the output construction.

- [ ] Write tests that call `run_registered` for the square with identity and rotated orientations, assert the returned relation/basis, independent support inclusion and actual output values. Add line, singleton, empty, ray, H, budget, validated-assurance, cancellation, overflow and forged-provider cases.
- [ ] Run the target to observe absent registration/policy support.
- [ ] Implement the producer and structural verifier, keeping stop checks inside vertex loops and rejecting nonfinite or unrepresentable bounds.
- [ ] Run focused and baseline approximation tests, then commit.

### Task 3: Finite families, documentation and installed consumer

**Files:** Extend `include/csl/geometry/ellipsoidal.hpp`, add `src/geometry/approximation/ellipsoidal_family.cpp`, `tests/contract/geometry/ellipsoidal_family_tests.cpp`, `tests/installed/ellipsoidal_client.cpp`; modify geometry CMake/installed fixtures and `docs/contracts/{approximation,core-interfaces}.md`; create `docs/contracts/ellipsoidal-approximation.md` and `docs/research/ellipsoidal-comparison.md` from the archived source audit, with current status corrected.

**Interfaces:** `run_ellipsoid_family(registry, vector<registry::Method>, ApproximationRequest, ExecutionContext) -> variant<EllipsoidFamily,registry::Rejection,OperationStopped,Unsupported>`. It runs each member through `run_registered`, retains their evidence and the common reference, and labels `intersection` for outer or `union` for inner; no family support or collapse route.

- [ ] Write tests for two outer orientations, preserved identities and intersection semantics; reject empty method list, mismatched reference/output/assurance and an inner request with no registered inner producer.
- [ ] Implement the family builder and public contract docs; add an installed `find_package(CSL CONFIG)` client exercising the route and family.
- [ ] Run focused tests and the installed client in Release, then commit.

### Task 4: Frozen numerical evidence and 2D example

**Files:** Add `benchmarks/reporting/app04/driver.cpp`, `scripts/reports/app04/{capture,collect,render_saved}.py`, `tests/reporting/test_app04_saved.py`, a content-bound bundle under `reports/algorithm-results/`, `reports/algorithm-results/app04-publications.json`, `scripts/reports/stage_app04.py`; modify `cmake/OptionalReports.cmake` and `.github/workflows/algorithm-reports.yml`.

**Interfaces:** The driver runs a literal symmetric square through public `run_registered` and independently checks the produced center, orientation, radii, PSD construction and complete four-vertex inclusion for every call. The collector binds raw calls to one clean source commit and executable hash; the renderer uses only saved bytes. The stager verifies exact inventory, manifest, ZIP, HTML links and catalog hashes.

- [ ] Add a native report smoke test and a saved-data test that fails on an altered output, count, source receipt or asset byte.
- [ ] Implement the driver, capture/collect/render/stage pipeline and report text with the complete input, labelled square/ellipse plot, hand-checkable inclusion inequality, limitations and reproduction commands.
- [ ] Capture one clean frozen Release revision, retain raw CSV including failures, generate the bundle, and verify exact-byte regeneration, visual layout and local site links.
- [ ] Run full reporting tests, commit the immutable bundle and workflow adapter, then push a draft PR.

### Task 5: Independent review, integration and cleanup

**Files:** PR and issue discussion; no code file is implied unless review finds one.

- [ ] Request independent specification, standards and scientific saved-result SubAgent reviews on exact base/head commits and have each post findings on the PR.
- [ ] Fix findings, post fix responses, rerun relevant tests and request scoped follow-up review.
- [ ] Confirm exact-head native and reporting CI, mark ready and merge using a merge commit so the frozen source remains reachable.
- [ ] Verify live Pages HTML, SVG, raw JSON and ZIP against committed bytes; close #34 with evidence and refresh affected issue dependencies.
- [ ] Audit free space, worktree status including ignored output, and local/remote branches. Preserve the final raw capture and remove only clean merged disposable worktrees/branches.
