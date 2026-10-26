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
- Memory credits account only declared active workspaces and retained-result reservations. They do not cap the native heap or process RSS; hard memory limits are rejected.
- Cancellation closes admission and requests cooperative stop. It does not interrupt a noninterruptible adapter call or promise a finite return deadline.
- Batch metadata and outcomes retain per-input ordering and explicit skipped, failed, cancelled and late-returned states.

These limits are described in [execution contract](../contracts/execution.md), [native ownership notes](../testing/native-ownership.md), and `src/execution/executor.cpp`. I found no contradiction between the implementation, tests and those declared guarantees in the inspected paths. This is not a whole-codebase proof of thread safety; other mutable caches and providers still require their own ownership contract.

## Checks on this checkout

The current source built in Release with CMake 3.31.6, GCC 16.2.1, HiGHS 1.11.0 and Qhull enabled. The standalone installed-package `scenario_cli` was built from that install.

`execution_tests` and `batch_runner_tests` passed on the ordinary Release build (2/2). The same targets passed in a separate GCC ThreadSanitizer build (2/2, `TSAN_OPTIONS=halt_on_error=1`); no data race was reported. The sanitizer build used the core configuration with HiGHS/Qhull disabled, so this does not cover native HiGHS internals or all library paths.

Two scenario runs checked the comparable-output boundary:

- `two-stage-integrator.json` with `ts01_exact_integrator` returned complete optimal families from both strategies, two distinct witnesses each, and numerical trajectory verification passed for both.
- `minimal-lti-linear.json` with `nominal_open_loop` returned candidate families from both strategies, but selected zero witnesses on both sides; Strategy B retained one numerical-feasibility candidate while reach-back retained none. Neither side had trajectory verification to compare.

The general run is an admission/result smoke check, not a timing result. Candidate counts differ and selected outputs are empty, so it is excluded from paired performance claims.

## Available paired timing evidence

The existing [T-S01 paired report](../../reports/algorithm-results/syn-ts01-paired-20261014-b7f1ac0/README.md) has one excluded A-then-B warmup and seven measured pairs whose order alternates. Each pair shares the same resolved problem, exact-family request, selector, provider registries, one-thread policy and two-witness numerical verification. All 16 strategy trials passed. Per-strategy elapsed time includes preparation through verification and excludes process startup, shared setup, serialization and report generation.

| Strategy | Median | Range | Repetitions |
| --- | ---: | ---: | ---: |
| Reach-back | 4.9929 ms | 4.6265–5.2077 ms | 7 |
| Strategy B | 1.3736 ms | 1.3185–1.4400 ms | 7 |

This is a descriptive result for a tiny two-stage scalar fixture, not a scalability curve or winner claim. The report has no separate limiter profile. Its independent [PERF-03 diagnostic profile](../../reports/algorithm-results/perf03-ts01-single-process-correlation-20261014/README.md) is Strategy B only, pins an earlier source revision, and identifies the sampled hotspot for that repeated diagnostic workload; it cannot explain the paired timing gap or generalize to current larger workloads. The paired fixture also exposes only a 5-coordinate exact relation (4 inequality rows and 4 equality rows), so it says little about representation or output growth.

This timing bundle predates the reviewed source revision: its measurement source is `b7f1ac0a9800326c825b6d8e35a8f23656496682`, and its linked library source is `b2b1eea88570977f31df3a607dda282cef631792`. The bundle records algorithm-source equivalence for that historical measurement, but it is not a fresh benchmark built at the REVIEW-05 commit. Its host was Windows 11 on an Intel i5-12400F, with one configured thread per strategy. The Linux build and smoke runs above establish current build behavior, not current-build timing.

## REVIEW-05 disposition

The ownership, resource-policy and batch-isolation portions have current source/test evidence. A race-tool run found no issue in the focused execution and batch suites. There is one valid equal-scope timing point from the existing T-S01 record, but it varies neither state dimension nor horizon, constraint count, representation size or output size.

The general scenario runner does not currently give a second usable sweep: its tested two-state horizon-3 profile rejects reach-back at the convex adapter's matrix-removal threshold (documented in `examples/scenarios/README.md`), while the scalar general-profile smoke has no selected, verified witnesses. I did not use either as a fair speed comparison. No fresh multi-axis paired sweep or current-build limiter profile is claimed here.

**Status: partial; keep #95 open.** Required remaining evidence is a compatible workload ladder that both general strategies complete with equal independently verified output scope, plus representation/output growth and phase/resource observations at those sizes. Native thread enforcement and hard heap limits remain unsupported contracts, not defects newly discovered by this review. An independent review of this report and the exact source revision is still required before sign-off.
