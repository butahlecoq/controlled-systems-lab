# EXT-07 request-wide provider admission

## Problem

Hybrid path and verifier preflights already cover the complete enumerated path set before relation composition, but selected LP/convex providers receive concrete programs only after composition, and projected reachability admits its geometry provider after assembling a relation. The accepted hybrid contract requires a complete request admission before an algorithm or workspace begins. A symbolic declaration cannot replace concrete provider preparation, so the design must preserve both checks and report their outcomes separately.

## Usage (caller's view)

Callers select the adapters and providers once, then submit the complete request to the hybrid coordinator:

```cpp
HybridExecutionSelection selection{
    .trajectory = trajectory,
    .reachability = reachability,
    .lp = lp,
    .convex = convex,
    .geometry = geometry,
    .verifier = &verifier,
    .resources = resources,
};

auto run = run_hybrid_request(system, request, problem, selection,
    enumeration_limits, relation_limits, objective_policy, context);
```

Reachability callers select only the operations they need; unused providers are not prerequisites:

```cpp
auto result = run_hybrid_reachability(system, request, reachability,
    geometry, enumeration_limits, relation_limits, context);
```

An explicit dry-run returns the request-scoped admission evidence without composing relations or creating workspaces:

```cpp
auto admission = admit_hybrid_request(system, request, selection,
    enumeration_limits, relation_limits, objective_policy, context);
```

## Shape

### Domain data

One canonical inventory owns the complete paths and requested operation obligations. Provider offers are derived from that inventory and keyed by operation, path, and stage, so objectives, projection, and verification cannot disappear into unrelated side lists.

```cpp
enum class HybridOperationKind {
    relation, projection, linear_optimization, convex_optimization,
    family_verification
};

struct HybridOperationKey {
    HybridOperationKind kind;
    std::optional<model::HybridPath> path;
    std::optional<std::size_t> stage;
};

struct HybridOperationDescriptor {
    HybridOperationKey key;
    std::optional<model::HybridRelationOperationRecord> relation_step;
    std::optional<optimization::ObjectiveClass> objective;
    std::optional<std::size_t> input_dimension;
    std::optional<std::size_t> row_limit;
    Assurance requested_assurance{Assurance::numerical};
};

enum class AdmissionDecision { supported, unsupported, unknown, conditional };
struct HybridOperationOffer {
    HybridOperationKey key;
    registry::Provenance provider;
    AdmissionDecision decision;
    Diagnostics diagnostics;
    ResourceCapabilityDeclaration resource_capability;
};

class HybridAdmissionToken; // private constructor, move-only, request/provider snapshots
using HybridAdmissionResult = std::variant<HybridAdmissionToken,
    HybridAdmissionRefused, OperationStopped>;

HybridAdmissionResult admit_hybrid_request(
    const HybridSystem&, const HybridRequest&, const HybridExecutionSelection&,
    HybridEnumerationLimits, HybridRelationLimits, ObjectivePolicy,
    const ExecutionContext&);

using HybridRefinementResult = std::variant<PreparedHybridExecution,
    HybridConcreteRefinementRejected, OperationStopped>;
HybridRefinementResult refine_hybrid_request(HybridAdmissionToken&&,
    const ExecutionContext&);
HybridRunResult execute_hybrid_request(PreparedHybridExecution&&,
    const ExecutionContext&);
```

The full-flow token owns stable provider snapshots, request identity, complete path inventory, canonical operation ledger, objective requirements, verifier scope, and requested resource policy. It is constructible only by the coordinator and can be refined once. Refinement builds every selected trajectory program, stages reachability for every path, concretely prepares every LP/convex request, and returns a move-only prepared execution only after all concrete preparations succeed. A projected reachability stage owns the path relation and prepared geometry pipeline without creating a workspace. Execution consumes these stages before solver branches, validates each result, and reports path-scoped success, failure, stop, requested resources, observed thread width, and provenance. When family verification is selected, execution first assembles candidate faces from completed solver branches, then invokes the verifier. It retains candidate assembly status separately from verifier output; incomplete solver evidence never dispatches verification or appears as a complete-family report. A missing symbolic provider declaration is `unknown`; strict execution refuses it unless the caller explicitly selects an observation-only/incomplete mode. `supported` means only that the provider declares the descriptor within its domain, not that a concrete generated request has passed `prepare` or that an algorithm will succeed.

