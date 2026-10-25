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

`csl.obs04-instrumentation-comparison-event/6` is the current raw per-attempt
payload; the codec continues to accept event `/2` through `/5`. It records
the `StrategyPort::run` interval, first and additional direction query, their
combined selection interval, independent verification, and attempt end-to-end
time. Family construction is currently `null`: the driver does not yet isolate
that phase inside either strategy, so the strategy interval is not relabeled as
family-construction time. Event `/4` was an exploratory increment that wrote
the full strategy interval into that field; the retained `/4` artifacts are
historical and must not be interpreted as a separate family-construction
measurement.
Event `/6` also distinguishes solver `status` from post-run `phase_status` and
retains partial selections and verifier reports when a later phase fails.
The selector runs two ordered single-direction requests and composes their
verified witnesses into the saved batch. The comparison record binds the event
to its arm and attempt indices; the per-run record stores the resolved request,
outcome/family data, selection and verification evidence, and collected spans.
Attempt end-to-end time starts before per-attempt workspace setup and ends after
witness verification; it excludes process startup, request resolution,
capability reporting, artifact serialization, report generation, and export.
This analytic fixture does not separately time those excluded phases.
The event `status` tracks the strategy terminal outcome and must agree with the
saved run; `phase_status` reports the subsequent selection, verification, and
analytic/span checks. A failed post-run phase can therefore retain a completed
solver outcome while recording `phase_status: failed` and `phase_error`. Any
available partial selection and verifier reports remain attached to the run.

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
enabled. Both bounded profiler attempts were rejected: the local attempt failed
its acknowledgement protocol after six samples, and the GitHub Actions Ubuntu
24.04 runner reported `perf_event_paranoid=4` and timed out waiting for the
perf acknowledgement. The limiter is not established and the result remains
inconclusive. See
[`linux-omarchy-gcc16-20261025.environment.txt`](results/linux-omarchy-gcc16-20261025.environment.txt)
and
[`linux-omarchy-gcc16-20261025.profile-summary.md`](results/linux-omarchy-gcc16-20261025.profile-summary.md)
and the retained hosted attempt in
[`linux-github-actions-ubuntu24-20261025.profile-attempt/`](results/linux-github-actions-ubuntu24-20261025.profile-attempt/)
for the run limits and profile status. These fixture timings do not establish a
general instrumentation overhead, end-to-end latency, scalability, or method
winner.

## Exploratory event `/4` phase timing capture (2026-10-25)

`results/linux-omarchy-gcc16-20261025-phase-timings-clean.json` and `.jsonl`
add first/additional query and attempt end-to-end measurements. All 32 attempts
passed the analytic-family and independent witness checks. This Release build
used clean source commit `dcb10390238ce9631a6c8b11d0e7d29a361ebb74`; the
immutable record carries its source tree digest and binary hash. Each cell
below is the median of seven measured attempts; query values are in ns.

| Strategy | Collection | Strategy run | Family construction | First query | Additional query | Attempt end-to-end |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| reach-back | disabled | 4,962,456 | unavailable | 238,021 | 226,147 | 5,570,846 |
| reach-back | enabled | 7,999,658 | unavailable | 440,980 | 435,183 | 9,596,307 |
| direct-joint | disabled | 861,357 | unavailable | 245,773 | 237,252 | 1,457,804 |
| direct-joint | enabled | 1,039,383 | unavailable | 324,414 | 302,764 | 1,988,879 |

The event `/4` records above predate the correction that stopped placing the
whole strategy interval in `family_construction_ns`. They are retained as
historical records only. The clean-source `/5` capture below predates `/6`,
which adds distinct post-run phase status and partial evidence retention.

## Clean-source event `/5` capture (2026-10-25)

`results/linux-omarchy-gcc16-20261025-phase-timings-v5.json` and `.jsonl`
record the corrected event contract from clean commit
`c5090ce6834abef61ec6eb285ca676676970fb05`. All 32 attempts passed the
analytic-family and independent witness checks, and every attempt returned two
distinct witnesses. The immutable record binds the source tree and binary
hashes. The table reports medians of seven measured attempts per arm (ns).

| Strategy | Collection | Strategy run | Family construction | First query | Additional query | Attempt end-to-end |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| reach-back | disabled | 4,976,786 | unavailable | 262,046 | 240,954 | 5,606,829 |
| reach-back | enabled | 8,144,181 | unavailable | 460,677 | 438,606 | 9,792,726 |
| direct-joint | disabled | 827,416 | unavailable | 240,395 | 222,935 | 1,400,328 |
| direct-joint | enabled | 984,211 | unavailable | 327,139 | 306,326 | 1,927,633 |

Family construction is explicitly unavailable because the driver still does
not isolate that interval inside the strategies. This one T-S01 capture only
demonstrates the timing fields and checks; it establishes no limiter, general
instrumentation overhead, workload latency, scalability, or strategy winner.

## Clean-source event `/6` capture (2026-10-25)

`results/linux-omarchy-gcc16-20261025-phase-timings-v6-clean.json` and `.jsonl`
record the current event schema from clean commit
`e9dc98f491d5bc465812d200755299737e7013ef`. All 32 attempts passed the
analytic-family, witness, and phase checks, and each returned two distinct
witnesses. The immutable record binds source and binary hashes. Values below
are medians of seven measured attempts per arm (ns).

