# Controlled Systems Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a modular C++20 library that returns optimal control/trajectory families, first compares two nominal discrete strategies, and supports independently replaceable numerical and geometry adapters.

**Architecture:** Immutable model/problem/set data, backend-neutral mathematical ports, exclusive solve/query workspaces, independent evidence verification, and artifact consumers for scenario input, tables and plots.

**Tech Stack:** C++20 and CMake proposed; matrix, LP, convex, test and parser dependencies are selected in CORE-01; VIZ-03 selects its scientific export adapter. Python is permitted for independent references and an external plotting adapter, not as the product algorithm core.

**Spec:** [Master specification v0.6](../specs/2026-10-11-controlled-systems-master-design.md), [native contract sketch](../specs/2026-10-11-cpp-core-contracts-design.md), [scenario sketch](../specs/2026-10-11-scenario-files-design.md).

## Global Constraints

- Architecture and native contracts come before numerical implementation. Each module has a small stable interface that hides backend complexity.
- The first executable profile is nominal discrete affine dynamics, known initial state, continuous controls and polyhedral admissibility. Finite/mixed/hybrid, disturbances, feedback and continuous time are later capability profiles.
- Preserve the complete joint optimal relation. A finite witness list or Cartesian product of stage marginals cannot replace it. Feasibility, optimality and completeness carry distinct evidence.
- Initial numerical arithmetic does not establish validated containment/completeness. Unsupported or limited outcomes remain distinct from mathematical infeasibility.
- Every implementation ships meaningful minimum tests. Dedicated test issues expand the suite independently; they do not defer basic testing.
- Raw archives remain private and unchanged. Archival B04 restoration is independent of synthetic module tests and implementation readiness.
- Model, strategy, LP kernel, hull policy, convex method, representation, geometry operator, approximation and selector are separate substitution axes.
- Final plots include controls, trajectories and selectable 2D fuel-coordinate views. Detailed timing tables record nested/parallel work without treating overlapping durations as additive latency.
- Shared inputs are immutable. Mutable workspaces have one owner. Use one total resource policy for outer tasks and native backend threads.

## Review Focus

Review scientific quantifiers, all-optima semantics, hidden representation assumptions, status/evidence translation, native ownership, extensibility, repeated allocations/materialization and actual measured complexity. Independent reviews run after code and tests exist. Every blocking finding needs a linked fix and independent recheck.

## Contracts and integration order

CORE-01 freezes the first revision of numeric buffers, model/problem identity, statuses/evidence, set payload/operation requests, neutral optimization programs, family/witness queries, execution resources and artifacts. Use the existing contract sketches as input; record concrete backend versions, licenses and small integration probes. Do not expose solver/matrix containers in public headers.

Each interface states inputs, output relation/guarantee, dimensions, ownership, cancellation and unsupported behavior. Downstream workers implement adapters against the integrated revision. A contract change must update the specification and affected tests before downstream tickets use it. Registry entries include algorithm/backend/version identity and supported assumptions. Test at least two actual compatible adapters where implemented; registration stubs only test the registry contract.

The first scientific oracles are the two-step integrator family u0+u1=1, a constant objective, and a unique terminal optimum with multiple histories. Both strategies must recover these relations and independently verified witnesses. A solver's single optimal point does not establish the minimizer set.

## Work units and first-release boundary

Each issue is an independently checked capability or adapter, not a time estimate. Its checklist is the implementation sequence: confirm assumptions/interface, write an independent failing acceptance test, implement the supported path, verify limits/diagnostics, and submit review evidence. Large future research capabilities are bounded demonstrations under declared assumptions; they do not promise universal solvers.

The first release consists of phases 1–2. It includes the two strategies, input templates, isolated execution, final comparison records, detailed timing tables, projections/figure export, separate test expansions and REVIEW-01–07. The archival table exporter can operate with current historical records; canonical B04 execution stays behind restoration issue #10. No later approximation or optimizer variant is required to finish the first comparison.

Phase 3 benchmarks optional optimizer substitutions and nonlinear replay. Phase 4 compares representations and approximations after the agreed first comparison. Phase 5 implements specific future profiles with their own assumptions and review gates.

## Agent execution protocol

1. Select an open ticket whose native GitHub blockers are closed. Recheck the manifest and source evidence; claim module/file ownership.
2. Create an isolated branch/worktree. Shared contract or schema edits have one integrator; dependent agents wait for the integrated revision.
3. Implement through the named module seam with meaningful unit/contract tests. Test through observable behavior and independent mathematical oracles.
4. Return commits, commands/results, capability/evidence limits and open findings. The integrator runs affected cross-module contracts before merging.
5. Run the separate independent test/review issues once their prerequisites exist. Turn blocking findings into fix issues and re-review.

Use [skill routing](../../agents/skill-routing.md) to select one workflow owner per stage. Scientific reviewers can file issues independently of agent code review.

## Ticket index

GitHub is the working tracker. All 94 issues are published: 61 implementation, contract, artifact or experiment tasks, 23 independent test expansions and 10 code-review tasks. The [machine-readable manifest](backlog.json) records stable keys, GitHub IDs, full prerequisites, minimal native blocking edges, proposed ownership and test IDs. Local ticket mirrors keep the same acceptance checklist.

