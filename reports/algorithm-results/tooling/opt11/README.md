# OPT-11 recursive hull report harness

This harness compares the registered `csl.hull.lp-membership` baseline with
`csl.hull.recursive-split-merge` version 1.0.0 on three fixed 2D fixtures:
signed grid points, duplicates on a line, and an affine rank-one cloud. The
independent Python oracle computes exact dyadic convex hulls, checks that both
outputs have the same hull, checks every retained input lies in the literal
hull, and validates every deletion certificate's nonnegative weights, exact
unit sum, exact point reconstruction, acyclic substitution, and final retained
hull reconstruction. It also binds each certificate's problem identity to its
fixture and checks baseline or recursive-tree program IDs against the removed
point ID. No solver witness is trusted as a certificate.

The native record schema is `csl.opt11-recursive-hull-report/1`. A native bundle
contains exactly `records.json`, `collection.json`, `raw-stdout.jsonl`,
`raw-stderr.txt`, `release-build-log-sanitized.txt`,
`compiler-identification.cmake`, `functional-validation.json`, `trials.csv`, `summary.csv`, `latency.svg`,
`index.html`, and `manifest.json`. The adjacent offline archive is
`<report_id>.source.zip`. Records include all paired trial rows, method
durations, LP call counts, recursive leaf/merge metrics, peak merge points,
parallel overhead, runtime-reported HiGHS registration identity/version,
configured single-thread/presolve/parallel settings, and explicit unavailable
counters. The report is exploratory and makes no universal speedup or
scalability claim. The measured source commit is
`488d4ca8888d91c44b64d5d2f0baf564d1c28ae7`. The validated native bundle is
[`opt11-8cfbc0c65f420dfd`](../../opt11-8cfbc0c65f420dfd/), with native source
archive [`opt11-8cfbc0c65f420dfd.source.zip`](../../opt11-8cfbc0c65f420dfd.source.zip).
Its schema-3 publication identity is
`opt11-a43ae7725dd3ab72d2034473aeb6c5805f2d1820b2ccd70b8383ef300a4b9865`;
the public archive is
[`opt11-a43ae7725dd3ab72d2034473aeb6c5805f2d1820b2ccd70b8383ef300a4b9865.zip`](../../opt11-a43ae7725dd3ab72d2034473aeb6c5805f2d1820b2ccd70b8383ef300a4b9865.zip).
The public Pages URL and live hashes remain pending until the reviewed artifact
is deployed from `main` and verified there.

## Functional smoke

On Windows, from a clean isolated checkout, use a dedicated disposable build
directory. This smoke executes one baseline/recursive pair per fixture. It is a
functional check only; it is not accepted benchmark evidence.

```powershell
cmake -S reports/algorithm-results/tooling/opt11 -B build/opt11-harness `
  -G 'Visual Studio 17 2022' -A x64 -DCSL_ROOT="$PWD" -DCSL_ENABLE_QHULL=OFF
cmake --build build/opt11-harness --config Release --target csl_opt11_measure --parallel 4
build/opt11-harness/Release/csl_opt11_measure.exe run smoke > build/opt11-harness/smoke.jsonl
python -B reports/algorithm-results/tooling/opt11/validate.py `
  build/opt11-harness/smoke.jsonl --purpose smoke
python -m py_compile reports/algorithm-results/tooling/opt11/oracle.py `
  reports/algorithm-results/tooling/opt11/validate.py `
  reports/algorithm-results/tooling/opt11/collect.py `
  reports/algorithm-results/tooling/opt11/build_bundle.py
