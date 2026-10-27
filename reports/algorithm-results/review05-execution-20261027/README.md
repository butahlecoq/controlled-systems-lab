# REVIEW-05 execution evidence

This bundle retains the focused execution tests, current-source T-S01 paired measurement and scenario-run outputs for [issue #95](https://github.com/butahlecoq/controlled-systems-lab/issues/95). The build/runtime identity and exact `ComparisonSpecId`/`ComparisonRunId` are in `environment.json`, `obs04-current-comparison.json` and `summary.json`.

## Current paired capture

`obs04-current-comparison.json` is the complete `csl.comparison-record/1`; `obs04-current-run.stdout.txt` contains every event `/9` row and the record digest; `obs04-current-run.stderr.txt` and `obs04-current-run.exit-code` preserve the process result. All 32 attempts passed, covering one warmup and seven measurements for each of four arms: reach-back/Strategy B crossed with collection disabled/enabled. Both strategies returned a registry-verified complete exact T-S01 family and two distinct witnesses verified against the original problem for every attempt.

The input is the two-stage scalar integrator, problem identity `csl.problem.v1.sha256:56871be36e6d8b0db2dde142a02722e82684a101171bd2975da3f4f708cb1d30`, `ts01_exact_integrator`, `csl.polyhedron.h`, numerical assurance, and absolute/relative tolerances `1e-8`. One backend thread and one driver worker were requested; the backend reported width one. The measured interval is the exclusive workspace `StrategyPort::run`; shared setup, collection setup, selection, verification, process startup and report encoding have separate or excluded scope. See the [OBS-04 contract](../../../benchmarks/reporting/obs04/README.md) for event semantics and limits.

The disabled arm medians were 4.947 ms for reach-back (4.867–5.712 ms) and 0.850 ms for Strategy B (0.831–1.236 ms). The enabled arm medians were 8.384 ms (8.254–10.844 ms) and 1.125 ms (1.036–1.304 ms), respectively. The paired instrumentation deltas and nested phase distributions are in `summary.json`. These observations describe one tiny fixture; they do not measure scaling. The source-level profiler `perf` was unavailable, so the dominant reach-back `strategy-a/forward` span is phase timing, not a source-resolved limiter profile.

The source commit is `2f05203b69e69f1eccbf6d33a175229775c06271`. CMake recorded a dirty source snapshot hash of `b202f9b655e6231ec8621d408d7ea8ccfbebf407a306b9b17d2c0e3625721d7d`; the working changes at capture time were the review document and evidence files, not source, include or benchmark implementation files. The executable hash and dependency archive hashes are in the comparison record. Raw results must be interpreted with that snapshot identity.

## Concurrency tests

- `release-ctest.txt`: Release `execution_tests` and `batch_runner_tests`, 2/2 passed.
- `tsan-ctest.txt`: GCC ThreadSanitizer build of the same targets, `TSAN_OPTIONS=halt_on_error=1`, 2/2 passed with no race report. HiGHS and Qhull were disabled in this sanitizer build.

## Scenario smokes

- `scenario-ts01-exact.txt`: current installed-package scenario CLI, both strategies complete and verify the exact T-S01 family with two witnesses each.
- `scenario-general-candidate.txt`: scalar `nominal_open_loop` candidate request; both strategies return candidate status but select zero witnesses, and trajectory verification does not pass. The CLI exit code is zero because candidate attempts were preserved. This is not a comparable timing point.

## Reproduction

From the repository root in a clean Release checkout, build the report driver and capture a new uniquely named record. The comparison record will carry the checkout's own source and executable identity:

```sh
cmake -S benchmarks/reporting/obs04 -B build/obs04 \
  -DCSL_SOURCE_ROOT="$PWD" -DCMAKE_BUILD_TYPE=Release
cmake --build build/obs04 --config Release --target csl_obs04_instrumentation_comparison --parallel 4
build/obs04/csl_obs04_instrumentation_comparison \
  --record reports/algorithm-results/<unique-run>/comparison.json
```

The recorded data is not a fresh multi-axis sweep. REVIEW-05 remains open pending compatible larger workloads with equal verified output scope, representation/output growth evidence and a current-build source-level limiter profile.
