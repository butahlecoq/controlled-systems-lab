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

The full-flow token owns stable provider snapshots, request identity, complete path inventory, canonical operation ledger, objective requirements, verifier scope, and requested resource policy. It is constructible only by the coordinator and can be refined once. Refinement builds every selected trajectory program, stages reachability for every path, concretely prepares every LP/convex request, and returns a move-only prepared execution only after all concrete preparations succeed. A projected reachability stage owns the path relation and prepared geometry pipeline without creating a workspace. Execution consumes these stages before solver branches, validates each result, and reports path-scoped success, failure, stop, requested resources, observed thread width, and provenance. A selection that requests family verification remains fail-closed until verifier preparation joins the transaction. A missing symbolic provider declaration is `unknown`; strict execution refuses it unless the caller explicitly selects an observation-only/incomplete mode. `supported` means only that the provider declares the descriptor within its domain, not that a concrete generated request has passed `prepare` or that an algorithm will succeed.

### Flow and guarantees

1. `admit_hybrid_request` validates the profile and fully enumerates permitted paths, derives the canonical operation/objective ledger, and preflights the selected relation adapter, projection provider, solver providers, and verifier. It does not compose a relation, execute an algorithm, create a workspace, or claim measured resource enforcement.
2. If any required operation is unsupported, unknown under strict mode, or stopped, it returns a request-scoped outcome naming the operation and affected path/stage/mode/edge. No relation or solver algorithm has run.
3. `refine_hybrid_request` builds every selected trajectory program and calls `stage_path` for every reachability path. Projected adapters compose their path relation and concretely call `PreparedProvider::prepare`, but do not create a workspace or run geometry. After every path stage succeeds, refinement concretely prepares all LP/convex requests. Any late rejection destroys the complete local stage set; no geometry or solver workspace has been created.
4. `execute_hybrid_request` consumes the prepared reachability stages before solver branches. Each stage creates its geometry workspace, runs, and returns a result checked by the same path/limit/assurance/operation-trace/projected-evidence validator used by the synchronous API. The report retains a path-scoped outcome even for refusal or stop. Reachability and solver reports capture provider-reported maximum backend thread width separately per operation and keep caller aggregation as a max. Resource capability declarations, enforcement scope, and broader measurements such as memory use remain future work; a resource declaration is never recorded as measurement.

The generic registry gains an optional provider declaration callback over a domain-neutral immutable descriptor view; the hybrid layer owns typed descriptors and adapts them at the registry boundary. Existing registrations without declarations return `unknown`. The descriptor's optional minimum nonzero matrix-coefficient magnitude is a lower-bound claim over every matrix sent to the provider; absent means unknown. Providers with coefficient-scale restrictions must return conditional unless this lower bound proves the request stays within their numerical domain. Concrete `prepare` remains unchanged and authoritative. Resource capability records distinguish advertised, enforceable, enforced, and observed fields; only runtime evidence can set enforced/observed outcomes.

The existing split APIs remain available as explicitly lower-level operations while call sites migrate; they cannot return a `HybridAdmissionToken` or assert complete request admission. This avoids source breakage and prevents a legacy call from being misreported as satisfying the new contract.

### Module map

- `include/csl/synthesis/hybrid_admission.hpp`: typed operation inventory, tri-state offers, token, selection and coordinator API.
- `include/csl/registry/registry.hpp` and `provider.hpp`: optional immutable symbolic declaration hook, defaulting to unknown; concrete preparation unchanged.
- `src/synthesis/hybrid_path_program.cpp`: inventory derivation, shared transactional branch construction/refinement, and coordinated execution boundary.
- `src/synthesis/hybrid_projected_reachability.cpp`: projected relation assembly, concrete geometry preparation, and deferred workspace execution.
- `tests/unit/synthesis/hybrid_path_program_tests.cpp`: operation coverage, unknown/refusal, provider snapshot stability, late geometry rejection, and zero workspace creation before request-wide preparation completes.

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

## Next implementation step

Connect the family verifier to the same concrete preparation barrier, then add resource capability/enforcement/measurement records and late-path stop/refusal tests across all selected operation roles.
