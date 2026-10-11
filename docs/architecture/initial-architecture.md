# Initial architecture hypothesis

Date: 2026-10-11. Status: discussion draft. No product implementation is approved by this document. The concrete working proposal is C++20; architecture contracts precede benchmark validation.

## Intended product

A convenient interface for defining controlled systems, computing reachable/controllable sets, synthesizing terminal controls, running feedback simulations, and comparing algorithms reproducibly. GitHub hosts the research record, review issues and eventual software. The initial applications come from [published archive experiments](../research/baselines.md).

The core should be general within explicitly declared system classes. Fuel management, flight mechanics and future applications supply physics, units and scenarios through domain adapters.

## Selected first user workflow

Owner selection, 2026-10-11: start with optimal control planning. The initial end-to-end interface should accept a model and constraints and return a representation of all optimal control sequences and their consistent trajectories, with optimum/quality evidence and individual witness queries. The result must identify feasibility and optimality evidence.

The owner subsequently selected nominal planning without process disturbances for the first solve, while retaining more general channels and observations in the model contract. The compiled implementation direction is C++ or Rust, with C++ proposed as the working target and Python allowed for verification. Continuous actions are selected for the first solver; finite and mixed domains remain future extension points. The first published baseline, supported continuous-domain shapes/couplings, and UI form remain open. Reachability supports this workflow; feedback control remains a later workflow.

## Architectural alternatives

| Approach | Benefit | Cost | Initial assessment |
|---|---|---|---|
| One scientific-language package, modular internals | Fast exploration, fewer integration boundaries | Ecosystem/deployment tied to language; external backends still needed | Strong candidate if Julia or another suitable environment wins benchmarks |
| Language-neutral problem/result contracts plus one numerical implementation and optional bindings | Reusable interfaces, multiple numerical backends and frontends | Serialization, lifetime and compatibility rules require care | Recommended direction; keep execution in-process initially |
| Distributed services for each mathematical operation | Operational isolation and remote scheduling | Expensive data transfer, failure modes and orchestration for tightly coupled math | Defer; distribute whole jobs or coarse subproblems only when justified |

Use the concrete [modular C++20 proposal](modular-algorithms-and-solution-sets.md) to define native algorithm ports, ownership and optimal-family outputs now. Baselines validate their mathematics and performance. Python references remain independent verification tools.

## Proposed modules

| Module | Owns | Does not decide |
|---|---|---|
| Domain adapters | Physical equations, units, reference trajectories, named examples | Generic set/optimization semantics |
| Models | Affine LTI/LTV data, nonlinear callbacks, observation model, discretization metadata | Control algorithm or worker scheduling |
| Geometry | Set representations and operations, inclusion/error metadata, conversion cache | Terminal objective or policy class |
| Problems | Horizon, constraints, uncertainties, objective, information pattern and requested output | Numerical backend choice |
| Reachability | Forward propagation, nominal/robust predecessors, reachable tubes | Plant simulation or UI |
| Synthesis | Nominal solve, finite minimax search, supported feedback algorithms | Measurements, hardware I/O, visualization |
| Estimation | State/model uncertainty from observations; optional initially | Controller actuation or silent model replacement |
| Controllers | observe–solve–act lifecycle, warm starts, remaining horizon, fallback selection | Raw transport/hardware protocol |
| Simulation | Independent plant evolution, integrators, disturbance realization and measurement generation | Certification of all disturbances from one simulation |
| Execution | Resource budgets, task scheduling, cancellation, checkpoints | Mathematical admissibility or approximation direction |
| Experiments and artifacts | Scenario manifests, result traces, provenance, benchmark comparisons | Solver internals |
| Interfaces | Library API first; CLI/notebooks; optional web frontend later | Duplicated scientific algorithms |

Numerical backend adapters supply LP/QP/SOCP/MIP/global optimization and polyhedral routines behind geometry/synthesis. They translate statuses and residuals into common result fields. A solver success flag alone is not the controller guarantee.

~~~mermaid
flowchart TD
    UI["Library / CLI / notebook / optional UI"] --> EX["Experiment runner"]
    EX --> P["Validated problem"]
    D["Domain adapters"] --> M["Models and discretization"]
    M --> P
    P --> R["Reachability"]
    P --> S["Synthesis"]
    R --> G["Geometry and representations"]
    S --> R
    S --> N["Numerical backend adapters"]
    G --> N
    EX --> C["Controller lifecycle"]
    C --> S
    C --> E["State / model estimation"]
    C --> SIM["Independent plant simulator"]
    EX --> RUN["Execution and resource policy"]
    EX --> A["Artifacts / traces / comparison"]
~~~

Arrows show responsibilities that call or use one another, not mandatory remote service boundaries. Controller feedback naturally forms a runtime loop with measurements; the diagram summarizes dependency roles.

The detailed [linear-system contract](linear-system-contract.md) describes dynamics, observation channels, timing, and natural special cases.

## Mathematical data contracts

A model snapshot contains dimensions, stage indexing, A/B/E/c or supported evaluation callbacks, coordinate convention, time grid, scalar type, sparsity/layout, units metadata, and provenance. Matrices for transitions number T; state constraints number T+1. A constant model is a compact view over the same contract.

