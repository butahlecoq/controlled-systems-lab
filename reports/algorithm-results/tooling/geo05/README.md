# GEO-05 numerical report harness

This Phase 1 harness measures the bounded GEO-05 profile from the exact source
commit in PR #166. It does not change solver code, register a catalogue row, or
publish a report. The executable has separate `--smoke` and `--measure` modes;
smoke output is functional evidence only and must never enter accepted timing
records.

## Fixture catalog and evidence

The four scenarios are singular-A predecessor samples, an unreachable target
equality, the integrator `x' = x + u` with `X=[-2,2]`, `U=[-1,1]` and
`S=[1,3]`, and V projection preserving a zero-image ray. Independent literal
checks observe selected points and generator coordinates. They are numerical
sample checks: they do not prove exact set equality, completeness, or validated
arithmetic. H/equality elimination and the nominal predecessor have relation
support **Unestablished**. V projection preserves all source vertices and rays,
including duplicates and zero images, with a symbolic argument relative to the
stored input only. Lazy creation defers elimination and its materialization
uses the caller-selected ConversionPort provider; lazy materialization is part
of the selected API profile but is not a timed fixture in this four-case set.

For the integrator fixture, the authored joint H relation has six rows. One
Fourier–Motzkin elimination has `p*q+z = 2*2+2 = 6` generated rows. Two
generated zero-coefficient tautologies are removed, so the returned H output
has four rows. The driver records authored input and returned output counts as
observed data; the six-row intermediate peak is labeled as an analytic
expectation, not a runtime counter.
The H projection provider receives the per-call option `max_rows=128`. This is
an experimental driver setting and headroom for a small fixture, not evidence
of capacity or a global numerical/dimension/memory threshold. Counts do not
claim observed intermediate row peaks unless a future API exposes them.
`input_rows` and `output_rows` count authored/returned H inequality plus
equality rows for H scenarios, and input/returned vertices plus rays for the V
scenario.
Each canonical fixture includes its authored representation and dynamics or
projection coordinates. Every trial binds SHA-256 digests of both its fixture
inputs and full catalog scenario. Trials also record the returned representation
kind. The unreachable equality case returns an H representation with the
observed contradiction row `0 <= -1`; this is a representation observation,
not an emptiness certificate. Literal negative samples are labeled as samples.

## Timing API

Measurement mode emits and retains one excluded warmup attempt per scenario and
at least seven measured repetitions. Scenario order alternates forward and
reverse by measured round. Failed, unsupported, or cancelled warmups are kept
and invalidate success summaries.
Every trial creates fresh input sets, provider registrations, prepared
operations and workspaces. All failed, unsupported, or cancelled trials stay
in the record and invalidate success summaries. Counts, output rows, configured
row limits, and work-observed checks are retained.

The driver records preparation, workspace, run/materialization, independent
verification, and end-to-end spans in nanoseconds. For predecessor operations,
the public API creates its workspace inside `PreparedNominalPredecessor::run`,
so workspace creation is unavailable as a separate span; the driver marks that
field null and records the enclosing public run call. Successful end-to-end
starts before fixture construction and ends after literal checks. It excludes
process startup, persistence, rendering, and object destruction. V projection
workspace creation is directly observable. These scopes do not expose native
subphases or prove a numerical certificate.

## Build and smoke

Request the CMake File API graph before configuring:

```powershell
$api = 'build/geo05-report/.cmake/api/v1/query'
New-Item -ItemType Directory -Force $api | Out-Null
New-Item -ItemType File -Force "$api/codemodel-v2" | Out-Null
New-Item -ItemType File -Force "$api/toolchains-v1" | Out-Null
cmake -S . -B build/geo05-report -G 'Visual Studio 17 2022' -A x64 -DCSL_BUILD_GEO05_REPORT=ON
cmake --build build/geo05-report --config Release --target csl_geo05_projection_predecessor_report --parallel 4
build/geo05-report/Release/csl_geo05_projection_predecessor_report.exe --smoke
python reports/algorithm-results/tooling/geo05/smoke.py --exe build/geo05-report/Release/csl_geo05_projection_predecessor_report.exe
python reports/algorithm-results/tooling/geo05/test_report_tools.py
```

The collector can save raw JSON/CSV/JSONL attempts, provenance, content hashes,
an offline ZIP bundle, and standalone HTML rendered from the saved record only.
`collect.py --help` documents the measurement invocation; do not use
`--measure` until the exact harness commit has passed independent review.
Collection requires a clean worktree, completed Release build log, source and
harness commit SHAs, concurrent-work note, and CMake File API replies.

The smoke emits one JSON trial for each fixture and must report `passed`,
`oracle_passed=true`, and `work_observed=true`. Do not collect accepted timings
until independent review of this exact harness commit. This phase has no
accepted timing record, catalogue entry, or publication. The collector binds
source and harness commits separately, allows only the report-harness files
plus the exact GEO-05 CMake target insertion, and records the complete File API
dependency graph and executable hash.
