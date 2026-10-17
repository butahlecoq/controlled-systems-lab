# Reconciled comparison program (owner review draft)

Status: review draft for Wayfinder #390/#405. This document and proposed backlog are not approved for publication or implementation scope until the owner reviews them. Research audit dossiers are in `docs/research/comparison-*.md` and linked from issues #391–#398.

## Purpose and evidence boundary

Build a reproducible, staged comparison program across archived methods and the current controlled-systems-lab architecture. Historical published values remain immutable and retain their historical labels. New runs use corrected-track labels and disclose every port deviation. Missing historical inputs mean a synthetic fixture is a new experiment, never a reproduction. Archive files remain local and are not redistributed. Decision details: [fixture ladder #399](https://github.com/butahlecoq/controlled-systems-lab/issues/399), [old-side fairness #400](https://github.com/butahlecoq/controlled-systems-lab/issues/400).

The comparison harness must preserve failures, refusals, timeouts, unsupported cases, and incomplete evidence. Each execution has a 300 second wall-clock limit and 8 GiB resident-memory limit; record the configured limits, actual peak memory when available, elapsed time, and termination reason. A timeout or resource limit is an outcome row and never a missing sample. For hull fixtures, require unique in-range source indices and mutual convex-hull containment of the two returned vertex sets under an independent exact low-dimensional oracle. For bounded H/V fixtures, require bounded-form validity and mutual containment/round-trip checks with an independent polyhedral oracle. For optimization, independently check primal feasibility and objective against a pinned analytic or reference solution, with tolerances stated per fixture. For exact reachability/control, check expected feasibility and terminal/state-constraint properties; for approximation, prove the declared inclusion direction with a complete oracle, never sampled directions alone. Volume alone is never a correctness oracle. Timing uses tuned Release builds, alternating sides for at least five repetitions, reports median and range, and retains a separate limiter profile. Historical values are not remeasured modern results. See `docs/architecture/published-algorithm-results.md` and [#398](https://github.com/butahlecoq/controlled-systems-lab/issues/398).

## First-stage matrix and order

| Stage | Family and cases | First-stage scope | Current gap / evidence |
|---|---|---|---|
| Parallel 1 | Convex hull / vertex finding | LP and basis-reuse reducers, ordered reduction, 2D geometric QuickHull; dimensions 2, 3, 4, 8, 16 | Recovered historical inputs are incomplete; modern family implementations exist, broad old-side ports and comparison evidence do not. See [#391](https://github.com/butahlecoq/controlled-systems-lab/issues/391) and [#399](https://github.com/butahlecoq/controlled-systems-lab/issues/399). |
| Parallel 1 | V/H conversion | Bounded binary64 H/V conversion only; retain explicit unsupported/refusal rows | Current Qhull adapter is bounded. Rays and unbounded inputs are excluded until a second usable side and independent round-trip/containment fixtures exist. Reconcile GEO-03 wording first. See [#391](https://github.com/butahlecoq/controlled-systems-lab/issues/391) and [#403](https://github.com/butahlecoq/controlled-systems-lab/issues/403). |
| Parallel 1 | Optimization methods | Reproducible archived LP/simplex, projection, QP and recovery methods only where inputs and modern counterpart permit a fair case | Projection parity and exact historical arrays remain gaps; candidate mappings are in [#396](https://github.com/butahlecoq/controlled-systems-lab/issues/396). |
| Stage 2 | Set approximation | Comparison follows existing backlog: policies #24; box/parallelotope #33; zonotope enclosure #42; ellipsoidal #34; lazy support/materialization #52; comparison artifacts #99; independent contract tests #100. | These are prerequisites and existing tickets, not duplicate Wayfinder tickets. #100 explicitly depends on #32, #52, #33, #42, #34, and #99. Do not claim a comparative inclusion result until the relevant producer and complete independent inclusion oracle are delivered. See [#393](https://github.com/butahlecoq/controlled-systems-lab/issues/393). |
| Stage 3 | Terminal control / reachability | Strict polytopes and approximation tracks; with and without state constraints, only when paired inputs and quality oracles are available | Current modern evidence is narrow and does not reproduce the archived strict-polytope claims. Recovered B04 variant is not a canonical reproduction. See [#392](https://github.com/butahlecoq/controlled-systems-lab/issues/392). |
| Stage 4 | Fixed-plan minimax | Finite action and disturbance catalogues, action sequence selected before disturbance (`exists u, for all w`), including supported state constraints | Matches the current finite-catalog oracle and comparable B06–B09 artifacts. Unsupported requests stay in the record. See [#394](https://github.com/butahlecoq/controlled-systems-lab/issues/394) and [#404](https://github.com/butahlecoq/controlled-systems-lab/issues/404). |
| Later, gated | Adaptive/observation-based control | Only after issue #5 settles the information pattern and policy guarantee; observation timing must be explicit | Replanning is not globally optimal causal synthesis. Observation/replay components do not establish a general estimator or robust feedback optimizer. See [#395](https://github.com/butahlecoq/controlled-systems-lab/issues/395), [#397](https://github.com/butahlecoq/controlled-systems-lab/issues/397), [#404](https://github.com/butahlecoq/controlled-systems-lab/issues/404), and issue #5. |

For hull and V/H, use dimensions 3, 4, 8, and 16, plus dimension 2 for QuickHull parity. Use 250, 1,000, and 5,000 points per cloud. Generate deterministic Halton clouds in the unit box plus simplex-with-interior and affine-rank-deficient cases with duplicate and boundary points. Pin the generator implementation/version and use fixed seed 20261017 for any randomized fixture generation; Halton sequence index starts at 1 with scrambling disabled. Hash every input. These are synthetic fixtures, not recovered B03 Normal/Uniform/Sphere samples. For synthetic control families, use n in {2, 4, 8}; for the n=4 fuel reference use horizons T in {4, 8, 16}. Preserve recovered historical cases as separate fixtures even when outside this ladder. The selected non-fuel double-integrator demonstration is horizon 3 and is not a substitute for this control ladder. These scopes follow [#399](https://github.com/butahlecoq/controlled-systems-lab/issues/399); the seed and sequence policy are made concrete here for owner review.

## Old-side policy and task generality

Transcribe MATLAB, Python 2, and Pascal methods into Python 3 by default. Use C++ only when a fair common-runtime comparison or integration requires it; run native originals where inexpensive, including Free Pascal when available. Put each authorized port in `tools/legacy-ports/<artifact-id>/` with provenance, source identity, and adjacent `DEVIATIONS.md`. Accept a port only with reproducible inputs and an independent quality oracle. Artifacts blocked by unrecovered inputs (#2/#10) do not block other ports; omit historical comparison claims for those cases until recovery succeeds. [#400](https://github.com/butahlecoq/controlled-systems-lab/issues/400).

Demonstrate task generality with a two-state double integrator (position, velocity, scalar acceleration), horizon 3, convex box constraints on acceleration and intermediate state, and a quadratic terminal tracking objective. Run it through the same resolve/prepare/execute/report path and label it as a generality demonstration, not a historical comparison. Linearization around a reference trajectory remains future adapter work. [#401](https://github.com/butahlecoq/controlled-systems-lab/issues/401).

## Result contract

Paired results use a separate content-addressed `csl.comparison-record/1`, keyed by `ComparisonSpecId` and unique `ComparisonRunId`. Store a shared input-manifest hash, immutable `RunRecordRef` per side and attempt, historical/corrected track label, deviations, quality evidence, and explicit success, refusal, unsupported, failure, or timeout status. Each side reference must resolve to its artifact identity: legacy artifact/source hash, port/runtime identity and deviation-log hash; modern module/provider ID and version; plus effective configuration, build/runtime fairness metadata, repetition index, and limiter-profile reference. If an immutable run record cannot supply these values, they belong in the comparison record. Retain every attempt. HTML is rendered from the immutable comparison record and is not itself the evidence source. The codec, matched-input/replay validation, failure retention, and renderer integration are backlog work, not existing capability. [#402](https://github.com/butahlecoq/controlled-systems-lab/issues/402).

No comparison-level speed or quality winner is claimed until both sides use matched inputs and their applicable independent oracle passes. Report inconclusive outcomes where evidence or timing cannot support a winner. Reproduction claims require recovered historical inputs and documented correspondence; a similar problem statement is insufficient. Later set representations (hybrid zonotopes, polynomial zonotopes, ellipsotopes) are excluded from this first comparison program; revisit them only after general approximation producers and independent inclusion verifiers exist. The estimator and replanning loop is also excluded: EXT-04 observation semantics alone do not define an estimator, and replanning runs must not be presented as globally optimal causal synthesis. Any such work requires a separate contract and remains behind issue #5 where its information pattern applies.

## Proposed backlog changes for owner review

This list is a proposed delta to the existing ticket families, not yet created or edited in the tracker.

| Proposed ticket | Family | Depends on / scope |
|---|---|---|
| Build deterministic comparison fixture generator and content-hash manifest | INP / TEST | #399; Halton, simplex/interior, rank-deficient and duplicate/boundary cases; fixed ladder and pinned generator. |
| Port recoverable legacy hull and V/H methods with deviation records | GEO / EXP | #400; split by archived artifact, bounded V/H first; depends on input recovery and independent quality fixtures. |
| Reconcile GEO-03 ray/unbounded support statement with delivered contract | GEO | #403; documentation and tracker acceptance alignment. |
| Port recoverable optimization methods and add projection comparison seam | OPT / EXP | #396/#400; only methods with source correspondence and recoverable inputs. |
| Add paired comparison record v1 codec, replay validation, and failure retention | RUN / EXP | #402; immutable side references, shared input hash, track/deviation and outcome fields. |
| Render comparison records as reproducible HTML views | VIZ / RUN | Depends on record schema and renderer consuming saved data only. |
| Add strict-polytope reachability comparison fixtures and recovered B02/B04 tracks | SYN / EXT / INP | #392; separate recovered variants from historical reproduction, preserve refusal/failure rows. |
| Add finite-catalog fixed-plan minimax paired harness | EXT / EXP | #394/#404; do not imply adaptive-policy optimality. |
| Add double-integrator non-fuel scenario through the paired pipeline | INP / SYN / RUN | #401; generality demo only, with independent expected-result checks. |
| Gate observation/adaptive comparison on resolved information pattern | OBS / EXT | #5/#395/#404; no delivery claim before policy semantics and guarantee are resolved. |
| Add general substitution sweep after family contracts stabilize | EXP / REVIEW | #397; current paired application is profile-specific, so broaden only with capability and evidence review. |
| Add a horizon-ladder fixture manifest and scaling acceptance cases | INP / TEST | Use synthetic control family sizes n={2,4,8}; use n=4 fuel reference horizons T={4,8,16}. The non-fuel generality demo is T=3, separate from this ladder. |
| Add hybrid/polynomial zonotope comparisons | APP / GEO / EXP | Explicitly excluded from first-stage scope; future proposal only after #24/#33/#42/#34 and independent inclusion verification are delivered. No duplicate ticket created now. |
| Add ellipsotope comparisons | APP / EXP | #34 already covers ellipsoidal approximations; ellipsotopes remain distinct future scope and require a separate owner decision before ticket creation. |
| Specify estimator/replanning contracts and a separate observation study | OBS / EXT / REVIEW | Explicit future scope beyond EXT-04; do not create a duplicate before issue #5 resolves the information pattern and an estimator contract is specified. |

Before applying this proposed delta, reconcile exact ownership, dependencies, labels and existing duplicate tickets against the live 183-edge issue graph. The current architecture has real narrow composition seams but not an architecture-wide substitution sweep; preserve that distinction. Audit evidence: [#397](https://github.com/butahlecoq/controlled-systems-lab/issues/397).

## Explicit exclusions and gates

- No reproduction claim for B03 or other artifacts without recovered arrays, seeds, and source correspondence.
- No ray/unbounded V/H parity in the first stage.
- No adaptive minimax or globally optimal causal feedback claim before issue #5 closes.
- No continuous-action minimax in the initial finite-catalog stage.
- No linearization or nonlinear-model comparison in this map.
- No hybrid zonotope, polynomial zonotope, or ellipsotope comparisons in the first program; reconsider only after approximation producers and independent inclusion verifiers are available.
- No estimator/replanning-loop comparison in this map; that needs separate observation and estimator contracts, with issue #5 governing adaptive-policy semantics.
- No redistribution of archive source code.
- The owner must review this summary and the final live backlog diff before the spec is published or issues are created/edited, as required by [#405](https://github.com/butahlecoq/controlled-systems-lab/issues/405).

## Disposition of the map’s former “Not yet specified” items

1. Geometry fixture generators, sizes, seed and sequence policy, structural cases, resource caps, and per-family quality checks are stated above; the fixture-generator implementation remains backlog work.
2. The non-fuel task is the horizon-3 double integrator in #401; its role is a generality demonstration.
3. A second V/H converter is not required for bounded first-stage comparisons. Rays/unbounded inputs require a second usable side and independent round-trip/containment fixtures (#403).
4. The general substitution sweep belongs as an extension of existing EXP-02 #94 after its scope is reviewed; no duplicate is proposed.
5. Two-sided comparison evidence uses the new `csl.comparison-record/1` defined above (#402); schema and publication implementation remain backlog work.
6. Hybrid/polynomial zonotopes and ellipsotopes are excluded from this first program; reconsider only after existing approximation producers and independent inclusion evidence mature.
7. Adaptive minimax is gated by issue #5 and excluded from the first fixed-plan finite-catalog stage (#404).
8. Linearization-near-reference work is outside this map and requires its own nonlinear input, residual-bound, and validity contracts (#401/#397).
9. Estimator/replanning work is outside this map; EXT-04 observation semantics do not supply an estimator or prove globally optimal causal control (#395).

These dispositions replace the map’s stale “Not yet specified” bullets. They are proposed edits to #390 for owner review, not yet applied.
