# Algorithm inventory for implementation tickets

Audit date: 2026-10-11. Read-only archival audit; no historical program executed and no product code changed. Public C++20 implementations should be independently written against explicit contracts rather than copied wholesale from these numerical scripts.

## Evidence roots and identifiers

- Original supplied-artifact register: [source map](source-map.md), identifiers L01–L31. Original root is recorded in `inventory.json`; extracted text is in `docs/research/extracted/Lxx.txt` (ignored; searched with `rg --no-ignore`).
- Larger archive root: `D:/work/PhD/PhD`. Existing A01–A23 paths/hashes are in `docs/research/archive-selected-sources.json`.
- Additional inspected sources have permanent IDs A24–A38 and SHA-256 hashes in the selected-source register. Paths below are relative to the larger archive unless prefixed otherwise.
- PDF pages below are physical PDF pages from the explicit `=== PDF page N ===` extraction markers; L03 is DOCX text, so use section references rather than fabricated page numbers.

## Main conclusion: multiple variants are evidenced, with different layers

There are at least three related LP hull strategies: independent phase-I membership checks; additional classification from a completed basis; ordered/grouped candidate filtering followed by final LP reduction. There is also a separate two-dimensional recursive Quickhull experiment. Calling all four “simplex variants” would conceal the difference between an LP pivot kernel, reuse of one solve's certificates, and a hull-level ordering/grouping algorithm.

The archive contains a concrete Zoutendijk-style procedure, `ZODENTEK`, inside A06 Pascal, beyond article references. It is specialized to Euclidean projection, not a recovered general-purpose smooth nonlinear optimizer. The current request for a C++20 interchangeable algorithm family is an owner-requested product direction; archival existence does not establish tested numerical robustness or a redistributable implementation.

## 1. Original professor-associated hull/phase-I procedure

Evidence:

- L01 `papers/1993 АиТ Алгоритм решения задачи терминального управления для ЛДС.pdf`, PDF p. 5: modified simplex for a linear feasibility problem; p. 8: control reconstruction through simplex. This is the mathematical lineage, not proof that one saved MATLAB file is exactly the professor's original released version.
- L07 `papers/Пояснительная записка.pdf`, §3.3, PDF pp. 47–48, equation (3.7): one convex-combination feasibility problem for each candidate point; §3.4, pp. 48–49 explicitly says phase I/artificial basis suffices.
- L03 `papers/pardalos.docx`, §§3.3–3.4: same conceptual baseline and later modifications; filename alone does not establish Pardalos authorship.
- L26 `Свидетельства/Свидетельство №1 (ОД)/ReachableSet.py`: `RedundancyRemoval`, `SimplexAlgorithm`; L25 PDF listing, `SimplexAlgorithm` (use extracted function anchor).
- Larger archive: `Scientific Research/Main_Hull_Shor.m:11–23` calls `Simplex_Hull_Shor.m`; the latter lines 1–32 initialize a fresh artificial identity basis per tested point, perform largest reduced-cost/ratio pivoting using `B\M`, then delete only that point if the auxiliary residual vanishes.
- A06 `Статьи/А.Ф. Шориков/btulshor.pas`: `KPABEP` lines 73–126 calls `MODIF` (128–213). This is an older related LP-based hull reduction, with distinct storage and solver interfaces.

Minimal contract: for a deduplicated finite point set P, classify p as redundant iff there exist nonnegative weights on P excluding p with sum 1 and weighted sum p. Return retained original point IDs with `conv(retained)=conv(P)` and preferably a convex-combination witness for every removed point. Empty/singleton/affine-dimension-zero inputs need defined outcomes. Feasibility must have a numerical-failure/iteration-limit status rather than converting failure into “vertex”.

Tests: triangle/square with center and edge points; all points extreme; duplicates; collinear/coplanar inputs embedded in a higher dimension; signed coordinates; scale disparity; deterministic pivot ties; infeasible membership returns a separation certificate if supported. Check hull equality independently by membership/support, not vertex order or timing. Compare against a small trusted LP oracle.

