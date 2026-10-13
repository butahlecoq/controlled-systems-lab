# OBS-02 overhead harness execution

Measured source: `55421fac65abf126a8360f9cea42d83153d490f0` (clean working tree).
Source base: `7f2eb4af1c55c5c7af29d03b30400c84c6aca652`.
This is a synthetic observability-infrastructure harness, not a scientific algorithm
benchmark or a claim about application overhead. Comparative performance conclusions
are **inconclusive**: no separate limiter profile or representative solver workload
was collected. The raw wall measurements are retained so the harness execution is
reviewable; no speedup or production scalability conclusion is asserted.

Host: Windows 11 x64, version 10.0.22631; Intel Core i5-12400F, 6 cores/12 logical
processors. Compiler MSVC 19.44.35215, x64 toolset 14.44.35207; CMake/CTest
3.31.6-msvc6. Release, default CMake MSVC optimization, `NDEBUG`; one calling
thread, no solver or native worker threads. The steady wall clock is measured;
CPU counters and actual clock resolution are unavailable in the collector's default
clock. A post-run OS aggregate CPU sample was 0%; this is not a load history or
limiter profile. No sanitizer/ThreadSanitizer run is claimed.

Commands from the isolated worktree:

```powershell
$cmake = 'C:/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
$ctest = 'C:/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/ctest.exe'
& $cmake -S . -B tmp/native -G 'Visual Studio 17 2022' -A x64 -DCSL_BUILD_OBSERVABILITY_BENCHMARK=ON
& $cmake --build tmp/native --config Release --parallel 4
& $ctest --test-dir tmp/native -C Release --output-on-failure --no-tests=error
./tmp/native/Release/observability_overhead.exe 10000 5 55421fac65abf126a8360f9cea42d83153d490f0 > tmp/obs02-overhead.csv
```

The benchmark runs five repetitions per mode, alternates the first side, creates a
fresh plan/collector per row, and measures a serial checksum loop over 10,000 spans.
`setup_ns` includes plan/configuration admission, clock construction and collector
allocation. `loop_ns` includes root scope start/close and all child scope start/close,
checksum work and failure checks. `publication_ns` includes snapshot aggregation,
OBS-01 shard creation/merge and immutable collection publication. `end_to_end_ns`
includes all three phases; output formatting and correctness validation are outside
it. There is no warmup exclusion or tuned production scenario. Allocation/cache
noise is included. The enabled plan uses summary mode, so text detail is not retained.

All ten raw rows have checksum **50,005,000** and **zero failures**. Enabled rows
have **10,001** completed observations including the root; disabled rows have **0**
observations and explicitly absent detailed metrics. The driver rejects checksum,
completion-count, availability or diagnostic mismatches. Exit status was 0.
Unit tests contain no timing thresholds. Full Release CTest passed **60/60**; the
new timing suite passed **17 cases / 411 assertions**. Both concurrent contract
cases also passed 20 repeated executions. A separate installed consumer linked
`CSL::artifacts` using only the installed package and timing header, and exited 0.

See [raw rows](overhead.csv) and the [timing contract](../../../docs/contracts/timing-collector.md).
The algorithm-results publication policy applies to numerical algorithm reports;
this harness performs no numerical solve and creates no family/result claim.