### Flow and guarantees

1. `admit_hybrid_request` validates the profile and fully enumerates permitted paths, derives the canonical operation/objective ledger, and preflights the selected relation adapter, projection provider, solver providers, and verifier. It does not compose a relation, execute an algorithm, create a workspace, or claim measured resource enforcement.
2. If any required operation is unsupported, unknown under strict mode, or stopped, it returns a request-scoped outcome naming the operation and affected path/stage/mode/edge. No relation or solver algorithm has run.
3. `refine_hybrid_request` builds every selected trajectory program and calls `stage_path` for every reachability path. Projected adapters compose their path relation and concretely call `PreparedProvider::prepare`, but do not create a workspace or run geometry. After every path stage succeeds, refinement concretely prepares all LP/convex requests. Any late rejection destroys the complete local stage set; no geometry or solver workspace has been created. A concrete path rejection retains its path index into the complete admission inventory; the operation key is present when the adapter identifies the failing stage.
4. `execute_hybrid_request` consumes the prepared reachability stages before solver branches. Each stage creates its geometry workspace, runs, and returns a result checked by the same path/limit/assurance/operation-trace/projected-evidence validator used by the synchronous API. The report retains a path-scoped outcome even for refusal or stop. Reachability and solver reports capture provider-reported maximum backend thread width separately per operation and keep caller aggregation as a max. Resource capability declarations, enforcement scope, and broader measurements such as memory use remain future work; a resource declaration is never recorded as measurement.
5. If family verification is selected, execution assembles optimal-face candidates only from a complete, comparable solver portfolio. `HybridPortfolioExecution::family_verification` retains that candidate-analysis outcome and, when candidates exist, the verifier result independently. Incomplete candidate analysis is explicit and the verifier is not called. The adapter interface currently accepts cancellation only, so the attempt reports requested resources but does not claim independent verifier CPU, memory, or thread enforcement.

The generic registry gains an optional provider declaration callback over a domain-neutral immutable descriptor view; the hybrid layer owns typed descriptors and adapts them at the registry boundary. Existing registrations without declarations return `unknown`. The descriptor's optional minimum nonzero matrix-coefficient magnitude is a lower-bound claim over every matrix sent to the provider; absent means unknown. Providers with coefficient-scale restrictions must return conditional unless this lower bound proves the request stays within their numerical domain. Concrete `prepare` remains unchanged and authoritative. Resource capability records distinguish advertised, enforceable, enforced, and observed fields; only runtime evidence can set enforced/observed outcomes.

The existing split APIs remain available as explicitly lower-level operations while call sites migrate; they cannot return a `HybridAdmissionToken` or assert complete request admission. This avoids source breakage and prevents a legacy call from being misreported as satisfying the new contract.

### Module map

- `include/csl/synthesis/hybrid_admission.hpp`: typed operation inventory, tri-state offers, token, selection and coordinator API.
- `include/csl/registry/registry.hpp` and `provider.hpp`: optional immutable symbolic declaration hook, defaulting to unknown; concrete preparation unchanged.
- `src/synthesis/hybrid_path_program.cpp`: inventory derivation, shared transactional branch construction/refinement, and coordinated execution boundary.
- `src/synthesis/hybrid_projected_reachability.cpp`: projected relation assembly, concrete geometry preparation, and deferred workspace execution.
- `tests/unit/synthesis/hybrid_path_program_tests.cpp`: operation coverage, unknown/refusal, provider snapshot stability, late geometry rejection, zero workspace creation before request-wide preparation completes, and post-solver exact-family verification.

The public surface hides inventory derivation and ordering behind one coordinator; callers still select algorithms and inspect explicit outcomes. It does not promise that symbolic support guarantees concrete acceptance or execution success. This keeps compatibility at the generic registry boundary and encodes the request-wide sequencing invariant in the move-only token (per boundary-discipline, type-system-discipline, and migrate-callers-then-delete-legacy-apis).

