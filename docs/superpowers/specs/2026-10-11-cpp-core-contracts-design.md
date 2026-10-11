# C++20 core contracts: nominal optimal-family slice

Date: 2026-10-11. Status: draft for owner and scientific review. The [C++ language direction](../../architecture/decisions/0001-cpp20-core.md) is accepted. These interface proposals are not implemented headers or an approved implementation plan.

Requirements, test IDs and delivery boundaries are governed by the [consolidated specification](2026-10-11-controlled-systems-master-design.md). This document details its proposed native interfaces.

## Purpose and scope

Provide a native library that accepts a controlled system and a nominal finite-horizon problem, constructs a representation of all optimal control sequences and their consistent trajectories, and extracts different complete witnesses for numerical, visual and runtime comparison. Algorithms, optimization solvers and set representations must be replaceable independently.

The first slice uses discrete affine dynamics, a known initial state, continuous convex polyhedral admissibility, stagewise constraints and one of three structured convex terminal objectives. It starts without process disturbances or added temporal couplings. Observation channels, external inputs, finite/mixed domains and temporal constraints remain representable; unsupported solver combinations produce capability diagnostics before execution. Hybrid models, feedback, arbitrary callbacks, GPU execution and distributed scheduling are separate later slices.

A native library API and CMake build targets are proposed. Selecting a matrix library or LP/convex solver is a later integration decision, not hidden in these contracts.

## Interface approach

| Approach | Benefit | Cost | Decision proposed |
|---|---|---|---|
| One inheritance hierarchy for every scalar, matrix, set and algorithm | Uniform dispatch | Fine-grained virtual calls and broad coupling | Reject |
| Templates for every representation and strategy in the public API | Kernel specialization | Combinations propagate through callers; runtime experiment selection becomes difficult | Keep templates inside kernels |
| Owning value data plus opaque immutable handles and coarse algorithm ports | Runtime interchangeability; isolated native workspaces | Adapter and capability plumbing | Use for the first slice |

Small closed choices, such as the three initial objective forms, can use std::variant. Representation and algorithm identifiers are extensible registered IDs; adding a representation does not require editing an enum in every controller. Public numerical data use library-owned values/views rather than exposing a selected third-party matrix type.

## Modules and direction of dependencies

| Module | Main contract | Inputs and result | Native state ownership |
|---|---|---|---|
| model | LinearDynamics, ObservationModel, SystemModel | Coefficient data/providers and time/channel metadata | Immutable snapshot |
| problem | ControlProblem, ProblemValidator | Model, horizon, initial information, domains, constraints, objective | Immutable validated problem |
| sets | SetHandle, SetMetadata | Ambient dimension, representation ID, relation/evidence, native payload | Shared immutable payload |
| geometry | SetOperator, RepresentationConverter, SetApproximator | Set queries/transforms with explicit output guarantees | Operator workspace per worker |
| optimization | LPBackend, ConvexBackend | Backend-neutral programs, bounds, candidates, optional diagnostics | Exclusive workspace per worker |
| synthesis | SynthesisStrategy, OptimalFamilyBuilder | Validated problem and services to joint family/evidence | Per-solve workspace |
| witnesses | WitnessSelector, TrajectoryVerifier | Family queries to complete trajectories and independent checks | Query workspace; owning output |
| execution | ExecutionContext | Resource budget, cancellation and provenance | Caller-owned session |
| experiments | ComparisonRunner | Same problem/query across configurations to comparison artifacts | Owns runs; plotting is an adapter |

Models and problems do not depend on a solver. Set payloads do not depend on a terminal objective. Geometry can call optimization through backend ports. Synthesis composes mathematical operations; execution controls resources without changing their guarantees. A direct sparse optimization strategy can bypass forward set materialization while obeying the same result semantics.

## Model and problem contracts

The following declarations illustrate boundaries. Supporting types and constructors are described in prose; this is design notation, not a compilable header listing.

~~~cpp
struct LinearStage {
    Matrix state_transition;           // A: n x n
    Matrix control_map;                // B: n x m
    Matrix external_map;               // E: n x p
    Vector offset;                     // a: n
};

struct LinearDynamics {
    Dimensions dimensions;
    TimeGrid time;
    CoefficientProvider coefficients;  // constant or stage-indexed
};

struct SystemModel {
    LinearDynamics dynamics;
    std::vector<ObservationModel> observations;
};

using TerminalObjective = std::variant<
    LinearTerminal,
    ConvexQuadraticTerminal,
    AffineResidualNormTerminal>;

struct ControlProblem {
    std::shared_ptr<const SystemModel> model;
    std::size_t horizon;
    InitialInformation initial;
    ControlDomain controls;
    StateConstraints states;
    TemporalLinearConstraints temporal;
    ExternalInputSpecification external;
    InformationPattern information;
    TerminalObjective objective;
};
~~~

