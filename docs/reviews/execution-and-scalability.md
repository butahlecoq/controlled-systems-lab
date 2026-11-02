# REVIEW-05: Execution and scalability audit

**Issue:** [#95](https://github.com/butahlecoq/controlled-systems-lab/issues/95)

**Reviewed source:** `2c7107a868a9fb25a0bca1da4fd8d640babe2cff`

**Review date:** 2026-10-27

## Execution ownership and resource contract

The executor stores immutable task descriptions in shared `const Storage`, while each task factory creates its own bound workspace. `Executor::run` rejects overlapping or recursive use of the same executor through an atomic busy guard. Batch slots are preallocated and each worker writes only its assigned slot; the scheduler mutex protects admission, stop state and reservation accounting. User adapter calls, workspace destruction and stop requests run outside that mutex. `dispatch` joins every started worker before it publishes a result.

The focused tests exercise stable input ordering despite different completion order, parallel strategy workspaces with separate LP attempt identities, repeated executor runs, recursive/overlapping rejection, cancellation while a factory is gated, failure plus late return, and reservation-credit admission. The source-level stress tests use explicit gates rather than sleeps to force overlap.

The implemented limits match the public contract:

- Outer worker admission and workspace reservation credits are enforced.
- Native/backend thread counts are declarations only; adapters must honor them. The executor does not police BLAS or global thread pools.
- Memory credits account only declared active workspace reservations. They do not cap the native heap or process RSS; hard memory limits are rejected.
- Cancellation closes admission and requests cooperative stop. It does not interrupt a noninterruptible adapter call or promise a finite return deadline.
- Each task slot retains one of `Skipped`, `Returned` or `TaskFailure` in input order. Cancellation is a skip reason when work does not start; a late noninterruptible return remains its actual returned result with stop and timing observations recorded separately.

These limits are described in [execution contract](../contracts/execution.md), [native ownership notes](../testing/native-ownership.md), and `src/execution/executor.cpp`. I found no contradiction between the implementation, tests and those declared guarantees in the inspected paths. This is not a whole-codebase proof of thread safety; other mutable caches and providers still require their own ownership contract.

## Checks on this checkout

The current source built in Release with CMake 3.31.6, GCC 16.2.1, HiGHS 1.11.0 and Qhull enabled. The standalone installed-package `scenario_cli` was built from that install.

`execution_tests` and `batch_runner_tests` passed on the ordinary Release build (2/2). The same targets passed in a separate GCC ThreadSanitizer build (2/2, `TSAN_OPTIONS=halt_on_error=1`); no data race was reported. The sanitizer build used the core configuration with HiGHS/Qhull disabled, so this does not cover native HiGHS internals or all library paths.

The exact CTest output, scenario CLI outputs and tool/host manifest are retained in the [REVIEW-05 execution evidence bundle](../../reports/algorithm-results/review05-execution-20261027/).

Two scenario runs checked the comparable-output boundary:

- `two-stage-integrator.json` with `ts01_exact_integrator` returned complete optimal families from both strategies, two distinct witnesses each, and numerical trajectory verification passed for both.
- `minimal-lti-linear.json` with `nominal_open_loop` returned candidate families from both strategies, but selected zero witnesses on both sides; Strategy B retained one numerical-feasibility candidate while reach-back retained none. Neither side had trajectory verification to compare.

The general run is an admission/result smoke check, not a timing result. Candidate counts differ and selected outputs are empty, so it is excluded from paired performance claims.

## Fresh paired timing evidence

The [current OBS-04 comparison record](../../reports/algorithm-results/review05-execution-20261027/obs04-current-comparison.json) was built from REVIEW-05 source revision `2f05203b69e69f1eccbf6d33a175229775c06271`. Its source snapshot hash is `b202f9b655e6231ec8621d408d7ea8ccfbebf407a306b9b17d2c0e3625721d7d`; CMake marks the source snapshot dirty because the review document and evidence files were present, but `src`, `include` and benchmark source files had no diff from that commit. The binary SHA-256, pinned HiGHS/Qhull archive hashes and complete comparison record are retained. It ran on the same eight-logical-CPU Ryzen 5 3550H host described in the evidence bundle.

The driver ran one warmup and seven measured attempts for each strategy with collection disabled and enabled. The first instrumentation mode and strategy order alternate; every attempt uses a fresh workspace, the same exact T-S01 request, one backend thread and `1e-8` absolute/relative tolerances. All 32 attempts passed the analytic family oracle and independent checks for two distinct witnesses. Each side returned a complete optimal family. Per-strategy run time excludes process startup, shared input resolution, selector and witness verification; those phases are recorded separately. Median whole-process RSS is an upper bound observed at process scope, not strategy allocation.

| Strategy | Collection | Median run time | Range | Median process peak RSS |
| --- | --- | ---: | ---: | ---: |
| Reach-back | Disabled | 4.947 ms | 4.867–5.712 ms | 13.04 MiB |
| Reach-back | Enabled | 8.384 ms | 8.254–10.844 ms | 13.10 MiB |
| Strategy B | Disabled | 0.850 ms | 0.831–1.236 ms | 13.13 MiB |
| Strategy B | Enabled | 1.125 ms | 1.036–1.304 ms | 13.13 MiB |

The paired enabled-minus-disabled median was +3.400 ms for reach-back (range +2.542 to +5.895 ms) and +0.244 ms for Strategy B (range -0.108 to +0.285 ms). These are instrumentation effects for this tiny fixture. The enabled spans measured reach-back's `strategy-a/forward` at a 7.518 ms median (7.444–9.803 ms) and `strategy-a/terminal-optimization` at 0.583 ms (0.551–0.733 ms). Strategy B's `strategy-b/run` inclusive median was 0.982 ms (0.898–1.117 ms), of which family construction was 0.014 ms (0.013–0.030 ms). The nested `strategy-a/run` span includes child spans; do not add inclusive timings. The forward span dominates the observed reach-back time in this fixture, but no source-level limiter profile is available: `perf` is absent on this host. This phase evidence does not identify a unique internal bottleneck.

The [summary JSON](../../reports/algorithm-results/review05-execution-20261027/summary.json), raw stdout events, run record and [build/runtime manifest](../../reports/algorithm-results/review05-execution-20261027/environment.json) preserve the measurements and provenance. The fixture is still only a two-stage scalar problem whose exact relation has five coordinates, four inequality rows and four equality rows. These numbers are current-build descriptive data, not a multi-axis scaling curve or a general strategy winner claim.

## Current-main replication and exploratory function profile

On 2026-10-30, the same T-S01 pair was rerun from clean `main` revision
`210bbe39377be3131f537d65d4f0857c6b4c3462`. Its immutable comparison record
marks the source clean, binds the source and binary hashes, and records all 32
attempts. One warmup and seven measured attempts ran for each strategy with
instrumentation disabled and enabled. All attempts passed the analytic
complete-family check and returned two distinct verified witnesses.

| Strategy | Collection | Median run time | Range | Median process peak RSS |
| --- | --- | ---: | ---: | ---: |
| Reach-back | Disabled | 5.061 ms | 4.895–6.927 ms | 13.15 MiB |
| Reach-back | Enabled | 8.511 ms | 8.366–8.783 ms | 13.15 MiB |
| Strategy B | Disabled | 0.840 ms | 0.822–0.913 ms | 13.30 MiB |
| Strategy B | Enabled | 1.098 ms | 1.038–1.123 ms | 13.30 MiB |

The eight-logical-CPU Ryzen 5 3550H host had a recorded load average of
2.12/1.37/0.74 before capture. Treat this as one descriptive replication; it
does not establish a stable performance ranking or overhead outside this
fixture. Full provenance and raw data are in the [current execution evidence
bundle](../../reports/algorithm-results/review05-execution-20261030/).

The host has no `perf` executable. To collect source-attributed context anyway,
the OBS-04 driver was extended to allow checked repeated calls without perf
FIFOs and to label that output `whole_process` with `perf_controlled: false`.
Separate gprof Release runs checked 500 reach-back calls and 2,000 Strategy B
calls. Their profiles contain only 48 and 38 samples, respectively, at 10 ms
resolution, and include process startup, workspace setup, verification and
shutdown. HiGHS option/model lifecycle and solver functions dominate the
sampled lists; reach-back also shows numeric matrix snapshots and forward-child
bookkeeping. With this sample count and process-wide scope, the profile does
not identify a unique limiter. It is exploratory evidence, not a per-strategy
timing comparison; see the [raw gprof bundle](../../reports/algorithm-results/review05-execution-20261030/gprof-whole-process/README.md).

## Ownership and native-adapter race audit

The static ownership inventory and focused TSan evidence are in the
[ownership audit bundle](../../reports/algorithm-results/review05-ownership-tsan-20261031/README.md), captured from clean committed source
`fd7641e6f106202eae4b5ebdf9ecc874ade0f63e` on 2026-10-31. The inventory covers
lazy support/materialization caches, immutable lazy payloads, executor and
timing state, HiGHS LP and convex workspaces, callback lifetime, test-only LP
hooks, and Qhull's native context and diagnostic streams. The inspected native
solver/conversion paths use per-workspace or per-call state; this does not
assert whole-library thread safety.

A GCC ThreadSanitizer build with HiGHS and Qhull enabled ran
`execution_tests`, `batch_runner_tests`, `timing_collector_tests`,
`highs_lp_tests`, `highs_convex_tests`, `hv_conversion_tests`, and
`quickhull_2d_lp_test`. All 7 passed with `TSAN_OPTIONS=halt_on_error=1` and no
race report. The LP and Qhull suites include concurrent independent native
workspace/call paths. The exact logs, build flags, host metadata, and scope
limits are retained in the bundle. These dynamic tests cover only executed
paths and do not prove general race freedom.

The initial build attempt filled the small `/tmp` tmpfs while GCC wrote
temporary assembly. The successful retry placed `TMPDIR` under `/home`; the
source revision, sanitizer flags, and enabled native adapters were unchanged.

An independent source audit of `main` at `d9e0f90285919828d7713855e8441a6be1b6f4ec`
found that reusing a caller-supplied backend-thread observation could carry a
previous batch's maximum into a later `BatchResult`. The current #95 PR gives
adapters a fresh observer for every batch and merges its maximum into the
caller-owned aggregate only after workers join. A regression case reuses one
aggregate across batches reporting maxima 5 and 1; the corresponding results
now report 5 and 1 while the aggregate retains 5. `execution_tests` passes on
the fix branch.

## 2026-10-31 gprof profile-matrix diagnostic

To get a source-attributed signal from the current exact-profile matrix, I built
`csl_review05_profile_matrix` at source commit
`be94be8923a576d6f7cb9b527d818b3469cd0606` with GCC 16.2.1 Release flags
`-O3 -DNDEBUG -pg`, then profiled the existing T-S01/T-S02/T-S03 schedules
with GNU gprof 2.47. All measured attempts passed the registered complete-family
and two-witness checks: 7/7 pairs for T-S01 and 5/5 for each of T-S02 and
T-S03. All three profiled processes exited zero without timing out.

The call-graph samples are too sparse to locate a limiter: T-S01 and T-S02
accumulated about 0.02 seconds at 0.01-second sampling resolution, while T-S03
accumulated no timer samples. The sampled HiGHS factor-solve and KKT-check
entries in T-S01 are only two coarse ticks and include setup and repeated calls;
they do not identify a strategy bottleneck. T-S02 also has too few samples, and
T-S03 supports call-count inspection only. The `-pg` durations are not
performance measurements and were not used in timing summaries.

Raw gmon data, per-process receipts, JSONL output, checker results, complete
gprof reports and SHA-256 hashes are retained in the [2026-10-31 diagnostic
bundle](../../reports/algorithm-results/review05-gprof-diagnostic-20261031/README.md).
This repeats the same one-state, one-control, two-step fixtures and therefore
does not close the matched size/output-growth gap.

## REVIEW-05 disposition

The ownership, resource-policy and batch-isolation portions have current source/test evidence. The focused execution and batch suites passed with and without ThreadSanitizer; the fresh instrumented run also includes timing, HiGHS, and Qhull targets. The two earlier paired T-S01 captures repeat only one tiny workload. The new horizon and size ladders below broaden the matched scalar evidence, but do not cover alternative set representations or all phase and resource costs.

The [verified paired Release horizon capture](../../reports/algorithm-results/review05-horizon-paired-20261103/README.md) adds six matched repetitions at T=2, 4, and 8. All 42 attempts and all 18 measured pairs pass the independent exact fixture oracle. Reach-back medians are 6.059, 11.361, and 27.337 ms; Strategy B medians are 0.770, 0.779, and 0.975 ms. The timed region is `SynthesisWorkspace::run()` only. These are descriptive timings from one scalar fixture and host, not a general winner, speedup, or complexity result. The joint relation grows from 5 to 17 coordinates, and the separate serialized-output medians grow from 1,351 to 2,301 bytes for reach-back and 1,219 to 2,180 bytes for Strategy B. Serialized bytes do not measure allocated memory or conversion cost.

The earlier [dimension ladder](../../reports/algorithm-results/review05-dimension-20261031/README.md) has six verified pairs each for n=1,T=2; n=1,T=4; and n=2,T=2. Its n=2,T=4 reach-back attempts are rejected, so that point has no paired timing. The [constraint-row ladder](../../reports/algorithm-results/review05-constraint-20261031/README.md) has six verified pairs each at 2, 4, and 8 authored state rows per stage. These exact-polytope pilots vary horizon, dimension, constraint rows, and emitted H-relation size, with fixture-specific equal output proofs. The 2026-11-02 profile ladder adds 3,000 exact-checked outputs per strategy at each horizon, but its `-pg` profiles remain attribution diagnostics and are not timing measurements. Their largest sampled reach-back symbol remains below 5%; Strategy B has only 31, 31, and 47 10 ms ticks. No unique source-level limiter was found.

This evidence still has specific limits. The representation-size axis here is the emitted exact-polyhedral H-relation size; it is not a comparison of different set families. The horizon runner enforces per-process CPU, address-space, and wall caps but does not observe RSS; the older OBS-04 run measures whole-process RSS only on T-S01. Internal phase measurements exist for T-S01, including strategy-forward and terminal-optimization spans, but sparse assembly/factorization, conversions, and family queries are not separately measured across the size ladders. Existing phase timing and gprof evidence does not identify a general bottleneck. The exploratory two-state profile that rejects reach-back remains excluded as an unmatched timing point.

The ownership and batch-isolation findings are addressed in the source audit and TEST-23 evidence above, with focused ThreadSanitizer coverage for executor, LP, convex, and Qhull paths. A backend-observer aggregation defect was fixed with a multi-batch regression. The test evidence covers executed stress paths rather than all possible schedules.

**Status: partial; keep #95 open.** The verified horizon, dimension, constraint-row, and emitted H-relation-size timing slices provide matched evidence; the n=2,T=4 rejection is retained. Remaining work is phase-level cost separation and resource observations across comparable sizes, plus the final independent review against the exact integrated source revision. No measured evidence identifies a defensible general optimization target. Native thread enforcement and hard heap limits remain unsupported contracts, not defects newly discovered by this review.
