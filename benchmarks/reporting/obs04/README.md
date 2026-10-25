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
after the strategy interval. Strategy A includes six planned spans. Strategy B
includes its run and T-S01 family-construction spans. Each enabled event stores
inclusive and exclusive wall-clock ticks for every span and the
clock period used to interpret them. Event schema `/7` introduced the
separately measured `family_construction_ns`; it covers complete-family
proposal assembly and is null when that phase is not entered or instrumentation
is disabled. The current driver emits `/9`, which adds process CPU time,
adapter-reported backend scheduler width, and per-call process peak RSS.
Linux resets `/proc/self/status` `VmHWM` immediately before the strategy call
and reads it afterward. This is the whole-process high-water mark for that
interval, including the driver and all threads; it does not identify
strategy-only allocations or enforce a memory limit. Other platforms report
the metric unavailable. Scheduler width is not active or busy-thread
utilization. Schemas `/5` and `/6` retain their earlier null-field meaning. The
driver requests one solver thread and one outer worker. Older captures lack
per-attempt RSS observations. Heap use and a unique source-mapped limiter
remain unavailable. Treat timing
differences as descriptive and inconclusive; this tiny analytic case is not
representative of application workloads.

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

The driver reports selected shared preflight phases in a structured
`# shared_preflight=` JSONL comment, keyed by the comparison spec and run IDs.
The JSONL is retained beside the immutable comparison record; keeping these
observed durations out of the comparison spec prevents timing noise from
changing `ComparisonSpecId`. Schema `/4` records the actual bounded parser
inside the scenario loader separately from schema/field translation and input
validation. Canonical problem resolution and source snapshotting are reported
as a nested interval within translation; both remain within the inclusive
semantic-load phase. Phase-entry flags identify which timing hooks were reached
for each emitted successful preflight. It also retains inclusive
`comparison_admission_ns` and records each strategy's capability callback
duration and call count nested inside admission. This callback-only timing
excludes common request guards and other registry work; the two callback
durations are not additive with admission and are not subtracted to estimate a
residual. Callback timers call the original capability functions exactly once.
The timers stop before configuration-template creation, workspace creation,
and the two analytic baseline strategy runs. Complete-family proposal
construction is measured separately inside each strategy on enabled runs.
Five clean Release captures of these `/4` loader, validation, canonical
resolution/snapshot, and capability timings are preserved in
[`results/phase-split-schema4-20261025`](results/phase-split-schema4-20261025/).

The current driver emits shared-preflight schema `/5`. It times the common
application guards and each registry preparation directly. A registry interval
pauses around the capability callback; the callback's own duration and call
count are recorded at that same boundary. Each registry arm reports its
accepted, rejected, or thrown status. The common guard reports passed, rejected,
or thrown status. A common-guard rejection leaves both registry arms
`not_entered`.

`common_guards_ns`, the registry callback-external duration, and the capability
callback duration are nested within `comparison_admission_ns`. The application
timer stops after the shared profile, objective, family, strategy, and
representation checks. Request construction and result assembly remain inside
inclusive admission only. Do not add nested values to admission or subtract a
callback interval to infer other registry work. The observed API resets its
caller-owned fixed-size record on each call. The existing unobserved APIs keep
their signatures and take no clock reads.

Schema `/4` captures retain their original fields and meaning. The `/5` driver
does not reconstruct new phase values for those records. The OBS-04 smoke run
produced a `/5` record with 32 attempts, zero failures, one capability call per
accepted strategy, and nested phase durations below inclusive admission. That
run checks instrumentation wiring only. It supports no performance claim.
Five clean-source Release process captures of `/5` are preserved in
[`results/phase-split-schema5-20261025`](results/phase-split-schema5-20261025/).
Each has 32/32 completed attempts. Their per-process preflight values and
hashes are summarized in that bundle; they verify phase capture and provenance
but make no strategy-performance claim.

If comparison admission is rejected or throws, the driver writes a complete
`csl.comparison-record/1` to `--record` (or a unique default path) before
exiting unsuccessfully. It contains all 32 ordered unsupported/failed arm
attempts, with valid run references, the admission diagnostics and timing, and
`strategy_run_ns: null`. Each event marks `admission_failure` and says that no
workspace ran. This preserves the refusal in the paired comparison record
without presenting it as a solver execution or completed comparison.

