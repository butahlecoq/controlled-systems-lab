# Algorithm report records and delivery

This is a saved-data reporting interface for the registered HiGHS LP adapter. C++20 executes numerical work through `Registry<LPPort>`, selection/preparation, exclusive workspace creation and `BoundWorkspace.run`. Python collects provenance and renders existing records. Rendering never invokes the executable or imports a native solver. Reporting adds no installed CSL API and changes no numerical contract.

The first report covers five analytic microfixtures. It is a descriptive single-adapter latency report, with no competitor, speedup, application-throughput or complete-minimizer-family claim. A passing numerical reference check is not a validated arithmetic certificate. Outcome support remains **Unestablished**. Until clean-code review, measurement review and deployment verification finish, measurements and the published URL remain pending.

## Commands and review stages

`CSL_BUILD_REPORTS` defaults to `OFF`. The private driver/support library also builds under `BUILD_TESTING`; product-only builds with both options off omit it. Standard-library tests require Python 3.11 or newer. CMake never installs Python packages. The separate plotting environment pins Matplotlib 3.11.2.

Build and run bounded functional tests:

```powershell
cmake -S . -B build/html01 -G 'Visual Studio 17 2022' -A x64 -DCSL_BUILD_REPORTS=ON
cmake --build build/html01 --config Release --parallel 4
ctest --test-dir build/html01 -C Release --output-on-failure --no-tests=error
python -m venv build/html01/report-env
$env:PIP_CACHE_DIR = "$PWD/build/html01/pip-cache"
$env:MPLCONFIGDIR = "$PWD/build/html01/mpl-config"
build/html01/report-env/Scripts/python.exe -m pip install -r scripts/reports/requirements.txt
build/html01/report-env/Scripts/python.exe -m unittest discover -s tests/reporting -p 'test_*.py'
python tests/reporting/test_smoke.py --exe build/html01/Release/csl_lp_report.exe
```

The smoke executes each case once with `purpose=test`. Test discovery without `--exe` explicitly skips that smoke; it does not claim to have executed it. Plot tests explicitly skip without the separate Matplotlib environment. Native CTest and the reporting workflow together cover these distinct gates. Neither runs an accepted benchmark.

The implementation is committed and independently reviewed **before** accepted measurements. Configure and build that fixed clean source commit, then, only after measurement allocation:

```powershell
$reportCodeCommit = git rev-parse HEAD
cmake -S . -B build/html01 -DCSL_BUILD_REPORTS=ON
cmake --build build/html01 --config Release --parallel 4 --verbose 2>&1 |
  Tee-Object build/html01/release-build.log
if ($LASTEXITCODE -ne 0) { throw 'Release build failed' }
# Write an accurate, public-safe concurrent-work note after checking current load.
python scripts/reports/collect_lp.py --exe build/html01/Release/csl_lp_report.exe `
  --build-info build/html01/report-build-info.json --build-log build/html01/release-build.log `
  --source-commit $reportCodeCommit --repetitions 7 --warmups 1 --profile-rounds 1000 `
  --concurrent-work-file build/html01/concurrent-work.txt --out build/html01/collection-001
build/html01/report-env/Scripts/python.exe scripts/reports/plot.py `
  --records build/html01/collection-001/records.json --out build/html01/figures-001
$reportId = (Get-Content build/html01/collection-001/records.json -Raw | ConvertFrom-Json).report_id
python scripts/reports/render.py --records build/html01/collection-001/records.json `
  --figures build/html01/figures-001 --out "build/html01/$reportId"
