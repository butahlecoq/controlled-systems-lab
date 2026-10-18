# OPT-12 measurement tooling

This directory documents the paired cold/warm workspace comparison for issue #46. The driver is `benchmarks/reporting/opt12_warm_start_measure.cpp`; the collector and saved-data-only renderer are `scripts/reports/opt12_collect.py` and `scripts/reports/opt12_render.py`.

## Measurement sequence

Review the implementation and this tooling at a fixed clean source commit before collecting measurements. Use a tuned Release build, an unused output directory, and at least five paired repetitions. The driver defaults to seven. For each pair it alternates cold and warm order. A warm trial first primes a fresh workspace on a source LP, then measures the same changed LP used by the cold trial in a fresh cold workspace. The cases have 1, 40, and 100,000 variables. The 1-variable case exposes fixed overhead; the 40-variable case checks ordinary reuse; and the 100,000-variable case changes the last objective coefficient after priming so the accepted basis must adapt while cold and warm solve work can be compared. The report identifies a case where reuse costs more only when retained medians show higher aggregate native work; iteration counts and transfer time remain separately visible.

On Windows PowerShell:

```powershell
cmake --preset dev-windows -DCSL_BUILD_REPORTS=ON
$buildLog = "$PWD/build/dev-windows/opt12-release-build.log"
cmake --build --preset dev-windows --target csl_opt12_warm_start_measure --verbose 2>&1 |
  Tee-Object $buildLog
if ($LASTEXITCODE -ne 0) { throw 'OPT-12 Release build failed' }
$sourceCommit = git rev-parse HEAD
python scripts/reports/opt12_collect.py `
  --exe build/dev-windows/Release/csl_opt12_warm_start_measure.exe `
  --source-commit $sourceCommit --build build/dev-windows `
  --repetitions 7 --out build/dev-windows/opt12-collection
python scripts/reports/opt12_render.py `
  --records build/dev-windows/opt12-collection/records.json `
  --out "reports/algorithm-results/opt12-$($sourceCommit.Substring(0,12))"
```

The collector requires the exact clean source commit, the CMake File API Release target artifact, a new destination, and complete verified trial rows. It retains raw JSONL, raw stderr, the executable, build graph and log, per-trial CSV and JSON, system-load snapshots, measurement command and hashes. Timed-out or invalid collections remain available for diagnosis but the renderer rejects them. The renderer verifies raw/typed consistency and all retained evidence hashes, then consumes only saved records without solver access.

## Timing and scope

The public-call wall interval wraps `LPWorkspace.solve` and excludes the priming solve, workspace construction, input construction and independent post-solve oracle. Native model-load, basis-install/setup, and native solve intervals are separately read from adapter diagnostics. Simplex iteration counts and cache state are retained for every measured row. Every trial checks completed optimal status, independent numerical feasibility and the literal expected objective before it is marked verified. No cost or speedup claim is supported unless the retained work components and iteration counts show it. No general speedup claim is supported by these synthetic cases.

The host snapshot records Windows processor load, free physical memory and process names/CPU totals before and after collection where available. This is a coarse observation, not a limiter profile. A separate sampling profile is required before attributing the measured cost to a particular implementation layer; if it cannot identify a limiter, the report's performance interpretation remains inconclusive.

The initial `csl.opt12-cost-report/1` saved schema is a bridge for this bounded adapter comparison. It must migrate into the authoritative OBS-04 run records and OBS-05 operation summaries when those are delivered; it does not define a second general experiment record system.
