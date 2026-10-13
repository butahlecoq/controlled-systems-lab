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

Functional smoke validates the actual configured Debug or Release executable and matching CMake File API configuration. Debug/sanitizer execution remains functional coverage; measurement admission independently requires clean Release, NDEBUG and C++20. Physical file identity is used for artifact/path checks, including Windows short-name aliases.

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

Before any measurement/profile call, the supplied executable must be the selected `csl_lp_report` codemodel artifact in the actual configured source/build directory. Embedded configuration/compiler/version/generator and source/build/compiler-owner hash must match that graph. Embedded common and Release flags are checked against the actual report/support compile groups; the transitive compile/link/archive graph remains saved. A same-commit executable from build B cannot borrow build A's flags or provenance.

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

The destruction exclusion applies to successful intervals. On a thrown operation the action's owners unwind before the failure boundary is stamped; that retained total explicitly has scope `end_to_end_including_unwind`. CSV exposes `end_to_end_scope`, and the HTML trial detail retains the exact phase objects. Such failed intervals never contribute to successful summaries or an accepted profile. This scope does not claim to isolate native cleanup or add it to successful latency.

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

Every successful row requires all six observed phase spans, actual backend provenance and a returned current first attempt; configured source identity must agree with the saved source. Native iteration availability/value/unit/scope is typed and must agree with the recognized retained diagnostic prefix. Failed/stopped/Unsupported rows may retain unavailable phases with reasons. Infeasible/unbounded literal reference matches do not require invented objective candidates.

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

The pure `csl.report-document/1` projection is shared by export and site validation. Every emitted trial/summary CSV field, the complete deterministic HTML document and figure-series metadata are compared with saved records, independently of the manifest. An altered residual, support/status, diagnostic, displayed objective or figure series cannot be admitted by recomputing file hashes. The offline parser uses an explicit generated-tag/attribute vocabulary: only charset/viewport meta directives, generated drawing resources and approved relative/source/artifact links are accepted; meta refresh, srcset and unsupported resource attributes are rejected.

Both bundle and catalogue provide repository artifact-tree and ZIP fallbacks separate from the measured source link. `render.py --artifact-ref main` (default) labels this as **current main**, which may advance and becomes available only after artifact publication. A controller may instead supply an existing 40-hex artifact commit; other references are rejected. The catalogue's optional `artifact_ref` must match bundle export metadata. No future/self-referential commit is invented, no measured source SHA is replaced, and these fallbacks are not proof of Pages availability. Artifact reference and document policy live in export metadata, outside the scientific payload hash.

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

## Convex view2 and the registered numerical reporter

`csl_convex_report` is a private C++20 reporting client of the actual registered
`ConvexPort` / `csl.convex.highs` adapter. It publishes the existing immutable
ConvexProgram, prepares a registry plan, creates one exclusive workspace and
runs it once. It does not introduce another objective, QP, PSD or solver
implementation. The report retains the original identity and canonical solver
identity, norm-square transformation and coefficient snapshot. Weights belong
in the authored residual map. There is no mixed-objective squaring operation.

The fixed native profile is HiGHS 1.11.0, adapter
`1.0.0+highs.1.11.0`, archive
`2b44b074cf41439325ce4d0bbdac2d51379f56faf17ba15320a410d3c1f07275`.
It uses the adapter's existing numerical binary64 profile, one configured
thread, presolve/parallel off, zero QP regularization and a 4096-variable
nullspace limit. No solver option or admission policy is changed by reporting.
Public tolerances are absolute and relative `1e-8`. Positive-semidefiniteness
and original-space KKT residuals are numerical checks, not validated proofs.

### Independent analytic fixtures

All objectives use the canonical `0.5*x'Q*x+q'x+c` convention. Every case has
its own ProgramId. Norm cases also have a different squared ProgramId. Empty
rows retain their authored dimensions and CSR offsets.

