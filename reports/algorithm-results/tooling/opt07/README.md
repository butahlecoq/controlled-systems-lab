# OPT-07 ordered hull harness and measured report

This standalone C++20 harness selects `csl.hull.ordered-membership` through
`Registry<HullReducerPort>` and supplies the production HiGHS LP adapter. It
records three fixed binary64 point clouds: a signed 2D score distinction, a
zero-width segment with a duplicate endpoint, and a 1D cloud with a late
exterior point. The C++ smoke checks literal processing order, LP/attempt
counts, complete status, original-ID certificates, retained cardinality and
analytic support. The separate Python validator independently rechecks all
saved certificate weights with `Fraction.from_float` and the complete batch
matrix. A changed unit in the last place is rejected.

The accepted native report is
[`opt07-bbb4aee749d643ff`](../../opt07-bbb4aee749d643ff/), collected from
clean reviewed source `52444e305684c0b59c049cce9f9de7ea09eb4a4a`.
Its 2,400 calls all passed independent validation. The 21 measured 100-call
batches are descriptive evidence for three small fixtures; there is no
comparator, speedup, source-mapped limiter or scalability conclusion. The
overflow identity fallback is covered by product tests but excluded from the
HiGHS timing fixtures because extreme scaling would confound this report.

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

## Reproducing the reviewed measurement protocol

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

The accepted run has one excluded warmup and seven measured batches per
fixture, with 100 calls per batch and fresh LP and hull workspaces created
before each timed batch. Each call retains original point IDs, all removal
terms and binary64 weights, attempts, counters and support values in raw
JSONL. Failed process output remains saved. Internal solver phase times,
pivots and observed OS thread count are unavailable. The report builder admits
only a complete, oracle-verified measurement and never silently filters failed
or missing rows. A failed collection retains its raw bytes locally for review.

After independent review of genuine saved collection bytes, these saved-only
commands create and recheck a versioned native bundle and deterministic offline
source ZIP:

```powershell
python -B reports/algorithm-results/tooling/opt07/build_bundle.py build `
  --collection build/opt07-harness/collection-001 `
  --out-root reports/algorithm-results
python -B reports/algorithm-results/tooling/opt07/build_bundle.py check `
  --bundle reports/algorithm-results/opt07-<content-id>
```

The collector records SHA-256 of exact raw stdout and stderr bytes at collection
time. The builder verifies both hashes before parsing the JSONL. It also requires
the exact reviewed source-file hash key set, recomputes the literal fixture
digest, and binds the saved harness digest to the executable description.
The bundle retains exact raw JSONL and stderr bytes, the sanitized Release log,
collection provenance including the raw local log hash, all batch outcomes,
derived CSV/HTML/SVG, and an exact-file manifest. The checker regenerates the
record and every display from raw bytes without invoking the driver. The
`opt07-ordered-hull` schema-3 publisher adapter and catalogue row admit only
this reviewed measurement bundle.
Synthetic tests use `purpose=test` in the collection and every raw row; they
exercise the complete 24-batch/2,400-row validator only through explicit
`build_bundle.py --allow-test`. Their records and pages say TEST / synthetic.
The publisher rejects these bundles even if the site checker has test mode.
Main-only Pages deployment and live URL/ZIP verification are the remaining
publication gates. No comparison or historical runtime assertion follows
from these fixtures.
