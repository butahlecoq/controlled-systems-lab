# OPT-06 basis-reuse hull classifier: Release results

This versioned standalone report records descriptive paired Release measurements of the OPT-06 within-solve phase-I basis classifier and the existing LP-membership reducer. The measured code source is commit `ef70e8c580a9556b0f5d96e49070d33221bf5b64`; report packaging is a later PR change. The saved record uses `csl.hull-benchmark-records/1`, the repository finite-hull report schema.

## Accepted collection

A clean Release executable ran three 2D fixtures: a permuted square with edge/interior points (10 points), a full-dimensional square with a duplicate corner and edge points (7 points), and a square with center ID 0 (5 points). Each method/case had one excluded warmup and seven measured repetitions; method order alternated. All 42 measured rows completed, passed the oracle, and produced no failures.

For each pair, the harness checks both containments between the exact point-ID outputs returned by the timed calls, using fresh HiGHS LP membership queries after timing. The interior-basis fixture baseline is complete. The basis-reuse trials report structural basis IDs `[0, 3, 4]` and retain center ID 0; the unit regression asserts ID 0 is a structural Phase-I basis column, requires a completed baseline, and checks both hull containments.

| Fixture | Method | Median | Observed range | Membership LP calls/trial | Basis solves | Pivots | Degenerate pivots | Bulk candidates | Exact bulk removals |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Duplicate-corner square | LP baseline | 0.6359 ms | 0.6224–0.6892 ms | 7 | 0 | 0 | 0 | 0 | 3 |
| Duplicate-corner square | Basis reuse | 0.0517 ms | 0.0502–0.0532 ms | 0 | 1 | 4 | 0 | 4 | 2 |
| Interior-basis square | LP baseline | 0.4656 ms | 0.4456–0.5117 ms | 5 | 0 | 0 | 0 | 0 | 1 |
| Interior-basis square | Basis reuse | 0.0465 ms | 0.0452–0.0486 ms | 0 | 1 | 4 | 2 | 2 | 0 |
| Permuted square | LP baseline | 0.9222 ms | 0.8727–1.0052 ms | 10 | 0 | 0 | 0 | 0 | 6 |
| Permuted square | Basis reuse | 0.0546 ms | 0.0501–0.0561 ms | 0 | 1 | 4 | 0 | 7 | 2 |

These are operation counts and call durations for small fixtures. No speedup verdict or universal performance claim is made: the workload is narrow and no dedicated limiter profile was collected. The accepted collection is descriptive; broader workloads and profiling are needed before judging practical performance.

The failed and superseded collections are preserved under `evidence/failed-attempts/` and `evidence/superseded/` with separate manifests. They are excluded from accepted statistics. Failed trials include earlier collinear and larger-interior cases where a reducer returned incomplete and earlier harness/provenance defects.

## Provenance and limits

- Windows 11 build 22631; Intel Core i5-12400F, 6 cores / 12 logical processors; 33,387,800 KiB visible RAM.
- Visual Studio 17 2022 x64, CMake 3.31.6-msvc6, MSVC 19.44.35215.0, C++20, HiGHS 1.11.0; Release `/O2 /Ob2 /DNDEBUG`.
- `records.json` includes executable, build log, CMake cache, algorithm-source and harness hashes, plus host load/RAM readings (21% CPU before, 13% after). A sanitized verbose Release build log and all raw process output are included.
- Timing is around `reduce_hull` or `reduce_hull_basis_reuse`; cloud setup, LP workspace construction and post-timing oracle checks are excluded. Basis reuse includes its phase-I registration and solve.
- HiGHS simplex uses presolve off, parallel off and one native thread. Each timed call uses a fresh LP workspace; one warmup per case/method is excluded.
- The hull oracle uses numerical HiGHS membership checks at tolerance `1e-8`, not a formal certificate of conditioning. The reducer bulk-deletion certificates use the exact binary64 convex-combination verifier.
- No profiler was collected; the fixtures do not model the fuel-consumption workload or establish scaling. Performance interpretation remains inconclusive.

## Reproduction

See the PowerShell commands below. Replace `build/opt06-report` paths as needed; `CSL_ROOT` must point to the measured source commit.

```powershell
git worktree add D:\work\PhD\worktrees\opt06-measured ef70e8c580a9556b0f5d96e49070d33221bf5b64
cmake -S reports/algorithm-results/opt06-basis-reuse-20261014-ef70e8c5/harness `
  -B build/opt06-report -G "Visual Studio 17 2022" -A x64 `
  -DCSL_ROOT=D:\work\PhD\worktrees\opt06-measured
cmake --build build/opt06-report --config Release --target csl_opt06_measure --clean-first --parallel 4 --verbose 2>&1 `
  | Tee-Object build/opt06-report/release-build.log
python reports/algorithm-results/opt06-basis-reuse-20261014-ef70e8c5/harness/collect.py `
  --exe build/opt06-report/Release/csl_opt06_measure.exe `
  --code-commit ef70e8c580a9556b0f5d96e49070d33221bf5b64 `
  --build-log build/opt06-report/release-build.log `
  --concurrent-work "Describe observed machine activity" `
  --out build/opt06-report/reproduction-001
python reports/algorithm-results/opt06-basis-reuse-20261014-ef70e8c5/harness/render.py `
  --records build/opt06-report/reproduction-001/records.json `
  --out build/opt06-report/reproduction-001/index.html
python reports/algorithm-results/opt06-basis-reuse-20261014-ef70e8c5/harness/validate.py build/opt06-report/reproduction-001
```

The HTML report is self-contained. Validation checks every raw/normalized trial is complete, the exact timed result passed the oracle, the interior basis invariant, and summary statistics against raw trials. Pages publication remains pending until main deployment is verified.