| Case | Original problem | Independent minimizer / outcome | Original / solver minimum |
|---|---|---|---|
| quadratic-boundary | `(x-3)^2`, `0<=x<=2` | decreasing on the interval, `x=2`; upper multiplier2 | 1 / 1 |
| quadratic-equality | `2x²+2xy+2y²-8x-10y+17`, free variables, `x+y=2` | substitute `y=2-x`: `2x²-2x+5`; `(0.5,1.5)`; gradient `(-3,-3)` | 4.5 / 4.5 |
| norm-positive | `sqrt((x-3)^2+16)`, `0<=x<=2` | `x=2`; original upper multiplier `1/sqrt(17)` | sqrt(17) / 17 |
| norm-zero | `abs(x-3)`, `0<=x<=5` | `x=3`, zero residual; no division by the norm | 0 / 0 |
| norm-constant | `||(0,0)x-(3,4)||`, `0<=x<=1` | every point of `[0,1]` | 5 / 25 |
| quadratic-face | `(x-1)^2`, `0<=x<=2`, `0<=y<=1` | complete analytic segment `(1,t)`, `t` in `[0,1]` | 0 / 0 |
| quadratic-zero-row | `(x-3)^2`, `1<=x<=5`, authored `0=0` | `x=3`; the row is redundant | 0 / 0 |
| quadratic-zero-contradiction | same quadratic/bounds, authored `0=1` | infeasible | unavailable |
| quadratic-unbounded | `x²-y`, free x, `y>=0` | along `(0,t)`, cost `-t` tends to minus infinity | unavailable |

The three squared norm snapshots have `(Q,q,c)` equal to `(2,-6,25)`,
`(2,-6,9)`, and `(0,-0,25)`. Signed zero is retained in canonical binary64
hashing. The driver independently checks case formulas, literal points or
coordinate predicates, original constraints, costs and all five available
original-space residual measures: rows, variables, stationarity, signs and
complementarity. It never requires one selected free coordinate or a particular
iteration count. The analytic description of a minimizer set is a fixture
oracle; the returned native witness does not represent that whole set.

Results keep termination, mathematical outcome and `Unestablished` support
separate. Candidate costs may exist on a stopped/nonoptimal result; they are
not minima. Certificates, justified bounds, basis and optimizer families remain
unavailable. Zero-variable wrapper programs, bad dimensions/nonfinite data,
pre-cancellation, typed admission rejection and native iteration limits are
functional checks outside the nine-case measurement catalogue.

### Native phase observations

View2 fixes the private `csl.convex-native-phases/1` policy. `native_phases`
contains exactly `feasibility`, `qp`, and `linear`. Each has `execution`,
`iterations`, and `elapsed` records. This is a report projection of retained
source-bound diagnostics, not a new native capability.

| Execution state | Evidence | Iterations when not explicitly available |
|---|---|---|
| observed_return | complete trusted API/model status pair after the native call | null / native_info_unavailable |
| known_not_called | independently established pre-entry, wrapper, pre-call stop, earlier-phase exit, invalid start, or nonselected route | null / phase_not_called |
| unknown | exception, interrupted observation or absent boundary evidence | null / execution_unknown |

Returned statuses do not establish successful mathematics. A `time_limit`
entry is a configured remaining budget before a stop poll; it never proves a
call or supplies elapsed time. A normally returned cancelled/resource-limit,
undetermined result with a configured phase but no returned pair and no setup
error can prove the pre-call stop. An exception or setup error cannot use that
inference. Fully observed earlier phases survive later failures. Explicit
`native_run=false`, constant-wrapper and invalid-QP-start markers are checked
against the route and any conflicting returned evidence.

The parser rejects duplicate keys, half pairs, contradictory info/counts,
negative/overflowed counts, error-status counts and forged projections. Only
the prefix before the exact `native.log` delimiter is evidence; log-body text
cannot create a phase observation. An explicit trusted count0 remains
available0, distinct from unknown or unavailable info. Every native elapsed
record is `{available:false,value:null,unit:"ns",reason:"not_exposed_by_adapter"}`,
including known non-calls. There is no invented phase-I/QP duration or sum of
unlike iteration counts. JSON, CSV and HTML retain every state, reason, status,
availability and null value.

Completed nonzero-Hessian cases require observed feasibility and QP returns,
except the contradictory row which requires observed infeasible feasibility
and a proved uncalled QP. The constant norm uses the observed linear route.
A reached QP requires the adapter's valid-start/no-default-fallback evidence.
Unknown or stopped relevant work cannot enter a successful measured group.

### Version dispatch, ownership and compatibility