Suggested tickets:

1. Define the hull result, point identity, tolerance and LP-feasibility status contracts plus tiny fixtures.
2. Implement a bounded phase-I simplex feasibility kernel with deterministic anti-cycling and witness extraction; scope this to equality/nonnegative feasibility needed by hull and recovery rather than promising a full LP optimizer.
3. Implement baseline per-point LP hull reduction using that kernel and a pluggable oracle seam.

Dependencies: (1) → (2) → (3). Do not label legacy code as fully validated professor-original software without version evidence.

## 2. Modified simplex/basis-information reuse

Evidence:

- L07 §3.4 pp. 50–51, (3.8) and ensuing steps: a completed phase-I basis classifies additional nonbasic points as convex combinations, moves basis points to the start, and skips further checks for them.
- L03 §3.4: explicitly describes additional interior/vertex classification from one LP result.
- A15 `Scientific Research/Main_Hull_mod.m:18–24`, A16 `Scientific Research/Simplex_Hull_mod.m:13–25`: on a redundant tested point, take selected basis columns, identify additional columns with `sum(abs(N)) < 1+eps`, delete them, move selected basis points to the front, and advance the driver by the count.
- `Scientific Research/Simplex_Hull.m:14–20` is a smaller distinct modification: deletes additional columns based on the basis coordinates but does not perform A16's front-moving/skipping. `Main_Hull.m` invokes it at line 49.
- `Scientific Research/SMLP.m:19–63` is a tableau-updating auxiliary LP experiment with basis/nonbasis tracking, tie handling and an `add` output; `Modified_SM.m:16–40` is an alternate inverse-basis LP membership predicate. Do not treat “Modified_SM” as synonymous with A16's multiple-point classification.

Important boundary: this is primarily **reuse of information inside one completed LP solve**. A16 starts again with `B = eye(...)` for each invocation; it does not persist a warm-start basis across different candidate LPs. A true cross-query warm start would be a new owner-requested optimization, not a recovered feature.

Minimal contract: same hull equality as the baseline; each bulk deletion has a nonnegative barycentric certificate relative to retained support. General feasible-basis columns are not automatically global extreme points; the archive's skip-as-vertex claim depends on its specialized pivot argument. Treat skipping as an optimization requiring justification or a final verification pass. Preserve point IDs through deletion and front-moving. Expose counters for LP solves, pivots and bulk classifications, not a universal speedup promise.

Tests: differential hull equality against baseline on deterministic clouds; multiple redundant points inside one simplex; points lying on faces; ties/degenerate bases; adversarial input permutations; clouds with interior basis candidates; verify every bulk certificate and ensure skipped basis candidates cannot leave a redundant output. Instrument one hand-constructed fixture where bulk classification reduces the number of LP calls, but avoid general timing assertions.

Suggested small tickets: (a) expose completed basis and valid barycentric classifications from phase I; (b) implement bulk removal without skip-as-extreme; (c) validate/implement A16-style point ordering/skipping as an optional strategy with final checking. Depend on baseline/kernel. Genuine cross-query warm start is separate and optional.

## 3. Ordered/grouped hull filtering inspired by divide-and-conquer

Evidence and precise version differences:

