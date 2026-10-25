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
post-run observation snapshot is outside that interval. Witness selection setup,
selector execution, and independent verification are also reported separately
after the strategy interval. Strategy A includes its
five documented phase scopes. Strategy B includes its run scope. Each enabled
event stores inclusive and exclusive wall-clock ticks for every span and the
clock period used to interpret them. There is one solver thread and one outer
worker. Native backend thread count, CPU time, heap use, and a source-mapped
limiter are unavailable. Treat any timing difference as descriptive and
inconclusive; this tiny analytic case is not representative of application
workloads.

The driver emits a commented header and one JSON event per attempt. It also
writes a digest-named `csl.comparison-record/1` artifact containing all 32
warmup and measured attempts. Each attempt binds the exact event payload to an
immutable `RecordedRunArtifact`; the artifact is decoded and its digest checked
before it is written. The `csl.comparison-spec/3` arms explicitly distinguish
strategy and instrumentation mode while preserving each resolved configuration
identity. The record declares the canonical resolved-problem hash as its shared
input manifest and labels this synthetic pilot `new-comparison`. Its immutable
environment manifest binds the source snapshot identity, compiler/build
configuration, pinned backend versions, binary digest, host OS/kernel/CPU
details, worker and thread policy, workspace reuse and warmup policy, seed
policy, and numerical tolerances. Facts the platform adapter cannot observe
carry an explicit unavailable status and reason. The source snapshot method is
`git-head-tracked-diff-untracked-content-sha256/1`; the dirty flag and digest
cover tracked changes and unignored untracked files at configure time. The
canonical spec digest binds the manifest to both comparison identities. Existing
`/1` and `/2` specs remain readable. Returned
unsupported, cancelled, resource-limited, incomplete, and failed outcomes retain
their run records and event status; thrown exceptions produce a synthetic failed
run record. Resolved arm configurations and an empty collection record are
prepared before per-attempt collector setup, so a plan or collector setup
exception can still be saved as a failed attempt. Errors after the strategy
returns retain the returned terminal and available statistics; their event
records `recording_error`. If the outcome itself cannot be serialized, a
synthetic failed run record is saved and the event separately retains the
returned status, termination, mathematical outcome, family summary, and
serialization error; it states that the run artifact does not contain that
outcome. Failed or analytically invalid attempts make the process exit nonzero.
The default artifact path is the current directory; `--record <path>`
selects a path, and existing files are never overwritten. Keep the separate
limiter-profile result with any retained measurement. Do not combine the
existing synthetic OBS-02 collector loop with these solver timings.

`csl.obs04-instrumentation-comparison-event/3` remains the raw per-attempt
measurement payload. It records requested, returned, and distinct witness counts,
with selection setup, selector execution, and independent verification measured
outside `strategy_run_ns`. The comparison record binds its strategy, instrumentation
mode, repetition, and status to the arm and attempt indices. The per-run record
stores the resolved request, outcome/family data and collected spans. This is
an analytic fixture increment; phase-separated parsing/validation, capability
checks, family construction, first/additional witness queries, serialization,
rendering and end-to-end timings remain outside this driver.

Build a clean Release source checkout and use a separate build directory:

```sh
cmake -S benchmarks/reporting/obs04 -B build/obs04 \
  -DCSL_SOURCE_ROOT="$PWD" -DCMAKE_BUILD_TYPE=Release
cmake --build build/obs04 --config Release --parallel
# Single-config generators:
(cd build/obs04 && ./csl_obs04_instrumentation_comparison)
# Multi-config generators place the executable in the Release subdirectory:
(cd build/obs04/Release && ./csl_obs04_instrumentation_comparison)
```

The output does not include process startup, parsing, artifact serialization,
rendering, or a complete end-to-end solve duration. The strategy timing excludes
the separately reported selection and verification phases. No correctness or
performance conclusion should be based on a timing row whose status is not
`passed` and whose complete-family oracle is not true.

## Captured analytic sample

`results/linux-gcc16-20261024.jsonl` records a sample run from source commit
`e782e2fbe6b7e16339fa27c24ac3175b59aaf7bf`. Its adjacent `.environment.txt`
file records environment details and the binary hash for that historical
sample. New `--record` artifacts carry those facts in the spec. All 32 events passed the
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

## Fresh paired instrumentation capture (2026-10-25)

`results/linux-omarchy-gcc16-20261025.json` and `.jsonl` preserve a fresh
32-attempt Release capture from source commit
`2d78543799c7ad267f22ccf613b89e5ac236259f`. Four arms use the same resolved
T-S01 request: both strategies with collection disabled and enabled. The driver
alternates strategy order and the first instrumentation mode by repetition,
with one warmup and seven measured repetitions per arm. All 32 attempts passed
the analytic-family and independent witness checks; each returned two distinct
witnesses. The record also binds build/runtime metadata and the executable hash.

Measured `strategy_run_ns` medians and ranges were:

| Strategy | Collection | Median (ns) | Range (ns) |
| --- | --- | ---: | ---: |
| reach-back | disabled | 4,951,254 | 4,873,729–5,242,147 |
| reach-back | enabled | 7,895,243 | 7,823,515–9,185,926 |
| direct-joint | disabled | 863,389 | 786,842–943,568 |
| direct-joint | enabled | 1,003,703 | 953,555–1,068,516 |

The median paired enabled-minus-disabled differences were +2,925,131 ns for
reach-back (range +2,696,957 to +3,943,779 ns) and +146,320 ns for direct-joint
(range +97,988 to +205,127 ns). Every measured pair was slower with collection
enabled, but the separate local profiler attempt failed its acknowledgement
protocol after six samples, so the limiter is not established and the result
remains inconclusive. See
[`linux-omarchy-gcc16-20261025.environment.txt`](results/linux-omarchy-gcc16-20261025.environment.txt)
and
[`linux-omarchy-gcc16-20261025.profile-summary.md`](results/linux-omarchy-gcc16-20261025.profile-summary.md)
for the run limits and profile status. These fixture timings do not establish a
general instrumentation overhead, end-to-end latency, scalability, or method
winner.

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
Invoke it separately with `--profile-strategy reach-back|direct-joint` and
`--profile-calls N`; it performs a warmup and the requested number of profiled
calls, then exits without comparison-record capture. The normal comparison run
(optionally `--record <path>`) does not control `perf`. Acknowledgements improve
control-boundary synchronization but do not make the small T-S01 workload
representative or support a unique limiter claim.

To exercise host capability, add the `run-obs04-perf-probe` label to a PR. The
Linux job builds the Release driver, tests the FIFO protocol with a mock perf
controller, then attempts eight acknowledged cycles samples with a 120-second
bound and 32 MiB file cap. It always uploads a machine-readable capability result
and logs; permission or PMU denial is reported as `unavailable`, while protocol
or capture errors are retained as `failed`. The workflow artifact is temporary
(14-day retention). The comparison record adds `measurement_payload` to the
public `ComparisonAttempt` C++ type, changing its layout and ABI; binary
consumers must rebuild against the updated headers and library. This
environment-manifest increment changes the wire schema while retaining legacy
decoding; it adds no C++ API, installed file, package workflow, or new
dependency. It does not prepare or publish a release. No capability result is
claimed until the labelled job has actually run. OBS-04 still needs
phase-separated parsing/validation, capability, family-construction, and
first/additional-query timing; complete resource policy and measurement;
instrumentation overhead analysis; report rendering; and a usable separate
limiter profile before it can close.