## Clean-source preflight capture

`results/linux-omarchy-gcc16-20261025-preflight-{a,b,c,d,e}.json`, their
JSONL logs, saved HTML renderings, and empty stderr logs retain five consecutive
Release runs from clean source commit
`372d5b57bf2a9f719e410842f382e9c9dbf2bab9` (source snapshot
`2627bbf3d0caccc70640ab1bc0c40ea0edfef1fd054ce76dced0e46dbf7f45cd`, binary
SHA-256 `5b1a74c907552003d6ca95d1afa357d2d549c9075bf0b3563522bd3ef0d66b32`).
Each run completed 32 attempts: seven measured attempts per
strategy/instrumentation arm and one warmup per arm. Every attempt passed the
analytic and witness checks. The structured `# shared_preflight=` JSONL comment
binds the measurements to the `ComparisonSpecId` and `ComparisonRunId` without
putting run-specific timings into the comparison spec. All five runs produced
the same spec ID and distinct run IDs.

Across the five samples, fixture construction and problem resolution had a
median of 113,563 ns (range 100,712–279,717 ns); provider registration had a
median of 103,017 ns (range 92,960–261,768 ns); comparison admission had a
median of 94,217 ns (range 91,074–289,356 ns). The wide upper values are
retained rather than discarded. These are process-level samples of the three
selected blocks, not all pre-attempt setup; the timers stop before
configuration-template creation, workspace creation, and the two analytic
baseline strategy runs. They do not establish a performance winner or general
latency claim. These `/1` records use the original in-code fixture and do not
contain scenario-file timings. Admission combines common request guards,
strategy capability checks, and registry preparation; the current interface
does not split these subphases.
Event `/7` is used in the historical per-attempt artifacts below. The current
driver emits event `/9`, and the codec accepts event `/2` through `/9`. It records
the `StrategyPort::run` interval, first and additional direction query, their
combined selection interval, independent verification, and attempt end-to-end
time. Events `/7` and `/8` also record complete-family proposal construction
where the strategy exposes that boundary. Event `/8` adds process CPU time for
the strategy invocation and adapter-reported backend scheduler width. Event
`/9` adds the per-call process peak RSS observation with explicit scope and
availability status. Event `/4` was an exploratory increment that
wrote the full strategy interval into that field; the retained `/4` artifacts
are historical and must not be interpreted as a separate family-construction
measurement.
Events `/6` and `/7` distinguish solver `status` from post-run `phase_status` and
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

## Five current-mainline instrumentation captures (2026-10-25)

`results/instrumentation-overhead-current-main-76d8-20261025/` retains five
fresh Release processes built from clean source commit
`76d8ae64b8ec7d36c975eae64f7581bf345cf387`. Every process used the same binary
(SHA-256
`9c8fdf63b91ab0c48c6e9650051f9b56753e231dd33ba03e906d444ee8af15f2`) and
produced the same `ComparisonSpecId` with a distinct `ComparisonRunId`. Each
contains one warmup and seven measured repetitions per strategy/instrumentation
arm. The driver alternates both strategy order and instrumentation mode within
each process. All 160 attempts passed the analytic-family and witness checks;
each requested, returned, and distinct witness count was two. The five complete
records, JSONL/stdout logs, stderr logs, saved HTML reports, environment
manifest, and computed summary are retained in that directory.

Across 35 matched measured pairs per strategy, the enabled-minus-disabled
`strategy_run_ns` deltas were:

| Strategy | Disabled median (range), ns | Enabled median (range), ns | Paired delta median (range), ns | Enabled slower pairs |
| --- | ---: | ---: | ---: | ---: |
| reach-back | 5,087,777 (4,893,617–6,584,141) | 8,581,691 (8,222,354–10,871,460) | +3,468,770 (+2,186,822–+5,913,938) | 35/35 |
| direct-joint | 867,856 (795,989–1,403,474) | 1,139,541 (1,034,219–2,229,774) | +263,862 (-226,846–+1,391,252) | 34/35 |

