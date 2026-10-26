# Stage-resolved reachable-set figures

This note records the current route capabilities and the proposed architecture for issue #708. It describes existing code separately from the future contract. It does not claim that every route currently supplies stage geometry.

## Existing route capabilities

| Route and source | Existing stage output | Metadata, relation, and assurance | Current limit for stage figures |
|---|---|---|---|
| `reachability::nominal_forward` (`include/csl/reachability/nominal_forward.hpp`, `src/reachability/nominal_forward.cpp`) | `ForwardTube::stages` contains the initial marginal and later state marginals. A failure retains its completed prefix and may retain a partial marginal. | The interface is dimension-generic. Each marginal is an `OperationResult` with geometry evidence and provider lineage. Scenario labels and units are not attached uniformly to the tube. | The implemented profile is discrete, nominal, open loop, and starts from a known point. It is not a general uncertain or feedback reachability route. |
| `reachability::fixed_plan_disturbance` (`include/csl/reachability/fixed_plan_disturbance.hpp`, `src/reachability/fixed_plan_disturbance.cpp`) | `FixedPlanReachable::stages` contains the initial set and generated later-stage vertex descriptions. | `LinearSystem` and `SetData` carry the numerical dimension. The result records an `Assurance` value, but no per-stage provider or geometry-operation evidence. It has no common coordinate-name and unit schema. | This is a finite numerical fixed-plan reference with a point budget. An unsafe successor rejects the plan. It does not represent the union of all plans or an optimal family. |
| `reachability::finite_feedback` (`include/csl/reachability/finite_feedback.hpp`, `src/reachability/finite_feedback.cpp`) | `Game::stages` stores safe-state flags and indexed successor relations. `Policy` stores robustly admissible actions by state and stage. | States are discrete ordinals. The model has no geometric embedding, coordinate names, or physical units, and the policy carries no geometric relation evidence. | The result is a finite-state policy, not a geometric state set. A geometric plot needs a separate declared state embedding. |
| `reachability::nominal_predecessor` (`include/csl/reachability/nominal_predecessor.hpp`, `src/reachability/nominal_predecessor.cpp`) | One predecessor `OperationResult` and its projection lineage. | The request carries ordered state, control, and target set handles. The result carries geometry evidence and projection-provider provenance. | This is a one-step backward set operation, not a forward stage sequence. |
| Strategy A (`include/csl/synthesis/strategy_a/strategy.hpp`, `src/synthesis/strategy_a/strategy.cpp`) | `CandidateHistory` retains a nominal forward tube alongside terminal and recovery relations. | It uses the nominal route's per-stage geometry evidence. Its synthesis result is a candidate relaxation scoped to the supplied forward slice, not a verified complete optimal-history family. | It inherits the nominal route's state profile and metadata limits. Recovery relations and stage marginals have different meanings. |
| Strategy B (`include/csl/synthesis/strategy_b/direct_joint.hpp`, `src/synthesis/strategy_b/direct_joint.cpp`) | `DirectJointPayload` retains a coupled state/control H relation and source-row lineage. | The payload records the selected provider and diagnostics. Its comments explicitly withhold binary64 program equivalence and numerical coverage claims for the optimal relation. Coordinates need route-owned mappings. | It does not expose a common `R0..RT` state-set sequence. Do not project unrelated transition columns as stage sets. |
| Terminal minimization (`include/csl/synthesis/terminal_minimizers.hpp`, `src/synthesis/terminal_minimizers.cpp`) | `TerminalSlice` and `TerminalMinimizers` retain a feasible terminal set and terminal minimizer relation. | The result has termination and optimum-evidence fields. Its construction support defaults to `Unestablished`; it has no separate coordinate schema. | This is terminal-only geometry. It does not supply prior stages or a trajectory. |
| Hybrid projected reachability (`include/csl/synthesis/hybrid_path_program.hpp`, `src/synthesis/hybrid_projected_reachability.cpp`) | The current adapter builds a coupled relation for one admitted scalar transition and projects its terminal state. | The result records numerical assurance and, for a projected state, provider provenance and scoped geometry evidence. | It supports one scalar source and target state under strict path and relation limits. It does not currently provide intermediate state marginals for a general hybrid path. |
| `simulation::replay` (`include/csl/simulation/nonlinear_replay.hpp`, `src/simulation/nonlinear_replay.cpp`) | `ReplayRecord::states` contains one sampled state per time point for a supplied control history. | The plant declares state/control units and optional time samples. Replay status and diagnostics describe the trajectory; the result has no set relation or reachability assurance. | It is one replayed trajectory. It is not a reachable set and gives no nonlinear optimality guarantee. |

