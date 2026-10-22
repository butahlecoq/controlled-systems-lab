# SYN-04 Strategy B T-S03 report

The fixed solver source is `2c0c92107acd1cfc2f7e6d359e030d0bc47fb98e`.
This report measures only the registered exact T-S03 profile through the public
`StrategyRegistry` path. Its problem has `x0=0`, `x1=u0`, `x2=u1`, controls in
`[0,1]`, universal state constraints, and terminal cost `(x2-1)^2`. The complete
optimal history family is `(0,s,1,s,1)` for `0<=s<=1`; the objective bounds are
`[0,0]`. Assurance is numerical, and all general singular-dynamics profiles
remain outside this result.

Each run checks the actual provider identities, completed/optimal result,
registered completeness verifier, exact H coefficients, objective bounds,
family endpoints, two distinct histories with the same terminal state, and
infeasible nonmembers. The measured interval covers construction/resolution,
provider registration/preparation, StrategyPort execution (including the QP
solve and optimal-level extraction), compiled verification, membership checks,
and local owner destruction. It excludes process startup, file output, build,
and rendering. One warmup is excluded; seven measured observations are retained.
This is descriptive single-profile evidence only: no comparator, speedup,
scalability result, native-only timing, or validated-arithmetic claim.

The separate diagnostic run is not part of timing statistics. Process counters
do not establish a source-mapped limiter. The report is generated from a fixed,
clean harness commit and the pinned solver source. Rendering, sanitization,
validation, and Pages staging use saved records and do not rerun the solver.

The bundle includes a labelled 2D projection of the full five-coordinate
relation, source and input identities, raw JSONL/CSV, compiler/build provenance,
and reproduction commands. Main-only deployment and live URL/hash checks remain
separate gates. Issue #67 stays open for the remaining Strategy B criteria.

## Reproduction

Use fresh local output paths and the pinned dependency cache:

```powershell
python reports/algorithm-results/tooling/syn04_ts03/collect.py `
  --cmake $cmakeExe `
  --dependency-cache $dependencyRoot `
  --build-root $measurementRoot `
  --out $collectionRoot
python reports/algorithm-results/tooling/syn04_ts03/build_bundle.py `
  --collection $collectionRoot `
  --out reports/algorithm-results/syn04-strategy-b-ts03-20261022-2c0c9210
python reports/algorithm-results/tooling/syn04_ts03/report.py --check `
  reports/algorithm-results/syn04-strategy-b-ts03-20261022-2c0c9210/records.json
python tests/reporting/test_syn04_ts03_report.py
python scripts/reports/site.py --catalog reports/algorithm-results/catalog.json `
  --check --out $siteOutput
```

The collector builds a clean MSVC Release/NDEBUG/C++20 executable from the
pinned solver commit and verifies its registered production HiGHS providers.
Build paths and private machine data are sanitized at the export boundary.
The immutable report bundle is then validated against the typed record,
raw-event, CSV, HTML, manifest and offline ZIP contracts.
