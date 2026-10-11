# Native ownership and public build boundary checks

TEST-01 expands the CORE-03 minimum tests through the published
[numeric interface](../contracts/numeric-data.md). It leaves the numeric
implementation and source contract unchanged. The original acceptance criteria
are in [issue #19](https://github.com/butahlecoq/controlled-systems-lab/issues/19).

## Independent oracles

The expansion is in [buffer_views_test.cpp](../../tests/unit/numeric/buffer_views_test.cpp).
Expected arithmetic results are literals calculated before the tests run.

| Input | Literal result | Defect caught |
|---|---|---|
| `[[1,2,3],[4,5,6]] * [7,11,13]` | `[68,161]`, from `7+22+39` and `28+55+78` | Layout or stride indexing, destructive handle move, stale assignment |
| `[[1,2,-1,3],[-4,0,2,-1],[5,-3,0,2]] * [2,-3,5,-7]` | `[-30,9,5]`, from `2-6-5-21`, `-8+10+7`, `10+9-14` | Wrong axes, signs or skipped rectangular columns |
| CSR rows `[(0,0),(3,-2)]`, `[]`, `[(1,3)]`, `[(0,-1),(2,4)]`, times the same signed vector | `[14,0,-9,18]` | Lost explicit zero, empty-row offsets, stale retained CSR arrays |
| Strides `(4,2)`, shape `2x2`, logical `[[2,-1],[3,4]]`, times `[5,-2]` | `[12,7]` | Incorrect rejection at the exact legal noncoprime boundary |

The required `[68,161]` fixture runs on contiguous and padded row/column layouts,
interleaved strides `(3,2)` and noncoprime strides `(8,2)`. Each layout goes
through copy construction, copy assignment, move construction and move assignment.
Moved-from sources must remain valid under the documented handle contract.
Replacing a source handle with the distinct `3 * -2 = -6` snapshot must leave
other copies unchanged. Padding and trailing nonfinite values cannot participate
in arithmetic. The signed fixture also runs through row-major, column-major,
general strided and CSR snapshots.

At strides `(4,2)`, shape `2x3` aliases `(0,2)` with `(1,0)`, so creation must
return `unsupported / numeric.dense.stride`. The adjacent valid `2x2` descriptor
addresses index 6; a six-element span is too short and must return
`invalid_input / numeric.dense.storage`. Incorrect layout labels, malformed
authored storage and multiplication shape mismatch have their own diagnostic
checks. Tests check code, field and a nonempty explanation, without fixing prose.

## Controlled lifetime checks

Dense descriptors, CSR arrays and vector spans are borrowed. Tests retain an
independent owning view before replacing the originating handle, then inspect
the old borrow and multiply through the retained owner. They never read a borrow
after its last owning view dies.

Four `std::async(std::launch::async, ...)` workers capture distinct owning handles.
A promise gate prevents them from obtaining descriptors or reading values until
all producer arrays and main-thread view handles have left scope. Before scope
exit, producers overwrite/reallocate their arrays and clear CSR structure arrays.
Workers then compute `[68,161]` from retained dense or CSR storage. Every future
is joined through `get()` or its destructor; an RAII gate releases workers during
exception unwinding before the futures join. No sleeps or elapsed-time limits
control execution. Each output is owning: mutating one result to `[-500,161]`
leaves the other three `[68,161]` results intact.

Zero-control/external numeric ports are exercised across all three layout labels.
Initialized NaN/infinity storage and huge positive strides describe `3x0`, `0x4`
and `0x0` shapes. Snapshots must discard storage and normalize strides to zero.
`3x0` times an empty vector yields `[0,0,0]`; `0x4` still requires four vector
entries. Negative strides and unknown layouts remain unsupported even when empty.
No coefficient accessor is called for an empty dimension.

## Source and installed clients

[public_headers_client.cpp](../../tests/contract/public_headers_client.cpp)
includes all six product headers installed after integration onto main
`56f2e9f7383089eb4d1fa4e131435c1423d50823`, including the public objectives header.
It links only `CSL::numeric`, uses neutral authored values and checks retained ownership,
the signed literal oracle and zero ports. The same source is copied to a separate
consumer tree. That project resolves CSL solely with `find_package(CSL 0.1 CONFIG
REQUIRED)` and the installed prefix. It receives no source-tree, matrix-library,
solver-library or test-library include path.

The installed test audits the actual `prefix/include/csl/*.hpp` files. It rejects
selected Eigen, HiGHS, nlohmann JSON and doctest includes or public type references,
after removing line and block comments. This is a targeted dependency check,
combined with compilation in the isolated consumer. It is not a general C++ parser
or a stable ABI test. Later public headers must also be added to the neutral client.

## Reproduction commands

From the repository root on Windows, set `cmake` and `ctest` to installed tools.
The exercised tools are VS 2022's CMake/CTest 3.31.6-msvc6 and MSVC 19.44.35215.0.

```powershell
$cmake = 'C:/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
$ctest = 'C:/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/ctest.exe'
& $cmake -S . -B build/test01/msvc -G 'Visual Studio 17 2022' -A x64 -DBUILD_TESTING=ON -DCSL_DEPENDENCY_PROBES=OFF
& $cmake --build build/test01/msvc --config Release --parallel 4
& $ctest --test-dir build/test01/msvc -C Release --output-on-failure --no-tests=error
& $cmake --build build/test01/msvc --config Debug --parallel 4
& $ctest --test-dir build/test01/msvc -C Debug --output-on-failure --no-tests=error
```

The MSVC fixture checks `_ITERATOR_DEBUG_LEVEL == 0` for Release and `== 2` for
Debug. The neutral client prints the compiler and iterator settings, including
in the installed build. Doctest assertions remain active in both configurations.

WSL Ubuntu has GCC 13.3.0 but no CMake. Direct sanitizer compilation uses only the
product include directory and the pinned doctest downloaded into this task's own
cache by the preceding Windows configure. Run these commands from the repository
root in WSL:

```bash
mkdir -p build/test01/wsl
g++ -std=c++20 -g -O1 -pthread -Wall -Wextra -Wpedantic -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  -Iinclude -Ibuild/test01/msvc/_deps/doctest-src \
  tests/unit/numeric/buffer_views_test.cpp src/numeric/data.cpp src/contracts.cpp \
  -o build/test01/wsl/numeric_buffer_views_tests
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=halt_on_error=1 \
  build/test01/wsl/numeric_buffer_views_tests
g++ -std=c++20 -g -O1 -pthread -Wall -Wextra -Wpedantic -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer -Iinclude \
  tests/contract/public_headers_client.cpp src/numeric/data.cpp src/contracts.cpp \
  -o build/test01/wsl/public_headers_client
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=halt_on_error=1 \
  build/test01/wsl/public_headers_client
```

Record actual results, tool versions and skips at delivery. These direct commands
do not exercise Linux CMake packaging or the whole Linux suite. Hosted exact-commit
CI can supply that additional gate. Local checks cover numeric ownership and
zero dimensions only: they do not establish scheduler/resource enforcement,
whole T-R01 execution behavior, observation knowledge, set semantics, validated
arithmetic or portable binary compatibility. No performance claim is made.

CORE-03's [data_tests.cpp](../../tests/unit/numeric/data_tests.cpp) and installed
numeric client remain unchanged. They are the originating module's minimum
acceptance tests; this separate expansion cannot establish their temporal test-first
provenance by itself. The original CORE-03 implementation-time report records
tests authored before implementation: an absent-header compile failure followed
by a temporary declared scaffold that ran 8 cases with 8 failures and 61 failed
assertions. The implemented module then passed 8 cases and 278 assertions. The
later coarse descriptor test also had a recorded runtime failure before its
implementation; final CORE-03 results were 10 cases and 316 assertions. These are
attributed historical execution records, not a new TEST-01 red/green run or proof
from commit timestamps. [CORE-03 PR #107](https://github.com/butahlecoq/controlled-systems-lab/pull/107)
retains the public implementation and review context. New expansion tests can
initially pass an existing correct API; no production defect or artificial failing
implementation is implied by that initial green result.

## Verification recorded for this expansion

On 2026-10-11, the independent TEST-01 worktree based on
`71a6c8216e87bec4f9457ed2626ace368b4350cf` produced these results:

| Check | Actual result |
|---|---|
| Windows MSVC Release, full root CTest | 13/13 passed; expanded numeric fixture 8 cases / 314 assertions |
| Windows MSVC Debug, full root CTest | 13/13 passed; iterator level 2 explicitly checked |
| Installed consumer CTest | 6/6 passed in Release and Debug; only prefix include path for the neutral client |
| WSL2 Ubuntu, GCC 13.3.0, ASan + UBSan + leak detection | Expanded numeric fixture 8 cases / 313 assertions and neutral source client passed |
| Installed audit comment control | Backend names in line/block comments accepted |
| Disposable installed audit injections | `#include <Eigen/Core>` and a public `HighsModel*` each rejected before client compilation; injected file removed |

Both new behavioral fixtures were initially green against the existing
implementation. There was no discovered product defect and no production change.
The two deliberate audit failures were isolated validation probes, followed by
a restored green suite. Linux CMake/installed-package testing and hosted CI on
the final integrated commit remain separate gates; neither is claimed by the
direct WSL compilation. The Windows configure emitted doctest's existing
CMake minimum-version deprecation warning; product builds emitted no new warning.

After rebasing onto main `56f2e9f7383089eb4d1fa4e131435c1423d50823`, integration
round 1 used a fresh `build/test01/integration-round1/msvc` cache. All objectives,
model, sets and other existing source/installed tests remained configured. Full
MSVC Release and Debug CTest each passed 15/15; the installed consumers each
passed 7/7. Iterator levels remained 0/2. The six-header neutral client retained
only the installed public include path and numeric/contracts product libraries.
The unchanged eight-case numeric expansion and updated neutral client were rebuilt
under WSL GCC 13.3.0 with ASan/UBSan and leak detection; both passed. Installed
audit comment/include/type controls were repeated, deliberate leaks removed, and
the restored full suites passed. The initial-base results above remain historical
records; these integration results do not imply Linux CMake packaging or hosted CI.