Current report drivers include `benchmarks/reporting/syn01/nominal_forward_driver.cpp`, `benchmarks/reporting/ext01/fixed_plan_driver.cpp`, `benchmarks/reporting/issue6/`, and `benchmarks/reporting/exp04/driver.cpp`. The `syn01` driver receives a `ForwardTube`; `ext01` receives fixed-plan stage vertex descriptions; the issue6 captures preserve terminal fuel sets but not stage histories; `exp04` stores sampled replay states. `benchmarks/reporting/finite_feedback/driver.cpp` exercises the finite-state feedback policy. These examples do not establish support for every task or dimension. The child integration issue must refresh the driver list from main before adding adapters.

The report layer has a different responsibility. `PlotData` in `include/csl/artifacts/plot_data.hpp` stores selected trajectories and their evidence. `PlotRequest` in `include/csl/artifacts/plot_request.hpp` handles a single pair and, for set geometry, a single stage. The `csl.plot-document/1` codec records completed plot results. Python validates saved records and renders SVG and PNG. The shared style and offline gallery live under `scripts/reports/`.

The fuel adapters read frozen report records. They do not recover missing stage sets. The visual route inventory covers report producers, not mathematical task routes. Issue #684 owns that report inventory. Issue #686 and PR #700 own saved-data control and witness companions, including the requested fuel flow/flow and stock/stock panels. This note adds no edits to either work package.

## Proposed ownership and data flow

```mermaid
flowchart LR
    A[Task route] --> B[Route stage source]
    C[Metadata and ordered coordinate request] --> D[Stage projection capture]
    B --> D
    E[Registered geometry projection port] --> D
    D --> F[Validated StageProjectionBatch]
    F --> G[Versioned codec]
    G --> H[Saved batch]
    H --> I[Offline SVG PNG and HTML renderer]
```

Task routes own the mathematical output and report which stage sets they can supply. A route adapter exposes those actual sets and their identity, relation, assurance, and evidence. It does not invent missing stages or rerun a task. When a user requests figures during a new task run, the driver can capture stage sets from that run. When a saved run lacks stage sets, capture reports that gap.

The generic capture module resolves each requested coordinate reference against a coordinate schema once. It sends an explicit projection request for each available stage and requested pair through the existing `GeometryPort`. It keeps the source set, stage, ordered coordinates, operation identity, provider, relation, assurance, evidence, and query resource record. It does not enumerate full-dimensional vertices as a shortcut.

The batch stores one typed outcome for every pair and every canonical stage from R0 through RT. An outcome can carry a rendered two-dimensional geometry, an empty result, an unsupported or unbounded result, or a typed stopped, failed, or missing-stage status. If one route stage has labelled branches, the record preserves those component identities and does not replace them with a convex hull. Trajectories remain separate series with their own method or policy identity and stage/time axis. A replay can lie outside a linear reachable set and is not clipped or called contained without a separate check.

A versioned domain record is the boundary between capture and rendering. The codec owns validation and schema conversion. The renderer reads only a validated saved record. It calls no task route, solver, geometry provider, or set conversion. The generated figures use the shared quantitative style, preserve coordinate order and units, label R0 and RT, and show negative fuel stock values when present.

## Request and batch contract

A request contains an ordered list of coordinate pairs, an optional trajectory selection, a stage range, and an explicit projection requirement. Each coordinate reference is either an ordinal or a declared coordinate name. Boundary validation rejects unknown, repeated-within-pair, or out-of-range references. The resolver stores the resulting zero-based indices and matching labels and units in the batch. Pair order defines axis order. Duplicate pairs are rejected at the request boundary.

The route adapter supplies a canonical ordered stage grid and the source relation for each stage. A `StageProjectionBatch` binds the source run, problem, route, scenario or model identity, stage identities, and coordinate schema. Each pair contains exactly one outcome for every stage identity. Missing or stopped stages use explicit outcomes; they do not disappear from the record. Relation and assurance remain scoped to the actual source and projection operation. No set marginal implies a complete optimal-history family.

The batch codec uses a new versioned schema unless a reviewed compatibility path can represent the distinct stage-set evidence without changing `csl.plot-document/1` trajectory semantics. Persist concrete two-dimensional geometry needed by the renderer, not a live `SetHandle`. Unsupported output representations remain explicit outcomes rather than scalar bounds, sampled hulls, or zero-valued placeholders.

Projection capture is opt-in. A task without a plot request performs no additional projection. Offline rendering can rerun from a saved batch without repeating task execution or geometry operations. A new scientific calculation or task run requires an explicit capture command and a separately identified artifact.