- L03 §3.4 distinguishes its second modification from the simplex modification: bounding-box distance sorting, incremental construction, optional nearby/grouped tests after a run of interior points, and final LP reduction. The extracted DOCX has a suspicious compatibility sentence in Step 2.2 (compatible leads to adding a point, whereas the baseline says compatible means redundant); formula images are absent. Use the LP contract and actual code rather than reproducing that sentence literally.
- L07 §3.4 p. 48 mentions sorting/grouping inspired by Divide-and-Conquer. However its concrete p. 51 steps describe sorted in-place basis reduction, not a recursive split/merge algorithm. It sorts **increasing** normalized distance; L03 describes **decreasing** ordering. These are distinct archived formulations.
- `Scientific Research/QLPHULL.m:7–19` deduplicates and sorts decreasing using `abs(max((p-d)./r))`; lines 23–36 sequentially test each candidate against C with `Modified_SM`; lines 44–64 (the proposed grouping Step 3) are entirely commented out; lines 65–76 perform independent final LP reduction. No recursive splitting exists in this active code.
- `Публикации/Минимакс/Constrained/QLPHULL.m:6–18` deduplicates and sorts decreasing using `max(abs((p-d)./r))` (different placement of absolute value, materially different metric). Lines 25–35 incrementally append candidates, apply `Simplex_Hull_mod`, and stop after 10 consecutive redundant outcomes. Lines 50–72 activate the grouping Step 3: `Ck` takes all current C (`floor(size(C,2)*1)`); C is then initially empty, and the remainder is tested against fixed Ck plus accumulated nearby Cj; outside points join C; the fixed Ck is restored. Lines 73–87 final-reduce using `Simplex_Hull_mod`. Its `itrt` is initialized to zero but actual pivot counts are discarded/commented out: it is not trustworthy instrumentation.
- `Конференция/ИТиС 2019/2/Main_Hull_mods.m:11–42` is yet another sorted streaming candidate strategy using the baseline predicate followed by final reduction; its function name differs from filename. It is not recursive divide-and-conquer either.

Minimal contract: filtering may discard p only with a certificate that p is in the convex hull of a retained candidate subset. Any candidate not provably interior remains for final reduction. Sorting or grouping must never change the result. Handle zero-width bounding-box coordinates, fewer than two unique points, duplicates, and threshold-trigger indexing explicitly. Sequential grouping is one strategy; literal recursive `hull(hull(P1) ∪ hull(P2))` is a separate new strategy if requested.

Tests: all permutations yield the same hull; zero-width box; <2 unique points; threshold never reached/reached at last point; outside points arriving after 10 interior points; points near/far from all grouping centers; signed metric example where `abs(max(v)) != max(abs(v))`; compare filtered hull to baseline. Assert counters accurately include every child LP invocation.

Suggested tickets: implement deterministic distance ordering/preconditioning; implement streaming filter plus mandatory final reduction; implement audited active grouping variant behind a separately named strategy; only then benchmark Normal/Uniform/Sphere fixtures corresponding to L07 pp. 53–55. Do not ship a ticket saying “the archived recursive divide-and-conquer simplex method” because that exact algorithm has not been found.

## 4. Separate geometric Quickhull experiment

`Scientific Research/quickhull.m:1–21` initializes extreme x-coordinate endpoints and sides; nested `qh:22–52` picks the farthest point and recursively processes subsets. It is a two-dimensional geometric hull algorithm with plotting mixed into computation, slope divisions (vertical lines problematic), and missing safe empty initial-subset handling. It contains no simplex calls.

Contract: return 2D extreme points in a documented cyclic order, with explicit collinear-edge policy, retaining original point identities. Tests: triangle/square; all-collinear/vertical line; duplicate endpoints; empty side; rotated clouds; compare to monotone-chain/baseline. A geometric 2D Quickhull implementation is a separate optional ticket depending only on common point/tolerance types, not on simplex. Higher-dimensional Quickhull or library integration would be another scope decision.

## 5. Zoutendijk feasible-direction method: stronger archival evidence

Article references:

- L11 `papers/ШориковАФ, КалевВИ, последняя версия.pdf`, PDF p. 11, step 2 says terminal convex minimization may be solved by Zoutendijk; reference 22 on p. 17 names the 1963 Russian book.
- L12 corresponding Word text names the method, but embedded equations are missing.
- L13 `papers/Электронная версия_статьи.pdf`, PDF p. 10, step 5 names Zoutendijk in the optimization stage; reference 13 on p. 15. Naming an optimizer there does not certify a convex maximization procedure's global result.

Actual archived implementation:

