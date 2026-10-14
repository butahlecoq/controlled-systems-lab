# PERF-03 T-S01 single-process correlation`n`nOpen the [standalone HTML result](index.html) for a concise visual report.

This companion evidence run resolves the sampled CPU path inside the timed T-S01 request operation. It supports a sampled hotspot attribution for this exact repeated diagnostic workload; it does not establish a latency improvement, compare algorithms, or generalize beyond T-S01. Issue #220 remains open for independent review.

## Finding

In the process-scoped profile, 96.74% of the target process's 130,813 stack hits were inside the individually timed `one_run()` operation. The dominant resolved path was `StrategyPort::run` → `DirectJointWorkspace::solve` → convex `Workspace::solve_native` → HiGHS QP optimization. The target profile excludes repeated process startup and teardown: all 30,000 measured calls ran inside one process, PID 23164. Function names resolve through the matching PDB and are mapped to source files in [profile-symbols.csv](profile-symbols.csv).

This establishes where sampled CPU work occurred within the diagnostic `one_run()` loop. It does not quantify the exact source contribution to the original seven-trial unprofiled wall latency. Sampling overhead and latency correlation are inconclusive: one unprofiled execution and one profiled execution ran sequentially under a busy host, and the observed per-call medians were lower in the profiled run despite overlapping ranges. No overhead ratio or speedup is claimed.

## Workload and build identity

- Solver source: `2a5ab835295dfd22f02b19d440bb8158267d985a`.
- Original measurement harness provenance: `4fc8e28587a7fe0e4130f1cb435cf6502ba0e4e2`.
- The only diagnostic harness change was `repetitions=7` → `repetitions=30000`; `one_run()` and all problem construction, provider registration, solve, verification and relation-membership checks are unchanged. See [harness-change.patch](harness-change.patch).
- Both executions used the same PDB-enabled executable. One warmup and 30,000 measured T-S01 calls ran per execution; all 30,000 measured calls passed and yielded the same result marker.
- Build: MSVC 19.44.35215.0, Visual Studio 17.14.19 build tools, CMake 3.31.6, Visual Studio 2022 x64 generator, Release `/O2` MaxSpeed, `/Zi`, `/DEBUG`, `NDEBUG`, `/MD`; HiGHS 1.11.0. Executable and PDB SHA-256 values are in [profile-summary.json](profile-summary.json).

The original published seven-run observations and publication bundle remain unchanged. Per-call measurements for both correlation executions are retained in [paired-timings.csv](paired-timings.csv); it includes the warmup row and every measured repetition, status, and result-marker equality.

| Execution | Wall time | Per-call median | Per-call range | Outcomes |
| --- | ---: | ---: | ---: | --- |
| Unprofiled | 36.136 s | 1.1303 ms | 0.8007–2.3337 ms | 30,000 passed, 0 failed |
| Process-profiled | 33.309 s | 0.9751 ms | 0.8402–2.1842 ms | 30,000 passed, 0 failed |

The two medians are not a performance comparison. This is a single non-alternated pair, with changing system load; the overlap and reversed median order make the observed timing difference inconclusive.

## Profile collection

Visual Studio DiagnosticsHub `VSDiagnostics 17.14.36412.1` loaded `DiagnosticsHub.CpuAgent.dll` with `AgentConfigs/CpuUsageHigh.json` (4,000 Hz). The collector started before the target process and attached only to PID 23164. Process-scoped collection succeeded without `SeSystemProfilePrivilege`; WPR was not used. The target executable's matching colocated PDB was used for symbol resolution.

The 33.79-second ETL is 48,037,888 bytes and contains 468,186 events, including 211,895 `SampleProf` and 137,835 `StackWalk` events. `tracerpt` reported 733 buffers and zero lost events. The PID-filtered xperf stack report contains 130,813 target stack hits. A separate `xperf -a profile -util` summary recorded 34 per-logical-CPU intervals across 12 logical processors: mean 12.45%, range 0.03–69.32%. These host-wide readings include the target and concurrent background work. The full ETL and HTML stack report remain local; their SHA-256 values are retained in the sidecar.

## Reproduction commands

From a clean checkout of the pinned source and the report's tooling, copy `strategy_b_measure.cpp` and `runner/CMakeLists.txt` to a temporary directory, apply `harness-change.patch`, then configure and build the diagnostic target. The recorded build used cached sources for the dependencies pinned by the existing report; those paths can be replaced with equivalent pinned FetchContent sources.

```powershell
cmake -S <temp>\runner -B <temp>\build `
  -G "Visual Studio 17 2022" -A x64 `
  -DCSL_SOURCE_ROOT=<checkout-at-2a5ab835> `
  -DBUILD_TESTING=OFF `
  -DCMAKE_CXX_FLAGS_RELEASE="/O2 /Zi" `
  -DCMAKE_EXE_LINKER_FLAGS_RELEASE="/DEBUG" `
  -DFETCHCONTENT_SOURCE_DIR_CSL_HIGHS=<pinned-highs-1.11.0-source> `
  -DFETCHCONTENT_SOURCE_DIR_CSL_OBJECTIVES_EIGEN=<pinned-eigen-source> `
  -DFETCHCONTENT_SOURCE_DIR_CSL_QHULL=<pinned-qhull-source> `
  -DFETCHCONTENT_SOURCE_DIR_CSL_JSON=<pinned-json-source>
cmake --build <temp>\build --config Release --target csl_syn04_strategy_b_report --parallel 4
```

The unprofiled command was the generated executable from the same build with stdout and stderr redirected to files. The profiled execution used the following sequence (run the target executable after `start`, attach it as soon as its PID is known, then stop the session after it exits):

```powershell
VSDiagnostics.exe start 89 /loadConfig:AgentConfigs\CpuUsageHigh.json /scratchLocation:<scratch> /package:dir
VSDiagnostics.exe update 89 /attach:23164
VSDiagnostics.exe stop 89 /output:profiled.diagsession
VSDiagnostics.exe expandDiagSession profiled.diagsession
xperf.exe -i <expanded>\sc.user_aux.etl -symbols verbose -o target-stack.html -a stack -pid 23164 -butterfly 1
xperf.exe -i <expanded>\sc.user_aux.etl -a profile -util
```

The actual session GUID, executable/PDB/config/trace hashes, paired timing distributions, profiler output counts, and symbol percentages are in the machine-readable [profile-summary.json](profile-summary.json). The CSV supplies the raw per-call timing and outcome records; `verify.py` checks its record count, all-success outcomes and reported distribution statistics.

## Limits

This profile supports a source-resolved sampled CPU hotspot for the exact registered Strategy B T-S01 request path. It is diagnostic evidence only. It does not claim a speedup, performance comparison, application-scale behavior, throughput or scalability, nor does the one-pair run isolate profiler overhead from host-load variance. Issue #220 is intentionally left open for independent review of the attribution and acceptance.

