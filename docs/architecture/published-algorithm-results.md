# Published algorithm results

The owner requires an English HTML report whenever an implemented algorithm can produce numerical results. Reports are deliverables of the algorithm work, not a feature deferred until the complete optimal-control application exists. [HTML-01 #123](../superpowers/plans/tickets/HTML-01.md) provides the initial report pipeline and first reference-LP report. Existing scientific and implementation acceptance criteria remain binding.

## Artifact and publication

Use saved, versioned records to render a standalone HTML page with numerical tables, suitable figures and measured performance. Publish an index and immutable report URLs through this repository's GitHub Pages site. The published index is a reading layer over the reviewed catalogue: it groups the reports by topic, states in plain language what each report measures, and repeats the scope and the evidence limits recorded with that report, its raw records and its source commit. It adds no claim that the report itself does not make, and every published report family needs a description there before it can appear. Keep the report, raw JSON/CSV and assets in version control, with a download path that remains useful offline. Link the actual published URL and source commit in each relevant PR and issue. Until a report is measured, reviewed and deployed, its URL and performance are pending rather than implied by passing tests.

Each report identifies algorithm/module/backend versions, code commit, scenario and input hashes, supported assumptions, expected analytic or sourced values, actual objectives/residuals/status and evidence scope. Distinguish historical published figures from new measurements. A solver witness is not a complete optimal relation. Failed, unsupported and cancelled runs retain their status and any available evidence.

## Measurements

Record hardware, OS, compiler and release settings; arithmetic/tolerances/seeds; requested and actual worker/native thread counts; cold/warm and workspace reuse policy. Specify precisely what each interval includes, with units and raw per-repetition data. Separate setup, solve, verification, end-to-end and rendering where measured. Name unavailable internal counters instead of guessing them. Nested or parallel durations cannot be summed as end-to-end latency. CTest runtime is test-harness time, not an algorithm benchmark.

Comparative performance claims require at least five alternating tuned repetitions per side, median/range, failures and a separate limiter profile, following [skill routing](../agents/skill-routing.md). Report inconclusive comparisons when the measurement does not support a winner. A first single-adapter report can report reproducible timings without an invented competitor or speedup. Check expected numerical outputs and that the work actually ran before accepting a timing record.

## Module boundaries and review

Keep execution, measurement collection, scientific saved records, HTML rendering and publication independently replaceable, outside solver logic. Future [OBS-04](../superpowers/plans/tickets/OBS-04.md), [OBS-05](../superpowers/plans/tickets/OBS-05.md) and [VIZ-03](../superpowers/plans/tickets/VIZ-03.md) extend the records/figures; they are not blockers for the first analytic LP report. The first small record must have an explicit migration path into those authoritative artifacts rather than a competing result schema.

Independent review checks mathematical/evidence labels, measurement validity and module boundaries. Verify raw-record/HTML consistency and regeneration, visually inspect the page, and open the deployed URL before claiming publication. The orchestrator publishes the reviewed artifact. Private historical source code and raw archives remain unchanged and are not copied into the report site.

## EXT-04 continuous affine policy evaluation

The saved [continuous-policy bundle](../../reports/algorithm-results/ext04-continuous-ebcf879d07ee9157/)
uses evaluator source `ebcf879d07ee91576a929becfc9b088b5453a327`. Its analytic
one-step fixture has a two-state initial square, a position-only observation,
one affine action and four supplied joint generators. Every measured call
checks the actual initial and terminal states, action, action safety margin and
numerical feasibility status for all four generators. One excluded 5,000-call
warmup and seven measured 5,000-call batches passed with no failures. Median
batch duration was 33,970,237 ns (range 33,093,233–37,847,996 ns), or 6,794.0 ns
per call at the median. The interval includes evaluator calls and literal
checks; fixture setup and JSONL serialization are excluded. Host load was not
controlled, and no separate limiter profile was collected. These are
descriptive single-adapter observations, with no comparator, speedup,
scalability, policy-synthesis or universal-disturbance claim. The report retains
raw outcomes, driver/renderer source, clean Release build log, standalone 2D
figure and offline ZIP. The custom publication catalogue and visual gallery
route are staged by the Pages workflow; deployment and live URL verification
remain pending. The earlier unregistered draft bundle
[`ext04-continuous-27d4ad2e12958609`](../../reports/algorithm-results/ext04-continuous-27d4ad2e12958609/)
is retained as historical evidence and is superseded by this bundle, which
records each batch's actual generator outcomes and full measurement metadata.

The joint H-domain policy evaluator bundle
[`ext04-h-policy-0c0a95116ce4642b`](../../reports/algorithm-results/ext04-h-policy-0c0a95116ce4642b/)
uses source commit `0c0a95116ce4642bd560d8f285b244e104aaa266`. Its analytic
one-step scalar fixture keeps the initial state and observation error coupled
by `e=0.1x0`, applies `u=-(x0+e)`, and checks six state/action support bounds
against their exact values. One excluded 100-call warmup and seven measured
100-call batches passed with no failures. Median batch duration was 76,114,922
ns (range 75,911,542–76,776,185 ns), or 761,149 ns per call at the median.
Each call performs one H-domain feasibility solve and six dual support LP solves;
the interval includes those calls and literal correlation, dual-residual,
support-bound and status checks. Fixture setup and JSON serialization are
excluded. The clean Release build used GCC 16.2.1, CMake 3.31.6, Ninja 1.12.1,
and HiGHS 1.11.0 on an 8-logical-CPU Ryzen 5 3550H host. The load average was
3.89/2.91/4.01 after the build; `perf` was unavailable, so a source-mapped
limiter was not measured. These are descriptive numerical observations for
one authored H-set and one LP adapter, not a speedup, universal uncertainty
guarantee, validated-arithmetic result, or policy-synthesis claim. Main-only
Pages publication and live URL/hash verification remain pending.
This bundle is historical relative to PR #785: the exact-witness checks added
there leave its former safe fixture inconclusive, so no current-source timing
is claimed and a new status-preserving measurement is pending. The archived
report, raw trials and ZIP remain unchanged.

The saved [affine-synthesis bundle](../../reports/algorithm-results/ext04-affine-synthesis-7eadf7c7ecbb2bbd/)
uses source commit `7eadf7c7ecbb2bbdc28683ebcdfc31849f01c133`. It synthesizes
one affine action from a pre-decision noisy observation for one two-state,
one-step fixture. The report independently checks all eight vertices of the
caller-authored joint initial-state/error V-hull against the plant equations,
action bounds, and terminal bounds. Its result is numerical binary64 feasibility
evidence; the joint hull's completeness is assumed, infeasibility is
inconclusive, and the returned policy is not cost-optimal. Seven 100-call batches
after one excluded warmup had no failures. Median duration was 481,762,806 ns
per batch (471,194,618–584,908,799 ns), or 4,817,628 ns per call at the median.
The Release build used GCC 16.2.1, CMake 3.31.6 and Ninja 1.12.1 on an 8-logical-
CPU Ryzen 5 3550H host; average load was 1.67, 0.99 and 0.90 before the run
(1/5/15 minutes). HiGHS and Qhull were disabled. This is one adapter and fixture,
with no comparative performance claim. The report retains the raw batches,
smoke output, environment capture, build log, figure, renderer source and
offline ZIP. Earlier development captures under source IDs `7f04289dfcdcb074`
and `71ef0bb0b379cee5` remain as immutable, unregistered evidence snapshots;
the current publication catalogue stages only the final report.

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
for that verifier. Its saved bundle remains in the repository as historical
evidence and is excluded from Pages publication because its build log is empty.
The earlier exact-verifier bundle
[`ext07-hybrid-two-parameter-26f402289a309403`](../../reports/algorithm-results/ext07-hybrid-two-parameter-26f402289a309403/)
remains in the repository as historical evidence and is excluded from Pages
publication because its build log is empty. The current
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

## ITIS17-informed hull reducer pilot

The exploratory [QuickHull/ITIS17 bundle](../../reports/algorithm-results/quickhull-it17-paper-adaptations-20261024-r1/)
uses source commit `7de5ad294ab8831ea3bcc2907f0355c602971d63` and compares
geometric QuickHull with five LP reducers on three exact-dyadic 2D clouds of
5–10 points. Seven interleaved measured calls per method/fixture pair and one
warmup per pair produced 126 measured and 18 warmup calls; all 144 passed the
independent bounded hull oracle. A43's certificate-safe basis adaptation had
per-fixture medians from 658,676 to 1,038,336 ns; A44's incremental LP
adaptation ranged from 944,399 to 1,466,116 ns. QuickHull medians ranged from
5,168 to 15,365 ns. The run has no source-mapped limiter profile or
representative workload, so the performance conclusion is inconclusive.
Neither new reducer is a faithful paper or Pascal port: A43 omits the paper's
per-candidate artificial-basis sequence and largest-norm tie rule; A44 records
one farthest-first interpretation of ambiguous ordering prose. Existing
OPT-06 and OPT-07 methods remain separately named related variants. No matching
Pascal source was found. The comparison does not complete EXP-02. The
[deployed versioned report](https://butahlecoq.github.io/controlled-systems-lab/quickhull-it17-paper-adaptations-20261024-r1/index.html)
and [offline bundle](https://butahlecoq.github.io/controlled-systems-lab/quickhull-it17-paper-adaptations-20261024-r1.zip)
use source commit `7de5ad294ab8831ea3bcc2907f0355c602971d63`. The live page
SHA-256 is `9bb9a9c7f8c9d317d457e7449c9271f1317a8843c5640f921bc051789581f058`;
the ZIP SHA-256 is `4690be18b48dd2e6ae33c75d46b2768163f9b5c54ff8cedd4875385077a0f5a0`.
The fetched page matched the reviewed HTML bytes, and its archive entries matched
the saved report bundle.

### ITIS17 A44 source-aligned follow-up

The next [EXP-02 pilot](../../reports/algorithm-results/exp02-it17-a44-paper-order-20261027-r2/)
implements the paper's k+1 farthest-point seed and normalized Euclidean
ordering as csl.hull.itis17.a44-incremental-lp@2.0.0. It records the paper's
conflicting ordering sentences and uses the interpretation that the seed points
are farthest from the box center. The v1 adaptation and its historical rows
remain unchanged. Five interleaved measurements on each of deterministic
64-point and 256-point exact-dyadic 2D square clouds yielded 10/10 passing A44
attempts; QuickHull and OPT-06 basis reuse also passed 10/10. The baseline,
OPT-07 ordered method and A43 adaptation failed their completion checks in all
30 measured attempts; their diagnostic elapsed times are excluded from timing summaries.
A44 medians were 7,132,748 ns (range 7,091,960–8,192,390) and 27,746,596 ns
(range 27,538,118–29,705,244); QuickHull medians were 157,284 ns and 548,399 ns,
and basis-reuse medians were 223,494 ns and 780,553 ns at the corresponding
sizes. The measured clean source commit is `ec7d183842d8725d10276dee8b8689ee5313448e`.
A separate profile observed one-core saturation, but no source-function
profile was available; LP workspace construction is excluded. The result is
therefore exploratory and performance-inconclusive. The saved report includes
the 2D input geometry, all 72 warmup/measured rows, failed-attempt diagnostics,
source/build identities and checksums. Pages publication and live URL/hash
verification completed after PR #747 merged as `444c0ee08497e79e740c06f6cdcb1a6c4a144396`.
The [deployed report](https://butahlecoq.github.io/controlled-systems-lab/exp02-it17-a44-paper-order-20261027-r2/index.html)
has SHA-256 `1da8dc942527df3f275e294b7df38e802cbd04745be8cf936dd8614c056d200b`;
the [offline bundle](https://butahlecoq.github.io/controlled-systems-lab/exp02-it17-a44-paper-order-20261027-r2.zip)
has SHA-256 `69a37d193fa3723059aaa0cdb684434d349b5b6f3e1b5eecaa92419302391ca0`.
All 17 deployed report files match the saved `SHA256SUMS`, every corresponding
ZIP entry matches, and the live landing page links to the report. This remains
partial EXP-02 evidence; issue #94 remains open for its paired strategy, full
workload/resource matrix and comparison-record requirements.

### EXP-06 A43/A44 paper-derived follow-up

The [r3 bundle](../../reports/algorithm-results/exp06-it17-paper-reducers-20261029-r3/)
uses `csl.hull.itis17.a44-paper-farthest-incremental-lp@1.0.0` and counts all
A43 candidate solves plus final rechecks. Source commit is
`1f34503eb3f5d4c3e239076a8d48b2af2e6bf06c`. All 36 attempts (six methods,
one warmup and five measured runs each) completed, and the saved renderer
rechecked every result with the exact 2D hull oracle. Median durations and
ranges in ns were: A29/A30 Python 4,672,975 (3,610,192–5,255,315); QuickHull
47,423 (36,737–48,051); A43 certified-basis adaptation 2,884,746
(1,674,806–3,332,710); A43 artificial-basis 3,200,431
(1,229,565–3,246,386); A43 largest-norm tie 3,152,379
(1,204,073–3,269,015); A44 paper-farthest incremental LP 4,201,054
(2,936,707–4,287,727). These intervals differ by implementation/runtime and
exclude exact checking, so the values are descriptive and do not rank speed.
The largest-norm tie rule activated once in each attempt; the A43 batch-removal
counter stayed at zero, so this fixture does not demonstrate that path. The
initial r1 and corrected r2 bundles remain unchanged as superseded historical
evidence; r2 used source commit
`b2b7dfa6a2151259cbe1cd3d0e6d99e790661533`.

### ITIS17 hull output-status update

The [r3 output-status report](../../reports/algorithm-results/exp02-it17-a44-paper-order-20261028-r3/)
uses schema version 3 for exploratory hull rows. The `passed` field means
complete source-index accounting plus independent exact hull verification; it
does not fail solely because an LP reducer retained unresolved redundant
points. `reducer_status_complete` records whether an LP reducer returned
`ReductionStatus::complete`; it does not certify that retained points are all
extreme vertices. QuickHull has no such status and is marked not applicable.
This preserves reducer status separately from geometric validity and output
size.

All 60 measured attempts passed the exact 2D hull checker over 64- and
256-point exact-dyadic square clouds. The LP baseline, ordered reducer and A43
adaptation reported incomplete `ReductionStatus` in all 10 attempts each;
basis reuse and A44 v2 reported complete status. QuickHull has no
`ReductionStatus`. Median reducer-call times at 64/256 points were 0.142/0.572
ms for QuickHull, 0.225/0.756 ms for basis reuse, 5.337/25.306 ms for A43,
7.112/28.176 ms for A44 v2, 10.252/69.935 ms for the baseline, and
10.302/69.555 ms for ordered LP. Timing excludes workspace creation and
verification. `perf` was unavailable, and no resource limiter or
source-function profile was available, so these are fixture-specific
descriptive values and the performance conclusion remains inconclusive.

The versioned HTML page, raw attempts, summary table, fixture figure, executable
identity and offline ZIP are staged in the bundle. The deployed URL and live
hash verification remain pending the main-only Pages deployment for this PR.
This is still a partial hull-method slice; #94 remains open for its broader
strategy, workload and representation matrix.

### 250-point dyadic continuation

The [250-point bundle](../../reports/algorithm-results/exp02-it17-dyadic-250-20261029-r1/)
adds a single deterministic 2D square cloud to the QuickHull/ITIS17-related
comparison. Six methods each have one warmup and seven interleaved measured
calls. All 48 attempts passed accounting, expected-corner retention, and the
independent bounded exact-binary64 hull check. The result separates hull
validity from LP reducer completion; the baseline, ordered LP method, and A43
adaptation retained redundant inputs and reported incomplete status.

The median public-call times range from 0.535 ms for QuickHull and 0.746 ms for
basis reuse to 67.116 ms for the LP baseline; they are descriptive for this one
fixture. No source-function profile was available (`perf`/`strace` absent), so
the comparison remains inconclusive and makes no performance-winner or scale
claim. The bundle retains the raw checker status/budget, 250-point fixture
plot, source/build identity, and offline-staging inputs. Pages publication and
live URL/hash verification remain pending; issue #94 remains open.

## EXP-02 paired synthesis profile slice

The [paired T-S02/T-S03 report](../../reports/algorithm-results/exp02-paired-profiles-20261027-r1/)
adds five alternating Release repetitions for reach-back and Strategy B on two
exact profiles, retaining one excluded warmup pair, all JSONL events, process
output, scenario/executable identities and checksums. Every measured attempt
completed its family checks and independently verified two distinct witnesses.
The medians were 5,345,407 ns vs 567,883 ns for T-S02 and 4,741,277 ns vs
1,249,958 ns for T-S03. These are descriptive observations only: pre-run load
was not recorded and no source profiler was available, so the limiter and
performance conclusion remain unknown. The report includes analytical 2D
control-family projections. This does not complete EXP-02 #94, which remains
open for the broader substitution and workload matrix.

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

## Issue #3 validated finite-action minimax report

The first validated-API measurement is saved in
[`issue3-validated-minimax-20261023-r1`](../../reports/algorithm-results/issue3-validated-minimax-20261023-r1/).
It measures three fixed fixtures with seven batches after one excluded warmup:
the 2D analytic residual case, one infeasible plan and the displayed-data B08
catalogue. The B08 capture checks 625 plans and 160,000 disturbance histories;
its returned bounds are `67.15060110132285` and `67.15060110146638`. This uses
the exact-real interpretation of saved binary64 inputs and is distinct from
the printed-decimal rational audit. On the captured GCC 16.2.1 Release host,
median batch times were 435,462 ns (418,910–458,161) for the analytic fixture,
139,125 ns (133,468–142,268) for the infeasible case, and 561,272,221 ns
(554,351,976–563,596,504) for B08. Other interactive processes were present;
no limiter profile was collected. These are descriptive timings with no
comparator, speedup, per-call latency or scalability claim. The report and raw
records are registered in the schema-3 catalogue and the site generator
validates the saved bundle. Main-only Pages publication and live URL/download
verification remain pending.

## Issue #6 owner-confirmed B06 reference

### Scenario-manifest erratum

The immutable B06 capture at source report
[`b06-owner-confirmed-7df01ba3af5e4c46`](../../reports/algorithm-results/b06-owner-confirmed-7df01ba3af5e4c46/)
contains a 15-entry `A_row_major` array despite declaring a 4-by-4 matrix. The
measured driver at source commit `7df01ba3af5e4c46e867e2d737aca56a8f2461af`
hardcodes the complete final row `[0, 0, -2, 1]`; the independent integer
oracle uses `x4_next = x4 - 2*x3`. The corrected canonical scenario inserts the
source-supported zero at row 4, column 2. No solver was rerun. The correction
companion retains the original scenario, report bytes, hashes, ZIP and public
report ID, and records why the existing measurements may be associated with
the hardcoded model while preserving their binary64 numerical-assurance limit.
It also carries the saved 4D terminal geometry projections into flow and stock
views for visual context. The [versioned manifest correction and corrected
scenario](https://butahlecoq.github.io/controlled-systems-lab/issue6-b06-manifest-correction-abbcd7aaf4ce35b7d08d332386516cc16f7b6757d69524beab8ba8244b504e5c/index.html)
is live on Pages; its report, original capture and source snapshot hashes were
verified after deployment.

The native bundle
[`b06-owner-confirmed-7df01ba3af5e4c46`](../../reports/algorithm-results/b06-owner-confirmed-7df01ba3af5e4c46/)
records a five-stage, four-state finite-action minimax reference based on the
displayed L09 model and the owner's later `[-1,1]^2` disturbance decision. The
paper does not print that numerical disturbance set, so this is a distinct
reference rather than a reproduction of its reported `10.11`. An independent
integer-scaled oracle exhausts 3,125 plans and 1,024 corner histories per plan;
it finds the unique printed plan `(-0.3, 1, 0, 0, 0.3)` with exact squared
objective `1100939049/9000000` (norm `11.060133859949435`). The solver path
reports binary64 numerical assurance. Seven measured Release calls follow one
excluded warmup; median is 1,196,536,901 ns (range 1,188,696,999–1,253,915,262)
with no comparator, speedup claim or limiter profile. The saved report includes
raw runs, exact oracle, build provenance and terminal vertices. Its
[standalone 2D example](../../reports/algorithm-results/b06-owner-confirmed-7df01ba3af5e4c46/example-2d.html)
and saved-figure gallery card show the flow projection and the zero
stock-balance target outside the computed projection. The schema-3 route is
`issue6-b06-reference-761bdc6e40b93814f873f105313d1eed4f63711653aa583a16a2ddfbc67c2a82`;
main-only deployment and live URL/download verification remain pending. This
partial result does not resolve canonical B04 inputs or the remaining B07/B08/B09
historical questions in issue #6.

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

## SYN-04 registered Strategy B T-S03 report

The [T-S03 report bundle](../../reports/algorithm-results/syn04-strategy-b-ts03-20261022-2c0c9210/)
uses solver source `2c0c92107acd1cfc2f7e6d359e030d0bc47fb98e` and clean report
harness `f95f1545d2e16fa61d6d506de2cc30d8168e724f`. It covers the exact
singular-integrator profile `x1=u0`, `x2=u1`, `u0,u1∈[0,1]`, with terminal cost
`(x2-1)^2`. Every warmup and trial checked the complete optimal-history relation
`(x0,x1,x2,u0,u1)=(0,s,1,s,1)`, `0≤s≤1`, objective bounds `[0,0]`, and two
distinct histories with the same terminal state. Completeness is numerical and
restricted to this registered profile.

The seven measured public-path observations have median `1,038,900 ns`
(`1.0389 ms`) and range `935,500–1,088,900 ns`; all seven passed and no trial
was dropped. The interval includes problem resolution, provider selection,
StrategyRegistry preparation, the StrategyPort run and QP solve, optimal-level
extraction, and the compiled verifier. It excludes process startup, serialization,
build and rendering. This is one tiny single-profile measurement with no
comparator. The separate Windows CPU-stack profile could not start because the
host denied profiling permission; process counters did not map a limiter to
source. Performance interpretation is inconclusive, and the number supports no
speedup, application-scale or general Strategy B performance claim.

The [standalone HTML report](../../reports/algorithm-results/syn04-strategy-b-ts03-20261022-2c0c9210/index.html)
links the complete inputs, raw JSONL/CSV, build provenance, profile evidence and
labelled two-dimensional control projection. Reproduce with the
[T-S03 report commands](../../reports/algorithm-results/tooling/syn04_ts03/README.md).
Main-only Pages deployment and live URL/hash verification remain separate gates;
SYN-04 issue #67 stays open.

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

## EXT-03 temporal-memory transform microbenchmark

The [saved transform report](../../reports/algorithm-results/ext03-transform-20261024-a3a3af9/)
uses source commit `a3a3af9e1903d7a2a4be6116cc1669215c2bba1b`, GCC 16.2.1,
CMake 3.31.6, and a Release build. Seven measured batches of ten lift-and-
recovery calls followed one warmup batch; all 70 calls passed coordinate-map,
recovery, and original-constraint checks. Median elapsed time was 45.63 μs per
call, with a 43.15–56.91 μs range. This transformation microbenchmark does not
run a solver, identify a source-mapped limiter, compare methods, or support an
application-scale or scalability claim. The labelled control-plane figure is
an analytic illustration, not a solver trace. Publication remains subject to
main-only Pages deployment and live URL verification; EXT-03 #73 remains open.

## EXP-05 finite fixed-plan minimax comparison

The [versioned report bundle](../../reports/algorithm-results/exp05-fixed-plan-minimax-20261026-6c561462/)
compares the numerical and interval-validated finite-action solvers on one
bounded one-stage scalar fixture. The exhaustive independent oracle checks all
four fixed-plan/disturbance pairs, both stage constraints, and terminal costs.
Seven measured calls per arm passed, and the `csl.comparison-record/1` archive
retains all 14 run records, source/configuration identities, and the
`csl.comparison-spec/3` build/runtime manifest. Timings cover only solver calls;
one warmup per arm was excluded. They are exploratory, have overlapping ranges,
and establish no performance winner or scale claim. No separate limiter profile
was collected. The 2D plot is an explanatory state-stage projection, not a
solver trace. Review, catalogue registration, main-only Pages deployment and
live URL verification remain pending.

## ENV-717 TwoPoints finite-feedback report

The new [TwoPoints feedback bundle](../../reports/algorithm-results/env717-two-points-feedback-v1/)
keeps the source-attributed fixed-plan minimax record and adds an exact
scale-2000 finite graph for the three-stage action-before-disturbance vertex
game. CSL `finite_feedback::solve` selected the minimum terminal squared-gap
threshold `58,323,769 / 4,000,000` after 23 candidate solves. The independent
Python checker rebuilds all four stage catalogues, every rectangular transition
cell (including unsafe padding), threshold minimality, every winning bit and
admissible action, and the deterministic selector's worst-case path. Its
comparison against the source's ten binary64 Euler substeps found a maximum
coordinate discrepancy of `3.552713678800501e-15` under the declared `1e-10`
tolerance. The open-loop disturbance set remains a convex hull in the fixed-plan
result; the feedback guarantee applies only to the exact listed disturbance
vertices. The admissible actions are feasible and are not cost-ranked. This is
not continuous-state feedback or an RL reproduction. The original
`env717-two-points-pilot-v1` source bundle is unchanged. Both it and the new
feedback bundle are staged through distinct content-addressed routes with file
hashes and offline ZIPs; main-only Pages deployment and live URL/hash checks
remain pending.

## EXP-03 TwoPoints projected approximation pilot

The [EXP-03 pilot bundle](../../reports/algorithm-results/exp03-two-points-approx-pilot-v1/)
applies the registered exact hull, axis-box, rotated-parallelotope,
directional-ellipsoid, and zonotope axis-cover methods to the terminal
projected convex hulls of the existing three-stage TwoPoints finite game. It
retains the exact integer replay, all 345 terminal states, raw method outputs,
seven alternating single-call observations per method and projection, and an
independent dyadic inclusion check for both `(x1,x2)` and `(x3,x4)`. All four
outer methods contain every binary64 reference vertex in each projection. The
additional exact rational lattice check records point misses: QuickHull 1/2,
axis box 1/2, parallelotope 1/0, ellipsoid 0/0, and padded zonotope 0/0 across
the two planes. Thus the first three methods are not claimed to enclose the
exact lattice reference. The zonotope area ratio is `1.00000000047` in both
planes, but it retains all three active generators, so this is not a lossy
reduction result. The seven single-call timings are observations from one
host; they are descriptive only and do not support a speed ranking. The
standalone figure overlays each final projection on the forward game geometry,
marks backward-winning nodes, and outlines the terminal winning-node hulls,
alongside both trajectories. It does not separately project the coupled
terminal target. It makes no 4D inclusion claim and does not yet propagate
approximations through the reachability or minimax recursions. This pilot
supplies no inner reachable-set or objective-bound claims; EXP-03 remains open
for those acceptance items.
Independent saved-result review, main-only Pages deployment, and live URL and
hash checks remain pending.

## MPC-05 finite causal minimax pilot

The saved [MPC-05 causal tree report](../../reports/algorithm-results/mpc05-causal-tree-pilot-v2/)
uses algorithm source commit `353518447a5fb6b27bf3cac276485501ca1c8928`.
An independent exact Python checker reconstructs the finite TwoPoints transition
graph, re-planning selector, terminal costs, backward-winning layers and plotted
worst-case path. In the strict-gap fixture, fixed-plan value and the executed
fixed-plan re-planning selector's worst cost are both `2`, while the causal
Bellman value is `1`. For TwoPoints, fixed-plan, executed re-planning and causal
values coincide at `14.58094225`; its HiGHS full-tree model has 91 decision
occurrences, 729 leaves, an optimal bound matching its incumbent, and an
independently replayed worst cost. The standalone figure shows forward and
backward geometry in player phase planes `(x1,x2)` and `(x3,x4)`. This is a
three-stage finite adaptation of an upstream continuous-control RL task, with
no continuous-control, continuous-disturbance or performance claim. The stock
do-mpc multi-stage objective is a weighted scenario sum and its robust horizon
can truncate branching; the saved report records the required full-horizon
worst-leaf epigraph change and uses an explicit HiGHS extensive form. PR review,
main-only Pages publication and live URL/hash verification remain pending.

## ENV-717 MultiPointCostGame finite minimax pilot

The [MultiPointCostGame report](../../reports/algorithm-results/env717-multipoint-cost-game-pilot-v1/)
plots the complete four-stage forward reachable state catalogues in the
position–velocity plane, with one worst-case trajectory for the best fixed
open-loop plan and one for exact-state causal feedback. An independent Python
replay reconstructs all transitions, 81 fixed plans against 81 disturbance
sequences, and the full Bellman value/action table. The recorded values are
177.4852655588 (open-loop) and 21.5124275626 (feedback) for the finite terminal
cost game. The upstream RL environment also charges checkpoint costs at t=1 and
t=3; this pilot intentionally omits them and is explicitly terminal-only. It
therefore demonstrates the information-pattern effect on reachable states and
terminal minimax cost, not the upstream RL result, continuous feedback, or a
backward winning set. Timings use seven alternating solver-only calls after one
warmup per method; no speed claim is made. The report route and source hashes
are staged reproducibly; Pages publication and live URL verification remain
pending.
