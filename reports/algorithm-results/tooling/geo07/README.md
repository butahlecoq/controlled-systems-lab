# GEO-07 fixed-source generator report harness

This harness is stacked on the exact GEO-07 source commit
`db7906cb33ca40da55e31b9bf6b21cf7ffcc1ee4` (draft PR #337). It calls the
public `CSL::geometry_generators` adapter through `GeneratorSet`,
`affine_image`, `dependent_sum`, and `factor_polyhedron`. The driver uses three
literal fixtures: an affine image of a two-factor box, exact cancellation of a
shared factor, and a dependent sum with distinct left/right equalities and a
shared factor. Each call checks the physical result against independently
written H inequalities or equalities, factor witnesses, outside points, factor
IDs, and representative coefficients. An infeasible factor tuple mapping to an
inside physical point is checked separately; factor feasibility is not claimed
to be equivalent to physical H membership for a noninjective map.

“Exact” describes representation algebra and preservation of factor identity.
The operations evaluate in binary64 and provide no validated rounding
enclosure. These three small fixtures are bounded examples, not proof of
general geometric correctness. The report is a single-adapter observation;
there is no competitor, speedup, application throughput, or scaling claim.

The native interval uses `steady_clock` around a batch of freshly constructed
sets, public operations, factor lifts, literal oracle comparisons, and JSON
result construction. Process startup, JSONL serialization, Python saved-row
verification, persistence, rendering, and deployment are outside that interval.
Every call must complete its oracle checks. One warmup batch per fixture is
excluded; at least seven measured batches per fixture alternate fixture order.
The collector admits only batches of at least 20 ms and retains every raw row.
The `checked_calls` count and literal result are independently validated from
saved JSONL. The resulting batch times include verification cost and are not
isolated operation latency. Internal phase counters, measured native thread
count, and a source-mapped limiter are unavailable; performance interpretation
remains exploratory and inconclusive.

## Review and collection sequence

This harness must be committed and independently reviewed before any timed
collection. No timing values are part of the harness PR. The collector requires
the exact clean reviewed harness commit and checks that the delta from the
frozen source contains only the report harness files. Only the configured MSVC
x64 Release graph with `/O2`, `/Ob2`, `NDEBUG`, C++20, and the
`csl_geometry_generators` library is admitted. It rejects `CL`, `_CL_`, and
`LINK` overrides. Supply an observed concurrent-work note immediately before
collection. Do not run the measurement while local builds or reviews compete
for the host.

Bounded pre-review checks, without timed collection:

```powershell
$cmake = 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
& $cmake -S . -B build/geo07-report -G 'Visual Studio 17 2022' -A x64 `
  -DCSL_BUILD_GEO07_REPORT=ON -DCSL_ENABLE_HIGHS=OFF `
  -DCSL_ENABLE_QHULL=OFF -DBUILD_TESTING=ON
& $cmake --build build/geo07-report --config Release `
  --target csl_geo07_generator_report --parallel 4
& 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\ctest.exe' `
  --test-dir build/geo07-report -C Release -R '^geo07_report_smoke$' --output-on-failure
python -B -m unittest discover -s tests/reporting -p test_geo07_harness.py
```

After independent review fixes the harness commit, collect from that exact
clean checkout. The following commands are a plan, not evidence of a run:

```powershell
$cmake = 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
& $cmake -S . -B build/geo07-report -G 'Visual Studio 17 2022' -A x64 `
  -DCSL_BUILD_GEO07_REPORT=ON -DCSL_ENABLE_HIGHS=OFF `
  -DCSL_ENABLE_QHULL=OFF -DBUILD_TESTING=OFF
& $cmake --build build/geo07-report --config Release `
  --target csl_geo07_generator_report --parallel 4
build/geo07-report/Release/csl_geo07_generator_report.exe --smoke
$load = (Get-CimInstance Win32_Processor | ForEach-Object {
  "CPU load=$($_.LoadPercentage)% logical cores=$($_.NumberOfLogicalProcessors)"
}) -join '; '
$jobs = (Get-Process cmake,MSBuild,cl,python -ErrorAction SilentlyContinue |
  Group-Object ProcessName | ForEach-Object { "$($_.Name)=$($_.Count)" }) -join ', '
"UTC $([DateTime]::UtcNow.ToString('o')); $load; selected concurrent processes: $jobs; snapshot only" |
  Set-Content -LiteralPath build/geo07-report/concurrent-work.txt -Encoding utf8
$harnessCommit = git rev-parse HEAD
python -B scripts/reports/geo07/collect.py `
  --exe build/geo07-report/Release/csl_geo07_generator_report.exe `
  --build-dir build/geo07-report `
  --out build/geo07-report/collection-001 `
  --harness-commit $harnessCommit `
  --concurrent-work build/geo07-report/concurrent-work.txt `
  --repetitions 7 --batch 1000
```

The collector saves native stdout as exact bytes in `trials.jsonl` and stderr
in `driver.stderr` before parsing. `process-capture.json` hashes those bytes.
Malformed JSON, wrong oracle output, missing calls, short intervals, nonzero
exit, timeout, or stderr leave a nonpublishable `collection-status.json` and
the raw evidence. Accepted rows produce deterministic `records.json`,
`build-provenance.json`, build logs, and an exact-byte SHA-256 manifest. The
collector records source and harness commits separately from a later artifact
commit. It does not render or publish a report. Scientific review, saved-record
to HTML consistency, offline artifact generation, main-only Pages deployment,
and live URL verification remain required by
[`published-algorithm-results.md`](../../../../docs/architecture/published-algorithm-results.md).