Matrix and Vector are owning values; immutable views declare scalar type, dimensions, stride, storage layout and lifetime. A view cannot outlive its owner or be retained asynchronously without retaining that owner. The first scalar implementation uses double. Exact/interval arithmetic needs compatible kernels and evidence; a scalar template alone does not certify results.

The problem has T transitions/control stages and T+1 state stages. The validator checks shapes, timestamps, objective properties and domain metadata; it does not silently add compactness or invertibility assumptions. Empty temporal constraints mean no temporal coupling. Universal sets mean no restriction; the empty set means infeasibility. Missing observation channels do not imply full-state observation. Zero-dimensional external/control ports support nominal/autonomous special cases naturally.

ObservationModel carries state/output maps, error and optional feedthrough maps, offsets and pre/post-decision timing. InformationPattern belongs to the problem and declares what is known when decisions are selected. A nominal planner uses known initial information without needing an estimator.

ControlDomain supports a continuous set, finite catalogue or mixed domain as distinct alternatives. The initial strategy accepts continuous convex polyhedral sets only. Nonpolyhedral continuous domains are representable but require another compatible strategy. Hybrid modes/guards are a separate model extension.

The three objective values are c^T x+d, (1/2)x^T Qx+q^T x+c with Q symmetric positive semidefinite, and ||Lx-r||_2. Rectangular L is valid. Backend reformulation and independent evaluation remain separate: solving the squared residual preserves minimizers but reported costs are evaluated in the original norm convention. Nonlinear callbacks do not inherit convexity from a label.

## Set operations and backend ports

SetHandle retains an immutable payload and metadata. Operator requests specify the mathematical operation and required relation to its ideal output. Results distinguish symbolic algebraic exactness, numerically checked calculations and validated inclusion. An algebraically exact polytope formula evaluated in floating point is not a validated inclusion certificate.

An exact representation conversion, an inner approximation and an outer approximation are separate operations. An operator unable to meet a requested guarantee returns unsupported; it cannot silently downgrade it. Empty/unbounded/lower-dimensional sets are explicit cases. Invertibility belongs to the capability of an inverse-based algorithm, not to the general model.

~~~cpp
class LPWorkspace {
public:
    virtual ~LPWorkspace() = default;
    virtual LPResult solve(const LinearProgram&,
                           const ExecutionContext&) = 0;
};

class LPBackend {
public:
    virtual ~LPBackend() = default;
    virtual BackendCapabilities capabilities() const = 0;
    virtual std::unique_ptr<LPWorkspace> make_workspace() const = 0;
};
~~~

ConvexBackend has the same separation of immutable configuration/factory and exclusive workspace, with declared QP/conic/objective support. Programs use backend-neutral sparse/dense buffers and explicit bounds. Backend adapters translate solver statuses and primal/dual residuals, and retain optional native basis diagnostics behind a separate capability. Historical phase-I basis methods can be alternative adapters without leaking tableau details into synthesis.

The registry resolves operation/representation/scalar/guarantee capabilities before creating workspaces. Strategy configuration identifies registered algorithms, LP/convex backends, converters and approximation policies independently. Registrations are built with compatible toolchains; portable dynamic binary plugins require a later versioned ABI. No selected dependency is implied by example names in earlier documents.

## Joint optimal family and evidence

For fixed known x_0, let F be the feasible relation over all states and controls. The intended result is

Z* = {(x_0,...,x_T,u_0,...,u_(T-1)) in F : phi(x_T)=v*}.

A family may store controls and derive states through an affine map, or retain a lifted joint relation. It must expose enough structure to recover complete consistent trajectories. State/control marginals alone are not a representation of Z*.

~~~cpp
struct OptimalFamily {
    ProblemId problem;
    JointRelationHandle relation;
    CoordinateMap coordinates;
    FamilyEvidence evidence;
};

struct Witness {
    std::vector<Vector> states;   // T+1 owning vectors
    std::vector<Vector> controls; // T owning vectors
    double original_objective;
    WitnessProvenance provenance;
};

struct SynthesisResult {
    Termination termination;
    MathematicalOutcome outcome;
    ObjectiveEvidence objective;
    std::optional<OptimalFamily> family;
    std::vector<Witness> incumbents;
    RunStatistics statistics;
};
~~~

Termination reports completed/cancelled/resource-limit/numerical-failure. MathematicalOutcome separately reports optimal/infeasible/unbounded/infimum-not-attained/undetermined/unsupported. A normal return from a numerical solver is not proof of the outcome. ObjectiveEvidence records bounds with evidence levels, residuals and their applicability. FamilyEvidence separately records feasibility, optimality and completeness, including any assumptions/certificates. All evidence binds to the same problem identity.

An unsupported strategy is diagnosed before expensive execution. A timeout can return an incumbent and bounds without a complete family. An approximation or finite sample cannot be labelled the full optimal family. If numerical sublevel relaxation phi <= incumbent+tolerance is used, the relation is explicitly a candidate relaxation, not exact Z*. Initial public queries request optimal families; approximate candidates are visible as diagnostic solve results.

