# ADR 0002: pinned native integrations for the first contract probes

Date: 2026-10-11. Status: CORE-01 implementation decision, pending integration review. Scope: reproducible probe defaults for [native interface revision 1](../../contracts/core-interfaces.md). The project license remains undecided; no project LICENSE file is added or changed.

## Decision and alternatives

Use Eigen 3.4.0 for private dense/sparse kernels, HiGHS 1.11.0 behind **independent LP and convex-QP ports**, nlohmann JSON 3.11.3 for the initial parser integration, doctest 2.4.11 with CTest, and CMake 3.31 (tested 3.31.6-msvc6) for build integration. These are reproducible stable baseline candidates, not claims to be the latest releases. Hash-pinned source archives are declared in the [isolated CMake project](../../../probes/core-01/CMakeLists.txt). No dependency source is vendored into the public repository.

Choosing one library for LP/QP reduces integration surface while retaining separate replaceable ports. A dedicated QP or conic backend remains possible. General conic/SDP/nonconvex optimization is not implied. Matrix alternatives remain deferred because CORE-01 needs a verified neutral boundary, not a universal numerical stack. Qhull v8.0.2 is now selected only for the bounded binary64 H/V conversion profile recorded in the appended revision; it does not resolve the general polyhedral backend requirement tracked by architecture issue #7, and Eigen is not a polyhedral geometry engine. The historical custom phase-I method remains an alternative LP/hull integration, not something HiGHS automatically reproduces.

JSON is a first parser probe, not an implemented scenario schema/loader or irrevocable user-file syntax. It maps to neutral values and errors. YAML from earlier architecture sketches was illustrative. The authored schema/template workflow remains INP-01/02. doctest has a small CMake/header integration sufficient for independent analytic assertions; the product may organize its targets in CORE-02 without exposing test types.

## Versions, licenses and upstream compatibility

