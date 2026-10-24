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
Strategy execution order also alternates by repetition, so each repetition
starts with the opposite strategy from the previous one.
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

`csl.obs04-instrumentation-comparison-event/2` is a capture-only schema for
this experiment, not the authoritative comparison artifact. Its repetition,
strategy, instrumentation mode, and status identify an attempted
`ComparisonAttempt`; phase durations and span timings are the raw measurement
payload, while outcome, tolerances, and family checks provide the corresponding
run evidence. The current driver does not yet bind these events to
`ComparisonSpecId` or immutable `RunRecordRef` values. Preserve this schema only
to read this saved sample; when OBS-04 writes authoritative comparison records,
those records should own the attempts and retain these raw events as payload or
replace them with fields in the run record. Do not treat this event stream as a
second canonical report format.

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

`results/linux-gcc16-20261024.jsonl` records a sample run from source commit
`e782e2fbe6b7e16339fa27c24ac3175b59aaf7bf`. Its adjacent `.environment.txt`
file records environment details and the binary hash. All 32 events passed the
analytic and span checks (four warmups and 28 measured attempts). Measured
`strategy_run_ns` medians and ranges were:

| Strategy | Collection | Median (ns) | Range (ns) |
| --- | --- | ---: | ---: |
| reach-back | disabled | 5,253,857 | 4,750,087–8,113,603 |
| reach-back | enabled | 8,029,374 | 7,712,990–8,705,164 |
| direct-joint | disabled | 776,153 | 745,143–1,037,851 |
| direct-joint | enabled | 960,256 | 903,684–1,096,169 |

This sample is descriptive and inconclusive. A separate user-space `perf`
profile is retained beside the raw timings. It captured 170 samples over
150.872 ms with zero samples lost, but it covers the whole driver process,
including initialization, baselines, workspace/collector setup, strategy calls,
and snapshots. Allocation/cleanup symbols and solver symbols appear in that
profile, but it cannot isolate a unique limiter in the timed region. The profile
summary and raw file are in `results/`. This tiny analytic fixture does not
represent application workloads and supports no general instrumentation
overhead or strategy winner claim.

`results/strategy-run-perf-20261024/` retains the 2026-10-24 exploratory
profiles, which were captured before control acknowledgements were added. They
send enable/disable around `StrategyPort::run` but do not wait for perf's
acknowledgement, so transitions may straddle call boundaries. The reach-back
capture passed 500 calls and retained 1,131 samples; direct-joint passed 2,000
calls and retained 486 samples. Both report zero lost samples. These counts are
not a performance comparison and do not establish a unique limiter. Their
original metadata and raw files remain unchanged and explicitly approximate.

The current profile driver requires both `CSL_PERF_CONTROL_FIFO` and
`CSL_PERF_ACK_FIFO`. It waits for `ack\n` after each enable/disable command,
with a five-second bound, and fails a capture if perf exits, rejects the command,
or does not acknowledge. Profile output marks this scope as
`acknowledged_perf_control_transitions` and records the number of acknowledgements.
The acknowledgement improves control-boundary synchronization but does not make
the small T-S01 workload representative or support a unique limiter claim.

To exercise host capability, add the `run-obs04-perf-probe` label to a PR. The
Linux job builds the Release driver, tests the FIFO protocol with a mock perf
controller, then attempts eight acknowledged cycles samples with a 120-second
bound and 32 MiB file cap. It always uploads a machine-readable capability result
and logs; permission or PMU denial is reported as `unavailable`, while protocol
or capture errors are retained as `failed`. The workflow artifact is temporary
(14-day retention). This change does not alter the installed API or package, so
no release is needed. No capability result is claimed until the labelled job
has actually run. OBS-04 still needs the remaining immutable attempt/resource/
publication records and other acceptance criteria.
