# Issue #7: pinned JSON, doctest, and installed-package integration review

Review date: 2026-10-18. Reviewed source revision: `d8a704c9ae7f07218550411c78a201fe57cdbd78`. This is a source/configuration audit of the repository's pinned JSON and doctest integrations and its installed-client harness. No build, test, or benchmark was run for this review. It does not establish a complete downstream packaging model, portability across platforms, or approval of any license.

## Findings

### Low at reviewed base: JSON notice was installed to two different destinations

At the reviewed base `d8a704c9`, the same fetched `LICENSE.MIT` was installed by [`cmake/JsonDependencies.cmake`](../../cmake/JsonDependencies.cmake) under `${CMAKE_INSTALL_DATADIR}/CSL/notices/nlohmann-json-3.11.3` and again by [`src/input/Module.cmake`](../../src/input/Module.cmake) under `${CMAKE_INSTALL_DATADIR}/csl/licenses` as `nlohmann-json-LICENSE.MIT`. The installed-client script checked for the first location, not the second. This was redundant package content with two naming/case conventions; it did not by itself show a missing notice in the tested prefix.

This PR removes the second install rule and retains the versioned canonical notice location. The installed-client test continues to assert that canonical notice exists. This is the implementation response to the base finding; its package behavior still requires CI execution.

### No blocking integration defect found in the reviewed source