| Strategy | Collection | Strategy run | Family construction | First query | Additional query | Attempt end-to-end |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| reach-back | disabled | 5,021,007 | unavailable | 242,212 | 226,637 | 5,644,696 |
| reach-back | enabled | 8,192,810 | unavailable | 466,545 | 441,750 | 9,780,946 |
| direct-joint | disabled | 818,547 | unavailable | 237,044 | 224,891 | 1,393,347 |
| direct-joint | enabled | 1,039,527 | unavailable | 331,469 | 305,000 | 1,982,743 |

This single tiny-fixture capture verifies event and artifact behavior only. It
does not locate a limiter or establish general overhead, application latency,
scalability, or a strategy winner. Family construction remains unmeasured.

`results/strategy-run-perf-20261024/` retains the 2026-10-24 exploratory
profiles, which were captured before control acknowledgements were added. They
send enable/disable around `StrategyPort::run` but do not wait for perf's
acknowledgement, so transitions may straddle call boundaries. The reach-back
capture passed 500 calls and retained 1,131 samples; direct-joint passed 2,000
calls and retained 486 samples. Both report zero lost samples. These counts are
not a performance comparison and do not establish a unique limiter. Their
original metadata and raw files remain unchanged and explicitly approximate.

The current profile driver requires both `CSL_PERF_CONTROL_FIFO` and
`CSL_PERF_ACK_FIFO`. It waits for either `ack\n` or the observed `ack\n\0`
frame after each enable/disable command,
with a five-second bound, and fails a capture if perf exits, rejects the command,
or does not acknowledge. Profile output marks the sample scope as
`acknowledged_perf_control_window` and records the number of acknowledgements.
Workspace creation occurs before the enable command and outcome checking after
the disable acknowledgement, so those phases are outside the window. The window
includes the small FIFO command/acknowledgement work around each `StrategyPort::run`;
it is not an exact instruction-only measurement of the call.
Invoke it separately with `--profile-strategy reach-back|direct-joint` and
`--profile-calls N`; it performs a warmup and the requested number of profiled
calls, then exits without comparison-record capture. The normal comparison run
(optionally `--record <path>`) does not control `perf`. Acknowledgements improve
control-boundary synchronization but do not make the small T-S01 workload
representative of larger problems.

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
claimed until the labelled job has actually run. The phase timing increment
records the full `StrategyPort::run` interval, first and additional direction
queries, and attempt end-to-end time. Separately timed family construction
remains unimplemented. OBS-04 still needs phase-separated parsing/validation
and capability timing; complete resource policy and measurement;
instrumentation overhead analysis; report rendering; and a usable separate
limiter profile before it can close.

## Acknowledged perf capture after FIFO fix (2026-10-25)

`results/linux-omarchy-gcc16-20261025-perf-ack-fix/` contains separate user-space
`perf` captures for both strategies from source commit
`0657a5e8c2470a24ce0967d37da76aac1411b935`. The fix accepts both the documented
`ack\n` frame and Linux perf's observed `ack\n\0` frame; the mock exercises
both forms and rejects a missing acknowledgement. Each capture ran 32 profiled
strategy calls with a requested 4,999 Hz sampling frequency and 64 acknowledged
enable/disable transitions. The effective sample frequency is not reported by
this probe.
Reach-back decoded 921 samples (104,012-byte capture); direct-joint decoded 160
(27,892 bytes). `perf report` found zero lost samples for both. The binary hash
is `ee6f65ce671950ffa73e367179bc44d99ff6fc18dbcb53ca1969afae1227b3da`.

These captures establish that bounded acknowledged profiling works on this
Linux host. The leading self samples are
allocator/free calls and C++ string operations: `malloc`/`cfree` account for
14.99% of reach-back samples and 13.25% of direct-joint samples. The reports
also attribute samples to HiGHS option registration and native solve methods.
This makes allocator-heavy backend initialization and solve setup candidate
hotspots for the T-S01 workload, rather than establishing a unique limiter.
Direct-joint has only 160 samples, both reports contain unresolved symbols, and
the sample window includes small control-protocol work; this is exploratory
evidence, not a general performance claim. Do not compare sample totals as
strategy speed. Capability metadata, driver/perf logs, text reports, and raw
`perf.data` are retained separately for each strategy.

## Render a saved comparison record

Run the renderer against a saved `csl.comparison-record/1` file:

```sh
python3 scripts/reports/obs04/render_saved.py \
  --record benchmarks/reporting/obs04/results/linux-omarchy-gcc16-20261025-phase-timings-v6-clean.json \
  --out benchmarks/reporting/obs04/results/linux-omarchy-gcc16-20261025-phase-timings-v6-clean.report.html
```

The renderer reads the saved JSON record. It does not run a solver or alter the
record. The HTML lists every attempt, including warmups and failed phases. Its
median and range summaries include only measured attempts whose solver and
post-run phase both passed. It reports statuses and timings from the record, not
from the adjacent JSONL event log. Before rendering, it checks the spec and
comparison identities, each saved run digest, attempt order, and status links
between the run and measurement payload. The saved HTML report is committed
beside the source record.

Run the renderer contract tests with:

```sh
python3 -m unittest tests/reporting/test_obs04_saved_renderer.py
```
