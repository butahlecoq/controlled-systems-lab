# Native C++20 build and public package

The root build supplies the current library modules, installed public targets and
optional native adapters. Start routine edits with the [development presets and
module map](development.md); see [current composition](../architecture/framework-composition.md)
for synthesis scope. Public interfaces require compatible C++20 toolchains; they
are not a stable binary/plugin ABI. Installation is a local development check;
project licensing remains an owner decision.

## Configure, build, test and install

Requires CMake/CTest >=3.31 and a C++20 compiler. Run from the repository root.
Check each command's exit code before continuing. Keep generated trees under the
ignored `tmp/`, `build/`, `install/` or `cmake-build-*` directories.

Windows x64 / Visual Studio 2022, PowerShell:

```powershell
$cmake = 'C:/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
$ctest = 'C:/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/ctest.exe'
& $cmake -S . -B tmp/native -G 'Visual Studio 17 2022' -A x64 -DCSL_DEPENDENCY_PROBES=ON
& $cmake --build tmp/native --config Release --parallel 4
& $ctest --test-dir tmp/native -C Release --output-on-failure --no-tests=error
& $cmake --install tmp/native --config Release --prefix install
```

Linux x64 / GCC >=12 or Clang >=16 (GCC 13.3 was exercised under WSL; Clang
remains a hosted CI target until its run is observed):

```sh
cmake -S . -B tmp/native -DCMAKE_BUILD_TYPE=Release -DCSL_DEPENDENCY_PROBES=ON
cmake --build tmp/native --parallel 4
ctest --test-dir tmp/native --output-on-failure --no-tests=error
cmake --install tmp/native --prefix install
```

Set `CC`/`CXX` before a fresh configure to choose a compatible compiler pair.
`BUILD_TESTING=OFF` disables tests; it does not select a contracts-only build or
remove production dependencies. The default full configuration builds the real
HiGHS and Qhull adapters and acquires their pinned vendors. JSON is also a
production dependency. `CSL_DEPENDENCY_PROBES` controls the separate historical
[CORE-01 probes](../../probes/core-01/README.md), not production adapter acquisition.
Use the `core` preset to disable both optional native adapters; this remains a
library build with production dependencies, rather than a dependency-free mode.
The [development guide](development.md) describes the installed-package checks.

## Installed consumer

The `installed_public_client` CTest installs the public library/header/config,
copies only the standalone consumer CMake file and backend-neutral client into
`tmp/native/installed-consumer/source`, configures/builds a separate project and
runs its own CTest. Its package dependency is `find_package(CSL 0.1 CONFIG REQUIRED)`;
it links `CSL::contracts`. No repository include path or backend/test header is
provided. Product version 0.1 denotes the package, independently of interface
document revision 1.1. The imported target propagates C++20.

To repeat that consumer manually after installation (the two input files may be
copied anywhere):

```sh
cmake -S tmp/native/installed-consumer/source -B tmp/manual-consumer -DCMAKE_PREFIX_PATH=/absolute/path/to/install -DCMAKE_BUILD_TYPE=Release
cmake --build tmp/manual-consumer --config Release --parallel 4
ctest --test-dir tmp/manual-consumer -C Release --output-on-failure --no-tests=error
```

On Windows add `-G "Visual Studio 17 2022" -A x64`. Installed files contain no
vendored source or third-party libraries; the contracts use only the standard
library. Test/dependency tools remain in the ignored build tree. Any later binary
distribution including native backends must collect actual bundled notices and
meet the [ADR 0002 restrictions](../architecture/decisions/0002-native-integrations.md).

## Historical CORE-02 evidence and limits

The following records the original CORE-02 checks and environment. It is retained
as historical evidence, not the current module inventory, dependency inventory or
a fresh verification of the commands above. Later modules have their own tests
and reports.

T-M01's master oracle is: **Reject wrong dimensions/stage counts; constant and
stagewise providers produce the same model behavior.** The public client checks
the integrated shape guard with valid constant/stagewise values, wrong control
dimensions, malformed matrix/offset storage, and stage counts 0, 1 and 3 for T=2.
It verifies the literal diagnostic code and field. A test-local affine helper
over public row-major buffers then checks each representation independently:
`A=[[1,2],[0,0]], B=[[2],[-1]], a=[1,3], x0=[2,-1], u=[2,-1]` gives
`x1=[5,1]`, `x2=[6,4]` by direct hand calculation. A is singular. These exactly
representable integer results use exact equality; checks remain active in Release.
This fixture checks neutral storage consumption, not an implemented product model
provider. Full T-M01 provider/time/domain validation and model evaluation remain
MODEL-01/02 and downstream module tests. No synthesis, optimal family, validated
containment or completeness result is claimed.

The preserved private dependency probes add literal Eigen transition `[7,5]`,
analytic HiGHS LP/QP cases, parser boundaries and separate backend-instance checks.
The caller example deliberately returns Unsupported and is distinct from numeric
evidence. The existing 20-case CORE-01 contract suite is also run by the root build.

Pinned sources: doctest 2.4.11, Eigen 3.4.0 (`EIGEN_MPL2_ONLY`), HiGHS 1.11.0
(static, no external BLAS/ZLIB/GPU/Python), nlohmann JSON 3.11.3. The SHA-256 URLs
and license constraints are recorded in ADR 0002 and the isolated CMake file.
Default FetchContent downloads verify archive hashes. Standard source overrides
are an offline development escape hatch and bypass archive verification; record
their use separately rather than treating them as verified default downloads.

Observed locally: Windows x64, VS 2022 Community / MSVC 19.44.35215.0, toolset
14.44.35207, SDK 10.0.26100.0, CMake/CTest 3.31.6-msvc6, Release: five root CTests
passed, including the private native probes and installed client. Ubuntu 24.04
under WSL2 / GCC 13.3.0, CMake/CTest 3.31.6, Ninja 1.11.1 also passed four root
CTests in Release and four in Debug with ASan/UBSan (including installed clients).
The Linux native dependencies were not exercised locally. Linux CMake and Ninja
were extracted into the ignored task cache from the pinned CMake wheel and Ubuntu
`ninja-build` 1.11.1-2 package; no global tool install was needed. Hosted CI is
configured for Windows/MSVC and Ubuntu 24.04/GCC 13 and Clang 18 Release, running
source/installed clients and private numeric probes. An additional GCC Debug job
requests ASan/UBSan for contracts and consumers; it excludes native backends.
These are CI intentions until actual workflow results are observed. The workflow
logs detected tool versions; runner images change independently of dependency pins.

Clang, ThreadSanitizer and `perf` were unavailable in the checked local Linux
environment. Hardware counters, profiling, race stress and performance measurement
were not run; their absence is not a passing check. Local ASan/UBSan checks cover
contracts and consumers, excluding native backends. The synthetic threaded caller
does not audit HiGHS's global thread-pool concurrency. MSVC ASan is not enabled
here; UBSan/TSan are not supplied by this local MSVC toolchain. Instrumented
backend/concurrency work is downstream.

CI configuration was checked against primary sources: [checkout v4](https://github.com/actions/checkout/tree/v4),
[setup-python v5](https://github.com/actions/setup-python/tree/v5),
[Ubuntu 24.04 runner inventory](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md),
[CMake 3.31.6 distribution](https://pypi.org/project/cmake/3.31.6/),
[FetchContent](https://cmake.org/cmake/help/v3.31/module/FetchContent.html) and
[package config helpers](https://cmake.org/cmake/help/v3.31/module/CMakePackageConfigHelpers.html).
Actions are pinned to the full upstream commit IDs resolved from their version tags.