The median paired relative changes were +68.7% for reach-back (range
+33.2%–+119.3%) and +32.4% for direct-joint (range -16.2%–+165.9%). The
second strategy's single faster pair and wide range show meaningful run-to-run
variation. These five same-host processes measure this T-S01 analytic fixture;
they do not establish general instrumentation overhead, end-to-end latency,
scalability, or a strategy winner. Whole-process time had a median of
849,555,844 ns (range 820,935,028–853,769,480 ns), including startup,
preparation, baselines, attempts, encoding, and file output.

The embedded environment reports CPU time and native backend thread count as
unavailable. The first bounded profile attempt is retained in `limiter-profile/`
and records `unavailable` because `perf` was not installed. Signed Arch
packages were then extracted into a user-space directory and used to profile
this exact binary for 32 acknowledged calls per strategy. The profiles and
source summary are retained in `limiter-profile-userspace-perf-32-*` and
`limiter-profile-summary.md`. Allocation/free, C++ strings, and HiGHS setup
appear as candidate hotspots; the small sample and fixture do not establish
one unique limiter, so the comparison remains inconclusive.

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
scalability, or a strategy winner. Family construction is unavailable in these
historical `/6` records; newer `/7` and `/8` captures report it where measured.

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
consumers must rebuild against the updated headers and library. Event `/8`
adds per-attempt process CPU time and adapter-reported backend scheduler width;
the width is not active-thread utilization. Saved-record rendering and legacy
`/2`–`/9` decoding remains available. No new dependency, installed file, or
package workflow is added. This PR does not publish a release; release planning
remains under the repository's release tracker.

The five clean-source captures report fixture-specific instrumentation deltas
but make no general performance claim. They record process-wide peak RSS and
CPU/wall time separately, with no memory or wall-time cap. The current driver
also records per-attempt process peak RSS on Linux as an observation only;
five clean-source event `/9` captures and their saved HTML are retained in
[`results/attempt-memory-20261025/`](results/attempt-memory-20261025/).
Memory enforcement remains unavailable. Shared preflight timing separates
file read, standalone parse, loader validation/resolution, provider registration,
and inclusive comparison admission. The retained records use schema `/4`,
which combines common guards and callback-external registry preparation. The
current source emits schema `/5` with those phases measured directly.
Workspace/setup, family construction,
queries, verification, and end-to-end timing are retained per attempt. Ten
record-to-HTML exports completed under individual 30-second bounds with saved
HTML hashes matching; no geometry plot or nonlinear replay applies to this
linear fixture. The bounded profiles show candidate hotspots but no unique
source-mapped limiter. Per-attempt RSS is observation-only, and the correctness
pilot does not use the enforced 300-second/8-GiB profile. The limiter-profile
conclusion remains inconclusive.

The OBS-04 report driver adds two functions in public headers. Existing
`prepare_comparison` and `StrategyRegistry::prepare` signatures and object
layouts remain unchanged. The observed functions add no dependency and do not
change installation or package workflows. No release is needed for this
additive API. Any later release still follows the repository's normal release
gates.

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

## One-process resource observation (2026-10-25)

`results/linux-omarchy-gcc16-20261025-resource-observation-v1/` retains one
fresh Release driver invocation wrapped by the standard-library
`resource.getrusage(RUSAGE_CHILDREN)` observer. The observed child-process peak
RSS was 46,344 KiB; wrapper-to-child wall time was 743,850,874 ns, with
0.692361 s user CPU and 0.065067 s system CPU. This is a single whole-process
observation on the recorded Linux host, not a per-attempt memory value or a
limit-enforcement claim. The binary SHA-256 is
`ee6f65ce671950ffa73e367179bc44d99ff6fc18dbcb53ca1969afae1227b3da`; its
embedded build manifest identifies source revision `be1c4e92` with
`source_dirty: true` and snapshot SHA-256
`abb455cd8e2e24cad66fc0f8f57bf2a29aa34fd5cc2870af18c62eafc17fa948`. This
resource measurement therefore does not claim a clean-source rebuild.

The driver exited successfully, wrote a 1,853,117-byte comparison record with
32/32 completed attempts, and emitted no stderr. The record passed the saved
renderer’s identity checks and produced the retained HTML report. The capture
script, raw stdout/stderr, measurement JSON, record, and report are kept beside
one another. This one observation does not establish a stable resource
envelope or general scalability.

## Five clean-source process observations (2026-10-25)

