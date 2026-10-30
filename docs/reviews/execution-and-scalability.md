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

## REVIEW-05 disposition

The ownership, resource-policy and batch-isolation portions have current source/test evidence. The focused execution and batch suites passed with and without ThreadSanitizer. There are now two fresh, equal-scope timing points for both strategies, but they vary neither state dimension nor horizon, constraint count, representation size or output size.

The general scenario runner does not currently give a second usable sweep: its tested two-state horizon-3 profile rejects reach-back at the convex adapter's matrix-removal threshold (documented in `examples/scenarios/README.md`), while the scalar general-profile smoke has no selected, verified witnesses. I did not use either as a fair speed comparison. No fresh multi-axis paired sweep is claimed here. The current-build gprof run is process-wide and too low-resolution to support a unique-limiter claim.

**Status: partial; keep #95 open.** Required remaining evidence is a compatible workload ladder that both general strategies complete with equal independently verified output scope, plus representation/output growth and phase/resource observations at those sizes. Native thread enforcement and hard heap limits remain unsupported contracts, not defects newly discovered by this review. An independent review of this report and the exact source revision is still required before sign-off.