## Synthesis decision

Candidate B is the base because its staged coordinator gives the strongest request-wide sequencing guarantee and covers projected geometry as well as trajectory providers. The cross-judge could not establish a distinct model family under the architect skill's family rules. Candidate A's canonical inventory and explicit `unknown` outcome are grafted into the base. Candidate B's boolean support and unqualified resource capability are rejected: symbolic outcomes must distinguish supported, unsupported, unknown, and conditional, while resource declarations must never be confused with enforcement or measurement. The coordinator is hybrid-scoped, and existing split APIs remain lower-level during migration rather than being deleted in this slice.

The projected-geometry follow-up keeps a single `stage_path` adapter entry point and a self-contained move-only stage object with `execute(context) &&`. The abstract stage is an extension point so custom adapters can opt into request-wide execution without exposing `PreparedPipeline`. Refinement stages all reachability paths and prepares every solver request before returning; execution consumes the geometry stages and records each path outcome. The candidate comparison and synthesis note is in `/tmp/ext07-geometry-arena/synthesis.md`; cross-judging was unavailable because this runtime exposes no model outside the configured runner family.

## Tradeoffs accepted

- We accept a symbolic provider declaration hook in exchange for support decisions before hybrid composition.
- We accept a second concrete refinement check in exchange for validating the exact generated requests before any workspace starts.
- We accept `unknown` and incomplete outcomes in exchange for never treating missing declarations as support.
- We accept a coordinator and move-only token in exchange for encoding ordering and provider identity in the API.
- We keep resource requests, advertised capabilities, enforcement scope, and measured consumption separate in exchange for honest resource evidence.

## Alternatives considered

- Concrete `prepare` only: simple for each provider, but cannot admit the complete request before hybrid composition.
- Caller-managed preflight/build/prepare/execute: supports incremental adoption, but exposes ordering and snapshot consistency to every caller.
- Passing `HybridSystem` to generic providers: hides descriptor derivation, but couples LP and geometry registry ports to hybrid semantics.

## Open questions and risks

- Which conservative descriptor fields can each current LP, convex, and geometry provider declare without duplicating or weakening its concrete capability checks?
- Should unknown symbolic support always refuse coordinated execution, or may a named incomplete mode proceed while preserving the missing evidence?
- Which backends can eventually provide enforceable CPU, memory, and thread declarations, and which observations remain runtime-only?

## Transition-semantics status

The stage-indexed order below is implemented by the model and joint-H composer and is covered by model and synthesis tests. The direct profile retains pre-reset and post-reset coordinates. It does not project a reset image or merge mode branches.

## Verifier execution-context decision

### Problem

The request coordinator already receives `ExecutionContext`, but the family-verifier virtual boundary receives only `NumericalPolicy` and `std::stop_token`. A long verifier cannot poll the caller deadline, and requested resources and run provenance do not reach the adapter. The wrapper can discard a late result after return, but cannot make a cooperative verifier stop at the deadline. `ResourcePolicy::memory_bytes` is accounting metadata, not a hard cap, so forwarding it must not imply enforcement.

### Caller view

Callers continue to pass one execution context to coordinated execution:

```cpp
auto portfolio = execute_hybrid_request(std::move(prepared), context);
const auto& verification = *portfolio.family_verification;
if (verification.verification) consume(*verification.verification);
if (verification.resources.observed_backend_threads)
    record(*verification.resources.observed_backend_threads);
```

An adapter receives one immutable invocation capability and polls it at bounded work checkpoints:

```cpp
HybridFamilyVerificationResult Adapter::verify(...,
    const HybridVerifierInvocation& invocation) const {
    for (const auto& path : paths) {
        if (auto stopped = invocation.interruption()) return *stopped;
        verify_path(path, invocation.numerical_policy());
    }
    return make_report();
}
```

### Shape

Add a focused `HybridVerifierInvocation`, projected from `ExecutionContext` by the coordinator. It carries cancellation, deadline, numerical policy, requested resources, run ID, optional timing collector, and an attempt-local thread-observation sink. It exposes `interruption()` so all verifier implementations use one cancellation-first, steady-clock deadline rule. Both verifier preflight and verification receive this type. The direct family-verification function accepts the same scoped invocation; there is one public verification route, not parallel token and context overloads.

