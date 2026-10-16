# EXT-01 fixed-plan numerical report harness

This stacked harness follows source PR #320, exact algorithm commit
`fd75a63657bc6b1d8cbd26c644bd8fb39cc1a3ec`. It builds the native public
`fixed_plan_disturbance` and `worst_case_vertex` APIs in a Release executable.
This commit contains no accepted measurement, saved numerical report, or Pages
publication. Review the exact harness commit before collecting report timings.

## Fixtures and literal checks

The executable has four independent fixtures:

| Fixture | Work and asserted result | Evidence limit |
|---|---|---|
| `l19` | Three V rows for `(x-1)^2` on `[0,2]`; public objective evaluations at 0, 1 and 2 return `[1,0,1]`; worst value 1 at endpoint 0, stationary midpoint value 0. | Native numerical objective and authored V rows. |
| `integrator_feasible` | Two-step `x'=x+u+w`, `u=0`, `w` in `[-1,1]`, safe `[-3,3]`; four terminal candidates `[-2,0,0,2]` and worst terminal `x²=4`. | Complete fixed-plan V candidates under independent compact disturbances and convex H safety. |
| `integrator_violation` | Same model with stage-one safe `[-0.5,0.5]`; stage-one successor `-1` rejects the entire plan. | Robust violation; no clipped tube or objective. |
| `b08_rounded` | Enumerates 625 fixed four-action plans and 256 disturbance-corner histories per plan; minimum worst value `67.150601101407` within `1e-8`, three ties. | Displayed rounded B08 arrays only. The published 67.12, nonlinear dynamics, unrounded MATLAB arrays, historical timing, and validated rounding are separate. |

The B08 fixture reuses the public-test literals and checks all 160,000
plan-history evaluations actually occurred. Its finite-action minimum is a
reference over the stated catalogue, not an optimal feedback policy or a
complete optimal-family certificate. All API assurances are numerical.

## Build and smoke

```powershell
cmake -S . -B build/ext01-report -G 'Visual Studio 17 2022' -A x64 -DBUILD_TESTING=OFF -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF -DCSL_BUILD_EXT01_REPORT=ON
cmake --build build/ext01-report --config Release --target csl_ext01_fixed_plan_report --parallel 4
build/ext01-report/Release/csl_ext01_fixed_plan_report.exe --smoke
```

Smoke emits four JSONL records with literal checks. `ext01_report_smoke`
checks the JSONL surface, including the evaluated L19 sample values, against
independent literals. These elapsed values are
functional smoke data, not accepted performance measurements. The driver exits
nonzero on any fixture or oracle failure.

After independent review, `--measure 7` emits an excluded warmup plus seven
observations per fixture in alternating order. L19 is batched 10,000 times,
the integrator fixtures 5,000 times, and B08 once per observation. Each call executes and validates
the literal result within the `steady_clock` interval, with `checked_calls`
and batch size retained. The interval includes fixture construction, public
API calls, literal validation, and JSON object creation for the returned
observation. It excludes process startup, JSONL serialization, persistence,
plotting, and rendering. It exposes no separate propagation, oracle, native
solver, or verification subphase. A failed call exits nonzero; the collector
must retain stdout and stderr rather than discard that attempt.

## Next report gate

Collection must use a pinned clean Release source and reviewed harness commit,
fresh build evidence (including the actual target graph and executable hash),
scenario/input hashes, OS/hardware/compiler/tolerance/thread metadata, and raw
JSONL for every warmup and measured run. Check that all expected calls ran,
each result matched its literal oracle, every interval is long enough to be
meaningful, and the run was not dominated by host contention. A separate
nonreported profile must identify the actual limiter before making any speed
claim. This is a single-adapter report with no comparator; inconclusive
performance is an acceptable conclusion.

Render standalone HTML, raw JSON/CSV, assets and offline ZIP from saved records
through the repository's `scripts/reports` schema-3 catalogue/site pipeline.
Independent review must check raw-to-HTML regeneration, scientific labels,
report layout, and the immutable main-only Pages URL. Link the verified URL
and source commit to PR #320 and issue #62. Until then, the report and #62
acceptance gate remain pending.
