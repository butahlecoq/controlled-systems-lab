# OPT-04 phase-I matched report harness

This private harness pairs the registered `phase-one-bland` equality/nonnegative
feasibility adapter with the registered HiGHS LP reference on the same five
analytic problems. It exercises the existing public `LPPort` registration,
preparation, exclusive workspaces and `BoundWorkspace.run`; it adds no solver
implementation. The report scope is descriptive. It does not claim a speedup,
exact feasibility, validated arithmetic, a complete solution family, or that a
returned witness proves all feasible points. Numerical support remains
**Unestablished**.

## Publication and migration status

This native report uses `csl.opt04-phase-one-report/2`. Its local saved-data
renderer and bundle are private source evidence; they are not registered with
`scripts/reports/site.py` or the authoritative algorithm-report catalogue, and
they do not create a public page or URL. The tracked path for validating this
native bundle, adapting it to the shared schema-3 envelope/catalogue, preserving
its raw files as source evidence, and integrating it into the main-only Pages
workflow is [issue #185](https://github.com/butahlecoq/controlled-systems-lab/issues/185).
Until that integration and deployment are complete, treat any local HTML as a
private renderer output only.

## Review boundary

The harness must receive fixed-source review before any accepted collection.
The only pre-review execution permitted is `--smoke`, which runs one functional
trial per fixture and side and discards all timing output. Do not invoke
`collect.py --measure` until that review is complete and the source commit is
fixed. No accepted OPT-04 timing has been collected by this change.

After review, each measurement collection uses one excluded warmup and seven
measured repetitions for each fixture and side. Every side constructs and
publishes a fresh immutable request, registers its adapter, prepares the
pipeline, creates a fresh exclusive workspace, calls the public run API, and
checks returned status and candidate independently. Side order alternates
within fixture/repetition; fixture traversal alternates forward/reverse.
The execution context requests one total thread, one outer worker and one
thread per worker; the registered HiGHS profile also fixes simplex, presolve
off, parallel off and one native thread. These are requested/configured values,
not an observation of OS thread counts.
Failures and failed warmups remain in the records and invalidate the group.
The collector requires complete matched pairs and validates the saved trial
matrix before deriving summaries.

## Fixtures and independent checks

| Fixture | Problem | Expected outcome | Literal check |
|---|---|---|---|
| `triangle` | `x2=.25`, `x3=.25`, `x1+x2+x3=1`, `x>=0` | feasible | phase-I witness `(0.5,0.25,0.25)` |
| `signed_triangle` | `-x1+x2-x3=-.5`, `-x1-x2+x3=-.5`, `x1+x2+x3=1` | feasible | phase-I witness `(0.5,0.25,0.25)` |
| `edge` | `x2=.5`, `x3=0`, `x1+x2+x3=1`, `x>=0` | feasible | phase-I witness `(0.5,0.5,0)` |
| `duplicate_tie` | `x1+x2=1` twice, `x>=0` | feasible | phase-I witness `(1,0)`; exercises deterministic tie handling |
| `contradictory_rows` | `x=0`, `x=1`, `x>=0` | infeasible | auxiliary optimum `1` |

Each method's observed classification is compared with the literal expected
classification. Feasible HiGHS results need not select the phase-I witness;
they are checked as independent feasible points against original equalities,
nonnegativity and the zero objective. Phase-I results additionally check their
literal candidate and auxiliary optimum. The contradictory fixture checks the
literal infeasible status and phase-I auxiliary value. Residuals use binary64
absolute tolerance `1e-8`, relative tolerance `0`. These checks are numerical,
not exact proofs. Reference agreement is supplementary evidence and not a
certificate.
The saved-data validator independently recomputes the successful HiGHS
witness residual checks from each trial's hashed input and saved primal; it
rejects recorded check flags that disagree with the recomputed residuals.

## Timing fields

All spans are nanoseconds and are stored per trial:

* `setup`: request publication, adapter registration, selection, preparation
  and fresh workspace creation;
* `public_run`: the inclusive `BoundWorkspace.run` call;
* `verification`: independent expected status, witness, residual and
  nonnegativity checks;
* `end_to_end`: fixture setup through independent verification, excluding
  process startup and JSON serialization.

Phase-I trials record the original-row maximum violation, maximum
nonnegativity violation, evaluated original objective, auxiliary equation
residual and auxiliary value. They also retain committed pivots, degenerate
pivots and factorization counts from the actual diagnostics snapshot. Reference
trials have null phase-I-only fields and retain the HiGHS outcome and witness.
The paired classifications are repeated in both trial rows so saved validation
can check agreement without joining external files.

## Build and smoke

From the repository root, in a Visual Studio developer PowerShell:

```powershell
$api = 'build/opt04-report/.cmake/api/v1/query'
New-Item -ItemType Directory -Force $api | Out-Null
New-Item -ItemType File -Force "$api/codemodel-v2" | Out-Null
New-Item -ItemType File -Force "$api/toolchains-v1" | Out-Null
cmake -S . -B build/opt04-report -G 'Visual Studio 17 2022' -A x64 `
  -DCSL_BUILD_OPT04_REPORT=ON -DBUILD_TESTING=OFF
cmake --build build/opt04-report --config Release `
  --target csl_opt04_phase_one_report --parallel 4
build/opt04-report/Release/csl_opt04_phase_one_report.exe --smoke
python reports/algorithm-results/tooling/opt04/collect.py --smoke `
  --exe build/opt04-report/Release/csl_opt04_phase_one_report.exe
```

The standalone CMake entry point is also available:

```powershell
cmake -S reports/algorithm-results/tooling/opt04 `
  -B build/opt04-harness -G 'Visual Studio 17 2022' -A x64 -DCSL_ROOT="$PWD"
cmake --build build/opt04-harness --config Release `
  --target csl_opt04_phase_one_report --parallel 4
```

The driver's ordinary mode is reserved for reviewed collection and emits a
warmup plus seven measured repetitions. `collect.py --measure --exe ... --out
...` saves `records.json`, the single-schema trial `stdout.jsonl`, and
`stderr.txt`. The command also requires `--build-dir`, `--source-commit`,
`--harness-commit`, and `--concurrent-work-file`; it checks a clean source tree
(including untracked, nonignored files), requires the algorithm source commit
to precede the reviewed harness commit, and verifies that the configured CMake
source, Release configuration, and selected executable belong to this
checkout. Immediately before measurement it performs a `--clean-first`
Release rebuild of the report target from the pinned HEAD and retains a
sanitized build log plus executable, CMake-cache, and build-log hashes. The
compiler identity/version, Release flags, CMake generator, and logical
processor count are recorded. The collector applies a 300-second outer driver timeout by default; override it
with `--timeout-seconds`. A failed, malformed, timed-out, or incomplete driver
run is still saved with its available rows, errors, failure/missing counts and
aborted status, but has no eligible summary statistics. The collector refuses
to overwrite an existing destination. Rendering and bundle generation consume
only saved records and are owned by the separate report renderer.

After review, the measurement command has this form:

```powershell
$sourceCommit = '<fixed algorithm source commit>'
$harnessCommit = git rev-parse HEAD
python reports/algorithm-results/tooling/opt04/collect.py --measure `
  --exe build/opt04-report/Release/csl_opt04_phase_one_report.exe `
  --build-dir build/opt04-report --source-commit $sourceCommit `
  --harness-commit $harnessCommit `
  --concurrent-work-file build/opt04-report/concurrent-work.txt `
  --out build/opt04-report/collection-001
```

## Later limiter evidence

After independent source review and before interpreting any timings, run a
separate CPU sampling profile with a separate profile-only execution of all
fixtures. Do not profile accepted timed runs. Preserve profiler commands,
profile hashes, sample counts, process CPU/counter evidence and resolved hot
functions; map the hottest resolved function to source or say attribution is
unavailable. Record host load and concurrent work. The benchmark skill's
limiter gate is separate from this harness and from reported durations. Until
that evidence supports a limiter and the trials pass all correctness checks,
describe performance as inconclusive and make no speedup claim.

The fixtures exercise small equality feasibility tasks from OPT-04's bounded
scope. They do not represent application throughput, capacity, the archived
author's original release, or every numerical corner case. The collinear-input
acceptance case remains outside this report's five-fixture catalogue; OPT-04
#29 stays open until its kernel and lineage criteria are reviewed separately.
See
[`docs/contracts/phase-one.md`](../../../../docs/contracts/phase-one.md),
[`docs/research/phase-one-lineage.md`](../../../../docs/research/phase-one-lineage.md),
and [`docs/contracts/algorithm-report-records.md`](../../../../docs/contracts/algorithm-report-records.md)
for supported mathematics, source lineage and broader reporting limits.