Control domains are distinct types: continuous set with declared convexity, finite catalogue, mixed-integer domain. Continuous control values are selected first; this is separate from the time domain and from hybrid dynamics with modes/guards. Uncertainty declares additive/model/measurement roles and stagewise-independent, correlated, fixed-parameter or statistical semantics. Converting a fixed unknown parameter into independent per-step errors must be an explicit conservative relaxation.

An objective describes terminal and optional stage terms, minimization/maximization use, known convexity, and weighted/nondimensional coordinates. User callbacks may be supported experimentally, but cannot inherit a convexity certificate merely because a user supplied a name.

A set object exposes ambient/affine dimension, representation, exactness/enclosure metadata and supported operations. Solvers may hold native buffers and lazy expressions. Materialization, projection and H/V conversion are explicit potentially expensive operations. A set operation returns the relation of its output to the requested mathematical set.

## Result contracts

Keep these independent:

- **Termination status:** completed, infeasible, unbounded, unsupported, iteration limit, deadline, cancelled, numerical failure.
- **Feasibility evidence:** checked constraints and residuals; robust containment or declared approximation.
- **Optimality evidence:** global optimum, valid objective bounds/gap, local stationary result, feasible candidate, or no candidate.
- **Set evidence:** exact representation, inner/outer enclosure, sampled set, heuristic result; reference set and error bound.
- **Model validity:** assumptions, region, residual/integration enclosure and uncertainty interpretation.

A timeout can return a feasible incumbent with a valid bound. A completed local solve can lack global optimality. No feasible plan discovered is not a proof of infeasibility unless the search or certificate justifies it.

Store the optimal solution family, completeness evidence, selected witness trajectory/policy, objective, worst-case witness when available, constraint margins, solver statistics, set sizes, wall time, memory, backend versions, seed, problem hash and source baseline ID. Tie handling, family coverage and finite versus implicit output must be explicit. Stage marginals alone do not preserve joint solutions.

## Algorithm extension contract

Each plugin declares:

1. Supported model, control domain, information pattern, objective, uncertainty and set representation.
2. Required properties such as invertible A, compactness, convexity, full dimensionality, Lipschitz bounds or finite actions.
3. Returned output and guarantee, approximation direction, tolerance/scalar support.
4. State ownership, thread safety, random behavior, cancellation and checkpoint support.
5. Cost-relevant features: generator/vertex growth, sparse structure, warm starts, GPU or batch availability.

Capability checking occurs before execution. Unsupported combinations fail clearly. Conversions and relaxations are logged with their assumptions and possible loss of guarantee.

Adding a method should require an adapter, capability description, source reference and compatible benchmark records. It should not require editing fuel physics, plotting code, scheduler or every other algorithm.

## Four concrete workflows

**Reachability study:** define model and initial/control/uncertainty sets → choose existential or fixed-plan/robust semantics → select exact or approximation backend → compute a tube → inspect projections/support values → export guarantee and performance data.

**Nominal terminal solve:** load B04 → validate objective/constraints → choose forward/backward set construction or direct sparse optimization → construct the optimal joint family and recover witnesses → independently evaluate dynamics, constraints, objective and family consistency → compare with reported values.

**Finite-action minimax:** load B07 or B08 → stream control prefixes → propagate all modeled disturbances → reject robustly infeasible prefixes → compute a justified terminal worst case → retain incumbent and bounds → compare action plan, objective, margins and runtime.

**Adaptive simulation:** load B09 after criterion restoration → observe state or estimated state set → solve remaining terminal problem → apply first action → advance an independent nonlinear plant → record observations and replan. Compare sampled realized cost and any model-based worst-case bound as different metrics.

## Parallel execution and state ownership

Keep immutable problem data shared and mutable solver workspaces isolated per worker. Schedule independent experiments, control prefixes or support directions at suitable granularity. Do not parallelize a constrained horizon as if its stages were independent.

A local execution policy controls worker count, numerical-library threads, memory limit, deadlines and device assignment. A future distributed executor uses the same job contracts and coarse artifacts. Centralize neither every matrix multiplication nor every vertex operation in a network service.

Cache deterministic derived objects by model/data hash, operation parameters, tolerance, backend version and representation. Warm-start state belongs to a specific compatible solve sequence. Checkpoints include the search frontier/incumbent and reproducible seed/resource metadata.

## First repository structure proposed

~~~text
docs/
  research/       # equations, source inventory, bibliography, baselines, reviews
  architecture/   # hypotheses, performance criteria, later decisions
benchmarks/       # later: complete executable scenarios and result manifests
examples/         # later: user-facing end-to-end studies
core/             # later: chosen implementation, not yet created
adapters/         # later: domain and numerical integration
.github/
  ISSUE_TEMPLATE/ # scientific correction, reproduction, algorithm proposal
~~~

The proposed native implementation is C++20 with separate module/adaptor build targets; see the concrete modular design. Keep archival raw files outside the public tracked set until release scope is agreed.

## Decisions still open

Owner preference between C++ and Rust, primary user interface, additional application domains, typical dimensions/horizons, timing/resource requirements, required guarantee strength, observation assumptions, and the first complete executable baseline. The first solve is nominal and returns the optimal solution family; the contracts remain general. Architecture and language boundaries are discussed now, while benchmark evidence validates implementations. See [interview agenda](../research/open-questions.md).