- A06 `Статьи/А.Ф. Шориков/btulshor.pas:766–886`: `ZODENTEK(n,m,A,Y,X)`, private implementation procedure (not declared in unit interface). Its `FUN:770–776` is exactly `sqrt(sum((X-Y)^2))`; `GRF:786` uses X-Y, which shares descent directions with the norm away from zero.
- Linear constraints are flattened rows `(a_i, c_i)` with intended `a_i·x+c_i <= 0`, supported by `VERLIM:894–897` and residual bounds in ZODENTEK.
- Active constraints identified by residual near zero (781–805), direction LP built with split signed variables (807–819), solved by `MODIF` at 821, direction extracted and normalized (823–836), inactive constraints used for a step bound (838–846), then a bespoke repeated halving/forward/backward line search (847–885).
- `VERLIM:888–910` attempts an initial single-plane correction and calls ZODENTEK to find a constrained nearest point. `ALOWER:617–764` invokes VERLIM at 723 as the projection component of another minimization routine.
- Dependencies are explicit in A06: `USES BIBTUSH,DIALOGS` (line 5), `uses term,funfnx` (26), type families `t7/t8/t12/t13`. They remain unrecovered according to the existing audit. No standalone Pascal executable or full numerical environment was restored here.

Review concern, not an executed failure: step-bound loop at 839–843 jumps out on the first inactive row with nonpositive directional derivative, resetting `sup` to the sentinel; it can ignore a later row imposing a finite upper bound. A modern implementation must recompute the minimum over **all positive** directional derivatives and check feasibility of accepted iterates. Zero direction/target coincidence and hard-coded mixed `1E-10`/`1E-05` tolerances also need explicit handling.

Minimal first contract: Euclidean projection onto a nonempty compact linearly constrained polytope, with supplied or computed feasible initial x, returns feasible x*, objective, termination status and a convex-optimality certificate/stationarity residual. First implement the convex quadratic equivalent `0.5*||x-Y||^2` so target coincidence is smooth. A later generic differentiable convex objective interface can accept f and gradient with a separate feasibility-preserving line-search policy. For nonlinear constraints or generic nonconvex objectives, a stationary point is the defensible guarantee unless stronger assumptions are provided.

Tests: projection onto interval/box; target inside feasible set; optimum on a face/corner; affine equality/singleton polytope; order permutation with an inactive zero-derivative row preceding a finite-bound row; feasible iterates after every step; coincident target/zero direction; infeasible start/set statuses; scaled constraints; objective descent and KKT residual compared to analytical projection or trusted QP solution. Do not claim “theory-proven convergence” from reproducing Pascal's line search.

Suggested tickets: (a) transcribe/document A06's projection direction LP and feasibility semantics with the above regression fixtures; (b) implement a bounded projection-focused feasible-direction solver against the LP kernel; (c) add smooth convex-objective generalization only after the specialized method passes independent analytical/QP checks. These implement an archival family without promising full Pascal workflow reproduction. Generic theory beyond the inspected sources requires primary references.

## 6. Additional concrete optimization routines