```

Linux equivalents use Ninja with `CMAKE_BUILD_TYPE=Release`, the native executable location and `report-env/bin/python`. All output destinations are new directories; export refuses to overwrite a bundle. The collector performs a final verbose build under clean-source checks before and after that build, checks the embedded executable commit/Release/NDEBUG identity, and retains the supplied build log plus that final build log and the complete CMake File API dependency graph. `SOURCE_ROOT`/`BUILD_ROOT` replace private checkout/build prefixes. A dirty or stale executable cannot produce a publishable report.

The collector records CPU/OS/RAM and pre/post load observations, public-safe process CPU deltas where available, exact configured resources and commands, executable and sanitized build-provenance hashes. It does not dump the environment or process command lines. The configured native thread count is not an observed OS thread count. Unavailable observations carry reasons. A busy system must be disclosed; do not remove slow individual trials or stop unrelated work.

The later artifact commit differs from the measured code commit. Regenerating figures/HTML from saved records does not rerun the solver or change that source identity. Code fixes require a new clean code identity, rebuild, review and new measurements as appropriate.

## Numerical references and evidence

| Case | Authored problem | Independent reference |
|---|---|---|
| offset-triangle | min `-x-2y+7`, nonnegative x/y, `x+y<=1` | `(0,1)`, value5: `x+2y<=2(x+y)<=2` |
| scalar-positive | min `3x+2`, `-1<=x<=4` | x=-1, value-1 by positive slope |
| scalar-negative | min `-2x+2`, `-1<=x<=4` | x=4, value-6 by negative slope |
| contradictory-rows | free x, `x<=0`, `x>=1`, zero objective | infeasible by contradictory bounds |
| free-unbounded | free x, min `-x` | unbounded as x grows |

Each case has a distinct ProgramId. Repetitions copy the same immutable mathematical request into fresh workspaces. Changing mathematical data requires a new ID. The driver checks literal point/value, independent row/variable feasibility, canonical result consistency and objective evaluation, original subjects, authoritative current attempt, absent bounds and the exact native-run/fresh-model diagnostic. It retains all returned candidates/residual contexts/raw diagnostics, including nonoptimal candidates. Native infeasible/unbounded status is checked against the analytic case, without inventing a certificate.

Primal, stationarity and sign residuals are numerical binary64 checks with absolute and relative tolerance 1e-8. Complementarity is unavailable from this LP adapter. Original objective offsets are retained. A point witness does not enumerate the optimizer relation. Historical values remain an empty separate track, and no private archival source or output is redistributed.

## Timing and statistical semantics

The measurement profile is one excluded warmup for each case, then seven fixed round-robin repetitions of all five cases. It uses native simplex/presolve-off/parallel-off/seed0, one configured native thread, and resource policy `{total_threads:1, outer_workers:1, threads_per_worker:1, memory_bytes:null}`. There is no solve deadline or iteration cap for these cases. The collector applies an outer process timeout and marks killed/incomplete processes aborted; that is not native cancellation.

The process, instruction/data caches and native TLS may be warm. Every measured trial creates a new immutable program, registry/prepared plan and exclusive workspace. There is no cold-process/OS-cache claim or same-workspace latency comparison.

| Interval | Boundary |
|---|---|
| input_publication | Authored input copy/construction through checked immutable program return |
| registration_preparation | Registry/factory registration, capability selection and snapshot preparation |
| workspace_creation | Prepared `create()` through owning bound workspace return |
| public_run | Public run through immediate consumption of status, witness bits, residual presence and diagnostic length into a uint64 observation token |
| independent_verification | Independent literal/constraint/evidence/identity checks plus canonical cross-check |
| end_to_end | Input-publication start through verification completion, including intervening harness work, before workspace/plan destruction |
| record_serialization | Trial JSON-byte construction after numerical timing; its duration is in the following metadata event, excluding framing/write/flush |
| plot/render | Separate Python monotonic saved-record export intervals, excluding their own metadata serialization |

End-to-end means **input-to-verified-result latency**, not application end-to-end. It excludes process startup, object destruction, JSON output/persistence and plotting. `public_run` includes translation/loading, native solve, logging and numerical work inside the adapter; native-only time and exclusive native/adapter decomposition are unavailable. The checksum observes completed work and is not a cryptographic input hash or mathematical certificate.

Record steady-clock integer boundaries, period and integer nanoseconds. A separate clock-read calibration records observed positive deltas, not guaranteed clock resolution. Zero intervals are legal at clock granularity and remain visible. Calibration, warmups and profile records never enter measured statistics.

Groups retain all attempts, expected/matched/failed/unsupported/cancelled/missing counts. Any failed reference check or incomplete process invalidates the benchmark group; a filtered success subset is not summarized. Expected infeasible/unbounded outcomes are successful reference matches. At least five complete matching trials are needed for median/min/max. For literal TEST values `[10,20,30,40,50]`, these are 30/10/50 ns; four values `[10,20,30,40]` have median25. Range is not a confidence interval or percentile. Nested phases appear separately and are never summed or stacked into end-to-end.

`--profile --rounds 1000` is a separate fresh-workspace run, without per-trial JSON output. It consumes every result, counts failures/work, and accumulates sequential phase totals. Windows GetProcessTimes/GetProcessMemoryInfo and Linux getrusage supply process CPU counters and process-lifetime peak resident memory where available. CPU deltas apply to the profile interval; a lifetime peak is neither per-call memory nor a delta. The largest measured component is mapped to its source path. Inner factorization/allocation/logging limiters remain unresolved without a separate sampling/call-stack profile. No speed ranking follows from this profile.

## Versioned saved-data interface

`csl.lp-report-events/1` is JSONL: one header/catalogue, trial and following serialization events, optional calibration/warmup events, and a final completion marker. The bounded CLI offers `--describe`, `--smoke`, `--measure --repetitions N --warmups 1`, and `--profile --rounds N`. Measurement repetitions are 5..1000; profile rounds are 1..10000. Arguments are validated before output or native work. Exceptions/Unsupported retain reached phases and diagnostics; independent cases continue where safe. Nonzero process exit is preserved.

`csl.algorithm-report-view/1` contains an envelope `{schema, report_id, payload_sha256, payload}`. `report_id` is `lp-UTCtimestamp-first12(payload_sha256)`. Required payload groups are:

| Group | Meaning |
|---|---|
| purpose / created_utc | Explicit test/measurement saved view and UTC identity; profile/calibration/warmup remain separate event purposes |
| provenance | Actual source/executable/backend/native-pin/build identity, clean build interval and actual compile/link graph |
| environment | Machine/load/tool observations, scalar/tolerances/seed/resources, reuse/warmup/order/clock policy |
| scenarios | Authored linear objective/offset/full CSR/bounds, original identity, independent reference/derivation/assumptions and hashes |
| trials | Case/round/order/identity, requested/actual registry provenance, current attempt, phase spans, observation token, neutral result, reference checks and native iteration metric |
| process | Expected/emitted counts, repetitions/warmups, return code, completion/abort and raw stderr/JSONL hashes |
| profile | Separate saved profile reference/hash/validity; not latency samples |
| historical | Separate empty array in this first report |

A metric is `{available:true,value:...,unit:...,scope:...}` or `{available:false,reason:...}`. Phase spans additionally contain decimal-string start/end ticks and integer `duration_ns`. A missing witness/objective is null with an explanation; nonfinite numbers are rejected rather than replaced by zero. Result support is explicit, and harness exception/unsupported/aborted status is separate from canonical termination. Residuals retain original subject, verifier/version, tolerances, violations and scales.

The complete literal fixture `tests/reporting/fixtures/view-v1.json` is conspicuously `purpose=test`, with synthetic source/build identity. Relabeling it as measurement does not create publishable provenance. Validators reject unknown schema versions, duplicate JSON keys, nonfinite values, changed hashes, wrong subjects, inconsistent success/reference/status, overlapping/reversed spans, mixed units, duplicate/out-of-order trials and inconsistent process counts. Failed but structurally valid results remain renderable. Corrupt input is an explicit error, never silently repaired.

Native iteration extraction recognizes only the exact `adapter.version=1.0.0+highs.1.11.0` / native1.11.0 prefix, before `native.log:`. Duplicate keys or a conflicting version fail. Arbitrary native log text is never interpreted as evidence or a runtime decomposition.

### Canonical bytes and file hashes

The report helper recursively sorts object keys, preserves array order, emits compact UTF-8 without BOM, and replaces binary64 values by `{"$binary64":"<float.hex()>"}` before hashing. Schema-declared coefficients/endpoints/objectives/residuals/tolerances normalize integer-looking JSON tokens to binary64. Counts/indices remain integers. Signed zero is preserved: -0.0 becomes `-0x0.0p+0`. C++ emits max_digits10 decimals with `.0` when needed to retain floating token identity. This is a documented local format, not RFC8785.

Input hash covers objective, offset, CSR and bounds. Scenario hash adds case/original identity, assumptions and analytic reference. Payload hash excludes its envelope and any future artifact commit. Each downloaded file has a separate exact-byte SHA256. Changing object key order does not change a mathematical hash; changing a coefficient or signed zero does. No future commit or file hashes itself.

## Figures, offline security and publication

Plotting reads the same validated aggregate as CSV/HTML. Separate public-run/end-to-end panels contain raw dots and median/min-max ranges, labelled in ns; objective/residual values remain accessible in tables. Matplotlib uses a fixed style/font/hash salt and records actual package versions. SVG and PNG are standalone exports.

The producer disables Date/Format/Type/Creator metadata and removes only the exact owned Matplotlib3.11.2 XML/public-DOCTYPE prefix from its newly created in-memory SVG. It then validates drawing elements/styles/internal references and writes final UTF-8 bytes before hashing. No imported-file repair command exists. Render/site consumers independently reject even a familiar unnormalized DOCTYPE, entities, processing instructions, metadata/RDF/unknown namespaces, scripts/event handlers/foreignObject, external href/CSS resources and escaping paths. Namespace identifiers are compared, never fetched. The real pinned producer-to-renderer/site/ZIP test checks final-byte identity and rejects default metadata.

HTML has no JavaScript, web font, CDN or runtime network request. It escapes labels/diagnostics, preserves negative numeric CSV costs, and prefixes dangerous CSV text cells for spreadsheet safety. Source/issue links are explicitly external GitHub references. Local filenames are allowlisted and escaping symlinks are rejected.

Reviewed bundles contain exactly thirteen files: `index.html`, `records.json`, `scenarios.json`, `raw-events.jsonl`, `profile.json`, `build-provenance.txt`, `process-stderr.txt`, `trials.csv`, `summary.csv`, `latency.svg`, `latency.png`, `export.json`, `manifest.json`. The manifest hashes the other twelve files. An adjacent ZIP contains these files under the report ID plus an offline index. Catalogue ZIP hashes are outside the ZIP.

The site validator also binds raw/profile/build/stderr sidecars to their saved payload hashes and checks CSV durations, summaries and units against the saved records. Rehashing a changed CSV in the manifest does not bypass these checks. An aborted writer may leave an unterminated final JSON line: the collector preserves the raw bytes, uses only complete preceding events, and records missing trials. A complete malformed line is rejected.

The orchestrator owns `reports/algorithm-results/catalog.json`, its deterministic index, immutable versioned bundles and publication. `site.py --catalog ... --check --out ...` validates inventory/hashes/records/links and stages only reviewed allowlisted files. TEST data cannot enter the publication path. The separate report workflow validates PRs without deployment and publishes main-only after validation; it does not run benchmarks or upload the repository wholesale. Pages settings remain an orchestrator action. A plausible URL, repository blob URL or green CI job is not proof of accessible deployment: open the actual Pages output URL, exact report, raw downloads and ZIP and compare the reviewed hashes before closing the report ticket.

## OBS migration

| Bootstrap field | Future authority |
|---|---|
| scenarios, hashes, source/environment | OBS-04 immutable scenario/run provenance; no invented strategy ID |
| trials, neutral result/evidence/reference checks | OBS-04 repetition/verifier records; program witness is not a trajectory/family |
| publication/preparation/creation | OBS-04 validation/capability/setup spans, preserving scopes |
| public_run | OBS-04 inclusive LPPort operation, not automatically first-witness/family-construction latency |
| verification/end-to-end/export | Corresponding named phases, keeping unavailable nonapplicable values |
| resources/process counters/profile | Separate OBS-04 environment/instrumentation track |
| median/range/counts/iterations | OBS-05 per-operation tables from original repetitions |
| saved plot series | VIZ-03 adapter input with units/evidence/nonadditivity |

OBS-04 overhead comparisons, strategy orchestration and family/query semantics remain future work. When their authoritative artifact exists, add an adapter to this small rendering view and retire the bootstrap collector as appropriate. The HTML renderer remains saved-data-only.