For a set-based builder, minimize over the reachable terminal set to obtain the entire terminal minimizer set M_T, then recover the preimage under the feasible state/control relation. A single terminal optimizer suffices only when uniqueness is justified. For a direct optimization builder, preserving the optimal level relation is an additional task beyond returning a minimizer. A black-box optimizer success flag cannot supply family completeness automatically.

A valid first implementation may combine one selected terminal optimizer with a polyhedral family builder where the minimum is attained and the terminal minimizer set has a supported polyhedral representation. For quadratic/residual objectives, proving a unique terminal point is one supported case; general nonunique terminal minimizers require an explicit compatible construction. Capability validation must reject an unsupported completeness case rather than report one optimum as all solutions. A bounded feasible polytope and continuous objective ensure attainment; these assumptions are checked for the chosen slice.

## Witness queries, comparison and concurrency

WitnessSelector asks the family for a requested number of different complete solutions using declared selection directions and, optionally, a recorded seed. Secondary optimization is an internal selection mechanism, not an additional first-release user-facing family query. Distinctness has a stated tolerance in control/trajectory coordinates. Failing to find another witness is not a singleton proof; return requested/returned/distinct counts and search diagnostics.

TrajectoryVerifier independently evaluates initial conditions, all dynamics, constraints and the original terminal criterion from problem data. It reports absolute/relative tolerances and residuals. It does not reuse the family builder's feasibility flag as its own check. Witness checks cannot establish completeness; numeric objective checks do not prove global optimality without suitable independent bound evidence.

ExecutionContext contains a shared resource budget, deadline/cancellation signal (std::stop_token), numerical policy and provenance collector. Each worker owns its backend/query workspace. Problem/set payloads are immutable and shared. Cancellation is checked at coarse boundaries; noninterruptible native calls document their latency limits. Outer tasks, solver threads and BLAS threads share a total thread budget. A declared memory budget is admission/accounting information unless the adapter can actually enforce it; enforcement support is recorded.

Parallelize independent configurations, runs or set queries first. Do not treat constrained horizon stages as independent jobs. Deterministic ordering, seed handling and solver configuration are recorded; bitwise equality across parallel floating-point executions is not promised. Versioned artifacts include problem hashes, algorithms/backend versions, tolerances, resource settings, setup/family/query/verification timing, set sizes and witness residuals.

## Intended usage

This is illustrative user flow, not an existing callable API. The analytic example is usable as a future acceptance oracle without claiming to reproduce B04.

~~~cpp
auto problem = examples::two_step_integrator();
// x_(k+1)=x_k+u_k, x_0=0, 0<=u_k<=1, phi=(x_2-1)^2

auto registry = configured_registry();
auto strategy = registry.make_synthesis(run_configuration);
auto support = strategy->check_capabilities(problem, registry);
if (!support.accepted()) return report(support);

auto result = strategy->solve(problem, execution);
if (!result.family) return report(result);

auto selected = select_witnesses(*result.family, selection, execution);
auto checked = verify_trajectories(problem, selected, numerical_policy);
export_comparison(problem, result, selected, checked);
~~~

The analytic optimum is zero and the optimal control relation is u_0+u_1=1 inside [0,1]^2. Recovering (0,1) and (1,0) demonstrates distinct complete witnesses. The stagewise marginals are both [0,1], but (1,1) is not optimal. Another required case has a constant objective: every feasible trajectory is optimal, preventing a single-terminal-point implementation from appearing complete.

For [B04](../../research/b04-restoration.md), the intended flow is load scenario -> audit executable status -> validate/capability-check -> solve using alternative configurations -> select and independently verify witnesses -> compare linear quality/time -> optionally simulate the same controls on the separate nonlinear plant. The [historical manifest](../../../benchmarks/scenarios/b04-historical.json) is currently non-executable: the control interval is only provisional and printed model/result consistency remains unresolved. Loading it must report restoration diagnostics instead of inserting guessed bounds or treating 30.899 as a verified target. Architecture and the analytic acceptance examples can progress independently.

## Review criteria and next slice

A reviewer should be able to verify that swapping an LP backend does not change model/objective types; swapping a set representation requires registered compatible operations rather than editing the planner; independent workers cannot share mutable solver state; and a returned family preserves all temporal dependencies and makes its completeness evidence explicit.

The first implementation plan should cover only the nominal polyhedral optimal-family slice, its capability checks, witness selection, independent verification and these analytic oracles. It should select a concrete native matrix/LP/convex integration with primary-documentation and licensing checks. General robust/feedback synthesis, all approximation families and arbitrary binary plugin loading remain subsequent plans, not acceptance requirements for that slice.

See [mathematical module definitions](../../architecture/modular-algorithms-and-solution-sets.md), [linear model contract](../../architecture/linear-system-contract.md), [set representation study](../../architecture/set-representations-and-ellipsoidal-toolbox.md) and [temporal-constraint proof](../../research/temporal-coupling.md).