LP remains view1/events1/profile1/document1 with unchanged payload hashes and
deterministic historical projection. Convex uses
`csl.convex-report-events/1`, `csl.convex-profile/1`,
`csl.algorithm-report-view/2` with `report_kind:"convex"`, and document policy2.
Its report ID starts `convex-`, followed by the UTC timestamp and payload hash.
Unknown kind/version combinations reject. Convex scenarios serialize existing
objective variants with dense shapes, CSR geometry, bounds, original/solver
identities and literal references. Saved validation never implements a second
general numerical objective engine.

The shared noninstalled report runtime owns timing, exception-unwind handling,
JSON primitives, process counters and the bounded typed CLI. The LP and convex
report records and mathematical checks remain distinct. The shared Python
collector accepts only fixed immutable LP/convex profiles. Fresh provenance
includes the runtime/support/executable compiler flags, complete reachable
native/objective/numeric link graph and actual physical source/build/executable
ownership. Legacy LP records legitimately predate the shared runtime target;
that historical graph is not silently rewritten.

Convex saved validation recomputes phase projections and checks original and
solver costs and residual values against retained native diagnostics. Raw
sidecars reconstruct the saved event view; separate-profile source, catalogue,
counts and assessment must agree. Warmups and failed/partial records are
retained and validated, with failed warmups blocking publication. Complete
CSV and HTML projections reject corruption even after hashes are refreshed.

A mixed `csl.algorithm-report-catalog/2` adds `report_kind` to each entry.
Catalogue1 remains LP-only with byte-compatible staging. A controller can add a
convex entry and annotate the old LP entry without changing the existing
thirteen-file LP bundle, ZIP or public URLs. There is no automatic migration or
rewrite of published scientific bytes. Both kinds use the same thirteen-file
bundle inventory and strict local-file/SVG/HTML boundary. Plotting retains the
pinned Matplotlib producer, exact owned-prolog normalization, disabled metadata,
final-byte hashes and two separate inclusive panels.

### Functional code, later measurement and publication gates

Configure the noninstalled reporters with `-DCSL_BUILD_REPORTS=ON`. With both
that option and BUILD_TESTING off, reporting targets and their Python test
requirements are absent. Functional commands include:

```text
cmake -S . -B build/convex-report -DCSL_BUILD_REPORTS=ON
cmake --build build/convex-report --config Release --parallel 4
ctest --test-dir build/convex-report -C Release --output-on-failure --no-tests=error
python tests/reporting/test_convex_report.py --exe build/convex-report/Release/csl_convex_report.exe
python -m unittest discover -s tests/reporting -p "test_*.py"
```

The last command uses the separately pinned plotting environment when testing
actual figures. `--describe` and bounded `--smoke` are catalogue/functional
operations, never benchmark evidence. The collector rejects Debug measurement
while permitting honest Debug functional smoke. Ordinary tests do not invoke
accepted measurement, profile or clock calibration.

Only after fixed-code review and an explicit measurement window does the
controller authorize `collect_convex.py` with one warmup per case, seven
round-robin repetitions and a separate 1000-round profile: 9 excluded warmups,
63 measured trials and 9000 separately profiled operations. The collector's
final clean Release build occurs before timers; record preceding compilation,
load and warm state. Keep all failures and outliers. Native inner-phase timing
and inner limiting mechanism remain unresolved. Process CPU deltas and lifetime
peak memory apply to the separate profile, not individual calls.

All six existing interval scopes remain: input publication, preparation,
workspace creation, public run, independent verification and end-to-end.
Public run includes lazy setup, feasibility, QP/simplex, logging and in-run
checks. Successful end-to-end ends before owner destruction; failure intervals
explicitly include actual unwinding. JSON construction follows numerical timing.
The profile's nested end-to-end total is not added to component totals.

Plot, render and site regeneration read saved records and never invoke a solver.
Fresh export durations/manifests may differ; scientific records and final figure
bytes are preserved when reusing saved figures. Stage1 synthetic records are
visibly TEST DATA and cannot be published. Actual convex measurement, independent
artifact review, its own desktop/narrow/full-scroll/expanded diagnostic QA and
verified live URLs remain separate later gates. No old LP screenshot or green
CTest result satisfies those numerical/publication obligations.

## Scenario statistics alongside historical algorithm reports

