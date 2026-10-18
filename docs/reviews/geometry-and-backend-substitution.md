# Geometry algorithms and backend substitution review

Issue: [REVIEW-02 / #70](https://github.com/butahlecoq/controlled-systems-lab/issues/70)  
Reviewed base: `599701fb1bd3174d10c9b5d95e9b843d57f67623` (`origin/main`, 2026-10-18)  
Scope: implemented polyhedral geometry, hull membership/reduction, H/V conversion, LP/convex contracts, registration and approximation guarantee routes.

## Review result

No blocking correctness or guarantee-direction defect was found in the examined supported profiles. The adapters state their assumptions and reject unsupported geometry cases. The main remaining architecture limitation is unbounded peak allocation during Qhull conversion; it is disclosed in the conversion contract and remains outside any hard memory guarantee.

This review covers the current implementation and recorded evidence. It does not claim validated arithmetic, general exact H/V equivalence, a general second LP solver, or arbitrary-size conversion support.

## Findings

### P2 — Qhull conversion has no output or peak-allocation budget

`QhullOptions` can cap input ambient dimension and row count. With those limits unset, admission only checks Qhull's signed integer widths. H-to-V conversion also creates dense Eigen copies, a flattened native coordinate buffer, facet and vertex vectors, and an owning output snapshot. Output size can grow combinatorially with the input. There is no Qhull-specific byte reservation, output vertex/facet limit, or peak allocation estimate.

The conversion contract already discloses the absence of default dimension, row, and combinatorial caps and identifies available memory as an implementation limit. This is therefore a known capability gap, not an undisclosed guarantee or a reason to misclassify an incomplete result. Task-level memory reservations can limit admission of concurrent work, but do not cap this adapter's allocator or native RSS. Applications needing a hard peak-memory limit must not treat this adapter as providing one until an operation-level reservation or output cap is available.

Relevant evidence: `src/adapters/polyhedral/qhull.cpp` admission and allocation paths (lines 103–131, 248–254, 406–425, 593–614); `include/csl/adapters/polyhedral/qhull.hpp` options; `docs/contracts/polyhedral-conversion.md` (lines 29–32).

### No finding — a distinct LP implementation is exercised for membership

`phase-one-bland` and `csl.lp.highs` are separate implementations selected through the same `LPPort`. The `phase_one_tests` target compares both on the same immutable LP requests and checks neutral termination, mathematical outcome, program identity, independently recomputed primal residuals, and HiGHS' exact Farkas evidence for infeasible cases. The phase-I implementation explicitly supports zero-objective equality rows and nonnegative variables, which matches the barycentric membership formulation; it does not claim general LP support.

Generic hull membership builds ordinary LP feasibility requests and verifies the returned convex combination independently. Basis diagnostics are optional on `LPPort`; the separate basis-reuse reducer requests them explicitly and falls back when they are absent. Thus generic membership does not depend on phase-I basis data.

Relevant evidence: `tests/contract/phase_one/simplex_tests.cpp` (lines 353–390); `src/optimization/Tests.cmake` (lines 1–6); `src/optimization/phase_one/simplex.cpp` (lines 48–55); `src/geometry/hull_reducer.cpp`; `src/geometry/basis_reuse_reducer.cpp` (lines 79–90, 103–108).

### No finding — LP status and evidence are not overstated

The HiGHS adapter maps completed optimal, infeasible, and unbounded statuses separately from resource limits and numerical failures. Primal and dual residual evaluations are numerical checks. A dual Lagrangian evaluation is explicitly not a certified objective bound; the adapter leaves objective-bound fields unset rather than translating an unestablished bound. Infeasible HiGHS results can carry an exact Farkas certificate only after the independent verifier accepts it. The phase-I/HiGHS comparison asserts that objective bounds remain absent for its zero-objective feasibility profile.

The analytic LP fixtures cover a bounded triangle, offsets, free/fixed variables and equality rows, contradictory rows, an unbounded ray, a degenerate optimal face, and scaled equalities. Rectangular residual maps and their squared-objective transformation are checked against literal coefficients and original-coordinate evaluation.

Relevant evidence: `src/adapters/lp/highs.cpp` status classification (lines 148–163); `include/csl/optimization/lp_backend.hpp`; `tests/fixtures/optimization/analytic_lp_cases.json`; `tests/contract/lp/highs_tests.cpp`; `tests/contract/phase_one/simplex_tests.cpp` (lines 375–390); `tests/unit/objectives/reformulation_test.cpp` (lines 22–48, 95–115).

### No finding — conversion and approximation directions are explicit

The Qhull converter admits bounded H/V cross-conversion under numerical assurance and an `equivalent` relation request. H-to-V performs feasibility and coordinate-boundedness queries through the injected LP registration, reduces explicit equalities, handles affine dimensions zero and one directly, and uses Qhull for higher affine dimensions. V-to-H restores affine equalities. Empty sets, singletons, segments, and lower-dimensional affine sets have explicit paths. Nonempty rays, unbounded H inputs for finite V output, ambiguous rank, unresolved near-zero width, and unsupported output/assurance requests reject instead of being silently relaxed.

Every successful conversion records numerical evidence. Finite residual checks alone do not prove global equality. Independent exact-dyadic coverage checks provide a zero or outward-rounded L-infinity bound for ambient-one H intervals and for supported axis-aligned boxes through dimension 12. General higher-dimensional conversion remains a numerical algorithm claim under recorded assumptions; validated assurance is rejected.

Approximation registration requires the requested relation, and execution checks the returned relation. Equivalent conversion, inner/outer approximation, and heuristic output remain distinct. There is no automatic downgrade to a weaker relation or an implicit route to an unregistered representation.

Relevant evidence: `docs/contracts/polyhedral-conversion.md`; `tests/contract/geometry/hv_conversion_tests.cpp`; `src/geometry/approximation/policy.cpp`; `tests/contract/geometry/approximation_policy_tests.cpp`.

### No finding — pinned dependency and license records match integration scope

The Qhull integration records v8.0.2, its archive SHA-256, the reentrant API, and installs the complete upstream `COPYING.txt` notice. The HiGHS integration records v1.11.0, its archive SHA-256, and installs its upstream and bundled dependency notices. Public CSL headers do not expose Qhull or HiGHS types. Existing integration reviews limit compatibility and numerical claims to the tested pinned profiles; this review did not independently re-download or re-hash those archives.

Relevant evidence: `cmake/QhullDependencies.cmake`; `cmake/HighsDependencies.cmake`; `docs/contracts/polyhedral-conversion.md`; `docs/contracts/highs-lp-adapter.md`; `docs/research/qhull-8.0.2-integration-review.md`; `docs/research/highs-1.11-integration-review.md`.

## Verification

Configured with the `dev-windows` CMake preset (Visual Studio 2022 x64, Release) and built these focused targets:

```text
hv_conversion_tests
phase_one_tests
hull_reducer_test
lp_backend_tests
objective_reformulation_tests
approximation_policy_tests
```

The corresponding CTest selection passed: 6/6 tests. This verifies the current Windows Release build for the listed areas; it is not cross-platform or race-tool evidence.

## Disposition

The P2 allocation limitation is explicitly documented and does not contradict an advertised hard memory cap, so no blocking fix was opened from this review. The architecture should add a Qhull operation-level reservation or output cap before describing conversions as resource-bounded. All other acceptance areas reviewed above are clear within their declared profiles and evidence limits.
