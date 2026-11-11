# Current-intent architecture audit

Audit date: 2026-11-11. Source baseline: `ff451f74d90d70cd9dd228889fa77c181fc1fd26` in the isolated `research/current-intent-architecture-949` worktree. Scope: the current learning-book and three-environment single-player comparison program in #936. The audit did not build, run benchmarks, or generate scientific results.

The owner asked for an architecture review and GitHub tickets for distinct findings. This note records candidate scopes for root reconciliation. The visual report is `/tmp/architecture-review-20261111T061549Z.html`; `xdg-open` exited 0. Its static CSS diagrams remain readable without the CDN. It includes source links, before/after diagrams, recommendation badges, and the top program recommendation.

## Finding

The best new architecture candidate is a narrow shared admission path for fixed-plan propagation. Four representation-specific implementations repeat structural checks against `FixedPlanRequest`. A shared check could make those rules local and support cross-representation contract tests, while each implementation keeps its own mathematical admission, enclosure, approximation relation, and assurance behavior. This candidate is smaller than the existing controller program and does not change published evidence.

The top program priority remains the observed-state episode across the three environments. It is already owned by #941, #943, and #945. Do not create a duplicate ticket for it.

## Candidate for root to reconcile

### Localize shared fixed-plan request admission

**Strength:** Worth exploring. This is a concrete but bounded opportunity. It should receive a focused implementation ticket only if the owner wants the repeated request rules consolidated.

