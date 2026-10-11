# Modular algorithms and optimal solution families

Date: 2026-10-11. Status: concrete architecture proposal for discussion; no product classes are implemented.

## Decisions and implementation direction

The owner requires architecture before numerical benchmarking, replaceable mathematical algorithms, and an initial result representing all optimal plans. The first workflow is nominal optimal control planning with continuous actions. Finite and mixed control domains remain explicit future extension points. Disturbance, observation and richer problem classes remain part of the [model contract](linear-system-contract.md).

Use C++20 as the proposed compiled implementation target now, with a library API and CMake packaging. This is a design choice for review, not a benchmark result or an owner choice of C++ over Rust. Python remains an independent mathematical reference and an optional future binding. Benchmarks validate algorithms, integrations and performance within these boundaries; they do not postpone defining the boundaries. Rust is a possible alternative, but the design below makes concrete C++ ownership and extension choices.

The first public request is an optimal solution family. Feasible sets are internal mathematical objects. Near-optimal output is a future explicit request, not the initial product requirement.

## Continuous-first control domains and future finite/hybrid extensions

Owner decision: first implement continuous control actions. Keep ContinuousDomain, FiniteDomain and MixedDomain as distinct domain contracts from the start. These are value domains, not a choice of continuous-time versus discrete-time dynamics. Convexity is an independently declared property; a continuous domain can be nonconvex. The proposed first solver uses affine discrete dynamics and compatible convex/polyhedral domains.