## Work packages and ownership

1. [#709 route audit and contract reconciliation](https://github.com/butahlecoq/controlled-systems-lab/issues/709) owns `docs/architecture/stage-projection-visualization.md` and scope updates in `docs/superpowers/specs/viz02-projection-architecture.md` and `docs/superpowers/specs/viz03-figure-document-design.md`. It leaves `visual-route-inventory.json` to #684 and the #686/#700 report files untouched.
2. [#710 request and capture API](https://github.com/butahlecoq/controlled-systems-lab/issues/710) owns `include/csl/artifacts/stage_projection_request.hpp`, `src/artifacts/stage_projection_request.cpp`, `include/csl/artifacts/stage_projection_capture.hpp`, `src/artifacts/stage_projection_capture.cpp`, `src/artifacts/Module.cmake`, and `tests/artifacts/stage_projection_capture_tests.cpp`. It adds typed ordered pairs, coordinate resolution, route-owned stage sources, and capture through existing geometry ports. It preserves partial and unsupported outcomes and adds no projection cost to ordinary runs. Blocked by #709.
3. [#711 saved batch schema and codec](https://github.com/butahlecoq/controlled-systems-lab/issues/711) owns `include/csl/artifacts/stage_projection_batch.hpp`, `src/artifacts/stage_projection_batch.cpp`, `src/artifacts/stage_projection_batch_json.cpp`, `scripts/reports/stage_projection_data.py`, and their schema and round-trip fixtures. It binds stage geometry to its source relation, request, coordinates, provider, and evidence. Blocked by #710.
4. [#712 offline figure renderer](https://github.com/butahlecoq/controlled-systems-lab/issues/712) owns `scripts/reports/stage_projection_figures.py`, `scripts/reports/render_stage_projections.py`, and `tests/reporting/test_stage_projection_figures.py`. It renders saved batches to SVG, PNG, and offline HTML with the existing quantitative style. It keeps trajectory overlays visually and evidentially separate from sets. Blocked by #711.
5. [#713 route adapters, demonstrations, and documentation](https://github.com/butahlecoq/controlled-systems-lab/issues/713) owns new adapters and demonstration inputs under `benchmarks/reporting/stage-projection/`, plus `scripts/reports/stage_projection_route_capabilities.json` and its documentation. It connects only routes that expose supported stage data, adds a fuel preset and a nonfuel demonstration through the same interface, and records other route limits. It does not edit files owned by active issues. Blocked by #710, #711, and #712.
6. [#714 independent checks and visual review](https://github.com/butahlecoq/controlled-systems-lab/issues/714) owns end-to-end tests under `tests/artifacts/` and `tests/reporting/` and a visual review record under `reports/algorithm-results/stage-projection-demo/`. It verifies analytic projections, stage alignment, route identities, incomplete outcomes, schema integrity, and no geometry calls in rendering. It inspects the actual fuel and nonfuel SVG, PNG, narrow layout, and print output. Blocked by #713.

The live GitHub dependency chain is #709 → #710 → #711 → #712 → #713 → #714 → #708. #713 also names #710, #711, and #712 as direct prerequisites. No package authorizes a benchmark sweep.

## Design history and constraints

Closed issue #91 deliberately limited `PlotRequest` to explicit final-set projection or witness-coordinate selection and excluded all-stage viewers. PR #666 implemented that single-stage contract. Issue #708 changes that scope. The new batch therefore adds stage-sequence data without changing the meaning of `PlotData` or the old plot document.

The design reuses existing geometry projection admission, evidence checks, quantitative figure style, and offline rendering. It preserves operation-specific guarantees, route-specific information patterns, immutable report bundles, and published result identifiers. It does not claim exact arithmetic when evidence is unestablished, infer reachable sets from trajectories, or treat stage marginals as one joint history relation.

## Source map

- Nominal stage results: `include/csl/reachability/nominal_forward.hpp` and `src/reachability/nominal_forward.cpp`.
- Fixed-plan stage sets: `include/csl/reachability/fixed_plan_disturbance.hpp` and `src/reachability/fixed_plan_disturbance.cpp`.
- Generic projection operation: `include/csl/geometry/contracts.hpp` and `include/csl/geometry/polyhedral_projection.hpp`.
- Existing trajectory and final projection data: `include/csl/artifacts/plot_data.hpp` and `include/csl/artifacts/plot_request.hpp`.
- Existing saved-data validator and renderer: `scripts/reports/control_figure_data.py`, `scripts/reports/control_figures.py`, and `scripts/reports/figure_style.py`.
- Route and result evidence boundary: `docs/architecture/published-algorithm-results.md`.