The project pins nlohmann JSON 3.11.3 by an HTTPS archive URL and SHA-256 in both product and CORE-01 probe configurations; the digest is the same in both places. The product's `FetchContent_MakeAvailable(csl_json)` uses `SOURCE_SUBDIR csl-no-build`, then gives the fetched `include` directory only to `csl_input` as a private system include. No JSON target is linked to an exported library. CMake 3.31 documents that `SOURCE_SUBDIR` can name a directory that does not exist, which prevents `FetchContent_MakeAvailable()` from adding the upstream top-level project while still populating its source. The official JSON 3.11.3 CMake file has build/test/install setup, so this choice is materially relevant: the integration consumes the source headers and explicitly installs the license instead of invoking JSON's own CMake install rules. [CMake FetchContent 3.31](https://cmake.org/cmake/help/v3.31/module/FetchContent.html#overriding-where-to-find-cmakelists-txt), [nlohmann JSON 3.11.3 CMakeLists](https://github.com/nlohmann/json/blob/v3.11.3/CMakeLists.txt), [nlohmann JSON 3.11.3 integration docs](https://json.nlohmann.me/integration/index.html).

The product's doctest dependency is declared only when `BUILD_TESTING` is enabled, pinned to v2.4.11 with a SHA-256 archive hash, and marked `EXCLUDE_FROM_ALL`. Its tests link `doctest::doctest`; product library modules do not. CMake 3.31 forwards `EXCLUDE_FROM_ALL` from `FetchContent_Declare()` to the added subdirectory; the corresponding directory property excludes that subdirectory's install rules when installing the parent. Upstream doctest 2.4.11 does define install rules, so the exclusion is significant to keeping those rules out of this parent install. The product install harness scans installed public headers for doctest includes/types; it does not explicitly assert that a doctest header or doctest package-config file is absent from the prefix. [CMake FetchContent 3.31](https://cmake.org/cmake/help/v3.31/module/FetchContent.html#fetchcontent-declare), [CMake `EXCLUDE_FROM_ALL` directory property](https://cmake.org/cmake/help/v3.31/prop_dir/EXCLUDE_FROM_ALL.html), [doctest 2.4.11 CMakeLists](https://github.com/doctest/doctest/blob/v2.4.11/CMakeLists.txt).

The root project requires CMake 3.31, so both the JSON `SOURCE_SUBDIR` behavior and doctest's `EXCLUDE_FROM_ALL` integration are within the declared CMake floor. The minimum version is an enforced configuration requirement; it does not demonstrate successful configuration with every CMake 3.31 patch release or generator.

## Source and test evidence

- [`cmake/JsonDependencies.cmake`](../../cmake/JsonDependencies.cmake) contains the product JSON URL/hash, no-build subdirectory, and versioned notice install. [`probes/core-01/CMakeLists.txt`](../../probes/core-01/CMakeLists.txt) pins JSON and doctest in the isolated dependency probe and links them to its probe executable. This establishes matching declared archive identities, not that the archives were downloaded or hash-verified during this review.
- [`cmake/Dependencies.cmake`](../../cmake/Dependencies.cmake) scopes doctest acquisition to the `BUILD_TESTING` path in root [`CMakeLists.txt`](../../CMakeLists.txt), and uses `DOCTEST_WITH_TESTS=OFF` plus `EXCLUDE_FROM_ALL`. Upstream's v2.4.11 build file conditions its own examples/tests on `MAIN_PROJECT AND DOCTEST_WITH_TESTS`; here it is brought in by the parent project. [doctest 2.4.11 CMakeLists](https://github.com/doctest/doctest/blob/v2.4.11/CMakeLists.txt).
- [`cmake/InstalledTests.cmake`](../../cmake/InstalledTests.cmake) registers `installed_public_client`. [`cmake/RunInstalledClient.cmake`](../../cmake/RunInstalledClient.cmake) installs to a temporary prefix, checks the JSON notice, rejects `nlohmann`/`csl_json` references in `CSLTargets.cmake`, scans installed CSL headers for selected private-dependency names, then configures and builds copied consumer sources that call `find_package(CSL 0.1 CONFIG REQUIRED)`. It also builds copied examples against that prefix. The harness is evidence for those specific export/header/client paths when run; it is not a general package-manager or relocation test.
- [`tests/installed/CMakeLists.txt`](../../tests/installed/CMakeLists.txt) exercises the input module through a separate installed consumer linked to `CSL::input`. [`tests/installed/input_client.cpp`](../../tests/installed/input_client.cpp) checks a literal loaded-problem identity, transition, and original objective value. The test setup also compiles other installed-client executables and conditionally checks optional adapter targets based on build options.
- [`cmake/CSLConfig.cmake.in`](../../cmake/CSLConfig.cmake.in) imports `Threads` and the CSL target export. The input JSON implementation is represented by the `CSL::input` API; the installed consumer does not itself find or link a JSON package.

## Boundaries and follow-up

The observed source supports the narrow statement that the product integration intends to use hash-pinned JSON privately and doctest only for repository tests, with an installed-client harness designed to catch JSON leakage through exported targets and installed public headers. The source alone does not prove the harness passes on a clean host. The approach still downloads dependencies through FetchContent at configure time; these files do not provide an offline acquisition procedure, supply-chain attestation for external mirrors, package-manager recipes, a full relocatable binary distribution, or a multi-platform CI matrix. The current install assertions also do not explicitly check absence of doctest files.

This PR also passes `CMAKE_INSTALL_LIBDIR` into the installed-client harness. The harness resolves `CSLTargets.cmake` under that configured relative location and reports a clear failure if the export is missing. It rejects an absolute `CMAKE_INSTALL_LIBDIR` before running `cmake --install`, because absolute install destinations bypass the temporary prefix and cannot be safely inspected by this harness. The required CI exercises the default install layout; custom relative library-directory layouts are not separately configured by this report.

Useful commands for a later implementation run (not run during this review):

```powershell
cmake -S . -B build/issue7-package-review -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=ON
cmake --build build/issue7-package-review --config Release --parallel 4
ctest --test-dir build/issue7-package-review -C Release --output-on-failure -R "^installed_public_client$"
```

For direct evidence that doctest artifacts are excluded from this configured parent install, extend that test to assert absence of doctest headers and CMake package files in its temporary prefix. That is a focused test improvement, not evidence currently produced by the harness.