| Selected integration | Primary source and license | Toolchain evidence and restrictions |
|---|---|---|
| Eigen 3.4.0 | [Tagged source](https://gitlab.com/libeigen/eigen/-/tree/3.4.0), [license inventory](https://gitlab.com/libeigen/eigen/-/blob/3.4.0/COPYING.README) | Header-only C++; GPL/LGPL portions are excluded with `EIGEN_MPL2_ONLY`. Included Eigen code is MPL-2.0 and compatible permissive portions; retain notices and meet MPL source obligations for covered files on distribution. Changes to Eigen covered files need their own review. |
| HiGHS 1.11.0, LP and QP | [Release](https://github.com/ERGO-Code/HiGHS/releases/tag/v1.11.0), [README/build scope](https://github.com/ERGO-Code/HiGHS/blob/v1.11.0/README.md), [MIT license](https://github.com/ERGO-Code/HiGHS/blob/v1.11.0/LICENSE.txt) | Upstream describes Windows/Linux/macOS builds, C++ with some C, CMake ≥3.15 and convex PSD QP. Build static, no external BLAS/ZLIB/GPU/Python; keep upstream and bundled third-party notices. LP basis availability is optional at the CSL port. |
| nlohmann JSON 3.11.3 | [Release](https://github.com/nlohmann/json/releases/tag/v3.11.3), [MIT license](https://github.com/nlohmann/json/blob/v3.11.3/LICENSE.MIT), [supported compiler notes](https://github.com/nlohmann/json/blob/v3.11.3/README.md#supported-compilers) | Header-only library; upstream lists GCC/Clang/MSVC families. Preserve notices in redistributed copies. Parser values/exceptions stay behind the future loader. |
| doctest 2.4.11 | [Release](https://github.com/doctest/doctest/releases/tag/v2.4.11), [MIT license](https://github.com/doctest/doctest/blob/v2.4.11/LICENSE.txt), [compiler support](https://github.com/doctest/doctest/blob/v2.4.11/doc/markdown/features.md) | C++ test-only dependency with GCC/Clang/MSVC support. Retain notices if distributed; it never appears in product headers. |
| CMake / CTest 3.31.6 baseline | [3.31 release notes](https://cmake.org/cmake/help/v3.31/release/3.31.html), [upstream notices](https://github.com/Kitware/CMake/blob/v3.31.6/Copyright.txt) | BSD-3-Clause core plus bundled-component notices. Local executable is Microsoft's 3.31.6-msvc6 distribution; project requires ≥3.31, no claim that vendor binary equals upstream tag. CMake is build tooling rather than linked product code. |

Pinned archives and license files were downloaded from the listed upstream repositories and inspected. Browser retrieval of Eigen's main page timed out, but tagged source/archive retrieval succeeded. License summaries describe integration constraints, not a decision on the license for newly authored CSL code. Packaging must collect all applicable notices from the actual selected build, including HiGHS bundled code and any distributed tooling. Probes download dependencies into ignored build/cache directories.

| Archive | SHA-256 |
|---|---|
| Eigen 3.4.0 tar.gz | `8586084f71f9bde545ee7fa6d00288b264a2b7ac3607b974e54d13e7162c1c72` |
| HiGHS v1.11.0 tar.gz | `2b44b074cf41439325ce4d0bbdac2d51379f56faf17ba15320a410d3c1f07275` |
| JSON v3.11.3 tar.gz | `0d8ef5af7f9794e3263480193c491549b2ba6cc74bb018906202ada498a79406` |
| doctest v2.4.11 tar.gz | `632ed2c05a7f53fa961381497bf8069093f0d6628c5f26286161fbd32a560186` |

## Integration probes and convex limits

The [probe executable](../../../probes/core-01/dependency_probes.cpp) checks:

1. Eigen maps a neutral row-major buffer and computes a singular affine transition with hand-derived output (7,5).
2. HiGHS LP returns optimum x=2/value=2, handles zero-objective feasibility, and distinguishes infeasible and unbounded models.
3. HiGHS QP solves a rectangular residual objective after squaring: minimize ||[x−3,4]||₂ on [0,2], giving x=2, squared solver value 17, original norm √17.
4. HiGHS solves the PSD problem (x−1)² on [0,2]×[0,1] with a flat second coordinate. This demonstrates an optimizer from a nonunique family, not recovery of that family.
5. Separate HiGHS instances retain separate programs and results.
6. JSON parses typed initial/strategy fields and rejects malformed input; doctest assertions run through CTest alongside contract tests and the compiled caller example.

For ||Lx−r||₂, squaring preserves minimizers because the norm is nonnegative. Use Q=2LᵀL, q=−2Lᵀr, c=rᵀr in the ½xᵀQx convention, and independently report the original norm. Squaring can worsen conditioning and does not preserve objective gaps in the original units. This is a reformulation decision for a later adapter, not a conic capability or completeness proof. PSD/ill-conditioned/degenerate QP needs proper scaling, validation and failure translation; a successful small probe does not establish general robustness or validated bounds.

## Platforms actually exercised

Windows x64, MSVC compiler 19.44.35215.0 from VS 2022 Community toolset directory 14.44.35207, Windows SDK 10.0.26100.0, CMake 3.31.6-msvc6, Release. The declared future portability target is Linux x64 with GCC ≥12 or Clang ≥16 and CMake ≥3.31; **Linux is not run in CORE-01**. Upstream support plus standard C++20 gives a reasonable integration target, not a tested portability claim. Cross-platform CI, sanitizer/race coverage and installed consumer targets belong to CORE-02 and test expansions.

All selected runtime dependencies build from source with a single compatible toolchain. No cross-version C++ ABI compatibility is assumed. Native solver threads are set to one in probes; no performance measurement is reported. The original independent-instance probe was sequential and its asynchronous caller used fixtures. A later bounded review of the product LP/QP adapters is recorded below.

## 2026-10-12 update: narrow Qhull conversion selection

This revision narrows the earlier statement that a concrete geometry backend remained unselected. Merged [PR #145](https://github.com/butahlecoq/controlled-systems-lab/pull/145) selects Qhull v8.0.2 as the private implementation for the bounded H/V conversion profile below. It does not select Qhull as the system's general polyhedral engine. The project license remains undecided.

| Integration | Source, notice, and integrity | Selected profile and limits |
|---|---|---|
| Qhull reentrant C library, v8.0.2 | [Official v8.0.2 source tag](https://github.com/qhull/qhull/tree/v8.0.2); [upstream `COPYING.txt` notice](https://github.com/qhull/qhull/blob/v8.0.2/COPYING.txt), installed intact at `share/CSL/notices/Qhull-8.0.2`; source archive SHA-256 `8774e9a12c70b0180b95d6b0b563c5aa4bea8d5960c15e18ae3b6d2521d64f8b`, pinned in [`QhullDependencies.cmake`](../../../cmake/QhullDependencies.cmake). | Static private `libqhull_r`, using the reentrant C API and fixed `Qx` option, behind `ConversionPort`. Supports cross-representation conversion of bounded H/V polyhedra with finite binary64 coordinates. It is not an exact-arithmetic or validated geometry backend. |

The adapter uses the caller-selected `LPPort` for feasibility, boundedness, and relative-interior queries. It reduces explicit affine equalities before H-to-V enumeration and restores affine equalities for V-to-H output. Rank-zero and rank-one cases use direct paths. The precise supported cases, evidence, observations, and source lineage are in the [polyhedral-conversion contract](../../contracts/polyhedral-conversion.md) and [current framework composition map](../framework-composition.md).

Capability admission returns `Unsupported` for nonempty V ray sets, unbounded H sets requested in finite V form, ambiguous rank, validated assurance, and unsupported output representations. Same-representation requests retain the input. The adapter has no fixed ambient-dimension or input-row cap; `QhullOptions` permits caller-selected limits for both. Qhull's signed-integer interface, host container and memory limits remain. It has no in-call cancellation guarantee, and this integration does not provide an output-size cap. These implementation limits do not settle the global hard-cap versus per-request-budget policy, which remains open for review.

This selection does not implement the general polyhedral operation algebra. Affine images, Minkowski sums, intersections, set projections, and nominal predecessor operations still require separate `GeometryPort` adapters and operation-specific guarantee rules; they remain open in #40/#41/#51. Conversion residual checks are numerical evidence only and do not prove global set equality. A successful `equivalent` result is the adapter's numerical algorithm claim under its recorded assumptions, not exact arithmetic or a validated certificate.

## 2026-10-18 update: bounded Qhull integration review

The source-backed [Qhull 8.0.2 integration review](../../research/qhull-8.0.2-integration-review.md)
records the supported bounded H/V profile, numeric-only evidence, signed-integer
and caller-capacity limits, boundary-only cancellation, and the evidence gap for
independent-instance concurrency. It also checks the upstream notice against
the configured install path; the installed-package script now asserts the
Qhull notice when that optional integration is enabled. This closes only the
source-scope and notice-presence-test subgate. It does not establish a global
memory/facet cap, interruptible Qhull calls, a verified thread-safety guarantee,
or downstream package completeness; issue #7 remains open.

## 2026-10-17 update: bounded HiGHS LP/QP integration review

The [pinned HiGHS 1.11.0 integration review](../../research/highs-1.11-integration-review.md) ties the selected static build and narrow downstream initialization patch to upstream source, the current adapters, concurrent-workspace and preexecution-stop tests, and the three-file notice inventory. It supports only the adapters' one-thread, separate-workspace Windows profile. Simplex cancellation is cooperative; the QP path has no prompt stop-token callback. No process-wide thread or memory cap, hard deadline, general thread-safety claim, or final distribution-license approval follows from this check.

## 2026-10-18 update: bounded Eigen integration review

The [pinned Eigen 3.4.0 integration review](../../research/eigen-3.4-integration-review.md)
maps the production headers and operations used by objectives, Phase I, and
Qhull conversion; the neutral matrix boundary and local index guards; target
compile definitions; configured notice installation; and the checked-in
behavior-test surface. It supports only those source-level findings. No tests
were run as part of that review, and it does not establish numerical
conditioning guarantees, a process-wide thread policy, universal index safety,
independent-instance thread safety, or downstream packaging compliance.

The [bounded JSON/doctest and installed-package review](../../research/issue7-package-install-integration-review.md)
records the pinned private JSON integration, test-only doctest integration,
installed-client checks, removal of a duplicate JSON notice install, and use of
the configured install library directory when locating the exported targets.
This closes the source integration and default-layout harness review subgate.
Hosted CI remains required to exercise the changes. Custom package layouts,
cross-platform and race coverage, and final notice collection remain pending.
The Eigen, HiGHS, and Qhull reviews are bounded component evidence;
they do not settle the broader scientific numerical profile, geometry operation
algebra, or capacity policy tracked by architecture issue #7, which remains
open.
