# Eigen 3.4.0 integration review

Date: 2026-10-18. Repository base: `b54737879eae9e49e6c5b033e9b36b4436ed5f07`.
Scope: the pinned Eigen 3.4.0 header integration and the operations consumed by
CSL's objective, Phase I, and optional Qhull conversion components. This is a
bounded source/build/test review for [architecture issue #7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), not approval of every Eigen use, a complete package audit, or closure of that issue.

## Verified findings

- **Pin and acquisition.** [`ObjectivesDependencies.cmake`](../../cmake/ObjectivesDependencies.cmake)
  declares the official Eigen 3.4.0 GitLab source archive and pins SHA-256
  `8586084f71f9bde545ee7fa6d00288b264a2b7ac3607b974e54d13e7162c1c72`.
  CMake consumes its source directory as a private SYSTEM include path. The
  module comment says headers only; `SOURCE_SUBDIR csl-no-build` prevents
  Eigen's own build/install subproject from being added by this integration.
  No Eigen binary target is linked or exported. Upstream describes Eigen as
  header-only, so CSL's use is template/header code compiled into its consumers
  ([Eigen 3.4.0 `INSTALL`](https://gitlab.com/libeigen/eigen/-/blob/3.4.0/INSTALL),
  [tag](https://gitlab.com/libeigen/eigen/-/tree/3.4.0)).

- **Operations and headers actually consumed.** The current source includes
  `Eigen/Eigenvalues` in [`objective_reformulation.cpp`](../../src/optimization/objective_reformulation.cpp)
  for `SelfAdjointEigenSolver<MatrixXd>` with `EigenvaluesOnly` to obtain a
  numerical minimum eigenvalue of the symmetrized quadratic coefficient
  matrix. [`simplex.cpp`](../../src/optimization/phase_one/simplex.cpp)
  includes `Eigen/LU` and uses `MatrixXd`, `VectorXd`, and `FullPivLU` in its
  dense Phase I implementation. The optional [`qhull.cpp`](../../src/adapters/polyhedral/qhull.cpp)
  includes `Eigen/Core` and `Eigen/SVD`; it uses dynamic matrices/vectors,
  `Map`, `JacobiSVD`, matrix products, transpose/block/row/column operations,
  dot products, norms, and finite-value checks. The private
  [`affine_coordinates.hpp`](../../src/geometry/conversion/affine_coordinates.hpp)
  also uses `Eigen/Core` and `Eigen/SVD` for a point-cloud affine basis and
  rank decision. No sparse Eigen module or unsupported module use was found in
  the production source scan. A separate CORE-01 probe includes `Eigen/Dense`
  and tests a row-major map and affine product, but it is not a production
  consumer.

- **Boundary, scalar and layout.** The project boundary types are
  [`numeric::DenseInput` and `MatrixView`](../../include/csl/numeric/data.hpp):
  scalar values are `double`, dimensions are `std::size_t`, and dense inputs
  explicitly identify row-major, column-major, or strided layout. Eigen's
  default dense index is `std::ptrdiff_t` in the pinned source, and the default
  dynamic matrix type is column-major ([Eigen 3.4.0 `Macros.h`](https://gitlab.com/libeigen/eigen/-/raw/3.4.0/Eigen/src/Core/util/Macros.h),
  [matrix tutorial](https://libeigen.gitlab.io/eigen/docs-3.4/group__TutorialMatrixClass.html)).
  CSL converts element by element: objective PSD checking copies and scales
  entries into a symmetric `MatrixXd`; Qhull's `read_matrix`/`view` routines
  read and write through `(row,column)` access rather than sharing Eigen's
  storage buffer with the neutral representation. The objective path checks
  the square extent against `Eigen::Index` before constructing the matrix.
  Phase I checks matrix extents against `Eigen::Index` in its resource
  estimator. Qhull admission bounds dimension and row count to Qhull's signed
  `int` range before its native calls. These are local guards, not evidence of
  a universal checked conversion helper for every future Eigen call.

- **Compile definitions and parallelism.** `EIGEN_MPL2_ONLY` is private on
  `csl_objectives`, `csl_phase_one`, and `csl_qhull_conversion` through the
  dependency helper and target definitions. `EIGEN_DONT_PARALLELIZE` is
  applied to Phase I and Qhull conversion, but **not** to `csl_objectives`.
  In Eigen 3.4.0 `Eigen/Core`, `EIGEN_HAS_OPENMP` is defined only when the
  compiler defines `_OPENMP` and `EIGEN_DONT_PARALLELIZE` is absent. Therefore
  the macro suppresses Eigen's OpenMP path for the two targets where it is
  defined; it does not establish a process-wide thread cap, constrain other
  libraries, or establish general thread safety. The objective target's
  behavior depends on its effective compiler flags: its CMake target does not
  define `EIGEN_DONT_PARALLELIZE`. The inspected repository CMake files do not
  request OpenMP, but externally supplied compiler flags were not inspected.
  Upstream source: [`Eigen/Core` 3.4.0](https://gitlab.com/libeigen/eigen/-/raw/3.4.0/Eigen/Core).

- **Tests and exported surface.** The source tree has behavior tests for
  quadratic symmetry/PSD classification and literal objective values in
  [`objectives_tests.cpp`](../../tests/unit/objectives/objectives_tests.cpp),
  and literal reformulation coefficients in
  [`reformulation_test.cpp`](../../tests/unit/objectives/reformulation_test.cpp).
  The Phase I test suite is registered in
  [`Tests.cmake`](../../src/optimization/Tests.cmake); its contract and unit
  cases exercise results and limits of the dense method. Geometry contract
  cases in [`hv_conversion_tests.cpp`](../../tests/contract/geometry/hv_conversion_tests.cpp)
  exercise affine rank, embedded sets, and H/V conversion outcomes. These tests
  check CSL-visible behavior, not Eigen's entire algorithm surface or numerical
  guarantees. The public objectives header and installed client use only CSL
  types; the installed-client script rejects Eigen includes/types in the
  generated public interface. No test suite was executed during this source
  review.

- **Notices and install behavior.** The dependency rule installs five upstream
  files—`COPYING.README`, `COPYING.MPL2`, `COPYING.BSD`, `COPYING.APACHE`, and
  `COPYING.MINPACK`—under `${CMAKE_INSTALL_DATADIR}/CSL/notices/Eigen-3.4.0`.
  The installed-client test checks those exact paths exist
  ([`RunInstalledClient.cmake`](../../cmake/RunInstalledClient.cmake)). The
  pinned upstream `COPYING.README` says Eigen is primarily MPL-2.0, some files
  contain BSD or LGPL third-party code, and defining `EIGEN_MPL2_ONLY` causes a
  compile error when LGPL code is included ([official `COPYING.README`](https://gitlab.com/libeigen/eigen/-/raw/3.4.0/COPYING.README)).
  The MPL text requires covered source distributions and executable-form source
  availability and preservation of license notices (sections 3.1, 3.2 and 3.4;
  [official `COPYING.MPL2`](https://gitlab.com/libeigen/eigen/-/raw/3.4.0/COPYING.MPL2)).
  This review checks the configured install list and test assertions, not the
  contents of a newly generated installed tree or all downstream package
  formats. `EIGEN_MPL2_ONLY` is a compile-time gate, not a legal audit of the
  compiled translation units or a substitute for preserving covered-source
  obligations. No license conclusion for CSL follows; the project license is
  undecided in ADR 0002.

## Claims not established by this review

The source and checked-in test definitions do not establish validated or exact
linear algebra, general numerical conditioning, complete Eigen API coverage,
bounded memory or execution time for every Eigen operation, a process-wide
thread policy, deterministic behavior under caller-enabled OpenMP, universal
index-conversion safety, independent-instance thread safety, or final
redistribution compliance. They do not establish that every configured
compiler/toolchain ran these Eigen tests. Eigen is a dense numerical component;
it does not supply CSL's general polyhedral operation algebra. Issue #7 still
has broader architecture and integration gates.

## Provenance and checks used

- Repository state inspected: commit `b54737879eae9e49e6c5b033e9b36b4436ed5f07`.
- Local sources inspected: `cmake/ObjectivesDependencies.cmake`,
  `src/optimization/Module.cmake`, `src/optimization/objective_reformulation.cpp`,
  `src/optimization/phase_one/simplex.cpp`, `src/adapters/polyhedral/Module.cmake`,
  `src/adapters/polyhedral/qhull.cpp`, `src/geometry/conversion/affine_coordinates.hpp`,
  `src/geometry/conversion/affine_coordinates.cpp`, `include/csl/numeric/data.hpp`,
  `include/csl/optimization/objectives.hpp`, `src/optimization/Tests.cmake`,
  `tests/unit/objectives/objectives_tests.cpp`,
  `tests/unit/objectives/reformulation_test.cpp`,
  `tests/contract/geometry/hv_conversion_tests.cpp`,
  `tests/installed/objectives_client.cpp`, `cmake/RunInstalledClient.cmake`,
  `docs/contracts/terminal-objectives.md`, and
  `docs/architecture/decisions/0002-native-integrations.md`.
- Source scans: `rg -n "Eigen/|Eigen::|EIGEN_MPL2_ONLY|EIGEN_DONT_PARALLELIZE" include src tests CMakeLists.txt cmake docs` and
  `rg -n "OpenMP|OPENMP|openmp|EIGEN_DONT_PARALLELIZE|Eigen" CMakeLists.txt cmake src tests .github`.
- Official Eigen 3.4.0 primary sources consulted: tag and release, `INSTALL`,
  `Eigen/Core`, `Eigen/src/Core/util/Macros.h`, `COPYING.README`, and
  `COPYING.MPL2`; the matrix storage statement is also linked to Eigen 3.4
  documentation. No build, test, benchmark, or archive re-download was run for
  this review. The archive integrity claim above is the repository's configured
  SHA-256 pin; it was not independently recomputed here.