`FixedPlanRequest` carries the linear system, initial set, fixed controls, disturbances, admissible state sets, and request identity ([header](../../include/csl/reachability/fixed_plan_disturbance.hpp#L10)). The box, ellipsoid, parallelotope, and zonotope propagators each inspect the horizon vectors and safe-set profile before propagation ([box](../../src/reachability/finite_plan_box.cpp#L90), [ellipsoid](../../src/reachability/finite_plan_ellipsoid.cpp#L162), [parallelotope](../../src/reachability/finite_plan_parallelotope.cpp#L229), [zonotope](../../src/reachability/finite_plan_zonotope.cpp#L238)). The shared horizon and state-dimension checks recur, but the algorithms also have real differences. Parallelotope propagation is limited to a four-state frame. Zonotope propagation has a generator cap. Ellipsoid and box traces have their own outward-enclosure calculations. Those checks must remain local.

**Deletion test:** Deleting the shared structural checks would put the same horizon and safe-set facts back in each implementation. The shared request seam has multiple real adapters: `finite_plan_box` and `finite_plan_ellipsoid` are two; `finite_plan_parallelotope` and `finite_plan_zonotope` are additional implementations.

**Proposed ticket scope:** Consolidate only common request-structure checks across box, ellipsoid, parallelotope, and zonotope fixed-plan propagation. Preserve representation-specific supported profiles, enclosure math, relation and assurance labels, stop behavior, and outcomes. Add cross-representation tests for shared malformed requests, plus existing algorithm-specific checks for unsupported profiles and numerical behavior. Do not add a general set-operation abstraction or change any scientific guarantee.

**Existing issue comparison:** #943 owns reachable-set/MPC feedback composition across five representations. #944 owns wiring vertex LP/simplex, conversion, and optimizers into control pipelines. The live acceptance scopes do not assign shared fixed-plan request admission to either issue. Both remain open. #943 has native dependencies #941 and #942; #944 has #942. The candidate has no evident prerequisite because it changes only current fixed-plan request handling.

## Candidate to investigate before ticketing

### Reduce hull-reducer consumer knowledge

`HullReduction` combines common retained indices, attempts, LP-call counts, and removal certificates with seven optional metric families ([header](../../include/csl/geometry/hull_reducer.hpp#L129)). The public header registers the common `HullReducerPort` and exposes LP, recursive, ordered, grouped, and paper-derived reducer variants ([header](../../include/csl/geometry/hull_reducer.hpp#L152), [header](../../include/csl/geometry/hull_reducer.hpp#L165)). This is a growing shared result surface, but a source-only review does not establish that consumers have high churn or poor locality.

Do not replace the optional metrics with exclusive alternatives. The A43 safe adaptation can combine basis-reuse observations with A43-specific recheck observations. A useful ticket requires an inventory of actual consumer edits, preserved composition/nesting semantics, and a focused test-surface proposal. #944 already owns wiring these reducer choices into control pipelines. Keep this as a follow-up question, not a new ticket now.

## Four-group coverage

| Group | Source findings | Architecture judgment and issue ownership |
| --- | --- | --- |
| Vertex LP/simplex, including faithful legacy | The glossary distinguishes vertex redundancy from terminal optimization and requires exact dyadic removal evidence. `hull_reducer.hpp` keeps common removal certificates beside reducer-specific observations. The learning-book audit already separates source-faithful BTULSHOR, modern certified reducers, paper-derived adaptations, and QuickHull ([book audit](pages-learning-book-audit.md#group-1-lpsimplex-algorithms-for-vertex-extraction), [reducer contract](../../include/csl/geometry/hull_reducer.hpp#L110)). Recent history adds source-faithful BTULSHOR in `038b4264`. | No new algorithm or evidence refactor is justified here. Preserve legacy operation order and source status. #944 owns selectable reducer/provider wiring; #942 owns the admitted composition catalogue. Reducer reporting remains a consumer-audit candidate only. |
| Polytope, zonotope, parallelotope, ellipsoid, and box | The matrix audit says support is route-specific: polytope fixed-plan V propagation, general-dimensional box and zonotope enclosures, a four-state parallelotope profile, and axis-aligned ellipsoid traces. Their relations and limits differ ([program map](pages-learning-control-program.md#four-module-groups), [representation table](three-environment-closed-loop-matrix-audit.md#representation-support-is-route-specific)). Source checks show shared fixed-plan shape checks and distinct per-representation numerical checks. | Ticket only the narrow structural admission candidate above. Do not unify the enclosure algorithms or transfer guarantees between approximate representations. #943 owns feedback composition; #944 owns selected representation operation wiring. |
| Reachable-set-based and MPC closed-loop controllers | The matrix audit finds existing nonlinear feedback for synthetic Lotka and fuel, a restricted Earth-orbit block-plan pilot, and finite-action fixed-plan methods. It distinguishes applied observed-state feedback from open-loop tails, local NLP results, and global feedback claims ([matrix audit](three-environment-closed-loop-matrix-audit.md#finding-and-task-boundary), [MPC11 runner](../../benchmarks/reporting/mpc11/run_nmpc.py), [independent replay](../../src/simulation/nonlinear_replay.cpp)). | This is the top program priority, but already owned: #941 defines common task/model/replay adapters, #943 composes reachable-set and MPC controllers, and #945 runs initial closed-loop episodes. Do not post a duplicate ticket. |
| Supporting V↔H, set operations, and optimization | `GeometryOperation` and `ConversionRequest` record operation identity, set handles, representation, relation, and evidence; separate `GeometryPort` and `ConversionPort` seams have concrete geometry and converter implementations ([geometry contract](../../include/csl/geometry/contracts.hpp#L20), [registry ports](../../include/csl/registry/registry.hpp#L83)). Projection/materialization, generator conversion, affine sums, support, intersections, and registered LP/convex providers are exercised through provider selection and operation-specific admission. | The current seams are real and intentionally capability-scoped. The three-environment matrix already requires actual provider invocation and calls for `not_used` when a slot is bypassed. No extra generic operation algebra is justified. #944 owns wiring actual operations; #942 and #947 own admission and exhaustive execution evidence. |

## Ticket deduplication and dependencies

The live issue tracker was re-fetched on 2026-11-11. #936 and #938–#947 are open. #942 is assigned to `butahlecoq` and marked in progress. #943 is blocked by open #941 and #942. #944 is open and lists #942 as its native prerequisite. #945 and #946 remain open; #947 lists #943, #944, #945, #946, and #940. Do not treat the planning document as a second ticket ledger; GitHub issue state and dependencies remain authoritative.

The closed architecture tickets are adjacent but do not cover this fixed-plan source contract: #735 localizes report-kind policy, #736 gives educational examples ownership of scientific content, #737 owns validation-before-write for site additions, and #738 localizes hybrid producer path layout and joint-H admission. They concern publication, examples, staging, and hybrid report production, not request admission in the four fixed-plan propagation algorithms.

## Constraints

Preserve the actual project vocabulary in [the glossary](glossary.md) and decisions 0001–0004. In particular, do not conflate vertex LPs with terminal optimization; do not imply that an outer enclosure is exact; and do not upgrade solver residuals or samples into proof. Preserve immutable source records and published results. No benchmarks or numerical experiments were run for this audit.
