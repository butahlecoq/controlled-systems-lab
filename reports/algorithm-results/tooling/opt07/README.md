# OPT-07 ordered hull harness: functional phase

This standalone C++20 harness selects `csl.hull.ordered-membership` through
`Registry<HullReducerPort>` and supplies the production HiGHS LP adapter. It
records three fixed binary64 point clouds: a signed 2D score distinction, a
zero-width segment with a duplicate endpoint, and a 1D cloud with a late
exterior point. The C++ smoke checks literal processing order, LP/attempt
counts, complete status, original-ID certificates, retained cardinality and
analytic support. The separate Python validator independently rechecks all
saved certificate weights with `Fraction.from_float` and the complete batch
matrix. A changed unit in the last place is rejected.

This is **functional harness evidence only**. No accepted measurement, report
bundle, performance conclusion or published URL exists for OPT-07 yet. The
overflow identity fallback is covered by product tests but excluded from the
HiGHS timing fixtures because extreme scaling would confound the small report.

## Functional smoke

Use an isolated checkout. On Windows, from its root:

```powershell
cmake -S reports/algorithm-results/tooling/opt07 -B build/opt07-harness `
  -G 'Visual Studio 17 2022' -A x64 -DCSL_ROOT="$PWD" -DCSL_ENABLE_QHULL=OFF
cmake --build build/opt07-harness --config Release --target csl_opt07_measure --parallel 4
build/opt07-harness/Release/csl_opt07_measure.exe smoke > build/opt07-harness/smoke.jsonl
python -B reports/algorithm-results/tooling/opt07/validate.py `
  build/opt07-harness/smoke.jsonl --purpose smoke
python -B -m unittest tests/reporting/test_opt07_oracle.py
```

`describe` prints the configured source commit, exact harness source hash,
configuration, C++ language mode, `NDEBUG` and later batch protocol. Smoke
emits three calls and three batch rows with `purpose=smoke`; its elapsed fields
are functional diagnostics, not benchmark results. Input setup, registry
preparation, workspace construction, post-call oracle checks and JSON output
are outside each batch timer. The timer includes the loop of public registered
`run_with` calls and moves of output variants into a preallocated vector.
Any lazy HiGHS initialization on those fresh workspaces is inside the timer.

## Proposed measurement after independent review

Freeze and independently review the source and harness commit, then configure
and build it from a **clean** worktree. Save a verbose clean Release build log
and an accurate concurrent-work note. The collector requires the reviewed full
commit, clean status, matching embedded executable and harness hash, actual
Release x64 project flags (`stdcpp20`, `MaxSpeed`, `NDEBUG`), and `/O2`,
`/D NDEBUG`, `/std:c++20` on the harness compile line in the verbose build log. Its `preflight` action
executes only `describe`; `measure` is a separate explicit command.

```powershell
$sourceCommit = git rev-parse HEAD
cmake -S reports/algorithm-results/tooling/opt07 -B build/opt07-harness `
  -G 'Visual Studio 17 2022' -A x64 -DCSL_ROOT="$PWD" -DCSL_ENABLE_QHULL=OFF
cmake --build build/opt07-harness --config Release --target csl_opt07_measure `
  --clean-first --parallel 4 --verbose *> build/opt07-harness/release-build.log
if ($LASTEXITCODE -ne 0) { throw 'Release build failed' }
'Describe observed concurrent work and machine load here.' |
  Set-Content build/opt07-harness/concurrent-work.txt
python -B reports/algorithm-results/tooling/opt07/collect.py preflight `
  --exe build/opt07-harness/Release/csl_opt07_measure.exe `
  --source-root . --source-commit $sourceCommit `
  --build-log build/opt07-harness/release-build.log `
  --concurrent-work-file build/opt07-harness/concurrent-work.txt
# Only after the code/harness and measurement protocol have been reviewed:
python -B reports/algorithm-results/tooling/opt07/collect.py measure `
  --exe build/opt07-harness/Release/csl_opt07_measure.exe `
  --source-root . --source-commit $sourceCommit `
  --build-log build/opt07-harness/release-build.log `
  --concurrent-work-file build/opt07-harness/concurrent-work.txt `
  --out build/opt07-harness/collection-001
```

The proposed run has one excluded warmup and seven measured batches per
fixture, with 100 calls per batch and fresh LP and hull workspaces created
before each timed batch. Each call retains original point IDs, all removal
terms and binary64 weights, attempts, counters and support values in raw
JSONL. Failed process output remains saved. Internal solver phase times,
pivots and observed OS thread count are unavailable. A later saved-data
report and publication adapter must summarize the raw rows, preserve all
failures, build an immutable standalone HTML/ZIP bundle, pass independent
saved-artifact review, and verify live Pages downloads. No comparison or
historical runtime assertion follows from these fixtures.