The additive [run-statistics format](run-statistics.md), now `csl.run-statistics/3`,
binds actual MODEL03 problem identity to an independently resolved execution
configuration. Standalone LP/convex bootstrap records keep their real program
identities, schema kinds, provenance and existing readers. They do not acquire
invented scenario IDs, strategy selections or configuration pins. No published
v1/v2 payload is rewritten; a future scenario runner may reference raw artifacts
only with its genuine scenario/configuration binding. Public-run timing retains
its wrapper/native/translation/check scope, and missing native observations stay
explicitly unavailable. OBS01 adds no native diagnostic parser or performance
publication gate exemption.

## Registered non-LP publication adapters

The shared Pages publisher accepts catalogue schema `csl.algorithm-report-catalog/3`
for mixed LP, convex, OPT-05, GEO-02, GEO-03, GEO-04 and GEO-05 catalogues.
LP/convex retain their validated view schemas and bundle projections. Other report
kinds use the corresponding registered adapters: OPT-05 and GEO-03 in
`registered_reports.py`, GEO-02 in `geo02_registered_reports.py`, GEO-04 in
`geo04_registered_reports.py`, and GEO-05 in `geo05_registered_reports.py`.
Each adapter validates its native source identity, typed trial/summary coherence,
explicit file inventory, manifest hashes and safe paths before staging. The shared
renderer projects measured tables, evidence limits and links from validated
records, then `site.stage` emits the registered pages, offline ZIPs and catalogue
links. Producer HTML remains hash-checked source evidence and is not copied as the
published page. Catalogue scope and limit text must match the adapter projection;
it cannot add claims. A staged result is not a public URL: the main Pages workflow
must publish the integrated catalogue before the live URL check can pass.

For registered kinds, the native `records.json.report_id` and source directory stay
unchanged. The schema-3 catalogue and publication envelope carry that identity as
`source_report_id`; their `report_id` is the public destination. The public suffix is
the full SHA-256 of a canonical identity record containing every validated native
source file hash, the native source ID, and the SHA-256 of the publisher module that
generates the staged page, envelope, manifest and ZIP. Publisher source line endings
are normalized to LF before hashing. This lets another measurement,
an updated evidence file, or changed publisher output use a different immutable URL
without rewriting the original numerical archive. The repository source-tree fallback
uses `source_report_id`; the repository ZIP and public page/download links use
`report_id`.
Both native `trials.csv` and `summary.csv` must match the complete typed rows in
`records.json`, even when their manifest and archive checksums are internally valid.

## Shared publication envelope

Every report in a schema-3 mixed catalogue uses the same versioned
`csl.algorithm-report-envelope/1` and
`csl.algorithm-report-publication-manifest/1`. The envelope records report
identity and kind, native payload schema and digest, provenance, measured scope,
evidence limits and typed payload. LP/convex scope is derived from the validated
scenario inventory, and their evidence-limit policy is fixed by report kind.
Schema-3 catalogue values must match their adapter projection. Registered
geometry and optimization reports retain method-specific payloads and render
HTML from validated typed records. Every generated page follows the shared
safe-link and HTML escaping policy.

The previously published LP and convex URLs retain their original schema-2 pages,
all thirteen original bundle files and offline ZIP bytes. The exact legacy hashes
are pinned in `reports/algorithm-results/legacy-publications.json`; the publisher
also checks a fixed digest of that pinset before staging. Schema-3 LP and convex
rows use those old IDs as `source_report_id` and derive new public IDs from the
complete validated source inventory, original ZIP and publisher code. The new
pages and ZIPs live only at the new IDs. The old paths remain available without
changing any historical measurement or download bytes.
The pinset applies only to those historical source IDs. Future LP and convex
source bundles may be registered with new content-bound public IDs without
editing the pinset; every pinned historical source must still be present and
staged byte-for-byte.

The manifest records the exact staged file inventory and SHA-256 values, including the staged page, figures, evidence files and serialized envelope. The manifest itself is excluded from its own file list. The offline ZIP contains the same envelope and manifest bytes as the staged directory and uses deterministic, uncompressed entries. Schema-1/2 catalogues remain readable under their existing publication path; schema-3 rows require the common envelope metadata. An unknown native payload schema is rejected before output is created.
