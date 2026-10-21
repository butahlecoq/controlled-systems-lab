# Published algorithm results

The owner requires an English HTML report whenever an implemented algorithm can produce numerical results. Reports are deliverables of the algorithm work, not a feature deferred until the complete optimal-control application exists. [HTML-01 #123](../superpowers/plans/tickets/HTML-01.md) provides the initial report pipeline and first reference-LP report. Existing scientific and implementation acceptance criteria remain binding.

## Artifact and publication

Use saved, versioned records to render a standalone HTML page with numerical tables, suitable figures and measured performance. Publish an index and immutable report URLs through this repository's GitHub Pages site. Keep the report, raw JSON/CSV and assets in version control, with a download path that remains useful offline. Link the actual published URL and source commit in each relevant PR and issue. Until a report is measured, reviewed and deployed, its URL and performance are pending rather than implied by passing tests.

Each report identifies algorithm/module/backend versions, code commit, scenario and input hashes, supported assumptions, expected analytic or sourced values, actual objectives/residuals/status and evidence scope. Distinguish historical published figures from new measurements. A solver witness is not a complete optimal relation. Failed, unsupported and cancelled runs retain their status and any available evidence.

## Measurements

Record hardware, OS, compiler and release settings; arithmetic/tolerances/seeds; requested and actual worker/native thread counts; cold/warm and workspace reuse policy. Specify precisely what each interval includes, with units and raw per-repetition data. Separate setup, solve, verification, end-to-end and rendering where measured. Name unavailable internal counters instead of guessing them. Nested or parallel durations cannot be summed as end-to-end latency. CTest runtime is test-harness time, not an algorithm benchmark.

Comparative performance claims require at least five alternating tuned repetitions per side, median/range, failures and a separate limiter profile, following [skill routing](../agents/skill-routing.md). Report inconclusive comparisons when the measurement does not support a winner. A first single-adapter report can report reproducible timings without an invented competitor or speedup. Check expected numerical outputs and that the work actually ran before accepting a timing record.

## Module boundaries and review

Keep execution, measurement collection, scientific saved records, HTML rendering and publication independently replaceable, outside solver logic. Future [OBS-04](../superpowers/plans/tickets/OBS-04.md), [OBS-05](../superpowers/plans/tickets/OBS-05.md) and [VIZ-03](../superpowers/plans/tickets/VIZ-03.md) extend the records/figures; they are not blockers for the first analytic LP report. The first small record must have an explicit migration path into those authoritative artifacts rather than a competing result schema.

Independent review checks mathematical/evidence labels, measurement validity and module boundaries. Verify raw-record/HTML consistency and regeneration, visually inspect the page, and open the deployed URL before claiming publication. The orchestrator publishes the reviewed artifact. Private historical source code and raw archives remain unchanged and are not copied into the report site.

## EXT-07 hybrid profile report

The frozen implementation source is `2965baafa325550ad60ec91d44f5e3f86a832178`.
The saved bundle
[`ext07-hybrid-51d9ee2e89d240eb`](../../reports/algorithm-results/ext07-hybrid-51d9ee2e89d240eb/)
contains a one-step scalar profile with interval control and guard, identity
reset, and a linear terminal objective. Its analytic joint relation is
`x0=0, x_pre1=u0, x1=u0, 0<=u0<=0.5`; the complete minimizing family is the
singleton at zero. The registered HiGHS LP provider and independent bounded
scalar family verifier completed 140 measured calls after an excluded warmup.
On the recorded Windows 11 / MSVC Release host, median end-to-end batch time
was 6,288,700 ns (range 5,492,300–9,158,900 ns); all seven batches matched the
analytic result with no failures. These timings are descriptive for this one
fixture and do not establish a performance winner, scalability, general
polyhedral coverage, or validated arithmetic. The first bundle covers the
one-step scalar interval profile; the implementation also has a bounded
finite-horizon verifier for exactly one free scalar control parameter, but the
first bundle does not measure that domain. An earlier frozen bundle,
[`ext07-hybrid-two-parameter-df7acc27de65930b`](../../reports/algorithm-results/ext07-hybrid-two-parameter-df7acc27de65930b/),
preserves the fixed two-stage, two-control fixture with `enter-half` and
`enter-full` branches. Its feasible sets are `[0,0.5] x [0,1]` and
`[0,1] x [0,1]`; both retain the complete minimizing family
`u0=0, 0<=u1<=1` for the objective `x_terminal=u0`. The registered HiGHS LP
provider and `TwoParameterScalarPolytopeHybridFamilyVerifier` completed 140
measured calls after an excluded warmup. Its timing remains historical evidence
for that verifier. The earlier exact-verifier bundle
[`ext07-hybrid-two-parameter-26f402289a309403`](../../reports/algorithm-results/ext07-hybrid-two-parameter-26f402289a309403/)
remains immutable. The current
[`ext07-hybrid-two-parameter-8ad871b5ea29fc7b`](../../reports/algorithm-results/ext07-hybrid-two-parameter-8ad871b5ea29fc7b/)
bundle replays the fixture with `ExactLinearHHybridFamilyVerifier`, preserving
both complete minimizing faces `u0=0, 0<=u1<=1`. At source commit
`8f7ea777621c337680b092ba6a15dd09a9d00a88`, it completed 140 measured calls
after an excluded warmup, with zero failures; on the recorded Windows 11 / MSVC
Release host, median end-to-end batch time was 73,188,000 ns (range
72,683,400-89,925,100 ns) and median individual call time was 3,673,950 ns.
This is descriptive evidence for this fixture, not a comparative benchmark,
speedup, scalability result, or validated-arithmetic claim. The older bundle
remains immutable; its timing is not a controlled comparison with the current
verifier. The current bundle retains nonempty sanitized Release build output,
a standalone feasible-set plot, raw rows, and an offline ZIP. The one-parameter
verifier is not measured by either two-control bundle. Broader independent
continuous-family oracle coverage and resource-scale evidence remain open
EXT-07 acceptance items. Main-only Pages
publication and live URL/hash verification remain pending.

## OPT-07 ordered hull membership report

The reviewed native bundle
[`opt07-bbb4aee749d643ff`](../../reports/algorithm-results/opt07-bbb4aee749d643ff/)
records source commit `52444e305684c0b59c049cce9f9de7ea09eb4a4a`.
It contains three fixed binary64 clouds, 2,400 independently verified calls,
and 21 measured 100-call batches after one excluded warmup per cloud. Original
point IDs, exact dyadic deletion certificates and literal support checks are
saved with the raw observations. These single-adapter timings are descriptive;
there is no comparator, speedup, source-mapped limiter or scalability claim.
The native bundle and source ZIP passed independent saved-data and scientific
review. Main-only Pages deployment and live exact-byte verification remain
publication gates. OPT-07 issue #38 remains open for grouped and streaming
reduction work.

## OPT-11 recursive split-and-merge hull report

The reviewed OPT-11 source is `488d4ca8888d91c44b64d5d2f0baf564d1c28ae7`.
Its native bundle is
[`opt11-8cfbc0c65f420dfd`](../../reports/algorithm-results/opt11-8cfbc0c65f420dfd/)
and its schema-3 publication ID is
`opt11-a43ae7725dd3ab72d2034473aeb6c5805f2d1820b2ccd70b8383ef300a4b9865`.
The collection contains 18 complete alternating baseline/recursive pairs,
with six measured pairs on each of three fixed 33-point clouds. The independent
exact-dyadic oracle validated 1,274 deletion certificates; all 42 calls
completed. In baseline/recursive order, median public-call durations were
2,704,100/2,786,750 ns for `signed-grid`, 2,778,150/2,822,650 ns for
`duplicate-collinear`, and 2,685,650/3,196,350 ns for `rank-one-offset`.
Ranges overlap and no performance winner is supported. Timing includes
recursive child LP-workspace creation and root async scheduling; it excludes
parsing, injected workspace creation, validation, serialization and rendering.
The source-mapped limiter is unavailable. These observations cover only the
three fixed binary64 clouds on the recorded host/backend and establish no
universal speedup, application-scale behavior, or scalability claim. The
deployed [versioned report](https://butahlecoq.github.io/controlled-systems-lab/opt11-a43ae7725dd3ab72d2034473aeb6c5805f2d1820b2ccd70b8383ef300a4b9865/index.html)
uses source commit `488d4ca8888d91c44b64d5d2f0baf564d1c28ae7`. Live page
SHA-256 is `702e8a91d3a757978289ef7b565ec03e841ba6dd765fe81af49fe4fd01aa2116`;
the public ZIP SHA-256 is `90b609866df72e0432ae7ef9dbe4f4692a321c6d7b84225a0cb1bf6254704767`
and matches the main catalogue. The live HTML bytes match the page in the ZIP
and the hash in its publication manifest.

## GEO-07 registered dependent generator sum report

The bounded GEO-07 dependent-sum bundle
[`geo07-dependent-4dcc5a8fe36f17ed`](../../reports/algorithm-results/geo07-dependent-4dcc5a8fe36f17ed/)
uses frozen algorithm source `5411e37ad456f0d5b3bf775130f149622ef5ebfa`
and sealed harness `eef1eda3d326418a392b3cc1e8f8f4b204ca7a73`, whose
code parent was independently reviewed. Its two public `GeometryPort`
fixtures check shared factor cancellation, constrained equalities, literal
physical H references and the existing independent Minkowski rejection.
The accepted collection contains one excluded warmup and seven alternating
2,000-call measured batches per fixture. Two earlier rejected attempts and
their raw bytes remain in the saved bundle. The observations cover the whole
checked public path on supplied binary64 examples. There is no comparator,
speedup, source-mapped limiter or validated rounding enclosure; performance
interpretation is inconclusive. Independent saved report review, main-only
deployment and live hash verification remain publication gates.

## GEO-06 QuickHull report

The GEO-06 report uses solver source `ce63bff5a0face88c3c5e977f7d96337e8cbe948`
and independently reviewed harness `74651cb028b9c2359d666ae5f141c66e0b03708b`.
Its saved native bundle is `geo06-b010fb3df212604b`: three small analytic
clouds, one excluded warmup and seven measured batches of 1,000 calls per cloud.
Every batch checks literal hull indices. The measured interval includes the
QuickHull call, index copy and oracle comparison. The Release build log,
compiler/link options, host note, all trial rows and exact file hashes are
retained with the versioned HTML and offline ZIP. This is a single-adapter
observation with no comparator, speedup or source-mapped limiter profile;
performance interpretation is inconclusive. The report covers the supplied
binary64 coordinates and does not establish general geometric correctness.
Independent report review, main-only deployment and verified live links remain
publication gates.

## APP-02 box and parallelotope approximations

Issue [APP-02 #33](https://github.com/butahlecoq/controlled-systems-lab/issues/33)
has a saved [five-case bundle](../../reports/algorithm-results/app02-box-8ff979de60ea9d22/)
from frozen public adapter source `8fecba49e34c37e5e01c40218a8f014a179818fd`.
The fixtures cover a 1D interval, two outer 2D diamond bounds, an inscribed
axis box and an inscribed rotated parallelogram. Every public call checks its
literal H rows/bounds or V corners after timing; the approximation policy
independently checks stored-binary64 containment. The capture retains one
excluded warmup and seven rotated 100-call batches per case: 3,500 measured
calls, zero recorded failures. The standalone 2D example is generated from the
same saved record. These are descriptive single-adapter observations, with no
comparator, source-mapped limiter, speedup, finite approximation error bound or
validated real-arithmetic claim. Independent saved-result review, main-only
Pages deployment and live-byte verification remain publication gates.

## APP-03 zonotope reduction and enclosure

Issue [APP-03 #42](https://github.com/butahlecoq/controlled-systems-lab/issues/42)
has a saved [three-case bundle](../../reports/algorithm-results/app03-zonotope-4522855018fa9b0b/)
from frozen public adapter source `e105a86b8e2ab7d09b1e7042fc5f0d5bc0ce5c40`.
Two planar outer covers and one exact zero-column conversion check literal
generator matrices, relations, factor counts and evidence identities after
every public call. The independent approximation policy checks stored-binary64
outer inclusion. One excluded warmup and seven rotated 100-call batches per
case yielded 2,100 verified measured calls with zero recorded failures. The
labelled 2D example is derived from the same saved fixture. These are
descriptive single-adapter durations; no comparator, speedup, source-mapped
limiter, finite approximation error bound or validated real-arithmetic claim
is supported. Independent saved-result review, main-only Pages deployment and
live-byte verification remain publication gates.

## APP-04 directional ellipsoidal approximation

Issue [APP-04 #34](https://github.com/butahlecoq/controlled-systems-lab/issues/34)
has a saved [three-case bundle](../../reports/algorithm-results/app04-ellipsoid-fd302c34092f8b19/)
from frozen public adapter source `5c11288e436f41ae832ab6ac89e180f6cf00a43d`.
Two planar square orientations and a degenerate segment check literal center,
orientation, projected bounds, PSD radii and complete vertex inclusion after
every public call. The approximation policy independently admits exact
stored-binary64 containment. One excluded warmup and seven rotated 100-call
batches per case yielded 2,100 verified measured calls with zero observed
failures. The labelled 2D SVG and example page are regenerated from the same
saved records. These are descriptive single-adapter durations; no competitor,
speedup, source-mapped limiter, finite approximation error bound, validated
prior rounding, MATLAB or ET comparison is supported. Independent saved-result
review, main-only Pages deployment and live-byte verification remain gates.

## EXT-05 continuous affine discretization

Issue [EXT-05 #54](https://github.com/butahlecoq/controlled-systems-lab/issues/54)
has a saved [two-state double-integrator bundle](../../reports/algorithm-results/ext05-discretization-a40ba9647cc023dc/)
from frozen source `6cc1740a59ca95e4a575e921cef793c2ac262e9f`.
The public adapter integrates two unequal physical intervals under zero-order
hold. Each call checks the complete analytic transition matrices and the
`(0,0) → (1,2) → (3,0)` state trajectory. The 2D figure draws the exact
within-interval quadratic paths and marks sampled grid states. The capture
retains clean source, build, host and executable receipts, an excluded 100-call
warmup and seven measured 100-call batches. All 700 measured calls passed
their literals with zero observed failures. Batch duration includes fixture
construction, conversion, snapshot, two state steps and checks; it excludes
CSV output and rendering. These are descriptive single-adapter observations
on one host, with no comparator, speedup or source-mapped limiter. The RK4
step-doubling local estimate is not a certified global error bound.
Independent saved-result review, main-only deployment and live-byte
verification remain publication gates.

## EXP-04 independent nonlinear plant replay

Issue [EXP-04 #56](https://github.com/butahlecoq/controlled-systems-lab/issues/56)
has a saved [analytic replay bundle](../../reports/algorithm-results/exp04-replay-93fe3b87795e1d3a/)
from frozen numerical source `eb4497e08f1532c732163e677d5d7aa03697c7de`.
It retains four declared scalar/two-state control histories, literal full-path
and objective checks, one excluded 1,000-call warmup per case and seven
rotated measured 1,000-call batches per case. The 28,000 measured public replay
calls completed with zero recorded failures. The HTML includes a labelled
two-dimensional state trajectory, raw input and result links, host/build
provenance, clean source receipts, raw build logs and an offline bundle. These are exploratory, descriptive
single-adapter durations. No speedup, source-mapped limiter, nonlinear
optimality, B04 reconstruction or validated rounding claim is supported.
Independent saved-result review, main-only Pages deployment and live byte
verification remain gates before issue closure.

## Reference-LP pipeline

The [report-record contract](../contracts/algorithm-report-records.md) specifies the executable, saved schemas, exact timing scopes, independent literals, build/environment provenance, commands and OBS migration. `csl_lp_report --smoke` is a bounded functional test. Accepted seven-trial measurements and the separate counter profile follow review of a fixed clean Release code commit; their source identity is distinct from the later artifact commit.

Collection, plotting, rendering and static staging are separate commands under `scripts/reports`. Regenerate a reviewed bundle from saved `records.json` without rerunning the solver. Keep all failures and unavailable fields, inspect actual figures/pages, and retain raw JSONL, JSON/CSV, profile/build evidence and exact-byte manifests. Bundles live under `reports/algorithm-results/<report-id>/`, with a catalogue/index and adjacent offline ZIP. Destinations are immutable, and only allowlisted reviewed files enter the main-only Pages deployment workflow. The actual deployed versioned URL and downloads must be verified before algorithm-report completion is claimed.

## OPT-12 workspace-local cross-query basis reuse

Issue [OPT-12 #46](https://github.com/butahlecoq/controlled-systems-lab/issues/46) measures the optional HiGHS workspace-local warm-start path from source commit `7b732a53716ce963af83095fd2aeca8a681b76c4`. The native bundle [`opt12-7b732a53716c`](../../reports/algorithm-results/opt12-7b732a53716c/) retains 42 verified paired rows across three synthetic LPs and seven alternating repetitions per side. On the 100,000-column transfer-cost fixture, median aggregate native work is 35.7031 ms cold and 37.7611 ms warm; the ranges overlap (33.3761–41.2337 ms cold and 34.7062–45.2157 ms warm). A separate PDB-enabled Release CPU profile resolves the dominant sampled path through `LPWorkspace::solve`, the HiGHS LP workspace, and `Highs::run`; its diagnostic trace is excluded from timings and does not attribute the measured cold/warm latency difference. Performance interpretation remains inconclusive. The measurement does not establish that warm reuse is slower, a general speedup, or a worst-case complexity change.

The timing workload is criterion 3 evidence only. The implementation contract tests in [`tests/contract/lp/highs_tests.cpp`](../../tests/contract/lp/highs_tests.cpp) cover optional activation, workspace isolation, row and column dimension invalidation, coefficient and bound changes, degenerate bases, rejected hints, cold retries, and independently checked cold/warm results for supported cases. The report is registered through the schema-3 catalogue/site adapter; publication remains pending until the main-only Pages deployment and live URL/download hashes are verified.

## SYN-04 registered Strategy B T-S01 report

`SYN-04 #213` is a separate result bundle for the integrated public StrategyPort
path `csl.synthesis.strategy-b` on the exact T-S01 profile. It builds the pinned
clean algorithm commit and executes through `StrategyRegistry` with the
registered production HiGHS LP and convex providers. A successful trial must
return a registry-verified `CompleteOptimalFamily` accepted by the registered
`csl.verifier.ts01-analytic` verifier, and check the canonical T-S01
H-relation and exact membership examples inside the timed interval. The request
declares `Assurance::numerical`; completeness applies only to the exact profile
and does not imply generic strategy coverage or validated arithmetic.

Use `reports/algorithm-results/tooling/syn04/collect.py` and
`build_bundle.py`, then register the typed report with
`syn04_strategy_b_registered_reports.py` in the schema-3 catalogue/site flow.
Retain JSONL/CSV observations, scenario, host/build/profile evidence and all
unavailable submodule counters. The profile is a separate non-reported run.
Without an observed, source-mapped limiter, report exploratory observations
with an inconclusive performance conclusion. This report is one strategy only,
has no comparator or speedup claim, and does not close SYN-04 issue #67. It does
not replace the distinct `csl.synthesis.ts01-analytic` measurement in SYN-07.

## OPT-10 smooth-convex feasible-directions report

The OPT-10 report uses frozen source
`9becda80d9a0eb7383fa2215f6b5c1932d3502a0` and a clean Release
capture of the public feasible-directions adapter with the production HiGHS
projection backend. Its two-dimensional box quadratic has the analytic
constrained solution `(1, -1)` and objective `1`. Every observed call checks
that literal result. The saved raw rows, source and build receipts, manifest,
offline ZIP, and illustrative two-dimensional figure are catalogued for
main-only Pages staging. See the [reproduction notes](../../scripts/reports/opt10/README.md).

The seven batches are descriptive single-adapter observations. They have no
comparator, speedup, or global-optimality certificate. Main-only deployment
and live URL byte verification are separate publication gates.

## Issue 4 candidate Volterra enclosure

The [saved candidate certificate](../../reports/algorithm-results/issue4-volterra-7dce05b47c50c27a/)
uses frozen checker source `9286b5ffa9313650ceea0fc033c1410395db22fe`.
It records outward-rounded integer boxes for all 60 stages and a labelled 2D
terminal-error illustration. Under identical control histories in the
candidate's control-only corrected-coordinate recurrences, the terminal
`L∞` difference is at most `11.384829795848264`. This is an analytic
certificate for the stated discrete candidate, not a measured algorithm
report or a reconstruction of L05 Table 1. It makes no runtime claim. The
[research note](../research/issue4-volterra-enclosure.md) gives the derivation
and historical limits. Independent scientific review, main-only Pages
deployment and live URL verification remain gates; issue #4 stays open.

## SYN-04 registered Strategy B T-S02 report

Issue #238 adds separate evidence for PR #237's merged exact constant-objective
profile. Its clean solver source is `e7f66a9ee698d05ed8779621116319158fa70158`;
its standalone harness uses StrategyRegistry with registered production providers.
Every warmup/trial checks the registry-verified exact H-relation, [3,3] bounds,
and two distinct feasible histories with equal terminal state. The production
T-S02 branch constructs the full feasible relation analytically and invokes no
native LP/QP solve; the report describes the whole public path explicitly.

The additive `tooling/syn04_ts02` collection/bundle commands and
`syn04_ts02_registered_reports.py` adapter retain schema-3 publication envelopes,
exact-byte raw/build/profile evidence and deterministic offline ZIPs. The seven
observations are exploratory single-profile evidence with an inconclusive
performance conclusion and no speedup claim. Existing T-S01 bytes are unchanged.
Main-only deployment and live URL verification remain separate gates; #67 stays
open. See the [reproduction notes](../../reports/algorithm-results/tooling/syn04_ts02/README.md).

## SYN-03 registered Strategy A T-S02 report

Issue #240 records the separate registered Strategy A T-S02 profile from exact
solver source `272fb9a51c40dedeb20dfcb1ea11dfc6b694edd7` (PR #239). Its public
StrategyRegistry harness uses Strategy A and the production projection,
affine-sum, Qhull conversion, HiGHS LP/convex and hull-membership providers.
Every execution checks the registry-verified complete family, literal canonical
five-coordinate feasible-history H-relation, objective bounds `[3,3]`, all four
control-box corners, and distinct histories with the same terminal state. The
single-profile observations are exploratory, with no comparator or speedup
claim. Native submodule counters and timings are retained as unavailable where
the runtime does not expose them. See the [reproduction notes](../../reports/algorithm-results/tooling/syn03_ts02/README.md).
Publication through main-only Pages and live URL verification remain separate
gates; SYN-03 #66 remains open.