| Evidence | What actually exists | Minimal contract/test | Small ticket/dependency |
|---|---|---|---|
| L14 optimal listing, PDF p. 2 `ConvexProgram`; A03 `Конференция/ICIE 2018/OpenLoopControl.m:34–38` | SLSQP / MATLAB `fmincon` over H/equality description of terminal hull, starting at vertex mean; A03 uses a weighted Euclidean fuel norm without the synchronization term | Minimize declared convex objective on terminal polytope; infeasible/solver-failed cases explicit; test optimum inside a segment and on constrained boundary, plus affine-degenerate sets | Convex terminal-optimizer interface and one reference backend. Depends on H/V conversion and objective metadata; these sources do not demonstrate Zoutendijk was the running backend |
| L14 p. 3 `LPControl`, `Snatch`; A03:103–106; `Конференция/ICIE 2018/Simplex_ctrl.m:1–32`, `Snatch.m:1–22` | Feasibility LP for two convex combinations, then predecessor/successor states and controls | Find λ≥0, μ≥0, sum λ=sum μ=1, Aλ+Bμ=x; return residual-certified witness or infeasible status. Test rank-deficient B, nonunique controls, unreachable x, full-horizon replay and every state/control constraint | One-step witness recovery then trajectory stitching. Depends on phase-I kernel and compatible state tubes |
| `Конференция/ICIE 2018/Simplex_lazy_ctrl.m:6–65` | Direct stacked terminal equality with signed control splits and two-phase tableau logic; experimental hard-coded rows | Recover a sequence satisfying terminal map and interval control bounds. State-path constraints are not visibly encoded in this routine | Optional direct LP recovery baseline, after full-horizon constraint contract; test LTV transition ordering and intermediate-state infeasibility |
| L19 `feasible_actions`, `minimax_openloop_control`, `optimize_on_rs`; A09 `Публикации/Минимакс/Adaptive_Samara/Minmaxopenloop.m:1–50` | Finite-action sequence enumeration; per fixed plan disturbance reachability; choose smallest worst cost. L19 runs local SLSQP on a negated convex objective; A09 also checks all terminal vertices | For convex continuous cost over a compact polytope, global maximum value is achieved at a vertex; exhaustive terminal vertex evaluation gives exact finite-horizon minimax value subject to hull/numerical correctness. Test midpoint stationary local oracle against larger endpoint values; robust constraint rejection; all plans infeasible; ties | Implement convex worst-case vertex oracle, then exhaustive finite-action minimax reference solver. Do not depend on Zoutendijk to maximize a convex cost |
| A06 `ALOWER:617–764` | Finite-difference gradient (APGRAD), step policies a/b/c, projection through VERLIM, external objective FUNF | Optional projected-gradient comparison method for a declared smooth convex objective, with checked projection and objective decrease | Lower priority separate optimizer candidate; depends on projection solver and declared objective; external FUNF missing |
| A06 `CHEBR:913–990` | Enclosing-radius optimization over finite points, active furthest points, auxiliary LP and radius updates | Intended minimum enclosing Euclidean ball, distinct from the Chebyshev center of an H-polytope (largest inscribed ball). Needs independent derivation before claims. Test two-point midpoint/radius, triangle, singleton and duplicates | Source-derivation ticket first; optional enclosing-ball backend later. Do not title it “polytope Chebyshev center implementation” solely from CHEBR name |

## 7. Exact set operations and algorithm seams

“Exact” here means the mathematical represented set, with numerical tolerance/status handling required in floating point. It does not mean exact rational arithmetic is already present.

| Seam and contract | Archival anchors | Essential tests and dependency |
|---|---|---|
| Affine image and Minkowski sum: `A conv(V)=conv(AV)`; `conv(V)⊕conv(W)=conv(v+w)` | L26 `ReachableSet`; L19 `Polytope.__add__`, `reachable_set`; A03:13–32; A06 `REACH:41–71` | Singular A, non-square B, singleton/empty inputs, support-function addition, interval analytical cases. Depends on hull reducer; finite **control catalogues** must not be silently convexified when exact finite union semantics matter |
| H/V conversion with affine equalities and boundedness statuses | L26 `DDM`; L19 `double_description`; A18 `Конференция/ICIE 2018/VertexEnumeration.m:1–83` (double-description style homogenized rays, rank completion and randomized initial basis); A17 `Scientific Research/GeoCalcLib-master/vertexEnumeration.m:1–8` calls external `libgeocalc` and reports vertices/rays | H→V→H membership equality for square/simplex/segment/point; equality sign; empty and unbounded polyhedra; rank-deficient rows; reproducibility. Conversion backend ticket should define statuses before porting the randomized legacy routine |
| Halfspace redundancy reduction | L26 `RedundancyRemoval(...,'halfspace')`; L19 `remove_redundancy`; A03:25,81 | Remove inequality i iff maximum violation under remaining constraints is nonpositive; duplicate/opposite rows, essential bounding row, equality constraints. Requires genuine implication certificate; do not infer from arbitrary convex-hull treatment of augmented columns |
| State intersection: preserve `(A R⊕B U)∩X_next` for nominal reachable states | L26 `ReachableSet` combines H rows and reconverts; A03:21–26,76–88 | Generated extreme points all outside but crossing edges create feasible intersection; empty intersection; constraints indexed at correct time. Depends on H/V and intersection representation |
| Nominal predecessor: `{x∈X_t : ∃u∈U_t, A_t x+B_t u∈S_next}` | L26 backward branch uses inverse A; A03:51–65; A06 `OBREACH:215–244`, `OBRMTR:246...` | Invertible analytic example, singular A supported via projection/LP or rejected explicitly, sign of B, time indexing, empty target. First small ticket may support invertible A honestly; general predecessor needs joint-polyhedron projection |
| Fixed-plan disturbance reachability and robust state admissibility | L19 `reachable_set`; A09:8–23 | For fixed u, `R_next=A R⊕{Bu}⊕D W`; robust plan valid only if **entire** R_next⊆X_next. Vertex checks suffice for linear constraints; clipping would discard counterexamples and change quantifiers | Depends on affine/Minkowski/hull operations and containment. Add regression where clipping is nonempty but plan violates robust constraint |

