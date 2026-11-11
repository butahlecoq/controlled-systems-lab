# Illustrated book and three-environment control program

Research date: 2026-11-11. Audited source: `ed2dda1ef049ac4fbe259a800d3314e446ceee28`.
Program [#936](https://github.com/butahlecoq/controlled-systems-lab/issues/936).
Research task [#937](https://github.com/butahlecoq/controlled-systems-lab/issues/937).

The owner requests a consistent illustrated Pages site, examples organized as a learning book, and all compatible module compositions on Lotka–Volterra, Earth orbit and fuel. Each comparison uses one nominal closed-loop control task, without a second player. This research records current capabilities and publishes implementation tickets. It does not delete HTML, redesign Pages or execute the new comparison suite.

## Findings

The [report retirement audit](pages-report-retirement-audit.md) finds 198 checked-in report HTML files, including 171 index pages. Sixteen index pages have no embedded graphic tag. The live root links 120 report index routes; all returned HTTP 200 at inspection, and eleven have no embedded graphics. These are distinct inventories. Source adapters can add or omit a figure, and separate staging/augmentation adds routes outside the 33-row catalogue. The audit includes exact candidate routes, source ownership, hashes, limitations and reproduction commands.

Absence of an embedded graphic does not establish absence of a linked example. A timing plot also does not make a complete lesson. The retirement ticket classifies illustration, educational completeness and evidence role independently. Obsolete generated wrappers can be deleted after reference and identity checks. Immutable scientific HTML, raw records and offline ZIPs retain their bytes and retrieval routes. Primary learning navigation stops presenting bare/superseded reports as tutorials.

The [learning-book audit](pages-learning-book-audit.md) identifies independently styled landing, gallery and example producers. It proposes one shared mutable presentation, a progressive source-owned chapter structure and browser acceptance checks. Historical report bundles remain evidence links. Shared templates and new companions provide a coherent reading experience without changing those bundles.

The [control matrix audit](three-environment-closed-loop-matrix-audit.md) finds substantial existing components but no common three-environment composition route. MPC11 has nonlinear feedback studies for synthetic Lotka and fuel. The Earth-orbit pilot enumerates 729 restricted block plans, with no shared observed-state feedback adapter. Delivered five-representation finite-action selectors are affine fixed-plan methods; their approximation scores do not establish feedback recovery or objective bounds.

## Four module groups

| Group | Choices the program records | Required distinction |
| --- | --- | --- |
| 1. LP/simplex algorithms for vertices | Membership/Phase-I algorithms, basis reuse, ordered/grouped methods, faithful legacy variants and geometric comparators | Vertex feasibility/redundancy is separate from terminal LP/QP optimization. Preserve faithful source behavior and independently check retained hulls. |
| 2. Reachable-set representations | Polytopes, zonotopes, parallelotopes, ellipsoids and boxes | H/V are polytope encodings. Every operation records equivalent/inner/outer/heuristic relation, dimensions and actual supported assurance. |
| 3. Control algorithms | Reachable-set-based control and MPC formulations | Record a real observed-state policy execution. Separate finite-graph optimality, nominal replanning, local nonlinear optimization and any global feedback claim. |
| 4. Supporting algorithms | V↔H, sums/images, intersections, projections, predecessors/recovery, approximation/reduction and optimization providers | Record actual operation calls and conversions. A bypassed slot is `not_used`; selecting its name does not exercise it. |

“All combinations” means a finite, versioned catalogue of semantically meaningful compositions, with every candidate classified and every admitted composition attempted. It does not require invalid inputs or infinitely many tuning values. A missing requested adapter remains linked implementation work; it cannot be hidden as mathematical incompatibility. Equivalent tuples that differ only in inactive choices count once.

The matrix must identify each set's mathematical role. In a deterministic model, one initial point under one policy produces one trajectory. Nontrivial sets can instead describe all admissible controls and backward target feasibility. These objects can accompany the trajectory without introducing an opponent. Singleton approximation tests are retained as such, rather than used to claim meaningful enclosure quality.

## Published implementation tickets

| Issue | Deliverable | Native prerequisites |
| --- | --- | --- |
| [#938](https://github.com/butahlecoq/controlled-systems-lab/issues/938) | Complete final-artifact inventory and actual retirement of obsolete presentation | None |
| [#939](https://github.com/butahlecoq/controlled-systems-lab/issues/939) | Shared visual design for mutable Pages and companions | None |
| [#940](https://github.com/butahlecoq/controlled-systems-lab/issues/940) | Learning book organized around the four module groups | #938, #939 |
| [#941](https://github.com/butahlecoq/controlled-systems-lab/issues/941) | Common task contracts and model/replay adapters for all three environments | None |
| [#942](https://github.com/butahlecoq/controlled-systems-lab/issues/942) | Exhaustive typed composition catalogue and admission ledger | None |
| [#943](https://github.com/butahlecoq/controlled-systems-lab/issues/943) | Reachable-set/MPC feedback composition across five representations | #941, #942 |
| [#944](https://github.com/butahlecoq/controlled-systems-lab/issues/944) | Actual selectable vertex LP, conversion and optimizer calls in control pipelines | #942 |
| [#945](https://github.com/butahlecoq/controlled-systems-lab/issues/945) | Common runner and initial closed-loop results for each environment | #941, #942 |
| [#946](https://github.com/butahlecoq/controlled-systems-lab/issues/946) | All-stage set/intersection/trajectory figures from saved records | #945, #939 |
| [#947](https://github.com/butahlecoq/controlled-systems-lab/issues/947) | Full admitted-composition execution and published coverage dashboard | #943, #944, #945, #946, #940 |

These tickets are native children of #936. Their dependency edges express implementation order; they are not requests for new owner approval. The live tracker remains authoritative for status, claims and subsequent changes. Research #937 closes when the audited findings and ticket handoff are delivered, not when #936's implementation is complete.

## Delivery order and verification

Publication inventory and shared design can start independently of the numerical program. Environment contracts/adapters and the capability catalogue can start immediately. The initial-results ticket deliberately does not depend on the complete book, all new approximation-feedback support or every vertex adapter. Start with admitted baselines, retain errors and initial numbers, then expand the same runner to the exhaustive suite.

Each task contract fixes physical model, state order/units, action domain, constraints, cost, time grid, observation timing, controller horizon semantics and numerical execution. Finite-action, continuous-action, affine-prediction and nonlinear-plant variants retain distinct identities. The common objective is evaluated from actual saved controls and independently replayed states. No constraint or running cost is removed to admit a method.

Fuel figures use the requested oxidizer x1–x2 and fuel x3–x4 planes. MPC11's native order `(m_ox,m_f,q_ox,q_f)` differs from archived flow/stock ordering, so the plots need an explicit physical-coordinate mapping. Lotka uses the population plane; orbit uses labeled physical projections. Figures show forward sets, target/backward sets and intersections when actually produced, together with the executed trajectory. Projection overlap is not full-state feasibility.

The owner has authorized autonomous implementation and runs. The existing specific acados exclusion in the [MPC11 contract](../contracts/mpc11-synthetic-controller-study.md) remains recorded; this audit does not erase it. New captures follow the [comparison evidence/resource contract](../architecture/comparison-program.md) and [published-results gates](../architecture/published-algorithm-results.md). Research itself runs no benchmarks and introduces no numerical result.

Validation for this handoff comprises local source-link checks, reproduction of local inventory counts, live HTTP observations in the retirement audit, and fresh GitHub checks of issues, native dependencies and child links. No browser appearance or redesigned deployment is claimed. Documentation-only research needs no release or native build; later API/example/publication changes carry their own delivery checks.