`results/linux-omarchy-gcc16-20261025-resource-observation-v2-clean/` adds
repeatability evidence from five fresh sequential processes using the same
Release binary (SHA-256
`f66c23baf4c8814db75fbc0ad763f58eb7d2a24f56670d526972c1165c83570b`). Its
embedded build manifest records clean source commit
`9994eef03eeae456a89e041b9cac6b7518ba77b4` and snapshot SHA-256
`0cc273de74066a9a24b0aae827501126c691905a8f5ad2c21a895892da472355`.

Each process completed all 32 attempts, returned status 0, and wrote no stderr.
Peak RSS had a median of 46,628 KiB and a range of 45,688–47,152 KiB. The
external whole-process wall-time observation had a median of 738,357,090 ns
and a range of 736,772,335–745,210,148 ns; it includes startup, fixture and
preparation, all attempts, encoding, and file output. Run-specific resource
measurements, comparison records, and stdout/stderr are retained separately;
the first saved record also has a rendered HTML report. The summarizer validates
all five records with the saved-record renderer before reporting the summary.

These measurements describe one small T-S01 process on this Linux host. They do
not measure per-attempt memory, enforce a memory limit, establish a general
resource envelope, compare strategy performance, or identify a unique limiter.
They add repeatable initial process-resource evidence to #83; full resource
policy/accounting and the missing timing phases remain open.

## Clean-source scenario-input phase capture (2026-10-25)

`results/linux-omarchy-gcc16-20261025-scenario-input-phases/` retains five
sequential Release runs of the OBS-04 driver using the public scenario loader
and `examples/scenarios/two-stage-integrator.json`. Each directory entry has
the immutable comparison record, JSONL event log, and stderr log; the first run
also has its saved HTML rendering and renderer log. The records have the same
`ComparisonSpecId`, five distinct `ComparisonRunId`s, and bind clean source
commit `a6320a015eb8eea915d241717db9f388830b3008` (tree SHA-256
`a14e1cb3c78cd9a98f6d9382d038e6d78c97aaa4a9aa3b5de87677a47a87e578`) and
binary SHA-256
`e203edd10130bd3f56158c46061281677ea4bc5f075870c6b3e476c7deadf86d`.
The build is Release with GCC 16.2.1 on x86-64 Omarchy/Linux, using one
requested driver worker and one requested backend thread. Native backend thread
count is unavailable from this driver.

All five runs completed 32 attempts with passed event status, zero failed
attempts, and empty stderr. The structured `/2` preflight comment reports these
medians and full ranges across the five runs:

| Phase | Median (ns) | Range (ns) |
| --- | ---: | ---: |
| Scenario file read | 53,848 | 41,905–93,937 |
| Standalone JSON parse | 54,267 | 44,908–117,823 |
| Public scenario load, validation, and resolution | 192,484 | 169,366–359,057 |
| Provider registration | 134,935 | 85,207–217,138 |
| Comparison admission | 123,899 | 89,607–213,436 |

The standalone JSON parse is a diagnostic on the file bytes; the public loader
parses them again, so the loader time includes parsing and is not a
validation-only measurement. Admission combines request guards, strategy
capability checks, and registry preparation. These are selected preflight
durations, not an end-to-end solve benchmark. The run-to-run ranges are wide,
no source-mapped limiter is established, and this capture supports no speedup,
winner, or general latency claim. The retained `summary.json` records every
sample, run/spec ID, attempt count, and source identity.

## Per-attempt resource observations (event /8)

The driver now records process CPU nanoseconds across each strategy invocation
and the maximum backend scheduler width reported through the execution context.
The CPU value covers all threads in the driver process during that call; it is
not thread CPU time. Scheduler width is the width configured/reported by a
backend adapter, not the number of threads observed busy at once. Either field
may be null when the platform or adapter cannot provide a value. These fields
supplement wall time and do not establish a unique performance limiter.

## Current clean-source CPU and scheduler capture (2026-10-25)

`results/process-cpu-scheduler-20261025/` records five fresh Release processes
from one clean source commit, including process CPU time and adapter-reported
backend scheduler width per strategy invocation. All 160 attempts passed. The
paired instrumentation differences remain fixture-specific and inconclusive;
the exact ranges, profile evidence, machine metadata, and retained superseded
attempts are described in that directory's README and `summary.json`.