`HybridPortfolioVerificationAttempt` owns candidate analysis, optional verifier result, and `HybridVerifierResourceEvidence`. This evidence preserves the requested policy, an explicit disposition (`not_requested`, `not_invoked`, or `requested_but_unenforced`), and optional adapter-reported backend thread width. Memory use stays absent because this path has no measurement source. The coordinator creates a fresh observer for each verifier invocation; adapter reports update that observer and the caller's aggregate. It never treats an adapter declaration, request, or report as independent proof that a limit was enforced.

The wrapper still owns model/path validation, candidate admission, report validation, provenance attachment, and outcome normalization. The adapter gets only the verifier call's invocation capability, not the caller-owned aggregate observer. Deadline stopping remains cooperative: the wrapper checks before and after the virtual call, and adapters poll inside long loops; synchronous native calls cannot be forcibly interrupted.

### Synthesis decision

Three independent sketches were compared against five criteria: cooperative cancellation and deadline polling; separation of requested, enforced, and observed resources; a bounded public adapter boundary; attempt-local observation ownership; and honest behavior for unsupported resource limits. Candidate A and B both projected a verifier-specific context but added overlapping capability/disposition types and either caller-side acceptance policy or adapter-authored enforcement claims. Candidate C made resource enforcement a wrapper-owned fact, but introduced a separate invocation result wrapper. The selected shape keeps C's scoped invocation capability and wrapper-owned evidence while storing that evidence directly on the existing portfolio attempt. This avoids a second result wrapper and preserves the existing distinction between candidate analysis and mathematical verifier output. A cross-family arena judge was unavailable: all configured and available runner models belong to the GPT family.

### Tradeoffs accepted

- We accept a source-breaking adapter-signature migration in exchange for deadline polling at the actual verifier boundary.
- We accept cooperative stop latency between adapter polling points; forced preemption would require process isolation or a different asynchronous contract.
- We record requested-but-unenforced resources instead of refusing verification, because the existing policy describes accounting/request semantics and does not require hard enforcement.
- We record only backend thread widths actually reported through the attempt-local observer; memory use remains unobserved.

### Alternatives rejected

- Passing `ExecutionContext` directly would expose its caller-owned aggregate observer to adapters. A scoped projection retains the standard context as the single input source while giving each invocation a fresh observer.
- Separate deadline, cancellation, numerical, resource, run-ID, timing, and observer parameters would expose repeated plumbing and distribute stop/reconciliation rules across adapters.
- Keeping the stop-token-only interface and checking deadlines after return cannot stop a verifier while it is running.
- Adapter-authored claims that requested limits were enforced cannot be independently established by the wrapper and are not accepted as enforcement evidence.

## Hybrid time and transition semantics

This section makes the semantics already encoded by `HybridSystem`, the joint-H composer, and the model/oracle tests explicit for review against EXT-07 acceptance items 1 and 2. It is a fixed, stage-indexed discrete model, not an event-triggered continuous hybrid automaton.

Mode IDs and edge IDs are each nonempty and unique within their respective catalogues. For horizon `N`, one complete path has modes `(m_0, ..., m_N)` and edges `(e_0, ..., e_(N-1))`; each edge satisfies `source(e_t)=m_t` and `target(e_t)=m_(t+1)`. At stage `t`, mode `m_t` is active for the entire flow interval. Let that mode's state dimension be `n_m` and control dimension be `p_m`; then `x_t,z_(t+1) ∈ R^{n_m}`, `u_t ∈ R^{p_m}`, `A_(m,t) ∈ R^(n_m×n_m)`, `B_(m,t) ∈ R^(n_m×p_m)`, and `c_(m,t) ∈ R^{n_m}`. Each mode invariant belongs to its `R^{n_m}` state space. Each transition edge has one guard in the source state space and one reset relation in the `[source,target]` product space for every stage. The stage flow and control are

