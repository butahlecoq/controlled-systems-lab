# ADR 0002: pinned native integrations for the first contract probes

Date: 2026-10-11. Status: CORE-01 implementation decision, pending integration review. Scope: reproducible probe defaults for [native interface revision 1](../../contracts/core-interfaces.md). The project license remains undecided; no project LICENSE file is added or changed.

## Decision and alternatives

Use Eigen 3.4.0 for private dense/sparse kernels, HiGHS 1.11.0 behind **independent LP and convex-QP ports**, nlohmann JSON 3.11.3 for the initial parser integration, doctest 2.4.11 with CTest, and CMake 3.31 (tested 3.31.6-msvc6) for build integration. These are reproducible stable baseline candidates, not claims to be the latest releases. Hash-pinned source archives are declared in the [isolated CMake project](../../../probes/core-01/CMakeLists.txt). No dependency source is vendored into the public repository.

Choosing one library for LP/QP reduces integration surface while retaining separate replaceable ports. A dedicated QP or conic backend remains possible. General conic/SDP/nonconvex optimization is not implied. Matrix alternatives and exact geometry libraries are deferred because CORE-01 needs a verified neutral boundary, not a universal numerical stack. A concrete geometry backend is still required under architecture issue #7; Eigen is not a polyhedral geometry engine. The historical custom phase-I method remains an alternative LP/hull integration, not something HiGHS automatically reproduces.

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

All selected runtime dependencies build from source with a single compatible toolchain. No cross-version C++ ABI compatibility is assumed. Native solver threads are set to one in probes; no performance measurement is reported. HiGHS global thread-pool behavior still needs a specific concurrency adapter audit before parallel native solves; the independent-instance probe is sequential and the asynchronous caller uses fixtures.