For a finite action catalog {v_1,...,v_k}, a one-hot representation is u=sum_j delta_j v_j, sum_j delta_j=1, delta_j in {0,1}. Replacing these binary variables by continuous weights changes the problem to a convex-hull relaxation. A finite-horizon method may branch on discrete choices and solve continuous subproblems under each choice; a compatible mixed-integer formulation is another route. [HiGHS](https://highs.dev/) provides an LP/MIP backend candidate, not a general solver for arbitrary hybrid dynamics or a complete optimal-family extractor.

Mixed controls combine discrete choices with continuous values and conditional constraints. Hybrid dynamics additionally need a mode variable, mode-dependent evolution, guards, permitted transitions and possibly resets. Keep that model extension separate from the control-domain extension. Neither is covered automatically by the initial continuous solver.

Future strategies must return their supported optimal relation/union and completeness evidence. Obtaining one optimum of a mixed-integer problem does not enumerate all optimal branches or the continuous families within them. Preserve equal-cost branches and temporal dependence. Leave these capabilities explicit and unsupported until the corresponding algorithms and theory have been reviewed.

### Temporal constraints: reserved, excluded from first experiments

Owner decision: preserve optional TemporalLinearConstraints in the general problem contract, while the first archival experiments use only their original stagewise state/control constraints. Do not introduce rate limits or other cross-step couplings by default. The initial baseline strategy declares stagewise-only support and rejects unsupported coupled requests; an empty temporal-constraint collection is the natural specialization.

The [temporal-coupling note](../research/temporal-coupling.md) proves convexity/attainment under specified nominal affine/polyhedral assumptions, gives a counterexample to physical-state-only propagation, and constructs an exact increment-state lift for one-step slew limits. That lift preserves nonsingularity when the original A_t is nonsingular, using augmented state constraints to enforce absolute input bounds. This is not a blanket compatibility proof for all historical implementations or all temporal constraints.

Future MemoryLift and joint-relation strategies declare which couplings they support, preserve original-to-auxiliary coordinate mappings, and record initial memory. Augmented dimension, intersections, representation class and numerical evidence must be checked. A new constrained study gets its own scenario ID and comparison record. Exact mathematical equivalence does not promise unchanged numerical cost or exact ordinary-zonotope closure.

### Structured objective modules for the first version

Owner agreement: begin with explicit linear, convex quadratic and weighted Euclidean terminal objectives. General user-supplied functions remain a future extension with value/derivative oracles and declared properties. The first archival experiments retain the original objective and weights.

| ObjectiveSpec | Mathematical form | Required data / capabilities |
|---|---|---|
| LinearTerminal | c^T x_T+d | Coordinate dimension and coefficient/offset conventions; linear minimization |
| ConvexQuadraticTerminal | (1/2)x_T^T Q x_T+q^T x_T+c, Q symmetric positive semidefinite | Explicit factor convention, PSD evidence and compatible convex quadratic backend |
| AffineResidualNormTerminal | norm(L x_T-r,2) | Residual coordinates/scaling, rectangular L and target r; compatible norm/conic or equivalent quadratic method |

The weighted-target form norm(W(x_T-x_d),2) is a special case with L=W and r=W x_d. Allow rectangular residual maps, not only diagonal weights: the B04 criterion includes a residual combining two mass coordinates. Units, scaling and the physical meaning of each residual remain scenario metadata.

The norm objective can be minimized through its square without changing minimizers, since the square is strictly increasing on nonnegative values. For the quadratic convention above, its square has Q=2 L^T L, q=-2 L^T r and c=r^T r. Report the original norm for comparisons and label any transformed solver objective. Do not apply this equivalence blindly to a sum containing other objective terms.

Convexity, differentiability and a concrete solver representation are distinct capabilities; the norm can be nondifferentiable at zero residual. A backend must support the requested form or an explicit justified reformulation. A future opaque callback must not silently inherit convexity, gradient or certificate claims.

ObjectiveModel supplies the primary criterion; ObjectiveReformulator creates compatible backend data and preserves the source-to-solver mapping; ObjectiveEvaluator independently evaluates returned trajectories in original coordinates. Diagnostics such as control energy or smoothness remain comparison metrics unless the problem explicitly includes them in its primary objective.

## 1. What constitutes the result

For nominal dynamics and a specified initial condition, let z=(x_0,...,x_T,u_0,...,u_{T-1}). Define F as the joint feasible relation containing dynamics, all state/control constraints and any temporal coupling. For terminal cost phi:

~~~math
v^*=\min_{z\in F}\phi(x_T),\qquad
Z^*=\{z\in F:\phi(x_T)=v^*\},\qquad
U^*=\operatorname{proj}_{u_{0:T-1}} Z^*.
~~~

Assume an attained finite minimum when requesting this family. Infeasible, unbounded, finite but unattained infimum, and unsupported problems must be distinguished. An uncertain initial set also needs a declared quantifier; an existential union over initial states is not a robust plan for every initial state.

The result stores Z* or an equivalent parametric/implicit relation, exposes its control projection, and can produce individual witnesses. It must retain dependence between stages and between states and controls. A list of per-stage reachable sets or admissible control intervals does not specify the solution family.

For example, x_{t+1}=x_t+u_t, x_0=0, T=2, u_t in [0,1], and phi=(x_2-1)^2 yield v*=0 and u_0+u_1=1. Both control marginals are [0,1]. Their Cartesian product wrongly admits (0,0) and (1,1). Even a unique optimal terminal state can have infinitely many optimal plans.

For terminal-only cost, first determine the entire terminal minimizer set M_T=argmin_{x in R_T} phi(x), then preserve all feasible trajectories ending in M_T. Selecting one terminal minimizer and running backward recovery can discard other optima. With stage costs, augment the relation or use a suitable value-function formulation; this terminal-only decomposition no longer suffices.

| Family representation | Suitable case | Required qualification |
|---|---|---|
| Joint H-polyhedron / optimal face | Polyhedral feasible relation, linear objective, attained optimum | Include equalities and rays if unbounded; vertex list alone needs boundedness |
| Generator coordinates with constraints | Affine dynamics, zonotope/CZ domains and compatible optimality constraints | Preserve shared variables and stage labels; do not treat dependent factors independently |
| Implicit convex relation | General supported convex criterion | Minimized value plus sublevel constraint; may not be polyhedral |
| Trie/DAG or mixed-integer relation | Finite/mixed control domains | Preserve discrete identities and temporal consistency; output may be exponential |
| Selected witnesses | Diagnostic or budget-limited computation | Does not by itself represent all optimal solutions |

Draft SolutionFamily operations: witness(selection), contains(candidate,tolerance), project(coordinates), optimize_secondary(criterion), and enumerate_finite(budget) when finite enumeration is supported. Query results carry their own termination and numerical evidence. Secondary selection does not alter the stored primary optimal family. A projection can stay lazy.

### Selected first query and comparison workflow

Owner decision: first extract different complete optimal control sequences and their consistent trajectories, then compare approaches visually, numerically and by computation time. This query does not replace the requirement to represent the optimal family.

Proposed separation: a WitnessSelector queries the family, a TrajectoryVerifier independently checks model/constraint/objective consistency, and a ComparisonRunner records aligned experiment results. Plot/export code consumes those records and contains no scientific solver logic. Selector identity, settings and any random seed belong in result provenance independently of the synthesis algorithm.

A request for k distinct witnesses records requested/returned counts, duplicate filtering and the selection rule. A singleton family may provide only one distinct solution. Failure to discover more witnesses does not prove uniqueness. Selection need not be uniformly random; no such sampling guarantee is implied. The default selector is proposed to be reproducible, with explicit diversity settings for multi-witness exploration.

| Comparison output | Fields / interpretation |
|---|---|
| Visual | Controls against the common time grid, state trajectories, terminal states, bounds/targets; identify witnesses and algorithms |
| Numerical | Primary objective, dynamics residuals, constraint violations/margins, terminal error under declared units/scaling, optimality gap when justified |
| Family evidence | Representation, coverage/completeness, assumptions and approximation status, separately from the quality of selected witnesses |
| Runtime | Setup, family construction, first-witness extraction, additional-witness extraction, independent verification, end-to-end time; plot/export separately |
| Resources | Peak memory, representation size, worker/library thread counts, hardware and backend versions |

Use the same problem data, primary objective, tolerances, output scope and witness request for comparable runs. Use a common selector when supported and record incompatible selection semantics. Different optimal trajectories can have equal primary cost; shape differences alone do not establish that one algorithm is better. A method returning one witness without the family has different output scope, even if its selected trajectory is optimal.

### Two verification levels

Owner decision: include numerical and validated/certificate-based verification in the architecture; implement numerical verification first. Mathematical assumptions and theoretical guarantees remain documented for every algorithm at both levels.

An EvidenceVerifier is a replaceable port alongside the solver. NumericalVerification checks selected trajectories against immutable problem data, recomputes the primary objective, and reports dynamics/constraint residuals with explicit absolute/relative tolerances, coordinate scales, arithmetic precision and verifier version. Preserve backend diagnostics and objective-bound provenance. A solver flag, small residual or agreement with a historical number does not establish global optimality or complete optimizer coverage.

A future ValidatedVerification adapter checks supported certificates and accounts for rounding/truncation under declared arithmetic and model assumptions. Feasibility, objective bounds, set inclusion and family completeness require evidence suited to their respective claims. A generic certificate container alone does not create a proof.

Result fields identify requested/applied verification levels, evidence scope, assumptions and verifier status. Distinguish trajectory feasibility, optimality evidence and family completeness. Store evidence references/data in versioned artifacts independently of plots. A request for validated evidence unsupported by the configured pipeline returns that limitation explicitly; numerical verification must not be silently relabeled as validated.

This decision does not authorize substituting near-optimal or sampled output for the requested optimal family. The first implementation reports its actual numerical evidence and any unestablished completeness rather than claiming a certified family.

Numerical solver success does not certify completeness. Family evidence identifies the mathematical target, supported plan/policy class, exact or enclosure relation, tolerances, objective bounds, and complete/partial/unknown coverage. Algebraically exact set construction in floating point is distinct from validated enclosure.

If only certified bounds L <= v* <= U are known, the feasible family phi <= U+epsilon is a candidate relaxation containing exact optimizers, with cost gap at most U-L+epsilon. It is not automatically the exact optimizer set. Conversely, a set of tied floating-point incumbents is not proof that no other optimizer exists. The initial API must report incomplete evidence rather than silently substituting approximate or sampled output.

## 2. Replaceable modules at the mathematical level

| Module / contract | Responsibility | Replacement examples |
|---|---|---|
| ProblemModel | Dynamics, domains, objective, horizon, uncertainty and information pattern | Affine discrete model, later nonlinear/descriptor adapters |
| SetRepresentation | Native mathematical data, dimensions, coordinate dependencies and query capabilities | V/H polyhedra, zonotopes, CZ, ellipsoids, implicit/union forms |
| SetOperator | One mathematical operation and its evidence | Affine image, sum, intersection, projection, preimage, support, containment |
| RepresentationConverter | Equivalent representation under declared assumptions | H/V conversion, zonotope-to-V, polytope-to-CZ |
| SetApproximator | Inner or outer enclosure with a budget/quality criterion | Generator reduction, enclosing ellipsoid, inscribed polytope, direction templates |
| HullReducer | Remove redundant points/inequalities without changing a hull | Phase-I basis reuse, generic membership LPs, geometric algorithms |
| LPBackend | Linear feasibility/minimization, statuses, residuals, bounds | Custom phase-I implementation, HiGHS adapter, exact-arithmetic reference |
| ConvexBackend | Supported QP/SOCP/SDP/general convex minimization | OSQP, conic solver, supported differentiable-convex implementation |
| ReachabilityStepper | Compose stage propagation and admissibility operations | Exact generator propagation, polyhedral method, ellipsoidal approximation |
| PredecessorAlgorithm | Nominal or robust predecessor with explicit quantifiers | Projection-based, inverse-based when allowed, structured CZ method |
| TerminalOptimizer | Optimum evidence and a representation of terminal minimizers | Polyhedral optimal face, convex implicit relation, finite search |
| OptimalFamilyBuilder | Preserve complete feasible histories satisfying optimality | Joint sparse constraints, dependency-preserving generators, finite DAG |
| ControlRecoveryOracle | Recover a consistent witness or conditional control fiber | Barycentric feasibility, joint optimization, relation queries |
| SynthesisStrategy | Assemble compatible algorithms into an end-to-end solve | Forward/backward set strategy, direct joint optimization |
| WorstCaseOracle | Global maximum/bounds for later minimax workflows | Vertex maximum, certified branch-and-bound, supported analytic formula |
| ExecutionContext | Workspace allocation, cancellation, resource budget, deterministic scheduling | Local workers, later coarse distributed jobs |

Numerical backends and algorithm strategies are independent choices. A HullReducer can use an LPBackend, but a specialized reducer may need optional basis diagnostics. A ConvexBackend does not become a valid global maximizer of a convex function merely by negating its objective.

High-level dependency direction:

~~~mermaid
flowchart TD
    P[Problem and requested family] --> S[Synthesis strategy]
    S --> R[Reachability / predecessor algorithms]
    S --> T[Terminal optimizer]
    S --> F[Optimal family builder]
    F --> Q[Recovery and family queries]
    R --> G[Set operators / converters / approximators]
    T --> G
    Q --> G
    G --> H[Hull and redundancy algorithms]
    G --> B[LP / convex / geometry backends]
    H --> B
    T --> B
    F --> B
    E[Execution context] -. workspaces and budgets .-> S
~~~

An operator registry resolves operation ID, input representation IDs, scalar type, requested output/guarantee and required capabilities. Keep this extensible rather than a closed enum switch in every controller. Representation implementations supply native operation adapters; shared queries form a small common surface. The registry selects a validated pipeline and records every conversion or relaxation. Unsupported combinations fail before expensive work.

## 3. The unusual historical LP procedures

L03 describes convex-hull membership by nonnegative barycentric coefficients: V lambda=p, 1^T lambda=1, lambda>=0. Its specialized procedure uses the first phase of simplex with an inverse basis and reuses information from a solve to classify other candidates. This is a feasibility/hull algorithm, not just ordinary linear objective minimization.

The L14 listing similarly solves joint barycentric feasibility when recovering a transition: A V lambda+B U mu=x_next, lambda>=0, mu>=0, 1^T lambda=1, 1^T mu=1. V and U contain candidate state and control vertices. Offsets and stage indexing must follow the chosen transition contract.

Separate ConvexHullMembershipOracle and ControlRecoveryOracle from the underlying LP implementation. Standard backends may implement these via zero-objective feasibility LPs. The specialized HullReducer can request BasisDiagnostics, warm starts or candidate-classification data. An adapter that lacks them must explicitly use a different supported algorithm; it cannot pretend to reproduce the specialized method's work or complexity. Audit any assertion that every selected basis point is an extreme point.

L14's SLSQP call selects one terminal point. Reusing that output unchanged would conflict with the selected solution-family contract unless uniqueness and full trajectory coverage were established. Historical results remain baselines, with output scope recorded separately.

## 4. Representations and approximation direction

Start with a catalog, not one universal representation. Support empty, singleton, universal and lower-dimensional sets naturally. Unbounded domains need an appropriate representation and solver capability.

- V/H polyhedra: reference geometry, equalities and optimal faces; conversions can cause large output.
- Boxes/parallelotopes: inexpensive bounds under compatible operations; a full-dimensional parallelotope has n independent generators.
- Zonotopes: exact affine images and Minkowski sums; intersections generally require another form or approximation.
- Constrained zonotopes: generator coordinates with equalities; useful for polytopal constraints and dependency preservation.
- Ellipsoids and families of ellipsoids: exact affine images, directional inner/outer approximations, lazy intersections/unions.
- Lazy support functions and expression graphs: defer expensive materialization; finite sampled directions generally define an approximation, not the full set.
- Hybrid zonotopes/unions: retain nonconvex discrete alternatives rather than silently convexifying finite actions.
- Polynomial/constrained polynomial zonotopes and ellipsotopes: extension candidates with distinct capabilities, query costs and solver requirements.

Scientific sources and reading depth are in the [representation review](set-representations-and-ellipsoidal-toolbox.md). This catalog does not claim every backend is implemented or interchangeable under every operation.

Conversion and approximation are separate contracts. Every operation result identifies its reference set, exact/inner/outer/heuristic relation, assumptions and any justified error bound. Generator reduction is exact only when its algorithm proves equivalence; otherwise record direction.

For R_in subset R subset R_out, minimizing a common objective gives min(R_out) <= min(R) <= min(R_in) when the minima exist. Thus outer reachable sets can give optimistic lower bounds; inner reachable sets can give achievable upper bounds if realizable trajectories are retained or recovered. Reachability membership alone does not supply a control witness. Robust predecessor directions require a separate quantifier audit. Approximation of a reachable set does not automatically approximate its optimizer set in the same direction.

## 5. C++ boundaries, configuration and performance

Proposed native structure: model/, sets/, geometry/, optimization/, reachability/, synthesis/, execution/, artifacts/, with backend adapters in separate build targets. Dependency order goes from application strategies toward mathematical ports and numerical adapters. Fuel-specific equations stay in examples/domain adapters.

Use immutable shared problem/set snapshots, explicit mutable per-worker workspaces, RAII-owned buffers and non-owning matrix views with declared lifetime/layout. Begin with double precision; scalar requirements are part of capabilities, so exact rational or validated arithmetic can be added without claiming existing double backends support them. Dense/sparse storage belongs in the numeric layer. Choose a concrete matrix library during interface review; do not expose one solver's proprietary containers as the public model format.

Use compile-time types/templates inside numerical kernels and runtime type erasure or polymorphic ports at coarse module boundaries. Avoid virtual dispatch for every scalar operation and a giant System class with solver flags. A factory creates independent solver instances/workspaces. Third-party solver termination maps to the common evidence contract while retaining raw diagnostics.

Initial plugin registration is in-process and built with compatible toolchains. Runtime selection of registered modules is required; arbitrary binary plugin loading is a later packaging capability. C++ ABI compatibility across compilers/releases must not be assumed. A future versioned C ABI can expose opaque handles and coarse buffers. Python bindings also cross coarse calls, not per-element loops.

Illustrative configuration, not an implemented API:

~~~yaml
core_language: cpp20
problem: nominal_terminal
request: optimal_solution_family
synthesis: joint_relation
sets: constrained_zonotope
lp_backend: highs
convex_backend: configured_conic_adapter
hull_reducer: barycentric_feasibility
conversion_policy: explicit
approximation_policy: reject_unapproved_relaxation
execution:
  workers: 4
  numerical_threads_per_worker: 1
~~~

Validate the whole pipeline: supported domains, objective, operations, output completeness and guarantee strength. Switching a backend must preserve the request or report incompatibility. Store module/version/configuration IDs in artifacts; use cache keys including dependencies, tolerance and backend version.

Parallelize independent jobs, support directions and independent membership LPs first. Nominal recurrence stages generally depend on predecessors. Prefix search can share an incumbent but must retain all ties/branches needed for the optimal family. An incumbent-finding prune condition may discard ties; complete-family enumeration needs a pruning rule justified for that output. Avoid duplicate plans and preserve action identity after DAG merging.

Share a total thread/memory budget between outer workers and BLAS/solver internals. Use cancellation and chunked/lazy output when conversions or families grow. Compact representation is valuable, but does not make every membership/projection/enumeration query cheap.

## 6. First implementation slice after design agreement

1. Agree model, set evidence, backend status and optimal-family query contracts, using the two-step integrator counterexample.
2. Build one nominal affine/polyhedral pipeline returning a joint optimal relation, with independent witness verification. Keep continuous, finite and mixed domains representable; the first baseline solver supports continuous actions and original stagewise constraints under its declared convexity/domain assumptions; new temporal couplings are excluded from these first experiments.
3. Plug in a second LP implementation and a second representation/conversion strategy without changing the problem or frontend API.
4. Compare exact generator propagation with a compatible ellipsoidal approximation, checking inclusion and objective bounds rather than demanding identical sets.
5. Restore and reproduce an archived nominal experiment with both historical and new output scopes recorded. Profile conversions, reduction, optimization, queries and memory separately.

The published experiments are validation anchors. They do not replace the architecture discussion or require implementing every possible representation before the first useful solve.
