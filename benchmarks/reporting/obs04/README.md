# OBS-04 analytic instrumentation comparison

This driver compares the same two registered strategies on the exact analytic
T-S01 fixture with timing collection disabled and enabled. Its expected result
is *mathematical equivalence*: the strategy termination, optimality outcome,
objective bounds, profile, and registry-verified complete-family status must
match an independently executed uninstrumented baseline for every trial. The
driver is not expected to establish that instrumentation is free or to select a
performance winner.

Before collecting trials, the driver checks each uninstrumented baseline against
the analytic T-S01 result: completed/optimal termination, zero objective within
the declared tolerance, and membership of two valid boundary histories while a
stagewise-feasible but globally nonoptimal history is rejected. Every trial must
also pass those analytic checks. Baseline comparisons use the declared absolute
and relative tolerances for objective bounds.

The output contains one excluded warmup and seven measured repetitions for
each strategy/mode pair. The first mode alternates by repetition and strategy.
`strategy_run_ns` covers only the exclusive workspace's public `StrategyPort::run`;
collector/configuration and workspace setup are reported separately, and the
post-run observation snapshot is outside that interval. Strategy A includes its
five documented phase scopes. Strategy B includes its run scope. Each enabled
event stores inclusive and exclusive wall-clock ticks for every span and the
clock period used to interpret them. There is one solver thread and one outer
worker. Native backend thread count, CPU time, heap use, and a source-mapped
limiter are unavailable. Treat any timing difference as descriptive and
inconclusive; this tiny analytic case is not representative of application
workloads.

The driver emits a commented header and one JSON event per attempt. Failed attempts must
remain visible and make the process exit nonzero. Keep the raw output, exact
source commit, compiler/build provenance, machine/OS capture, and separate
limiter-profile result next to any retained measurement. Do not combine the
existing synthetic OBS-02 collector loop with these solver timings.

Build a clean Release source checkout and use a separate build directory:

```sh
cmake -S benchmarks/reporting/obs04 -B build/obs04 \
  -DCSL_SOURCE_ROOT="$PWD" -DCMAKE_BUILD_TYPE=Release
cmake --build build/obs04 --parallel
./build/obs04/csl_obs04_instrumentation_comparison
```

The output does not include process startup, parsing, artifact serialization,
rendering, or the separate verification/selection path. No correctness or
performance conclusion should be based on a timing row whose status is not
`passed` and whose complete-family oracle is not true.

## Captured analytic sample

`results/linux-gcc16-20261024.jsonl` records the sample run from the source
commit identified in its adjacent `.environment.txt` file. The file contains
environment details, source and binary hashes, and profiler availability.
Summary statistics are recorded here only after rerunning the driver from the
committed source; the result remains descriptive and inconclusive. `perf` is
unavailable, so no limiter profile exists, and this tiny analytic fixture does
not represent application workloads. It supports no general instrumentation
overhead or strategy winner claim.