Only [CORE-01 #11](https://github.com/butahlecoq/controlled-systems-lab/issues/11) is initially dependency-ready. Re-evaluate labels as prerequisites close. Existing research issues remain open and were not rewritten. Native GitHub links use 183 nonredundant edges with the same transitive prerequisite relation as the complete graph; issue descriptions retain the full list.

### Phase 1: Native foundations and contracts

| Ticket | GitHub | Kind | Full prerequisites |
|---|---|---|---|
| [CORE-01: Fix public contracts and choose compatible native dependencies](tickets/CORE-01.md) | [#11](https://github.com/butahlecoq/controlled-systems-lab/issues/11) | implementation | None |
| [CORE-02: Build and run a portable C++20 client with test support](tickets/CORE-02.md) | [#12](https://github.com/butahlecoq/controlled-systems-lab/issues/12) | implementation | CORE-01 |
| [CORE-03: Provide owning numeric data and safe matrix views](tickets/CORE-03.md) | [#13](https://github.com/butahlecoq/controlled-systems-lab/issues/13) | implementation | CORE-02 |
| [CORE-04: Select compatible algorithm adapters through a registry](tickets/CORE-04.md) | [#14](https://github.com/butahlecoq/controlled-systems-lab/issues/14) | implementation | CORE-03 |
| [MODEL-01: Define affine LTI/LTV models and separate observations](tickets/MODEL-01.md) | [#15](https://github.com/butahlecoq/controlled-systems-lab/issues/15) | implementation | CORE-03 |
| [GEO-01: Represent exact polyhedral and elementary sets](tickets/GEO-01.md) | [#16](https://github.com/butahlecoq/controlled-systems-lab/issues/16) | implementation | CORE-03 |
| [OPT-01: Evaluate and reformulate structured terminal objectives](tickets/OPT-01.md) | [#17](https://github.com/butahlecoq/controlled-systems-lab/issues/17) | implementation | CORE-03 |
| [OPT-02: Expose linear-program and basis-diagnostic interfaces](tickets/OPT-02.md) | [#18](https://github.com/butahlecoq/controlled-systems-lab/issues/18) | implementation | CORE-03 |
| [MODEL-02: Represent control domains, constraints and initial information](tickets/MODEL-02.md) | [#20](https://github.com/butahlecoq/controlled-systems-lab/issues/20) | implementation | MODEL-01, GEO-01 |
| [RUN-01: Execute isolated workspaces with budgets and cancellation](tickets/RUN-01.md) | [#25](https://github.com/butahlecoq/controlled-systems-lab/issues/25) | implementation | CORE-04 |
| [MODEL-03: Validate complete problems and strategy assumptions](tickets/MODEL-03.md) | [#28](https://github.com/butahlecoq/controlled-systems-lab/issues/28) | implementation | MODEL-02, OPT-01, CORE-04 |
| [INP-01: Load and validate versioned scenario files](tickets/INP-01.md) | [#44](https://github.com/butahlecoq/controlled-systems-lab/issues/44) | implementation | MODEL-03 |

### Phase 2: Nominal two-strategy comparison

| Ticket | GitHub | Kind | Full prerequisites |
|---|---|---|---|
| [TEST-01: Expand native buffer, ownership and build-boundary tests](tickets/TEST-01.md) | [#19](https://github.com/butahlecoq/controlled-systems-lab/issues/19) | test | CORE-02, CORE-03, CORE-01 |
| [OPT-03: Integrate a reference native LP adapter](tickets/OPT-03.md) | [#21](https://github.com/butahlecoq/controlled-systems-lab/issues/21) | implementation | OPT-02, CORE-04 |
| [OPT-08: Integrate convex-program interfaces and a reference adapter](tickets/OPT-08.md) | [#22](https://github.com/butahlecoq/controlled-systems-lab/issues/22) | implementation | OPT-01, CORE-04 |
| [TEST-02: Expand affine model and observation contract tests](tickets/TEST-02.md) | [#26](https://github.com/butahlecoq/controlled-systems-lab/issues/26) | test | MODEL-01, CORE-03 |
| [TEST-04: Expand objective evaluation and justified reformulation tests](tickets/TEST-04.md) | [#27](https://github.com/butahlecoq/controlled-systems-lab/issues/27) | test | OPT-01 |
| [OPT-05: Reduce hulls with independent membership LPs](tickets/OPT-05.md) | [#30](https://github.com/butahlecoq/controlled-systems-lab/issues/30) | implementation | OPT-03, GEO-01 |
| [GEO-03: Convert H and V descriptions with equality and ray support](tickets/GEO-03.md) | [#31](https://github.com/butahlecoq/controlled-systems-lab/issues/31) | implementation | GEO-01, OPT-03, CORE-04 |
| [TEST-05: Run reusable LP adapter contracts on every selected backend](tickets/TEST-05.md) | [#35](https://github.com/butahlecoq/controlled-systems-lab/issues/35) | test | OPT-03, OPT-02, RUN-01 |
| [TEST-06: Run reusable convex adapter contracts with singular objectives](tickets/TEST-06.md) | [#36](https://github.com/butahlecoq/controlled-systems-lab/issues/36) | test | OPT-08, OPT-01, RUN-01 |
| [GEO-02: Compute polyhedral affine images and Minkowski sums](tickets/GEO-02.md) | [#40](https://github.com/butahlecoq/controlled-systems-lab/issues/40) | implementation | GEO-01, OPT-05 |
| [GEO-04: Intersect state sets and remove redundant inequalities](tickets/GEO-04.md) | [#41](https://github.com/butahlecoq/controlled-systems-lab/issues/41) | implementation | GEO-03, OPT-03 |
| [SYN-06: Verify trajectories and evidence independently](tickets/SYN-06.md) | [#43](https://github.com/butahlecoq/controlled-systems-lab/issues/43) | implementation | MODEL-03, OPT-01 |
| [TEST-03: Expand problem validation and whole-pipeline capability tests](tickets/TEST-03.md) | [#47](https://github.com/butahlecoq/controlled-systems-lab/issues/47) | test | MODEL-03, CORE-04, MODEL-01, GEO-01 |
| [TEST-07: Expand barycentric membership and hull reduction tests](tickets/TEST-07.md) | [#48](https://github.com/butahlecoq/controlled-systems-lab/issues/48) | test | OPT-05, OPT-03, GEO-01 |
| [OBS-01: Define versioned module and operation statistics artifacts](tickets/OBS-01.md) | [#49](https://github.com/butahlecoq/controlled-systems-lab/issues/49) | contract | CORE-01, MODEL-03, RUN-01, CORE-04 |
| [GEO-05: Project joint polyhedra and compute nominal predecessors](tickets/GEO-05.md) | [#51](https://github.com/butahlecoq/controlled-systems-lab/issues/51) | implementation | GEO-03, GEO-04 |
| [SYN-01: Propagate nominal reachable sets with stage constraints](tickets/SYN-01.md) | [#53](https://github.com/butahlecoq/controlled-systems-lab/issues/53) | implementation | GEO-02, GEO-04, MODEL-03 |
| [TEST-14: Expand independent trajectory verification and evidence isolation tests](tickets/TEST-14.md) | [#58](https://github.com/butahlecoq/controlled-systems-lab/issues/58) | test | SYN-06, CORE-01, OPT-01, MODEL-03 |
| [REVIEW-01: Deep review of core composition, native contracts and ownership](tickets/REVIEW-01.md) | [#59](https://github.com/butahlecoq/controlled-systems-lab/issues/59) | review | CORE-03, CORE-04, MODEL-01, MODEL-03, TEST-01, TEST-02, TEST-03 |
| [OBS-02: Implement nested and parallel timing with explicit wall and CPU semantics](tickets/OBS-02.md) | [#60](https://github.com/butahlecoq/controlled-systems-lab/issues/60) | implementation | OBS-01, RUN-01 |
| [SYN-02: Construct the entire terminal minimizer relation](tickets/SYN-02.md) | [#61](https://github.com/butahlecoq/controlled-systems-lab/issues/61) | implementation | OPT-08, GEO-05 |
| [TEST-08: Expand exact polyhedral operation tests with degenerate cases](tickets/TEST-08.md) | [#63](https://github.com/butahlecoq/controlled-systems-lab/issues/63) | test | GEO-02, GEO-03, GEO-04, GEO-05, GEO-01, OPT-03 |
| [TEST-09: Expand geometry registry, conversion and guarantee contract tests](tickets/TEST-09.md) | [#64](https://github.com/butahlecoq/controlled-systems-lab/issues/64) | test | CORE-04, GEO-03, GEO-02, GEO-04, GEO-05 |
| [TEST-10: Expand reachability and nominal predecessor mathematical tests](tickets/TEST-10.md) | [#65](https://github.com/butahlecoq/controlled-systems-lab/issues/65) | test | SYN-01, GEO-05, GEO-02, GEO-03, GEO-04, MODEL-01 |
| [SYN-03: Build optimal families by reachability and backward recovery](tickets/SYN-03.md) | [#66](https://github.com/butahlecoq/controlled-systems-lab/issues/66) | implementation | SYN-01, SYN-02, GEO-05, OPT-02 |
| [SYN-04: Build optimal families by direct joint-trajectory optimization](tickets/SYN-04.md) | [#67](https://github.com/butahlecoq/controlled-systems-lab/issues/67) | implementation | MODEL-03, OPT-08, SYN-02 |
| [TEST-11: Expand terminal minimizer-set construction tests](tickets/TEST-11.md) | [#69](https://github.com/butahlecoq/controlled-systems-lab/issues/69) | test | SYN-02, OPT-01, OPT-08, OPT-03, GEO-05 |
| [REVIEW-02: Deep review of geometry algorithms and interchangeable backends](tickets/REVIEW-02.md) | [#70](https://github.com/butahlecoq/controlled-systems-lab/issues/70) | review | GEO-02, GEO-03, GEO-04, GEO-05, CORE-04, OPT-03, OPT-08, OPT-05, OPT-01, TEST-04, TEST-05, TEST-06, TEST-07, TEST-08, TEST-09 |
| [SYN-05: Extract different complete witnesses without changing optimality](tickets/SYN-05.md) | [#71](https://github.com/butahlecoq/controlled-systems-lab/issues/71) | implementation | SYN-03, SYN-04 |
| [INP-03: Publish simple executable templates with known answers](tickets/INP-03.md) | [#72](https://github.com/butahlecoq/controlled-systems-lab/issues/72) | implementation | INP-01, SYN-04, SYN-06 |
| [TEST-12: Expand direct joint-trajectory family tests](tickets/TEST-12.md) | [#74](https://github.com/butahlecoq/controlled-systems-lab/issues/74) | test | SYN-04, SYN-02, OPT-03, OPT-08 |
| [INP-02: Select scenarios and run method profiles from a native CLI](tickets/INP-02.md) | [#75](https://github.com/butahlecoq/controlled-systems-lab/issues/75) | implementation | INP-01, SYN-05, SYN-06, RUN-01 |
| [TEST-13: Expand backward recovery and distinct witness-selection tests](tickets/TEST-13.md) | [#77](https://github.com/butahlecoq/controlled-systems-lab/issues/77) | test | SYN-03, SYN-05, SYN-01, SYN-02, SYN-04 |
| [TEST-15: Expand execution isolation, cancellation and resource-policy tests](tickets/TEST-15.md) | [#78](https://github.com/butahlecoq/controlled-systems-lab/issues/78) | test | RUN-01, OPT-03, OPT-08, SYN-03, SYN-04, SYN-05 |
| [OBS-03: Instrument mathematical ports and expose substitutions and rejected capabilities](tickets/OBS-03.md) | [#79](https://github.com/butahlecoq/controlled-systems-lab/issues/79) | integration | OBS-02, CORE-04, MODEL-03, GEO-01, OPT-02, OPT-08, SYN-03, SYN-04, SYN-05 |
| [RUN-02: Run independent scenario sweeps within one resource budget](tickets/RUN-02.md) | [#80](https://github.com/butahlecoq/controlled-systems-lab/issues/80) | implementation | RUN-01, INP-02 |
| [REVIEW-03: Rigorous review of both strategies and complete optimal-family semantics](tickets/REVIEW-03.md) | [#82](https://github.com/butahlecoq/controlled-systems-lab/issues/82) | review | SYN-03, SYN-04, SYN-02, SYN-01, SYN-05, TEST-10, TEST-11, TEST-12, TEST-13 |
| [OBS-04: Record reproducible comparison runs and instrumentation overhead](tickets/OBS-04.md) | [#83](https://github.com/butahlecoq/controlled-systems-lab/issues/83) | integration | OBS-03, INP-01, SYN-03, SYN-04, SYN-05, SYN-06 |
| [TEST-16: Expand scenario-file and comparison-artifact contracts](tickets/TEST-16.md) | [#84](https://github.com/butahlecoq/controlled-systems-lab/issues/84) | test | INP-01, INP-03, OBS-04, OBS-01, SYN-03, SYN-04, SYN-06 |
| [REVIEW-04: Deep review of numerical verification and scientific evidence claims](tickets/REVIEW-04.md) | [#85](https://github.com/butahlecoq/controlled-systems-lab/issues/85) | review | SYN-06, OPT-01, OBS-04, TEST-14, TEST-04 |
| [OBS-05: Export detailed module computation tables and raw performance records](tickets/OBS-05.md) | [#86](https://github.com/butahlecoq/controlled-systems-lab/issues/86) | implementation | OBS-04 |
| [VIZ-01: Prepare backend-neutral final control and state plot data](tickets/VIZ-01.md) | [#87](https://github.com/butahlecoq/controlled-systems-lab/issues/87) | contract | OBS-04, SYN-05, MODEL-01, SYN-06 |
| [TEST-23: Expand batch sweep isolation and provenance tests](tickets/TEST-23.md) | [#88](https://github.com/butahlecoq/controlled-systems-lab/issues/88) | test | RUN-02, OBS-04 |
| [TEST-17: Verify detailed submodule timing tables and accounting](tickets/TEST-17.md) | [#89](https://github.com/butahlecoq/controlled-systems-lab/issues/89) | test | OBS-02, OBS-03, OBS-04, OBS-05 |
| [REVIEW-06: Deep review of scenario workflow, application independence and provenance](tickets/REVIEW-06.md) | [#90](https://github.com/butahlecoq/controlled-systems-lab/issues/90) | review | INP-01, INP-03, INP-02, VIZ-01, OBS-04, TEST-16 |
| [VIZ-02: Support selectable fuel-state 2D plots with explicit projection guarantees](tickets/VIZ-02.md) | [#91](https://github.com/butahlecoq/controlled-systems-lab/issues/91) | implementation | VIZ-01, OBS-03, CORE-01, GEO-05 |
| [EXP-01: Present B04 historical tables alongside restoration diagnostics](tickets/EXP-01.md) | [#93](https://github.com/butahlecoq/controlled-systems-lab/issues/93) | artifact | OBS-05 |
| [REVIEW-05: Deep review of per-worker execution and measured scalability](tickets/REVIEW-05.md) | [#95](https://github.com/butahlecoq/controlled-systems-lab/issues/95) | review | RUN-01, OPT-03, OPT-08, SYN-03, SYN-04, OBS-02, TEST-15, TEST-17, RUN-02, TEST-23 |
| [VIZ-03: Export standalone scientific final-result figures](tickets/VIZ-03.md) | [#96](https://github.com/butahlecoq/controlled-systems-lab/issues/96) | implementation | VIZ-01, VIZ-02, OBS-05, CORE-01 |
| [TEST-18: Verify fuel-case 2D projection data and visual artifacts](tickets/TEST-18.md) | [#98](https://github.com/butahlecoq/controlled-systems-lab/issues/98) | test | GEO-05, VIZ-02, VIZ-03, VIZ-01, OBS-04 |
| [REVIEW-07: Deep review of fuel projections, timing tables and comparison validity](tickets/REVIEW-07.md) | [#101](https://github.com/butahlecoq/controlled-systems-lab/issues/101) | review | VIZ-02, VIZ-03, OBS-03, OBS-04, VIZ-01, TEST-17, TEST-18, TEST-16, REVIEW-03, REVIEW-04 |

### Phase 3: Optimizer variants and replay

| Ticket | GitHub | Kind | Full prerequisites |
|---|---|---|---|
| [GEO-06: Add a separate two-dimensional QuickHull adapter](tickets/GEO-06.md) | [#23](https://github.com/butahlecoq/controlled-systems-lab/issues/23) | implementation | GEO-01 |
| [OPT-04: Implement the archival phase-I feasibility kernel](tickets/OPT-04.md) | [#29](https://github.com/butahlecoq/controlled-systems-lab/issues/29) | implementation | OPT-02, OPT-03 |
| [OPT-06: Add basis-reuse hull classification as a replaceable method](tickets/OPT-06.md) | [#37](https://github.com/butahlecoq/controlled-systems-lab/issues/37) | implementation | OPT-04, OPT-05 |
| [OPT-07: Add ordered and grouped hull reduction strategies](tickets/OPT-07.md) | [#38](https://github.com/butahlecoq/controlled-systems-lab/issues/38) | implementation | OPT-05 |
| [OPT-09: Implement the Pascal-derived Zoutendijk projection method](tickets/OPT-09.md) | [#39](https://github.com/butahlecoq/controlled-systems-lab/issues/39) | implementation | OPT-04, OPT-08 |
| [OPT-11: Add a recursive split-and-merge hull strategy](tickets/OPT-11.md) | [#45](https://github.com/butahlecoq/controlled-systems-lab/issues/45) | implementation | OPT-05, RUN-01 |
| [OPT-12: Add optional cross-query LP warm starts](tickets/OPT-12.md) | [#46](https://github.com/butahlecoq/controlled-systems-lab/issues/46) | implementation | OPT-02, OPT-03, OPT-05, RUN-01 |
| [EXP-04: Implement an independent nonlinear replay adapter](tickets/EXP-04.md) | [#56](https://github.com/butahlecoq/controlled-systems-lab/issues/56) | implementation | MODEL-01, OPT-01, SYN-06 |
| [TEST-19: Expand historical optimizer and hull-variant differential tests](tickets/TEST-19.md) | [#57](https://github.com/butahlecoq/controlled-systems-lab/issues/57) | test | OPT-04, OPT-06, OPT-07, OPT-09, OPT-11, OPT-12, GEO-06 |
| [VIZ-04: Associate nonlinear replay results with linearly optimal witnesses](tickets/VIZ-04.md) | [#92](https://github.com/butahlecoq/controlled-systems-lab/issues/92) | integration | VIZ-01, OBS-04, EXP-04, SYN-05, OPT-01 |
| [EXP-02: Benchmark module substitutions under common optimal-family outputs](tickets/EXP-02.md) | [#94](https://github.com/butahlecoq/controlled-systems-lab/issues/94) | benchmark | OBS-04, OBS-05, SYN-03, SYN-04, OPT-04, OPT-06, OPT-08, OPT-09, GEO-03, INP-03, TEST-12, TEST-13 |
| [TEST-22: Expand independent nonlinear replay and association tests](tickets/TEST-22.md) | [#97](https://github.com/butahlecoq/controlled-systems-lab/issues/97) | test | EXP-04, VIZ-04 |
| [REVIEW-10: Review nonlinear replay adapters and linear-result associations](tickets/REVIEW-10.md) | [#103](https://github.com/butahlecoq/controlled-systems-lab/issues/103) | review | TEST-22, REVIEW-04, REVIEW-07 |

### Phase 4: Structured sets and approximations

| Ticket | GitHub | Kind | Full prerequisites |
|---|---|---|---|
| [APP-01: Define inner and outer approximation policies and evidence](tickets/APP-01.md) | [#24](https://github.com/butahlecoq/controlled-systems-lab/issues/24) | implementation | GEO-01, CORE-04 |
| [GEO-07: Add zonotope and constrained-zonotope exact operations](tickets/GEO-07.md) | [#32](https://github.com/butahlecoq/controlled-systems-lab/issues/32) | implementation | GEO-01, CORE-04, OPT-03 |
| [APP-02: Implement box and parallelotope approximations](tickets/APP-02.md) | [#33](https://github.com/butahlecoq/controlled-systems-lab/issues/33) | implementation | APP-01, OPT-03 |
| [APP-04: Implement ellipsoidal approximation and reference comparison](tickets/APP-04.md) | [#34](https://github.com/butahlecoq/controlled-systems-lab/issues/34) | implementation | APP-01, OPT-08 |
| [APP-03: Implement zonotope reduction and enclosure adapters](tickets/APP-03.md) | [#42](https://github.com/butahlecoq/controlled-systems-lab/issues/42) | implementation | APP-01, GEO-07 |
| [GEO-08: Provide lazy support queries and controlled materialization](tickets/GEO-08.md) | [#52](https://github.com/butahlecoq/controlled-systems-lab/issues/52) | implementation | GEO-02, GEO-03, CORE-04 |
| [EXP-03: Add later exact-versus-approximate reachability comparison artifacts](tickets/EXP-03.md) | [#99](https://github.com/butahlecoq/controlled-systems-lab/issues/99) | later-extension | EXP-02, VIZ-02, VIZ-03, APP-02, APP-03, APP-04, SYN-06, GEO-05, SYN-03, SYN-05 |
| [TEST-20: Expand exact structured-set and approximation contract tests](tickets/TEST-20.md) | [#100](https://github.com/butahlecoq/controlled-systems-lab/issues/100) | test | GEO-07, GEO-08, APP-02, APP-03, APP-04, EXP-03 |
| [REVIEW-08: Review optimizer variants, structured sets and approximation scalability](tickets/REVIEW-08.md) | [#102](https://github.com/butahlecoq/controlled-systems-lab/issues/102) | review | TEST-19, TEST-20, EXP-03 |

### Phase 5: Explicit future capability profiles

| Ticket | GitHub | Kind | Full prerequisites |
|---|---|---|---|
| [OPT-10: Extend feasible directions to declared smooth convex objectives](tickets/OPT-10.md) | [#50](https://github.com/butahlecoq/controlled-systems-lab/issues/50) | implementation | OPT-09 |
| [EXT-05: Discretize continuous models through an explicit model adapter](tickets/EXT-05.md) | [#54](https://github.com/butahlecoq/controlled-systems-lab/issues/54) | implementation | MODEL-01, SYN-06 |
| [EXT-06: Verify claim-specific certificates with validated arithmetic](tickets/EXT-06.md) | [#55](https://github.com/butahlecoq/controlled-systems-lab/issues/55) | implementation | SYN-06, APP-01 |
| [EXT-01: Add fixed-plan disturbance reachability and global worst-case reference](tickets/EXT-01.md) | [#62](https://github.com/butahlecoq/controlled-systems-lab/issues/62) | implementation | SYN-01, OPT-01, GEO-03 |
| [EXT-04: Add initial-set semantics and observation-based control workflows](tickets/EXT-04.md) | [#68](https://github.com/butahlecoq/controlled-systems-lab/issues/68) | implementation | MODEL-02, SYN-06, EXT-01 |
| [EXT-03: Add temporal-constraint strategies and exact memory lifts](tickets/EXT-03.md) | [#73](https://github.com/butahlecoq/controlled-systems-lab/issues/73) | implementation | MODEL-02, SYN-04, #9 |
| [EXT-02: Preserve all optimal branches for finite and mixed control domains](tickets/EXT-02.md) | [#76](https://github.com/butahlecoq/controlled-systems-lab/issues/76) | implementation | MODEL-02, SYN-05, SYN-06, EXT-01 |
| [TEST-21: Expand declared extension profiles with independent quantifier oracles](tickets/TEST-21.md) | [#81](https://github.com/butahlecoq/controlled-systems-lab/issues/81) | test | EXT-01, EXT-02, EXT-03, EXT-04, EXT-05, EXT-06, OPT-10 |
| [REVIEW-09: Review extension quantifiers, information patterns and native scalability](tickets/REVIEW-09.md) | [#104](https://github.com/butahlecoq/controlled-systems-lab/issues/104) | review | TEST-21, REVIEW-08 |

## Proposed file ownership map

These paths are planning proposals, not existing APIs. CORE-01/02 settle names. Record any rename before parallel work. One integrator owns shared contracts, schema and build configuration; tests and reviews own separate files and report defects through linked fixes.

| Ticket | Proposed files/modules |
|---|---|
| CORE-01 | `docs/contracts/core-interfaces.md`, `docs/architecture/decisions/0002-native-integrations.md` |
| CORE-02 | `CMakeLists.txt`, `cmake/`, `tests/contract/public_client.cpp`, `.github/workflows/native.yml` |
| CORE-03 | `include/csl/numeric/`, `src/numeric/`, `tests/unit/numeric/` |
| CORE-04 | `include/csl/registry/`, `src/registry/`, `tests/contract/registry/` |
| MODEL-01 | `include/csl/model/`, `src/model/`, `tests/unit/model/` |
| GEO-01 | `include/csl/sets/`, `src/sets/` |
| OPT-01 | `include/csl/optimization/objectives.hpp`, `src/optimization/objective_reformulation.cpp` |
| OPT-02 | `include/csl/optimization/lp_backend.hpp`, `include/csl/optimization/linear_program.hpp` |
| TEST-01 | `tests/unit/numeric/buffer_views_test.cpp`, `tests/contract/public_headers_client.cpp`, `docs/testing/native-ownership.md` |
| MODEL-02 | `include/csl/problem/domains.hpp`, `include/csl/problem/constraints.hpp`, `include/csl/problem/initial_information.hpp` |
| OPT-03 | `src/adapters/lp/`, `tests/contract/lp/` |
| OPT-08 | `include/csl/optimization/convex_backend.hpp`, `src/adapters/convex/` |
| GEO-06 | `src/geometry/hull/quickhull_2d.cpp` |
| APP-01 | `include/csl/geometry/approximation.hpp`, `docs/contracts/approximation.md` |
| RUN-01 | `src/execution/`, `include/csl/execution/` |
| TEST-02 | `tests/unit/model/affine_dynamics_test.cpp`, `tests/unit/model/observation_model_test.cpp` |
| TEST-04 | `tests/unit/objectives/evaluator_test.cpp`, `tests/unit/objectives/reformulation_test.cpp` |
| MODEL-03 | `include/csl/problem/validator.hpp`, `src/problem/validator.cpp` |
| OPT-04 | `src/optimization/phase_one/`, `tests/contract/phase_one/` |
| OPT-05 | `src/geometry/hull/lp_reducer.cpp`, `tests/unit/geometry/hull/` |
| GEO-03 | `src/adapters/polyhedral/`, `src/geometry/conversion/` |
| GEO-07 | `include/csl/sets/generator_sets.hpp`, `src/geometry/generators/` |
| APP-02 | `src/geometry/approximation/box_parallelotope.cpp` |
| APP-04 | `src/geometry/approximation/ellipsoidal.cpp`, `docs/research/ellipsoidal-comparison.md` |
| TEST-05 | `tests/contract/optimization/lp_backend_contract.cpp`, `tests/fixtures/optimization/analytic_lp_cases.json` |
| TEST-06 | `tests/contract/optimization/convex_backend_contract.cpp`, `tests/fixtures/optimization/analytic_convex_cases.json` |
| OPT-06 | `src/geometry/hull/basis_reuse_reducer.cpp` |
| OPT-07 | `src/geometry/hull/ordered_reducer.cpp`, `src/geometry/hull/grouped_reducer.cpp` |
| OPT-09 | `src/optimization/zoutendijk/projection.cpp`, `docs/research/zoutendijk-derivation.md` |
| GEO-02 | `src/geometry/polyhedral/affine_sum.cpp` |
| GEO-04 | `src/geometry/polyhedral/intersection.cpp`, `src/geometry/polyhedral/halfspace_reducer.cpp` |
| APP-03 | `src/geometry/approximation/zonotope.cpp` |
| SYN-06 | `src/verification/trajectory_verifier.cpp`, `src/verification/evidence_verifier.cpp` |
| INP-01 | `src/input/scenario_loader.cpp`, `schemas/scenario/` |
| OPT-11 | `src/geometry/hull/recursive_reducer.cpp`, `tests/unit/geometry/recursive_reducer_test.cpp` |
| OPT-12 | `src/optimization/warm_start.cpp`, `tests/contract/optimization/warm_start_test.cpp` |
| TEST-03 | `tests/unit/problem/validator_test.cpp`, `tests/contract/pipeline_capability_test.cpp` |
| TEST-07 | `tests/unit/geometry/barycentric_membership_test.cpp`, `tests/unit/geometry/hull_reducer_test.cpp` |
| OBS-01 | `include/csl/artifacts/run_statistics.hpp`, `include/csl/execution/observability.hpp`, `docs/contracts/run-statistics.md`, `tests/artifacts/run_statistics_contract.cpp` |
| OPT-10 | `src/optimization/feasible_directions/`, `docs/research/feasible-directions.md` |
| GEO-05 | `src/geometry/polyhedral/projection.cpp`, `src/reachability/nominal_predecessor.cpp` |
| GEO-08 | `src/geometry/lazy/` |
| SYN-01 | `src/reachability/nominal_forward.cpp` |
| EXT-05 | `src/model/discretization/`, `docs/contracts/time-domains.md` |
| EXT-06 | `src/verification/validated/`, `docs/contracts/certificates.md` |
| EXP-04 | `include/csl/experiments/plant_replay.hpp`, `src/experiments/plant_replay.cpp`, `tests/unit/experiments/plant_replay_test.cpp` |
| TEST-19 | `tests/unit/optimization/archive_variants_test.cpp`, `tests/unit/geometry/hull_variants_test.cpp` |
| TEST-14 | `tests/unit/verification/trajectory_verifier_test.cpp`, `tests/contract/verification/evidence_scope_test.cpp` |
| REVIEW-01 | `docs/reviews/core-composition-and-ownership.md` |
| OBS-02 | `src/execution/timing_collector.cpp`, `include/csl/execution/timing_collector.hpp`, `tests/execution/timing_collector.cpp`, `benchmarks/observability_overhead.cpp` |
| SYN-02 | `src/synthesis/terminal_minimizers.cpp`, `docs/research/terminal-minimizer-relations.md` |
| EXT-01 | `src/reachability/fixed_plan_disturbance.cpp`, `src/optimization/worst_case_vertex.cpp` |
| TEST-08 | `tests/unit/geometry/polyhedral_operations_test.cpp`, `tests/reference/polyhedral_oracles.py` |
| TEST-09 | `tests/contract/geometry/registry_contract.cpp`, `tests/unit/geometry/conversion_test.cpp` |
| TEST-10 | `tests/unit/reachability/stepper_test.cpp`, `tests/unit/reachability/predecessor_test.cpp` |
| SYN-03 | `src/synthesis/reachability_strategy.cpp`, `src/synthesis/control_recovery.cpp` |
| SYN-04 | `src/synthesis/joint_optimization_strategy.cpp` |
| EXT-04 | `src/estimation/`, `src/controllers/`, `docs/contracts/information-patterns.md` |
| TEST-11 | `tests/unit/synthesis/terminal_minimizers_test.cpp`, `tests/fixtures/synthesis/terminal_minimizer_cases.json` |
| REVIEW-02 | `docs/reviews/geometry-and-backend-substitution.md` |
| SYN-05 | `src/synthesis/witness_selector.cpp` |
| INP-03 | `examples/scenarios/`, `docs/how-to/create-scenario.md` |
| EXT-03 | `src/problem/temporal_lifts.cpp`, `src/synthesis/temporal_joint.cpp` |
| TEST-12 | `tests/unit/synthesis/direct_family_test.cpp`, `tests/reference/optimal_family_oracles.py` |
| INP-02 | `src/cli/`, `docs/how-to/run-scenario.md` |
| EXT-02 | `src/synthesis/finite_search/`, `src/synthesis/mixed_domains/` |
| TEST-13 | `tests/unit/synthesis/backward_family_test.cpp`, `tests/unit/witnesses/selector_test.cpp`, `tests/contract/synthesis/two_strategy_contract.cpp` |
| TEST-15 | `tests/unit/execution/resource_policy_test.cpp`, `tests/integration/execution/workspace_isolation_test.cpp`, `tests/integration/execution/cancellation_test.cpp` |
| OBS-03 | `include/csl/execution/instrumented_operation.hpp`, `src/execution/operation_observability.cpp`, `tests/integration/operation_observability.cpp` |
| RUN-02 | `src/experiments/batch_runner.cpp` |
| TEST-21 | `tests/contract/extensions/profile_oracles_test.cpp`, `tests/reference/extension_oracles.py` |
| REVIEW-03 | `docs/reviews/optimal-family-mathematics.md`, `docs/reviews/two-strategy-equivalence-cases.md` |
| OBS-04 | `include/csl/experiments/comparison_artifact.hpp`, `src/experiments/comparison_runner.cpp`, `tests/integration/comparison_artifact.cpp`, `benchmarks/observability_comparison.cpp` |
| TEST-16 | `tests/unit/scenarios/loader_test.cpp`, `tests/integration/experiments/comparison_artifact_test.cpp`, `tests/fixtures/scenarios/invalid/` |
| REVIEW-04 | `docs/reviews/numerical-verification-and-evidence.md` |
| OBS-05 | `src/artifacts/performance_table.cpp`, `include/csl/artifacts/performance_table.hpp`, `docs/artifacts/performance-tables.md`, `tests/artifacts/performance_table.cpp` |
| VIZ-01 | `include/csl/artifacts/plot_data.hpp`, `src/artifacts/final_plot_data.cpp`, `tests/artifacts/final_plot_data.cpp` |
| TEST-23 | `tests/integration/execution/batch_sweep_test.cpp` |
| TEST-17 | `tests/unit/observability/timing_collector_test.cpp`, `tests/integration/observability/timing_table_test.cpp`, `tests/fixtures/observability/fake_clock_traces.json` |
| REVIEW-06 | `docs/reviews/scenario-workflow-and-provenance.md` |
| VIZ-02 | `include/csl/artifacts/plot_request.hpp`, `src/artifacts/projection_plot_data.cpp`, `tests/artifacts/projection_plot_data.cpp` |
| VIZ-04 | `include/csl/experiments/replay_artifact.hpp`, `src/experiments/replay_comparison.cpp`, `tests/integration/replay_comparison.cpp` |
| EXP-01 | `src/artifacts/historical_comparison_table.cpp`, `tests/artifacts/b04_historical_comparison.cpp`, `docs/artifacts/historical-versus-reproduced.md` |
| EXP-02 | `benchmarks/configurations/module-substitution/`, `benchmarks/tools/run_module_comparison/`, `docs/benchmarks/module-substitution-protocol.md`, `tests/integration/substitution_benchmark_contract.cpp` |
| REVIEW-05 | `docs/reviews/execution-and-scalability.md`, `benchmarks/results/review-scalability/` |
| VIZ-03 | `tools/plotting/export_final_results/`, `docs/artifacts/figure-export.md`, `tests/artifacts/figure_export/` |
| TEST-22 | `tests/unit/experiments/replay_adapter_test.cpp`, `tests/integration/replay_artifact_test.cpp` |
| TEST-18 | `tests/unit/visualization/projection_data_test.cpp`, `tests/integration/visualization/fuel_projection_export_test.cpp`, `tests/fixtures/visualization/`, `docs/testing/projection-visual-qa.md` |
| EXP-03 | `benchmarks/configurations/reachability-approximations/`, `src/artifacts/approximation_comparison.cpp`, `tests/integration/approximation_comparison.cpp`, `docs/benchmarks/approximation-comparison.md` |
| TEST-20 | `tests/contract/geometry/structured_sets_test.cpp`, `tests/contract/geometry/approximation_test.cpp` |
| REVIEW-07 | `docs/reviews/observability-and-comparison-validity.md`, `benchmarks/results/review-observability/` |
| REVIEW-08 | `docs/reviews/optimizer-and-representation-extensions.md` |
| REVIEW-10 | `docs/reviews/nonlinear-replay.md` |
| REVIEW-09 | `docs/reviews/future-capability-profiles.md` |

## Planning verification

- [x] Check unique keys, acyclic dependencies and complete dependency resolution.
- [x] Check every issue has scope, acceptance criteria, test IDs, ownership and source/specification links.
- [x] Verify live issue numbers, labels and native blocking edges against the manifest.
- [x] Check documentation links, archive hashes and Git whitespace before publication completion.

No product code or product unit tests are delivered by this planning change. Implementation begins with CORE-01 after the published backlog is reviewed.