Separate approximation families exist in A04 zonotope and A05 ellipsoid scripts. They belong to approximate-enclosure interfaces, not exact-set tickets; archive-followup already records unfinished generator reduction/external dependency concerns. Robust feedback predecessor with `∃u ∀w` requires an explicit quantifier contract and is not established by the nominal inverse-image or fixed-open-loop scripts alone.

## Algorithm prerequisite order

1. Shared set/objective/result contracts, tolerance/status policy and provenance fixtures.
2. Phase-I feasibility kernel; baseline LP hull reducer; bounded polytope H/V conversion and intersection.
3. Affine image/Minkowski propagation; nominal reachable tubes; one-step witness; invertible predecessor and trajectory replay.
4. Terminal convex minimization reference backend; exact convex vertex maximization; exhaustive finite-action minimax reference.
5. Basis bulk classification with certificates; ordering/filter/grouping strategies; counters and strategy comparisons.
6. Pascal-derived projection/Zoutendijk family; optional generic convex feasible-direction generalization.
7. Independent 2D geometric Quickhull; optional direct LP recovery/projected-gradient/enclosing-ball follow-ups.

Keep each algorithm ticket scoped to one contract and its independent verification fixtures. A generic “optimization algorithms” ticket or one “all simplex variants” ticket would lose the distinctions found here. Archival benchmarks should be acceptance fixtures only where their full model/objective/input version is established; B04 and adaptive B09 version gaps remain as documented elsewhere.

## Additional permanent source identifiers

| ID | Archive-relative path |
|---|---|
| A24 | `Scientific Research/Main_Hull_Shor.m` |
| A25 | `Scientific Research/Simplex_Hull_Shor.m` |
| A26 | `Scientific Research/Main_Hull.m` |
| A27 | `Scientific Research/Simplex_Hull.m` |
| A28 | `Scientific Research/LPHULL.m` |
| A29 | `Scientific Research/QLPHULL.m` |
| A30 | `Scientific Research/Modified_SM.m` |
| A31 | `Scientific Research/SMLP.m` |
| A32 | `Scientific Research/quickhull.m` |
| A33 | `Публикации/Минимакс/Constrained/QLPHULL.m` |
| A34 | `Конференция/ИТиС 2019/2/Main_Hull_mods.m` |
| A35 | `Конференция/ICIE 2018/Snatch.m` |
| A36 | `Конференция/ICIE 2018/Simplex_ctrl.m` |
| A37 | `Конференция/ICIE 2018/Simplex_lazy_ctrl.m` |
| A38 | `Конференция/ICIE 2018/SimplexIntersect.m` |

The implementation backlog separates archival algorithms from new recursive hull reduction and cross-query warm starts. See the [implementation plan](../superpowers/plans/2026-10-11-controlled-systems-backlog.md).
