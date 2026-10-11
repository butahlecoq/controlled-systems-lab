# CORE-01 isolated contract and dependency probes

This is not the product build or a synthesis executable. It compiles [interface revision 1.1](../../docs/contracts/core-interfaces.md), its guards, dependency probes and two explicit strategy fixtures. Dependency choices and upstream licensing are in [ADR 0002](../../docs/architecture/decisions/0002-native-integrations.md).

From the repository root in PowerShell (build directory is ignored):

```powershell
$cmake = 'C:/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
$ctest = 'C:/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/ctest.exe'
& $cmake -S probes/core-01 -B tmp/core01-build -G 'Visual Studio 17 2022' -A x64
& $cmake --build tmp/core01-build --config Release --parallel 4
& $ctest --test-dir tmp/core01-build -C Release --output-on-failure
& tmp/core01-build/Release/contract_tests.exe
& tmp/core01-build/Release/dependency_probes.exe
& tmp/core01-build/Release/caller_example.exe
```

Check each command's exit code before continuing. `CSL_DEPENDENCY_PROBES=OFF` excludes Eigen/HiGHS/JSON while retaining doctest, contracts and the caller. FetchContent archives have SHA-256 pins and are cached under the build tree; source overrides are available through standard `FETCHCONTENT_SOURCE_DIR_<NAME>` for offline development, but overrides bypass archive verification and are not the default evidence path.

Future Linux invocation (not executed for this ticket):

```sh
cmake -S probes/core-01 -B tmp/core01-linux -DCMAKE_BUILD_TYPE=Release
cmake --build tmp/core01-linux --parallel 4
ctest --test-dir tmp/core01-linux --output-on-failure
```

The first TDD run compiled four permissive guard bodies returning empty diagnostics. With the authored tests in place it failed 9 of 10 cases, 23 of 34 assertions. Replacing the placeholders with the guards produced 10/10 cases and 66/66 assertions. The dependency probe produced 6/6 cases and 51/51 assertions. Neither CMake configuration, dependency compilation nor the deliberately unsupported caller fixture is treated as proof that numerical synthesis exists.

Revision 1.1 review fixes extended outcome evidence and geometry channels. Outcome-guard red: 13 cases/3 failed, 82 assertions/4 failed; green: 13 cases/90 assertions passed. Geometry-guard red: 20 cases/7 failed, 122 assertions/16 failed; initial green: 20 cases/145 assertions passed. With additional positive shape cases and safe diagnostic-index assertions, the final suite passes 20 cases/151 assertions. These guards check identities, claim scopes and operand/metadata shapes; they do not execute geometry or validate certificates.

Observed platform: Windows x64, MSVC 19.44.35215.0, CMake 3.31.6-msvc6, Release. Upstream doctest/HiGHS may emit CMake compatibility deprecation notices; these are upstream configuration warnings, not test failures. No sanitizer/race test or Linux run is claimed.
