# OPT-06 basis-reuse hull classification: Release results

This versioned report records descriptive paired Release measurements of within-solve Phase-I basis reuse against the generic LP-membership reducer. The measured algorithm sources are commit `ef70e8c580a9556b0f5d96e49070d33221bf5b64`; report harness, collector, and packaging changes are recorded separately. The record schema is `csl.hull-benchmark-records/1`.

## Accepted collection

The clean Release executable was run on three 2D fixtures: a permuted square with edge/interior points (10 points), a full-dimensional square with a duplicated corner and edge points (7 points), and a square whose center has ID 0 (5 points). Each case/method pair has one excluded warmup and seven measured repetitions with alternating method order. The accepted-006 collection contains 48 total rows (6 warmups, 42 measured) and zero failures.

For every warmup and measured row, the harness validates completion, unique/in-range output IDs, and membership of every original input point in the exact output hull. It performs independent HiGHS membership checks after each timed call, and checks mutual containment for each timed pair. The interior-basis fixture has a completed baseline; the basis-reuse structural basis IDs are `[0, 3, 4]`, including center ID 0. A harness self-test exercises valid, duplicate and out-of-range IDs plus positive and negative containment cases.

| Fixture | Method | Median | Observed range | Membership LP calls (excludes Phase-I solve) | Phase-I basis solves | Pivots | Degenerate pivots | Bulk candidates | Exact bulk removals |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Duplicate-corner square | LP baseline | 0.6446 ms | 0.6231–0.6601 ms | 7 | 0 | 0 | 0 | 0 | 3 |
| Duplicate-corner square | Basis reuse | 0.0506 ms | 0.0484–0.0540 ms | 0 | 1 | 4 | 0 | 4 | 2 |
| Interior-basis square | LP baseline | 0.4747 ms | 0.4596–0.4921 ms | 5 | 0 | 0 | 0 | 0 | 1 |
| Interior-basis square | Basis reuse | 0.0442 ms | 0.0431–0.0503 ms | 0 | 1 | 4 | 2 | 2 | 0 |
| Permuted square | LP baseline | 0.9174 ms | 0.8720–0.9939 ms | 10 | 0 | 0 | 0 | 0 | 6 |
| Permuted square | Basis reuse | 0.0543 ms | 0.0520–0.0593 ms | 0 | 1 | 4 | 0 | 7 | 2 |

These are operation counts and durations from small fixtures. They do not establish a speedup or general performance claim: the workload is narrow and no dedicated limiter profile was collected. Performance interpretation remains inconclusive.

## Complexity and representation

For `n` points in `R^d`, the Phase-I formulation has `n` structural variables and `d+1` equalities. The assembled matrix stores `(d+1)n` coefficients, `O(nd)`, plus `O(n+d)` indexing and right-hand-side data; solver workspace and factorization storage depend on the backend. The method performs one Phase-I LP solve and at most `n` basis-coordinate queries and exact convex-combination certification attempts, one per nonbasis candidate. Each certificate uses at most `d+1` structural basis points. LP solve cost is solver-dependent; no general runtime bound is claimed.

## Evaluation plan

This report compares three small permuted, duplicate/degenerate, and interior-basis 2D clouds against the generic LP-membership reducer. Follow-up evaluation should vary `n`, `d`, rank/degeneracy, duplicates, interior/face points, ordering, and conditioning; compare paired outputs with exact input-containment checks; preserve operation counters and failures; and use a separate limiter profile before making performance conclusions. Include the fuel-consumption workload when its scenario fixture is available.

## Provenance and limits

- Windows 11 build 22631; AMD64 host, 12 logical processors and 33,387,800 KiB visible RAM; processor load and available RAM recorded before and after measurement. Unrelated background activity cannot be excluded.
- Visual Studio 17 2022 x64, MSVC 19.44.35215.0, C++20, HiGHS 1.11.0; Release `/O2 /Ob2 /DNDEBUG`.
- `records.json` binds the executable, build log, CMake cache, algorithm source files, and measurement harness by SHA-256. The sanitized verbose Release build log and raw process output are included.
- Timing covers `reduce_hull` or `reduce_hull_basis_reuse`; cloud setup, LP workspace creation, and post-timing oracle checks are excluded. Basis reuse includes Phase-I registration and solve. HiGHS uses presolve off, parallel off, and one thread; each invocation uses a fresh workspace.
- The hull oracle uses numerical HiGHS membership checks at tolerance `1e-8`; it is not a formal conditioning certificate. The reducer's bulk-deletion certificates use the exact binary64 convex-combination verifier.
- No profiler was collected. These fixtures do not represent the fuel-consumption workload or establish scaling.
- Pages publication is registered in this PR but cannot be verified until the main-only deployment workflow runs after merge. The immutable deployed URL and source commit must then be recorded on PR #210 and issue #37.

## Reproduction

Use a clean worktree at the measured source commit. Paths below are illustrative and should be adjusted to the local checkout.

```powershell
git worktree add D:\work\PhD\worktrees\opt06-measured ef70e8c580a9556b0f5d96e49070d33221bf5b64
cmake -S reports/algorithm-results/opt06-basis-reuse-20261014-ef70e8c5-r2/harness `
  -B build/opt06-report -G "Visual Studio 17 2022" -A x64 `
  -DCSL_ROOT=D:\work\PhD\worktrees\opt06-measured
cmake --build build/opt06-report --config Release --target csl_opt06_measure --clean-first --parallel 4 --verbose 2>&1 `
  | Tee-Object build/opt06-report/release-build.log
python reports/algorithm-results/opt06-basis-reuse-20261014-ef70e8c5-r2/harness/collect.py `
  --exe build/opt06-report/Release/csl_opt06_measure.exe `
  --code-commit ef70e8c580a9556b0f5d96e49070d33221bf5b64 `
  --build-log build/opt06-report/release-build.log `
  --concurrent-work "Describe observed machine activity" `
  --out build/opt06-report/reproduction-001
python reports/algorithm-results/opt06-basis-reuse-20261014-ef70e8c5-r2/harness/render.py `
  --records build/opt06-report/reproduction-001/records.json `
  --out build/opt06-report/reproduction-001/index.html
python reports/algorithm-results/opt06-basis-reuse-20261014-ef70e8c5-r2/harness/validate.py build/opt06-report/reproduction-001
```

The HTML report is self-contained. The validator checks raw/normalized trial agreement, completion, unique/in-range IDs, containment of every input point, the deterministic interior-basis invariant, summary statistics, chart bounds, and SHA-256 manifests without rewriting them.

