# SYN-04 registered Strategy B T-S02 report

This additive report covers issue #238 and the merged, reviewed solver source
`e7f66a9ee698d05ed8779621116319158fa70158` (PR #237). It preserves the separate
T-S01 report and its published bytes. The fixed measurement harness is
`cabd2f37199e2f8412d75328cf7b881e590a468e`; the later artifact commit is distinct.

The exact fixture has x0=0, A=B=1, two independent controls in [0,1], universal
state constraints, no temporal/external/observation inputs, and LinearTerminal
with zero coefficient and offset 3. Every feasible history is optimal:
`(x0,x1,x2,u0,u1)=(0,s,s+t,s,t)` for s,t in [0,1]. Every execution checks
completed optimal status, registry-verified exact family, numerical assurance,
compiled verifier identity/binding, [3,3] result and complete-family bounds,
every literal coefficient of the 4-inequality/3-equality H-relation, endpoint
members, infeasible nonmembers, and two distinct histories sharing x2=1.

The executable uses StrategyRegistry and registered production HiGHS LP/convex
providers. The admitted T-S02 implementation constructs the relation analytically
and invokes neither provider's numerical solve. No incumbent trajectory residual,
native timing or solver iteration count is fabricated. The single public-path
interval includes problem construction, preparation, execution, verification,
membership checks and local owner destruction. It excludes process startup,
JSON serialization, persistence, compilation and HTML generation.

One excluded in-process warmup precedes seven measured observations. The separate
profile process repeats the same checked workload; its output and counters are
retained but excluded from the measured distribution. WPR denied sampled stacks
with 0xc5585011 on this host. Process counters cannot establish a source-mapped
latency limiter. These are single-profile exploratory observations with an
inconclusive performance conclusion, without a comparator or speedup claim.
Host load was 1.0% immediately before and 3.1% after the accepted process;
12 logical/6 physical CPUs and 34,189,107,200 bytes RAM were observed. Build and
reporting tests preceded measurement; no dedicated quiet-host guarantee is made.

## Reproduction

Use a clean checkout at the harness commit and a new build/output destination.
The collector creates a detached clean solver worktree at the pinned source,
checks it before and after build and execution, and verifies optimized Release,
NDEBUG and C++20 properties in the generated Visual Studio project. Published commands retain the measured command structure using portable root
placeholders. Source-archive directory hashes identify the exact dependencies.
The original private collection remains local; public sanitized build evidence
retains both original SHA-256 values and hashes of the sanitized file bytes.
Choose local values for the variables below; they are not stored in the report:

```powershell
python reports/algorithm-results/tooling/syn04_ts02/collect.py `
  --cmake $cmakeExe `
  --dependency-cache $dependencyRoot `
  --build-root $measurementRoot `
  --out $collectionRoot
python reports/algorithm-results/tooling/syn04_ts02/build_bundle.py `
  --collection $collectionRoot `
  --out reports/algorithm-results/syn04-strategy-b-ts02-20261014-e7f66a9e
python reports/algorithm-results/tooling/syn04_ts02/report.py --check `
  reports/algorithm-results/syn04-strategy-b-ts02-20261014-e7f66a9e/records.json
python tests/reporting/test_syn04_ts02_report.py
python -m unittest discover -s tests/reporting -p 'test_*.py'
python scripts/reports/site.py --catalog reports/algorithm-results/catalog.json `
  --check --out $siteOutput
```

The native inventory preserves exact raw JSONL/JSON/CSV, scenario/input hash,
source/build/compiler/host evidence, commands, build logs/cache/project/compiler
configuration, and separate profile output. The schema-3 adapter validates typed
records, raw projections, complete inventory/hash identity, and standalone HTML,
then generates the shared publication envelope, manifest and deterministic offline
ZIP. Regeneration and staging consume saved records without running a solver.

Historical adapters that hash raw publisher bytes require LF working-tree files,
matching the repository source. On Windows with core.autocrlf=true, run final
historical publication checks in a separate `git -c core.autocrlf=false archive` export (LF source blobs),
matching Linux CI, while preserving the original report workspace bytes.

The versioned staged page and offline ZIP are reviewable locally. Deployment and
live immutable URL/download verification remain pending for main-only Pages;
this branch does not publish or push. Keep SYN-04 #67 open. This report does not
cover T-S03, singular A, other dynamics/objectives or general completeness.

## Review and validation status

The staged page and inline figure passed desktop and narrow headless Chrome visual
inspection by the controller: text wraps, the equation/table use local horizontal
scroll where needed, and no visual defect was observed. Interactive browser QA
was unavailable because the browser/app inventory was empty. Main-only Pages
deployment and live page/raw-download/ZIP verification remain pending.

Public provenance uses SOURCE_ROOT, BUILD_ROOT, HARNESS_ROOT, DEPENDENCY_ROOT,
MEASUREMENT_ROOT, VISUAL_STUDIO_ROOT and PROGRAM_FILES_ROOT. The exporter and
publication adapter reject any remaining absolute Windows host path. The
executable, driver, source-tree and dependency-source hashes and all numerical
observations remain unchanged. Sanitization regenerates the bundle inventory,
typed payload hash, content-bound public ID and offline ZIP without rerunning
the solver. Raw private build logs are not redistributed.
