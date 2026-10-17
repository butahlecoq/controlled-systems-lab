# Reconciled comparison program (owner review draft)

Status: review draft for Wayfinder #390/#405. This document and proposed backlog are not approved for publication or implementation scope until the owner reviews them. Research audit dossiers are in `docs/research/comparison-*.md` and linked from issues #391–#398.

## Purpose and evidence boundary

Build a reproducible, staged comparison program across archived methods and the current controlled-systems-lab architecture. Historical published values remain immutable and retain their historical labels. New runs use corrected-track labels and disclose every port deviation. Missing historical inputs mean a synthetic fixture is a new experiment, never a reproduction. Archive files remain local and are not redistributed. Decision details: [fixture ladder #399](https://github.com/butahlecoq/controlled-systems-lab/issues/399), [old-side fairness #400](https://github.com/butahlecoq/controlled-systems-lab/issues/400).

The comparison harness must preserve failures, refusals, timeouts, unsupported cases, and incomplete evidence. Quality is decided by independent properties such as containment, inclusion, feasibility, or literal expected outputs as appropriate; volume alone is never a correctness oracle. Timing uses tuned Release builds, alternating sides for at least five repetitions, reports median and range, and retains a separate limiter profile. Historical values are not remeasured modern results. See `docs/architecture/published-algorithm-results.md` and [#398](https://github.com/butahlecoq/controlled-systems-lab/issues/398).

## First-stage matrix and order

| Stage | Family and cases | First-stage scope | Current gap / evidence |
|---|---|---|---|
| Parallel 1 | Convex hull / vertex finding | LP and basis-reuse reducers, ordered reduction, 2D geometric QuickHull; dimensions 2, 3, 4, 8, 16 | Recovered historical inputs are incomplete; modern family implementations exist, broad old-side ports and comparison evidence do not. See [#391](https://github.com/butahlecoq/controlled-systems-lab/issues/391) and [#399](https://github.com/butahlecoq/controlled-systems-lab/issues/399). |
| Parallel 1 | V/H conversion | Bounded binary64 H/V conversion only; retain explicit unsupported/refusal rows | Current Qhull adapter is bounded. Rays and unbounded inputs are excluded until a second usable side and independent round-trip/containment fixtures exist. Reconcile GEO-03 wording first. See [#391](https://github.com/butahlecoq/controlled-systems-lab/issues/391) and [#403](https://github.com/butahlecoq/controlled-systems-lab/issues/403). |
| Parallel 1 | Optimization methods | Reproducible archived LP/simplex, projection, QP and recovery methods only where inputs and modern counterpart permit a fair case | Projection parity and exact historical arrays remain gaps; candidate mappings are in [#396](https://github.com/butahlecoq/controlled-systems-lab/issues/396). |
| Stage 2 | Set approximation | Exact and approximation adapters with independent inner/outer inclusion evidence | General production approximation producers and nontrivial inclusion evidence remain incomplete. See [#393](https://github.com/butahlecoq/controlled-systems-lab/issues/393). |
| Stage 3 | Terminal control / reachability | Strict polytopes and approximation tracks; with and without state constraints, only when paired inputs and quality oracles are available | Current modern evidence is narrow and does not reproduce the archived strict-polytope claims. Recovered B04 variant is not a canonical reproduction. See [#392](https://github.com/butahlecoq/controlled-systems-lab/issues/392). |
| Stage 4 | Fixed-plan minimax | Finite action and disturbance catalogues, action sequence selected before disturbance (`exists u, for all w`), including supported state constraints | Matches the current finite-catalog oracle and comparable B06–B09 artifacts. Unsupported requests stay in the record. See [#394](https://github.com/butahlecoq/controlled-systems-lab/issues/394) and [#404](https://github.com/butahlecoq/controlled-systems-lab/issues/404). |
| Later, gated | Adaptive/observation-based control | Only after issue #5 settles the information pattern and policy guarantee; observation timing must be explicit | Replanning is not globally optimal causal synthesis. Observation/replay components do not establish a general estimator or robust feedback optimizer. See [#395](https://github.com/butahlecoq/controlled-systems-lab/issues/395), [#397](https://github.com/butahlecoq/controlled-systems-lab/issues/397), [#404](https://github.com/butahlecoq/controlled-systems-lab/issues/404), and issue #5. |

For the shared geometric ladder, use deterministic Halton clouds with 250, 1,000, and 5,000 points in the unit box; add simplex-plus-interior and affine-rank-deficient fixtures containing duplicate and boundary points. Pin the generator/version and hash each input. These are synthetic fixtures, not recovered B03 Normal/Uniform/Sphere samples. Horizon and model cases should use recoverable canonical archived inputs first; no historical horizon is invented where source arrays are absent. [#399](https://github.com/butahlecoq/controlled-systems-lab/issues/399) settles dimensions and point counts; family dossiers identify source-specific limits.

## Old-side policy and task generality

Transcribe MATLAB, Python 2, and Pascal methods into Python 3 by default. Use C++ only when a fair common-runtime comparison or integration requires it; run native originals where inexpensive, including Free Pascal when available. Put each authorized port in `tools/legacy-ports/<artifact-id>/` with provenance, source identity, and adjacent `DEVIATIONS.md`. Accept a port only with reproducible inputs and an independent quality oracle. Artifacts blocked by unrecovered inputs (#2/#10) do not block other ports; omit historical comparison claims for those cases until recovery succeeds. [#400](https://github.com/butahlecoq/controlled-systems-lab/issues/400).

Demonstrate task generality with a two-state double integrator (position, velocity, scalar acceleration), horizon 3, convex box constraints on acceleration and intermediate state, and a quadratic terminal tracking objective. Run it through the same resolve/prepare/execute/report path and label it as a generality demonstration, not a historical comparison. Linearization around a reference trajectory remains future adapter work. [#401](https://github.com/butahlecoq/controlled-systems-lab/issues/401).

## Result contract

Paired results use a separate content-addressed `csl.comparison-record/1`, keyed by `ComparisonSpecId` and unique `ComparisonRunId`. Store a shared input-manifest hash, immutable `RunRecordRef` per side and attempt, historical/corrected track label, deviations, quality evidence, and explicit success, refusal, unsupported, failure, or timeout status. Retain every attempt. HTML is rendered from the immutable comparison record and is not itself the evidence source. The codec, matched-input/replay validation, failure retention, and renderer integration are backlog work, not existing capability. [#402](https://github.com/butahlecoq/controlled-systems-lab/issues/402).

No comparison-level speed or quality winner is claimed until both sides use matched inputs and their applicable independent oracle passes. Report inconclusive outcomes where evidence or timing cannot support a winner. Reproduction claims require recovered historical inputs and documented correspondence; a similar problem statement is insufficient.

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

Before applying this proposed delta, reconcile exact ownership, dependencies, labels and existing duplicate tickets against the live 183-edge issue graph. The current architecture has real narrow composition seams but not an architecture-wide substitution sweep; preserve that distinction. Audit evidence: [#397](https://github.com/butahlecoq/controlled-systems-lab/issues/397).

## Explicit exclusions and gates

- No reproduction claim for B03 or other artifacts without recovered arrays, seeds, and source correspondence.
- No ray/unbounded V/H parity in the first stage.
- No adaptive minimax or globally optimal causal feedback claim before issue #5 closes.
- No continuous-action minimax in the initial finite-catalog stage.
- No linearization or nonlinear-model comparison in this map.
- No redistribution of archive source code.
- The owner must review this summary and the final live backlog diff before the spec is published or issues are created/edited, as required by [#405](https://github.com/butahlecoq/controlled-systems-lab/issues/405).