```text
z_(t+1) = A_(m_t,t) x_t + B_(m_t,t) u_t + c_(m_t,t)
u_t ∈ U_(m_t,t)
```

The model may supply one affine flow reused at every stage or one flow per stage. Each mode has one control set per flow stage and one invariant set at every state stage. The current profile requires zero external-input columns in each affine flow; disturbance/exogenous-input semantics are outside this profile. The request pins `m_0` and `x_0`; the relation also requires `x_0 ∈ I_(m_0,0)`.

At the integer boundary after the flow, `z_(t+1)` is the pre-reset state. The current mode's next-stage invariant and the selected edge's stage-`t` guard both constrain it. The edge reset relation then relates the pre-reset state to the next mode's post-reset state:

```text
z_(t+1) ∈ I_(m_t,t+1) ∩ G_(e_t,t)
(z_(t+1), x_(t+1)) ∈ R_(e_t,t)
x_(t+1) ∈ I_(m_(t+1),t+1)
```

`G_(e_t,t)` lives in the source mode's state space. `R_(e_t,t)` lives in concatenated `[source-state, target-state]` space, so resets may change dimension. The target invariant is applied after reset; the source invariant is applied before reset. A guard is evaluated on the flow-produced pre-reset state, not the post-reset state. Missing edges are forbidden transitions. A no-op or identity reset must be represented by an explicit reset relation. Parallel edges are distinct path branches even when they share endpoints.

The terminal objective is evaluated on `x_N` in mode `m_N`, after the final reset. `m_N` must be an allowed terminal mode and `x_N ∈ I_(m_N,N)`. Every allowed terminal mode has exactly one objective, and mode-indexed objectives must use the same declared quantity and units. Each branch couples its complete numeric joint relation (all stage states, controls, and pre-reset states) with its ordered `HybridPath` identity. Mode and edge identities remain branch metadata; they are not numeric coordinates to be merged into a convex hull or unlabeled point cloud. If `N=0`, the path contains only the pinned initial mode and no controls, flows, edges, guards, or resets; the same state is both initial and terminal and must satisfy its stage-zero invariant and terminal objective.

The timing above is an inference from current code and tests, and is the contract proposal for review—not a claim that all set representations, reset operations, or dimensions are supported. Each adapter must continue to admit its operation plan and limits explicitly; unsupported operations must be rejected before execution, with per-path and per-operation provenance retained.

The built-in direct joint-H composer embeds each supported invariant, guard, control set, flow equation, and reset relation as rows over the common joint coordinates. It intersects constraints by row concatenation and retains pre/post reset coordinates; it does not compute a projected reset image or merge mode branches, so this path makes no inner/outer approximation claim. It admits H, empty, universal, and singleton sets for composition and rejects V conversion as unsupported. Its assurance remains numerical because the model coefficients are binary64. The projected-state adapter is a separate operation: it requests an equivalent projection, checks the returned relation guarantee and `GeometryEvidence`, and retains that evidence with the selected provider provenance in `ProjectedStateEvidence`. Its narrow preflight profile must not be generalized to arbitrary hybrid paths.

Current executable evidence includes `independent tiny trajectory oracle matches guarded reset branches and ties`, `zero-horizon path is the initial terminal mode and has no edge`, `an absent transition edge is forbidden and yields no path`, `profile admission accepts rectangular reset relations between different mode dimensions`, and `profile admission checks source guard and source-plus-target reset dimensions` in `tests/unit/model/hybrid_system_test.cpp`. The end-to-end `independent two-stage oracle checks every edge history and tied mode sequence` lives in `tests/unit/synthesis/hybrid_path_program_tests.cpp`.

### Remaining implementation and evidence

The stage/reset ordering has been cross-checked against the implementation and existing path-oracle/model tests. Model tests now also pin the direct composer's V-representation guard and reset refusals, including path-scoped preflight diagnostics and the absence of partial operation records. Remaining EXT-07 work includes broader continuous-operation support, concrete family-verifier refinement, resource capability and enforcement evidence, and a measured capability profile by horizon, mode/edge counts, and state/control dimensions. Do not infer general scalability from finite fixtures.
