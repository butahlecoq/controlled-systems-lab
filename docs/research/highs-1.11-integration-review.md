# HiGHS 1.11.0: bounded LP/QP integration review

Review date: 2026-10-17. Repository base: `6a81dc6d1b06d11110960fb06363f749c5112f8f`.
Scope: the selected HiGHS LP and convex-QP adapters on Windows x64, their
one-thread concurrency and stop behavior, and the notice files carried by the
current install rule. This is an architecture evidence increment for [issue
#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), not approval
of all dependencies or closure of that issue.

## Source and build identity

[`HighsDependencies.cmake`](../../cmake/HighsDependencies.cmake) downloads the
official [v1.11.0 archive](https://github.com/ERGO-Code/HiGHS/tree/v1.11.0)
(tag commit `364c83a51e44ba6c27def9c8fc1a49b1daf5ad5c`) with SHA-256
`2b44b074cf41439325ce4d0bbdac2d51379f56faf17ba15320a410d3c1f07275`.
The build is static, disables default native threads, ZLIB/GPU/Python, does
not select external BLAS, and uses 32-bit `HighsInt`. The fetched source is
**not compiled pristine**:
[`ApplyPinnedHighsPatch.cmake`](../../cmake/ApplyPinnedHighsPatch.cmake)
initializes six `HVectorBase` fields. It checks the upstream header hash
`b45e2dc39671f42f772d742d5d287668d59a22c53f94b409402c1d4816a33aa3`
and the Windows postimage
`f0f4f4f4a4b33088c3b30e63bbe5796c7c2fd498600a7e2acc8002bc4e7eace3`.
The latter matched the configured fetched tree. The Unix postimage is separately
pinned in the CMake file; this review did not run a Unix build.

## Concurrency and stop evidence

| Upstream 1.11.0 source | Current CSL behavior and observed check | Limit |
|---|---|---|
| [`HighsParallel.h:25-37`](https://github.com/ERGO-Code/HiGHS/blob/v1.11.0/highs/parallel/HighsParallel.h#L25-L37) maps the default to one worker with `HIGHS_NO_DEFAULT_THREADS`; [`HighsTaskExecutor.cpp:1-22`](https://github.com/ERGO-Code/HiGHS/blob/v1.11.0/highs/parallel/HighsTaskExecutor.cpp#L1-L22) holds scheduler handles in thread-local state. [`Highs.cpp:995-1005`](https://github.com/ERGO-Code/HiGHS/blob/v1.11.0/highs/lp_data/Highs.cpp#L995-L1005) rejects an already-initialized scheduler whose worker count disagrees with `threads`. | [`highs_session.hpp`](../../src/adapters/highs_session.hpp) sets `parallel=off`, `threads=1` per solver. LP and QP each have a two-caller-thread/two-workspace test, with simultaneous barrier release and independent result/attempt checks ([LP](../../tests/contract/lp/highs_tests.cpp), [QP](../../tests/contract/convex/highs_tests.cpp)). | This exercises the selected one-thread profile, not arbitrary scheduler counts, another native client's pre-existing scheduler, process-wide thread accounting, or concurrent calls to one workspace. The adapters do not call `resetGlobalScheduler`. |
| [`HEkk.cpp:3419-3436`](https://github.com/ERGO-Code/HiGHS/blob/v1.11.0/highs/simplex/HEkk.cpp#L3419-L3436) checks time and invokes the active simplex interrupt callback at a bailout point; [`HighsCallback.cpp:77-84`](https://github.com/ERGO-Code/HiGHS/blob/v1.11.0/highs/lp_data/HighsCallback.cpp#L77-L84) observes `user_interrupt`. | The scoped callback in [`highs_session.hpp`](../../src/adapters/highs_session.hpp) polls stop/deadline and sets `user_interrupt`; both adapter suites test pre-requested cancellation, expired deadline, and absence of a stale prior candidate. | The tests do not establish an upper bound on latency for a stop requested during a native solve. Translation and factorization are not preempted. |
| [`quass.cpp:344`](https://github.com/ERGO-Code/HiGHS/blob/v1.11.0/highs/qpsolver/quass.cpp#L340-L351) checks its time limit inside the QP loop; the adapter registers only the simplex interrupt callback. | The [convex contract](../contracts/convex-programs.md) says QP cancellation can be observed before/between phases and on return, while native time/iteration status is classified as a resource limit. | No prompt asynchronous QP cancellation or hard deadline is established. |

The result is a **bounded integration finding**: the current adapters' selected
one-thread concurrent-workspace and preexecution-stop behavior has executable
contract evidence, consistent with the pinned source. It does not establish
general HiGHS thread safety, a process-wide resource cap, race freedom, or
deterministic prompt interruption.

## Notice inventory

The official v1.11.0 tree's recursively enumerated paths matching
`license|copying|notice|copyright` contain three license files and two
copyright-header maintenance scripts. The three license files are installed by
[`HighsDependencies.cmake`](../../cmake/HighsDependencies.cmake):

| Source at v1.11.0 | SHA-256 of fetched file | Installed relative to `share/CSL/notices/HiGHS-1.11.0` |
|---|---|---|
| [`LICENSE.txt`](https://github.com/ERGO-Code/HiGHS/blob/v1.11.0/LICENSE.txt), HiGHS MIT | `10b39dba7b7731175f0705398b6db4320b64add1bd2ed9f9ec5b512a9ef1bd95` | `LICENSE.txt` |
| [`extern/filereaderlp/LICENSE`](https://github.com/ERGO-Code/HiGHS/blob/v1.11.0/extern/filereaderlp/LICENSE), MIT | `4374bb8064e5302f5ac6b82fd3e153a36670f04d0a6ee1bc55b3dc3faee923cc` | `extern/filereaderlp/LICENSE` |
| [`extern/pdqsort/license.txt`](https://github.com/ERGO-Code/HiGHS/blob/v1.11.0/extern/pdqsort/license.txt), zlib-style notice | `323fc18e35fcf058d69d684022ef844f206cb8fefb2bac1298fa1767e0b9ae38` | `extern/pdqsort/license.txt` |

This is a file inventory and install-rule check, not legal approval of a final
distribution. The project license remains undecided. An installed artifact
notice audit and any other distributed-tooling obligations remain for packaging
review.

## Reproduction and disposition

On Windows x64 with MSVC 19.44.35215.0 and CMake 3.31.6-msvc6, from this base:

```text
cmake -S . -B build/issue7-highs-review -G "Visual Studio 17 2022" -A x64 -DBUILD_TESTING=ON -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=OFF -DCSL_DEPENDENCY_PROBES=OFF
cmake --build build/issue7-highs-review --config Release --target highs_lp_tests highs_convex_tests --parallel 4
ctest --test-dir build/issue7-highs-review -C Release --output-on-failure -R "^(highs_lp_tests|highs_convex_tests|pinned_highs_patch_contract)$"
```

To reproduce the narrow repeat check, run these filtered cases 20 times each;
an exit code other than zero on any run is a failure:

```text
build/issue7-highs-review/Release/highs_lp_tests.exe --test-case="prepared ownership survives producers and independent workspaces solve concurrently"
build/issue7-highs-review/Release/highs_convex_tests.exe --test-case="independent concurrent native workspaces retain history after owners disappear"
```

The archive hash matched the downloaded `archive.tar`, and the patched-header
postimage is enforced at configure time. The tests above cover the adapter's
public behavior and the patch contract. All three CTest entries passed. The
named LP and QP concurrent-workspace cases each passed 20 separate filtered
runs (59 and 49 assertions per run, respectively). This is a short repeat
check, not a stress, sanitizer, or real-time stop test.
ADR 0002 may now cite this as a scoped HiGHS review. Its overall integration
status remains pending, and issue #7 still needs its other architecture gates.