```

The smoke output carries `purpose=smoke`. Its clock values are diagnostics and
must never be passed to the bundle builder as a measurement. A clean working
tree is required for source-bound preflight and is best obtained after this
harness is committed.

## Fixed-code review and later accepted measurement

Do not run `collect.py measure` until the exact product source, harness, oracle,
validator, collector and builder commit have been independently reviewed and an
explicit measurement window is approved. The source commit is the immutable,
clean commit at which source hashes and the compiled description agree. Configure
and build it from a clean Release tree, keep the full verbose log private, and
write an accurate concurrent-load note. The collector requires the full source
commit, clean source status, executable/harness identity, VS 2022 Release x64
project settings, the generated CMake compiler identity file and its hashes, and
actual `/O2`, `/D NDEBUG`, `/std:c++20` compiler evidence
for the harness, recursive reducer, registered hull reducer, and HiGHS adapter.
The verbose log must show the explicit MSBuild clean command before those compiles, bind the compile
commands to the requested source root, and link the two registered libraries
into the expected Release executable. `test_collect.py` checks acceptance and
rejection of missing clean-first or timing-unit evidence.
It writes exact raw stdout and stderr bytes before validating them; failed or
incomplete executions stay in the collection directory and are rejected by the
saved report builder.

```powershell
$sourceCommit = git rev-parse HEAD
cmake -S reports/algorithm-results/tooling/opt11 -B build/opt11-harness `
  -G 'Visual Studio 17 2022' -A x64 -DCSL_ROOT="$PWD" -DCSL_ENABLE_QHULL=OFF
cmake --build build/opt11-harness --config Release --target csl_opt11_measure `
  --clean-first --parallel 4 --verbose *> build/opt11-harness/release-build.log
if ($LASTEXITCODE -ne 0) { throw 'Release build failed' }
'No deliberate competing benchmark or build workload was started. Ordinary background processes were not stopped; before/after host snapshots and matching-process CPU deltas aggregated by process name are retained.' |
  Set-Content build/opt11-harness/concurrent-work.txt
python -B reports/algorithm-results/tooling/opt11/collect.py preflight `
  --exe build/opt11-harness/Release/csl_opt11_measure.exe --source-root . `
  --source-commit $sourceCommit --build-log build/opt11-harness/release-build.log `
  --concurrent-work-file build/opt11-harness/concurrent-work.txt
# Only after fixed-code and harness review, and during the approved window:
python -B reports/algorithm-results/tooling/opt11/collect.py measure `
  --exe build/opt11-harness/Release/csl_opt11_measure.exe --source-root . `
  --source-commit $sourceCommit --build-log build/opt11-harness/release-build.log `
  --concurrent-work-file build/opt11-harness/concurrent-work.txt `
  --out build/opt11-harness/collection-001
```

Each fixture has an excluded warmup pair followed by six measured pairs. Pair
order alternates by round and fixture. Reducer workspaces, injected LP
workspaces, validation, serialization and rendering are outside the timer;
recursive child LP-workspace construction and root async scheduling occur inside
its public call interval. The baseline public call uses its injected LP
workspace. Thus the observations cover these registered public call paths and
their differing workspace policies; they are not isolated kernel timings.
Native LP phase timing, iteration counts, observed native thread count, CPU
time, peak memory, per-node wall time and source-mapped limiter are unavailable.
The recorded recursive overhead is the implementation's own root wall minus
the longer child subtree wall, not an independent operating-system overhead
measurement.

After separate review of the saved collection, generate the report without
rerunning the executable:

```powershell
python -B reports/algorithm-results/tooling/opt11/build_bundle.py build `
  --collection build/opt11-harness/collection-001 --out-root reports/algorithm-results
python -B reports/algorithm-results/tooling/opt11/build_bundle.py check `
  --bundle reports/algorithm-results/opt11-<content-id>
```

The builder requires the exact raw-byte hashes, complete pair matrix, independent
exact validation, source inventory and matching executable description. It
reconstructs records, CSV, SVG, standalone HTML, manifest and deterministic
offline ZIP solely from saved bytes. It does not execute or rebuild the
algorithm. Inspect the HTML and figure, compare every projection with raw rows,
and retain failed collections for review. Bundle generation alone does not
publish a URL or authorize a performance claim.
