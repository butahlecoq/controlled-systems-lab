# Class-level architecture for optimal control workflows

Status: review draft for scientific and architecture feedback; no new interface is approved for implementation by this document.

Baseline inspected: `main` at `d45b0114282045bf6ba96a9d196261f66a9a8372` (including merged PRs #143 and #144). The selected language is C++20. Public types and module names below are implementation facts only where marked **Implemented**. **Draft PR** means proposed code is not part of that baseline. **Proposed** describes a role and a contract to refine before coding.

This document adds a class-level workflow map to the [current framework composition](../../architecture/framework-composition.md) and [modular algorithm design](../../architecture/modular-algorithms-and-solution-sets.md). It does not repeat their full scientific background or promise that every representable model has an available algorithm.

## First workflow and proposed solver profile

The first solver profile is `nominal_open_loop`: affine discrete-time stages; a known deterministic initial state; absent or zero process disturbance; continuous controls; and a supported terminal-only linear, convex-quadratic, or weighted Euclidean residual objective. For newly authored baseline scenarios, the owner-approved control bound is `u ∈ [-1, 1]`, recorded as an explicit modeling assumption. This bound is not a source-verified canonical archival input; any scenario using it must remain distinct from the historical B04 record until its original inputs are restored. The first experiments add no other new stagewise or cross-time restrictions. Strategy admission must report unsupported constraints rather than silently discard them. The first profile has no observation-driven policy, nonempty temporal coupling, or uncertain-initial-state quantifier; those inputs remain representable but require a later profile to define their semantics. This revised profile reflects the owner's direction to reserve constraint support without changing the initial experiments.

The first completed application solves this profile and returns the full joint relation of optimal states and controls. It compares reachability with backward recovery against direct joint-trajectory optimization on the same resolved problem, objective, tolerances, output scope, and compatible LP/convex backend wherever both strategies support that backend. A backend exception is recorded and explained; backend substitutions are separate crossed comparisons. The first strategy comparison uses exact operations only; reachable-set approximations are deferred. Each approach must retain dependence across time; samples or separate per-stage control marginals are not the family.

The two-strategy integration gate passes only when both strategies return the declared complete optimal-family target for a supported case, with independently checked objective and feasible witnesses. A candidate relaxation, partial relation, failed/unsupported run, or absent completeness evidence remains visible in the comparison record but cannot pass the gate or count as a completed first workflow. For performance comparisons, alternate at least five tuned Release repetitions per strategy, retain every raw run, report median and range, and profile the limiter separately from timed runs.

The current problem model has data types for disturbance, observation, continuous/finite/mixed control domains, and temporal constraints; these do not imply support from the first strategies. It does not represent hybrid modes, guards, resets, or permitted mode transitions. Those require a separate future model extension, not another name for finite or mixed-valued controls; that scope is tracked in [EXT-07 #156](https://github.com/butahlecoq/controlled-systems-lab/issues/156). The first archival experiments use no process disturbance or newly added state/temporal coupling constraints; only source-documented domain bounds may be present. Numerical verification comes first. Validated verification remains an explicit future capability. Whenever any algorithm first produces numerical results, publish an English HTML report with raw data and performance measurements, even before a paired strategy comparison exists. Generate reports from persisted run/comparison data, never by invoking a solver while rendering.

The interface vocabulary follows the repository glossary and the deep-module terms: a **module** has one caller-facing **interface**; an **adapter** implements a replaceable **seam**; depth is the capability callers receive through that interface. Proposed class names below are role names, not settled C++ declarations. The [synthesis note](2026-10-12-class-level-system-architecture-synthesis.md) records Candidate B as the base, the independent review, and the adopted corrections.

## Compact module seam map

This is the short architectural index; the detailed map below records current status, evidence, tickets, and caveats. The interfaces are domain-level requests and results: framework and backend types remain behind adapters, and each proposed seam is still subject to the open decisions later in this draft.

| Module | Responsibility and caller-facing interface | Main extension seam |
|---|---|---|
| Scenario intake and resolution | Parse a versioned scenario or authored `Problem` into an immutable `ResolvedProblem` with source and mathematical identity. | File-format adapters and model/problem value types. |
| Strategy preparation | Admit a strategy and its complete known dependency requirements before creating workspaces; return a prepared strategy with selected identities and versions. | `StrategyPort`/`StrategyRegistry`, typed backend and geometry registrations, generated-request providers where needed. |
| Dynamics, domains, objectives, and sets | Describe the original controlled system, information pattern, constraints, terminal objective, and set-valued data independently of any algorithm. | Model/domain/objective contracts and set representations with declared capabilities. |
| Mathematical operations | Apply a requested set operation, conversion, approximation, LP, or convex program and return the result with scoped status/evidence. | `GeometryPort`, `ConversionPort`, `ApproximationPort`, `LPPort`, and `ConvexPort` adapters. |
| Synthesis strategy | Solve one admitted problem/request and return an `OptimalFamily` relation plus optimum and family evidence. | Shared `StrategyPort`/`SynthesisWorkspace`; Strategy A composes reachability/backward recovery, Strategy B builds and extracts a direct joint-trajectory relation. |
| Family query and witness selection | Select consistent witnesses or request a supported projection while preserving family identity and evidence. | Capability-admitted query/selector adapters over the opaque joint relation. |
| Verification | Recompute original-problem feasibility and objective for returned witnesses; report evidence scope separately for feasibility, optimality, completeness, and validated claims. | Independent numerical verifier first; later assurance-specific verifier adapters. |
| Execution and observation | Give each task exclusive mutable workspaces under declared resource/cancellation policy and collect actual module/run observations. | Executor policies, coarse task scheduling, instrumentation collectors. |
| Records, comparison, and publication | Persist owning run/comparison data and render tables, plots, and HTML without solver execution. | Versioned record/export adapters and backend-neutral plot/report data. |

The first profile is deliberately a capability-bounded path through these modules. Data being representable does not mean a strategy or operation supports it; admission must reject unsupported domains, couplings, guarantees, or evidence requests before execution.

### Model equation, policy, and constraint composition

The reusable mathematical model is a discrete-time affine LTV system with continuously valued control in the first solver profile. Keep physical dynamics, observations, admissible data, and decision policy as separate contracts so each omission is a natural specialization, not a second solver-specific model:

| Proposed/implemented role | Contract and composition | Scope and extension |
|---|---|---|
| `LinearDynamics` logical role (`csl::Dynamics` / `csl::SystemModel`, evaluated by `model::LinearSystem`) | `x[t+1] = A[t] x[t] + B[t] u[t] + E[t] w[t] + a[t]`. `A` is free evolution, `B` is control, `E` maps an external/process input, and `a` is the affine offset. The input-channel meaning is supplied by the problem, not inferred from its matrix. | The affine discrete subset is implemented as model data. Continuous-time descriptions are representable separately; they are not the first solver profile. Descriptive channel names avoid relying on archives that call the disturbance matrix `C` or `D`. |
| `ObservationModel` logical role (`csl::Observation` / `ObservationStage` today) | Pre-decision example: `y_pre[t] = C[t] x[t] + F[t] v[t] + b[t]`. Optional post-action/direct-feedthrough observations add declared `D_u[t]u[t]` and `D_w[t]w[t]` terms. Each sample records source stage, measurement event, and availability event. | Scheduled observation data and causality checks are implemented. An absent observation does not grant full-state information. Observation timing and algebraic-loop policy remain explicit capability requirements. |
| `ControlProblem` logical role (`problem::Problem` today), `InitialData`, `Constraints`, and domains | Compose the system with horizon, known point or quantified initial set, stage state/control/external sets, objective, and optional temporal constraints. Continuous, finite, and mixed action domains remain distinct; continuous-valued controls do not imply continuous-time dynamics or convex admissibility. | Problem data and optional temporal constraint values are implemented; a strategy must declare the subset it supports. New baselines use continuous controls `u ∈ [-1,1]`, a known initial state, and no added coupling constraints; historical B04 bounds remain unresolved. |
| Proposed `UncertaintyModel` and `InformationPattern` semantic roles | Declare whether an external signal is known, bounded exogenous, stochastic under an explicit law, or adversarial, including temporal dependencies, quantifiers, and what each decision maker knows when acting. These roles refine existing external-input data; they are not claims that these named public classes already exist. | Future strategy semantics, not consequences of adding `Ew` to the state equation. Bounded uncertainty and a two-player objective are different problem classes; robust/adversarial strategy and policy contracts require separate review. |
| Proposed policy-class role | The first profile is nominal open-loop: the full control sequence is chosen without conditioning on future observations. A future feedback policy maps only the declared available observation/history to an action. | Feedback, estimation, partially observed and multi-player policies are not silently accepted by either first strategy; admission reports them unsupported until a compatible strategy exists. |

The equations and event-ordering details live in the [general linear-system contract](../../architecture/linear-system-contract.md). In particular, conventional `C` denotes the state-to-observation map; use a named external-input map such as `E` in the common model instead of overloading `C` as a disturbance matrix. A zero/absent channel can be omitted while preserving the same composition contract.

### Proposed contracts for the high-risk seams

These are recommended defaults for review, not owner-approved implementation interfaces. They close the gaps between the broad module names and the guarantees the first workflow requests.

**Objective to complete family.** `TerminalOptimizer` returns the full terminal minimizer relation and numerical optimum evidence. The private relation builder lifts that relation back to joint state/control coordinates. The single `FamilyPublisher` binds and constructs the claim. The existing `SelectorPort` exposes consistent witness selection; capability-admitted coordinate projection uses `GeometryPort`. Membership and secondary optimization remain later query variants. Under the stated first profile, the feasible joint relation is polyhedral and all three supported terminal objective forms admit polyhedral minimizer conditions. A linear objective uses its complete optimal face. For a PSD quadratic and any one minimizer `x*`, minimizers satisfy `Qx = Qx*` and `qᵀx = qᵀx*`. For a weighted residual objective, write the objective as `||A(Lx-r)||₂`, where `A` already includes the residual weights. The attainable transformed residual set `{A(Lx-r) : x is terminal-feasible}` is convex; minimizing the Euclidean norm over it has a unique transformed residual `y*`, and all minimizers satisfy `A(Lx-r)=y*`. The untransformed residual `Lx-r` need not be unique when `A` has a nontrivial nullspace. Intersecting these affine terminal conditions with the feasible-history polyhedron gives the full family, retaining all state/control dependencies. This characterization does not itself certify that a numerically computed optimum, affine condition, or family is exact or complete: report numerical optimum evidence and family-completeness evidence as separate claims, and do not call either certified merely because the relation is polyhedral. If the configured representation or evidence cannot establish full coverage for the requested profile, the strategy returns unsupported/partial output and cannot pass the first-workflow gate. Implicit convex/SOC family forms remain an extension for future objectives or relations that require them.

**Family outcome and evidence shape (proposed coordinated migration).** Keep the existing `SynthesisResult`, `SynthesisOutcome`, `SynthesisWorkspace`, and `StrategyPort` names. Evolve their request and family fields together in SYN-07 #155; do not add a parallel `FamilySolve` or `SynthesisReport` interface. Today's independent `OptimalFamily { target, evidence }` fields permit contradictory claims. Replace that shape with a guarded product while preserving the existing separation of termination, mathematical outcome, bounds, and incumbents:

```cpp
struct CompleteOptimalFamily {
	JointRelation relation;
	OptimumEvidence optimum;
	CompletenessEvidence completeness;
};
struct PartialOptimalFamily {             // every retained history is known optimal
	JointRelation relation;
	OptimumEvidence optimum;
	InnerSubsetEvidence optimal_subset;
	CoverageScope known_scope;              // completeness is not established
};
using FamilyRelationToTarget = std::variant<OuterCandidateEvidence,
	FeasibleCandidateEvidence, HeuristicRelationEvidence>;
using CandidateFeasibilityEvidence = std::variant<UnestablishedFeasibility,
	WitnessFeasibilityEvidence, RelationFeasibilityEvidence>;
struct CandidateFamily {                  // no optimal-membership claim implied
	JointRelation relation;
	FamilyRelationToTarget relation_to_target;
	CandidateFeasibilityEvidence feasibility;
};
using OptimalFamilyOutcome = std::variant<CompleteOptimalFamily,
	PartialOptimalFamily, CandidateFamily>;
struct ScopedOperationStopped {
	OperationStopped stop;
	RequestProvenance request;
	RetainedEvidenceScope retained;
};
struct RequestRejectionEvidence {           // registry-independent value in lower contracts
	std::string port;
	ModuleId requested_module;
	std::optional<std::string> requested_version;
	std::optional<ModuleId> actual_module;
	std::optional<std::string> actual_version;
	Diagnostics diagnostics;
};
struct ScopedRequestRejection {
	RequestProvenance request;
	RequestRejectionEvidence rejection;     // registry adapter translates its Rejection
	TransformLineage completed_lineage;
	RetainedEvidenceScope retained;
};
struct NoStop {};
using StopEvidence = std::variant<NoStop, ScopedOperationStopped, ScopedRequestRejection>;
struct FeasibleIncumbent { Witness witness; FeasibilityEvidence evidence; };
struct SynthesisResult {                  // evolves the existing result
	Termination termination;               // completed/cancelled/resource_limit/numerical_failure/operation_rejected
	SynthesisOutcomeClaim outcome;          // optimal/infeasible/unbounded/infimum_not_attained/undetermined
	ObjectiveEvidence objective;            // retained independently supported bounds
	std::optional<OptimalFamily> family;    // guarded identity + OptimalFamilyOutcome
	std::vector<FeasibleIncumbent> incumbents; // retains each feasibility claim
	StopEvidence stop;                      // includes scoped generated-request rejection/provenance
	std::vector<TimingSpan> spans;
};
using SynthesisOutcome = std::variant<SynthesisResult, Unsupported>;
```

`OptimalFamily` becomes an immutable handle with private construction. It binds relation identity, effective request, coordinate schema, and lineage to its product. One `FamilyPublisher` owns claim construction and binding validation; strategies supply derivation facts rather than construct products directly. The closed product requires evidence fields but does not prove their correctness. A feasible incumbent whose primary optimality is unproved remains a candidate, even when it has the same value as another witness. Candidate feasibility evidence names its scope: an outer relaxation can contain infeasible histories, so a checked witness does not establish feasibility of the whole candidate relation. `PartialOptimalFamily` requires evidence that every retained history belongs to the true optimal relation, not merely evidence of feasibility or an inner subset of the feasible set.

The result-boundary validator keeps cancellation and resource/numerical stops separate from mathematical outcomes. Only completed, supported optimal results can carry a complete family. Interrupted results can retain a labelled partial/candidate relation, valid bounds, and independently supported feasible incumbents. A numerical failure preserves earlier valid evidence. Infeasible, unbounded, and unattained-infimum claims cannot carry an optimal-family product; absence of a witness does not prove infeasibility. `Unsupported` records capability admission failure before solving. Once solving has produced evidence, a later generated-request rejection is represented inside `SynthesisResult` as `operation_rejected` with `ScopedRequestRejection`: exact request provenance, provider diagnostic, completed transformation lineage, and a scope naming retained bounds, incumbents, and any partial/candidate relation. The registry adapter translates its registry-specific rejection into this registry-independent evidence DTO, preserving port, requested/actual module and versions, and diagnostics. It cannot become infeasibility, numerical failure, or a top-level `Unsupported` that discards evidence. Boundary validation requires `operation_rejected` and `ScopedRequestRejection` together. Cross-field contradictions reject at publication rather than silently lose evidence.

This sketch keeps completeness evidence structurally present only in the complete case and makes a candidate's relation direction explicit; it does not prove evidence correctness by construction. Bind every completeness claim to all of: the resolved-problem content digest; the effective objective and family request (including profile and tolerance identity); the ordered joint-coordinate schema; the strategy ID/version; and the ordered transformation lineage with input/output identities. The verifier rejects a binding mismatch before it checks evidence. A witness, any finite collection of witnesses, objective agreement, or a small floating-point residual alone is never completeness evidence.

The evidence assurance must be a typed distinction, not a boolean: `NumericalToleranceSupport` records the arithmetic, tolerances, coverage procedure and diagnostics that support a numerical claim but does not prove exact set equality or certify coverage; `ValidatedCompletenessCertificate` is reserved for a checked certificate under an explicitly supported validated arithmetic/model profile. Do not label binary64/tolerance evidence exact, certified, or validated. `CompleteOptimalFamily` denotes a completeness claim at the explicitly carried assurance level; callers can require validated assurance and reject numerical support. If a method cannot establish its requested coverage level, it returns `PartialOptimalFamily`, `CandidateFamily`, or `Unsupported`. Exact evidence payloads, numerical acceptance policy, and which methods can produce each assurance remain proposed/open for review. Query results carry their source family identity and cannot change the family outcome or upgrade its completeness.

The intended typed binding is approximately:

```cpp
struct CompletenessBinding {
  ResolvedProblemDigest problem;
  EffectiveFamilyRequestDigest request;
  JointCoordinateSchemaId coordinates;
  StrategyVersion strategy;
  std::vector<TransformStepIdentity> lineage;
};
struct NumericallySupportedCompleteness {
  ArithmeticProfile arithmetic;
  ToleranceProfile tolerances;
  CoverageProcedureId procedure;
  CoverageDiagnostics diagnostics;
};
struct ValidatedCompleteness {
  ValidatedCertificate certificate;
  ValidatedArithmeticProfile arithmetic;
};
using CompletenessAssurance = std::variant<NumericallySupportedCompleteness,
                                           ValidatedCompleteness>;
struct CompletenessEvidence {
  CompletenessBinding binding;
  CompletenessAssurance assurance;
};
```

These names are conceptual and remain proposed; the snippet specifies the required distinctions, not settled C++ declarations or a claim that every strategy can construct either assurance.

**Public evidence migration gate (#155, #157, T-V02).** Today's `check_family_evidence` is not a safe gate for complete-family publication. It rejects validated assurance and rejects `NumericalCheck` when supplied as completeness support, but for an exact-family target under numerical assurance it does not require established completeness: `Unestablished` passes, and any `SymbolicArgument` or unchecked `CertificateReference` also passes after problem-ID checks. For partial or candidate targets it requires `Unestablished` completeness support. Registry admission can separately require `Completeness::established`, but that declaration does not validate the family's evidence. Treat the exact-family guard as a migration gap: publish no complete-family claim until the shared boundary accepts only evidence whose type, binding, provenance, and support have been checked for the requested assurance. The proposed `NumericallySupportedCompleteness` is not accepted by today's guard. Before either strategy publishes a complete family, migrate `OptimalFamily`, request/result contracts, `check_family_evidence`, registry offers/admission, artifact encoding, and all callers together. Review the scientific coverage procedure, arithmetic/tolerance policy, and acceptance criteria; owner/reviewer-selected thresholds remain open and are not invented here. Then add independent public-interface tests for rejected unestablished or unverified support and the reviewed positive evidence case. No sketch overrides the current guard.

T-V02 must reject samples, relaxed relations, backend success, plain numerical residuals, incomplete scope, and mismatched bindings as complete-family evidence. It also rejects numerical evidence presented as validated. Extend it with positive acceptance of the reviewed numerical-coverage evidence at numerical assurance only, negative validated-assurance admission, and tampered problem/request/coordinates/strategy/lineage cases. #157 additionally tests cancellation, resource limit, numerical failure, retained bounds/incumbents, and illegal complete-family combinations through the public strategy seam. Until that migration and policy are checked, return a supported partial/candidate relation or unsupported; T-X01 remains open. Residual checks support witnesses and optimum diagnostics, never complete coverage by themselves.

**Geometry operation planning (proposed; owner review open).** Keep registered geometry adapters, and add one typed planning seam for representation-dependent operation pipelines. A proposed `GeometryOperationRequest` names the operation, ordered input representation IDs, requested output representation (if constrained), guarantee relation and strength, and required capabilities. `GeometryOperationPlanner` resolves it to a `PreparedGeometryPlan`: a typed sequence of operation/conversion/approximation registrations with intermediate representation IDs, assumptions, provenance, and an operation-specific guarantee transfer for each step and for the composition. There is no generic “best available guarantee” ordering: admission must check whether each specific operation preserves the requested relation and whether the composed result proves the requested claim. A missing transfer rule, incompatible representation, or weakened guarantee rejects the plan before any workspace is created. Every path that may claim a complete optimal family requires exact/equivalent transformations at every step under the declared mathematical contract; an inner, outer, heuristic, or otherwise weaker relation can only produce an appropriately typed partial/candidate result unless a separate reviewed theorem proves coverage. Exact algebraic operations evaluated in floating point still carry numerical support, not a validated exactness certificate. The proposed v1 plan composes the existing geometry, conversion, and approximation registries as the single selection path. It introduces no operation-plan registry. The first comparison admits only exact-compatible plans.

**One bounded-work and cancellation owner (proposed v1 default; owner review open).** One task-level execution owner creates a control object and lends it to the selected strategy and nested algorithms/adapters; `SynthesisWorkspace` receives the shared cancellation/resource context, not a second scheduler. Strategy and algorithm work is serial within each task in v1. The outer executor owns parallelism across independent tasks/scenarios/strategy runs and admits them under its declared task/resource policy. A future internal-fan-out seam may issue permits from that same owner; strategies must not create an independent pool or budget. Report resource policy as separate configured, admitted, observed, and enforced facts for backend threads and memory: a requested/selected thread count or memory estimate is not proof of runtime enforcement, and OS-level thread/memory limits must not be claimed unless the adapter/platform actually enforces them. Record backend-reported or measured use where available, and say “unknown/unavailable” otherwise. This policy avoids oversubscription in v1 without implying a global hard limit that the implementation cannot enforce.

**Strategy A/B joint-history contract (proposed v1 invariant).** Both strategies consume the same immutable resolved problem and effective family request, and both must target the full minimizer locus in canonical joint coordinates `(x0,…,xT,u0,…,u(T−1))`. Strategy A may propagate reachable relations and recover backward, but its recovery result must remain a joint history relation (or equivalent dependency-preserving parameterization); it cannot multiply independent state/control/time marginals. Strategy B may build a joint LP/convex program, but after finding the optimum it must extract the entire optimal face/minimizer locus through the source-to-program coordinate map, including degenerate or constant-objective cases. A primal optimum, tied witness list, or terminal minimizer alone is insufficient. Both outputs carry the same typed completeness/assurance and identity-binding contract above; inability to preserve coordinates, dependencies, or coverage lowers the outcome to partial/candidate/unsupported. The proposed callable flow below assigns the common relation and lineage to one publisher, while each strategy owns its derivation and exclusive workspaces.

**Comparison identity and immutable run references (proposed v1 contract; owner review open).** Give the normalized comparison definition a content-derived `ComparisonSpecId` over the resolved-problem digest; effective strategy/profile and objective request; tolerances and requested assurance; requested outputs/projections; and selected strategy, algorithm, backend, thread/memory policy and relevant version/configuration identities. Persist every repetition as an immutable content-addressed run record, referenced by a `RunRecordRef` that identifies that exact record. An executed paired comparison has a `ComparisonRunId`, derived from its `ComparisonSpecId` and the ordered full set of `RunRecordRef`s (including repetition identity). Preserve every requested repetition and every terminal outcome, including unsupported, failed, cancelled and incomplete runs; do not form the run identity from successful runs only. This separates “same experiment definition” from “these exact observed runs,” while ensuring that changes in backend configuration, output scope, evidence level, or any run payload cannot silently reuse a comparison identity. Comparison rendering reads those references and never executes a solver.

### Callable preparation, synthesis, and publication

These C++20 sketches evolve the existing contracts in one migration. Names absent from the inspected headers remain **Proposed**. No second strategy registry or solve interface is introduced. `FamilyRequest` is the effective request after application defaults are resolved. It carries the profile, objective identity, target scope, arithmetic/tolerance policy identity, requested assurance, representation, and declared output limits. Preparation snapshots the resolved problem and this request together.

```cpp
// Proposed evolution of existing registry::StrategyRequest and contracts.
struct FamilyRequest {
	ProfileId profile;
	ObjectiveIdentity objective;
	FamilyTarget target;
	NumericalPolicy numerical;              // authoritative immutable policy identity
	Assurance assurance;
	FamilyOutputContract output;
};
struct StrategyRequest {
	problem::ResolvedProblem problem;
	StrategyConfiguration configuration;
	FamilyRequest family;
};
class SynthesisWorkspace : public ExclusiveWorkspace {
public:
	virtual SynthesisOutcome solve(const problem::ResolvedProblem&,
		const FamilyRequest&, const ExecutionContext&) = 0;
};
// StrategyPort::run calls w.solve(r.problem, r.family, context).
problem::StrategyAdmission problem::prepare_strategy(
	const ResolvedProblem&, const registry::StrategyRegistry&,
	const StrategyConfiguration&, const FamilyRequest&,
	const registry::Requirements&, std::optional<std::string> strategy_version = {});

// Caller sketch after migration; handle admission/task alternatives first.
auto admitted = problem::prepare_strategy(resolved, strategies, configuration,
	effective_family_request, requirements);
auto prepared = require_admitted(admitted);
auto task = require_task(execution::make_task(task_id, prepared.preparation(), resources));
auto observed = executor.run(tasks_containing(task));
// Persist Returned<StrategyPort>, Skipped, TaskFailure, or preparation rejection.
```

`FamilyRequest.numerical` is the authoritative policy identity for solving and family evidence. The execution owner derives the `ExecutionContext` numerical policy from that prepared request; it cannot independently override tolerances. Reject a mismatched context before the first workspace runs. Verification has a separately identified policy only when explicitly requested; bind its identity into verification evidence and report it separately from the solve policy, so it cannot retroactively change the solve claim.

The current overload lacks `FamilyRequest` and `StrategyPort::run` passes a DTO `Problem`. The migration updates request snapshots, `PreparedResolvedStrategy`, strategy registration capability callbacks/factories, and callers together. The existing include graph has `problem/validator.hpp` include `registry/registry.hpp` before `ResolvedProblem` is defined, so this by-value request cannot simply be placed in `registry.hpp`. Break the cycle as part of the same migration: move the immutable `ResolvedProblem` handle declaration and storage-independent identity into a lower-level `problem/resolved_problem.hpp` included by both headers, or define an immutable owning `ResolvedProblemHandle` there. Move only registry-independent data/identity into that header; keep registry admission glue in a layer that can include both modules without making either depend on the other. Do not use a raw pointer or permit a mutable DTO across the admission boundary. Retire the old solve overload once callers move; it must not remain a route that bypasses family admission. `PreparedResolvedStrategy` retains the resolved owner and effective request through execution and verification. `PreparedStrategy` retains selected registration/provenance after registry destruction. Whole-plan admission checks every known dependency before factories run. Each generated concrete request then passes through `PreparedProvider<Port>::prepare(request)` with frozen requirements before its request-specific workspace is created. No per-query requirement override is added.

Candidate B's first relation storage is an immutable `HistoryRows` with sparse inequality/equality rows, canonical `JointLayout`, and source-row origins. `JointLayout` owns state/control block offsets. `ProgramCoordinateMap` binds source and native variables, slack/eliminated coordinates, source rows, and objective reformulations to the exact program identity. Every transformation records ordered input/output relation identities, coordinate maps, module versions, assumptions, and guarantee transfer. Program compilation and family extraction use the same map, not separately inferred offsets.

```cpp
class HistoryRelationBuilder {            // private to one strategy solve
public:
	Result<void> append_stage_factor(StageIndex, const TransitionFiber&);
	Result<void> append_original_rows(const OriginalRowMap&);
	Result<void> append_terminal_minimizers(const TerminalMinimizerRelation&);
	Result<HistoryRows> freeze();             // immutable owning snapshot
};
class ReachBackWorkspace final : public SynthesisWorkspace {
public:
	SynthesisOutcome solve(const problem::ResolvedProblem&, const FamilyRequest&,
		const ExecutionContext&) override;
private:
	StageOutcome forward(StageIndex, const SetHandle&, const ExecutionContext&);
	RecoveryOutcome recover(StageIndex, const SetHandle& reachable,
		const SetHandle& viable_next, const ExecutionContext&);
	// Owns prepared geometry recipe, LP/convex providers, scratch, and builder.
};
class DirectJointWorkspace final : public SynthesisWorkspace {
public:
	SynthesisOutcome solve(const problem::ResolvedProblem&, const FamilyRequest&,
		const ExecutionContext&) override;
private:
	Result<CompiledHistoryProgram> compile(const problem::ResolvedProblem&);
	Result<HistoryRows> extract(const CompiledHistoryProgram&,
		const TerminalMinimizerRelation&, const ProgramCoordinateMap&);
	// Owns prepared LP/convex providers, sparse program, map, and builder.
};
class FamilyPublisher {                   // sole constructor of claimed OptimalFamily
public:
	Result<OptimalFamily> publish(const problem::ResolvedProblem&, const FamilyRequest&,
		HistoryRows, const DerivationRecord&, const FamilyClaimFacts&) const;
};
Diagnostics check_synthesis_result(const SynthesisResult&,
	const problem::ResolvedProblem&, const FamilyRequest&);
struct VerificationRequest { NumericalPolicy numerical; Assurance assurance; };
struct VerificationRecord {
	ProblemId problem;
	std::vector<NamedTrajectoryResidual> residuals;
	ScopedClaimCheck feasibility, optimality, completeness;
	Verifier verifier;
};
VerificationRecord OriginalProblemVerifier::check(const problem::ResolvedProblem&,
	const SynthesisResult&, const WitnessSelection&, const VerificationRequest&) const;
```

For A, `R[0]` is the initial point intersected with its admitted domain. Forward propagation computes `R[t+1] = X[t+1] ∩ image(R[t] × U[t])` under the original affine transition. Terminal optimization returns all minimizers `M`, then backward recovery starts with `K[T]=M`. Each recovery step retains `C[t]={(x,u,y): x∈R[t], u∈U[t], y∈K[t+1], y=A[t]x+B[t]u+a[t]}` and computes `K[t]=projection_x(C[t])`. The builder joins the retained `C[t]` on the same canonical state coordinates, anchored at the initial point. It never multiplies stage marginals. These forward/predecessor operations implement #53 and #51 inside Strategy A #66; the hull reducer is only an optional admitted operation implementation.

For B #67, `compile` writes the original initial row, every transition and admitted domain row, and the supported terminal objective into one LP/convex program. Its provider admits that generated program, then the optimizer and terminal-minimizer analysis #61 supply the full optimal equalities. `extract` adds those equalities to the retained original feasible-history rows and maps the result to canonical coordinates. It does not infer a family from one primal or from only the active inequalities at that primal. Both paths handle singular dynamics without an inverse assumption and feed the same `FamilyPublisher`.

The publisher checks claim binding, coordinate coverage, source-row coverage, objective reformulation, and every registered guarantee transfer. It cannot prove an adapter's theorem or validate numerical coverage from residual checks. Independent original-problem verification #43 checks returned witnesses; a separate evidence audit checks the claim binding and scope. Only the result guard accepts the finished combination of outcome, termination, relation, bounds, and incumbents.

### Family selection and mathematical projection

Use the existing `registry::SelectorPort`, whose workspace is `WitnessSelectorWorkspace`; there is no new family-query registry. Evolve `SelectorRequest` to carry the guarded `OptimalFamily` handle and retain `select(family, WitnessRequest, context)`. Admission checks the representation, requested selection directions, count, distinctness metric/tolerance, assurance, and output limits. Later membership or secondary optimization needs a separately reviewed query variant.

```cpp
struct WitnessSelection {                // proposed evolution of existing result
	FamilyId source;
	WitnessBatch batch;                      // requested and returned counts retained
	SelectionStatus status;                 // fulfilled, shortfall, or stopped
	Termination termination;
	StopEvidence stop;
	SelectionEvidence evidence;             // metric, duplicates, search/shortfall facts
	registry::Provenance provenance;
};
using SelectionOutcome = std::variant<WitnessSelection, Unsupported>;
// Existing selector workspace method, with the evolved owning family handle:
SelectionOutcome WitnessSelectorWorkspace::select(const OptimalFamily&,
	const WitnessRequest&, const ExecutionContext&);

struct FamilyProjectionRequest {
	OptimalFamily source;
	std::vector<std::size_t> coordinates;     // ordered canonical indices
	GeometryOutputRequest output;            // representation, relation, assurance, limits
};
struct FamilyProjectionResult {
	FamilyId source;
	SetHandle projected;
	ProjectionCoordinateMap coordinates;
	GeometryEvidence evidence;
	TransformLineage lineage;
};
using FamilyProjectionOutcome = std::variant<FamilyProjectionResult,
	OperationStopped, Unsupported>;
FamilyProjectionOutcome project_family(const FamilyProjectionRequest&,
	const PreparedGeometryPlan&, const ExecutionContext&);
```

For selection, an admitted LP provider searches different directions on the retained relation, decodes complete histories, evaluates the original objective, and records duplicate filtering. Every query result preserves source family identity and claim scope. A shortfall explains exhausted directions, duplicates, or a stop; fewer witnesses proves neither uniqueness nor completeness. A stopped selection may retain already checked witnesses without upgrading the source claim.

Mathematical projection uses the existing `GeometryPort` `Projection` operation. A representation adapter exposes the immutable relation as a `SetHandle` with an equivalent map to canonical coordinates. If that adapter or projection capability is absent, admission returns unsupported. Geometry evidence binds the source relation, ordered requested coordinates, and output identity. Projection of a partial or candidate relation remains explicitly a projection of that source scope. Selected-witness plots are a different artifact and never receive set-projection evidence.

### Geometry plans over the existing registrations

`GeometryOperationPlanner` owns no new registry. Its catalogue view borrows the current typed registries during admission; a successful plan retains selected registrations through owning `PreparedProvider` values. Ordered operand contracts include representations and coordinate schemas; concrete operand identity is bound when each generated request is admitted.

```cpp
struct GeometryOperationRequest {
	GeometryRequestIdentity identity;         // problem + immutable full request payload
	GeometryOperation operation;              // tagged operands: affine map, projection, etc.
	GeometryOutputRequest output;            // relation + assurance + capacity requirements
};
struct GuaranteeTransfer {
	OperationSpecificRuleId rule;
	std::vector<GuaranteeContract> required_inputs;
	GuaranteeContract output;
	CoordinateTransfer coordinates;
	std::vector<Assumption> assumptions;
};
struct GeometryStep { registry::PreparedProvider<registry::GeometryPort> provider;
	GuaranteeTransfer transfer; };
struct ConversionStep { registry::PreparedProvider<registry::ConversionPort> provider;
	GuaranteeTransfer transfer; };
struct ApproximationStep { registry::PreparedProvider<registry::ApproximationPort> provider;
	GuaranteeTransfer transfer; };
using GeometryPlanStep = std::variant<GeometryStep, ConversionStep, ApproximationStep>;
class PreparedGeometryPlan {
public:
	std::span<const GeometryPlanStep> steps() const;
	GuaranteeContract composed_guarantee() const;
	std::unique_ptr<GeometryPlanWorkspace> create() const;
};
struct GeometryPlanRejected { GeometryRequestIdentity identity; registry::Rejection reason; };
using GeometryPlanAdmission = std::variant<PreparedGeometryPlan, GeometryPlanRejected>;
GeometryPlanAdmission GeometryOperationPlanner::prepare(const GeometryOperationRequest&,
	const ExistingGeometryRegistries&) const;
struct GeometryPlanResult { OperationResult result; TransformLineage lineage;
	GuaranteeContract applied_guarantee; };
struct GeometryPlanStopped { GeometryRequestIdentity identity; OperationStopped reason;
	TransformLineage completed_lineage; };
struct GeometryPlanRejectedAtRuntime { GeometryRequestIdentity identity;
	registry::Rejection reason; TransformLineage completed_lineage; };
using GeometryPlanOutcome = std::variant<GeometryPlanResult, GeometryPlanStopped,
	GeometryPlanRejectedAtRuntime>;
GeometryPlanOutcome GeometryPlanWorkspace::run(const GeometryOperationRequest&,
	const ExecutionContext&);
```

This reuses the existing discriminated geometry operand contract: `AffineImage` carries its matrix and offset; `Projection` carries ordered coordinate indices; `AffinePreimage` carries its map and offset; and other variants carry their set operands, direction, or containment pair. `GeometryRequestIdentity` binds the complete immutable payload. The planner derives ordered representation/coordinate contracts from those operands, checks every intermediate representation and operation-specific guarantee transfer before workspace creation, and freezes concrete requests in prepared providers. The workspace runs those exact prepared requests; it cannot substitute a different matrix, projection, or operand after admission. Existing support/containment outcomes retain their own typed results. Execution verifies each returned identity/evidence and appends actual transformation lineage. Preparation rejection carries the original request identity; a stopped or late-rejected step carries that identity, its reason, and all completed lineage. Such an outcome yields no successful final set and cannot discard prior synthesis evidence when propagated to the strategy result.

There is no universal ordering of guarantees. Image, intersection, predecessor, and projection each need a reviewed rule for their input/output relation and assurance. Missing rules or weakened guarantees reject a complete-family request. Inner/outer/heuristic steps can produce a correspondingly scoped partial/candidate result only where their registered rule supports that claim. Exact/equivalent mathematical transformations evaluated in binary64 still carry numerical assurance. Approximation adapters remain outside the first comparison. Selecting the concrete exact operation/capacity fixture for #51 remains an open scientific gate.

### Comparison records and offline export

Extend the existing `artifacts::RunRecord` and `publish_run`/`encode_run` path with versioned synthesis, family, query, verification, and lineage attachments. Reuse its resolved configuration, module/resource observations, spans, and execution summary. The application composition root writes one record for every requested attempt, including preparation rejection, skipped task, task failure, unsupported, stopped, or incomplete output. Allocation/internal invariant failures are runtime failures, never mathematical infeasibility.

```cpp
struct ComparisonSpecId { problem::ContentDigest digest; };
struct ComparisonRunId { problem::ContentDigest digest; };
struct RunRecordRef { artifacts::RunId run; ArtifactDigest content; };
struct ComparisonSpec {
	ComparisonSpecId identity;
	ProblemId problem;
	FamilyRequest request;
	std::vector<RunSelection> methods;
	RepetitionPlan repetitions;
	QueryOutputScope output;
};
struct AttemptRecord { AttemptId attempt; MethodIndex method; RepetitionIndex repetition;
	AttemptStatus status; RunRecordRef record; }; // status checked against saved outcome
struct ComparisonRecord { ComparisonSpecId spec; ComparisonRunId run;
	std::vector<AttemptRecord> attempts; };  // full ordered set, never successful-only
ArtifactResult<ComparisonSpec> resolve_comparison(const problem::ResolvedProblem&,
	const ComparisonDefinition&);
ArtifactResult<ComparisonRecord> compare(const problem::ResolvedProblem&,
	const ComparisonSpec&, ExecutionOwner&, RunArtifactWriter&);

struct ExportLimits { std::optional<std::size_t> bytes, artifacts, projection_elements; };
struct ReportProjectionRequest { ReportViewScope scope; ExportLimits limits; };
struct CompleteReportProjection { ReportData data; std::vector<RunRecordRef> sources; };
struct LimitedReportProjection { ReportData data; std::vector<RunRecordRef> sources;
	OmissionManifest omissions; ExportLimitEvidence limit; };
using ReportProjectionOutcome = std::variant<CompleteReportProjection,
	LimitedReportProjection, ExportRejected>;
ReportProjectionOutcome project_report(const SavedComparisonView&,
	const SavedRunReader&, const ReportProjectionRequest&);
struct CompleteExport { ExportManifest manifest; };
struct LimitedExport { ExportManifest manifest; OmissionManifest omissions;
	ExportLimitEvidence limit; };
using HtmlExportOutcome = std::variant<CompleteExport, LimitedExport, ExportRejected>;
HtmlExportOutcome export_html(const ReportProjectionOutcome&,
	const SavedArtifactReader&, const HtmlExportRequest&);
```

Comparison normalization binds the resolved problem, effective request/objective, requested and actual method/version/configuration identities, numerical/resource policies, query/output scope, and repetition setup. `ComparisonRunId` binds the spec and every ordered attempt reference. Admission rejection has a persisted diagnostic record with a known-not-called observation. Incomplete/stopped runs remain visible but fail the complete-family comparison gate. Backend substitutions are separately identified comparisons; a compatible fixed backend is used for the first strategy comparison.

The offline report projection reuses saved family projections and witness artifacts; it cannot launch geometry, query, or synthesis work. `LimitedReportProjection` and `LimitedExport` name omitted payloads, plots, or raw-data attachments and retain identities/counts/limit evidence. Missing or mismatched required records reject export; size limits never silently truncate evidence. HTML uses the existing publication envelope/report-kind adapter path where available, with synthesis as a new saved-data kind rather than a per-strategy publisher. Reports distinguish witness traces from mathematical set projections and carry coordinate names/units. #83 and T-X02 cover round-trip provenance, phase timings, and unavailable counters. The first numerical result gets an English HTML report even while T-X01 remains open.

## End-to-end flow and dependency direction

```mermaid
flowchart LR
    File[Scenario file or C++ Problem] --> Load[load_scenario_file / input adapter]
    Load --> Resolve[problem::resolve → ResolvedProblem]
    Resolve --> Prepare[prepare_strategy / StrategyRegistry]
    Prepare --> Plan[StrategyPlan → PreparedStrategy]
    Plan --> Task[make_task / Executor]
    Task --> Strategy[StrategyPort → exclusive SynthesisWorkspace]
    Strategy --> Provider[PreparedProvider::prepare for each generated request]
    Provider --> Geometry[PreparedGeometryPlan / geometry and conversion ports]
    Provider --> LP[LPPort / ConvexPort]
    Geometry --> Strategy
    LP --> Strategy
    Strategy --> Family[FamilyPublisher → guarded OptimalFamily]
    Family --> Query[SelectorPort / typed GeometryPort projection]
    Query --> Verify[Independent original-problem verifier]
    Strategy --> Observe[Execution and module observations]
    Query --> Observe
    Verify --> Record[RunRecord + comparison records]
    Observe --> Record
    Record --> Export[Saved-data HTML / tables / figures]
```

Application strategies depend on mathematical ports and immutable problem data. Numerical adapters depend on those port contracts, not on fuel-specific equations, strategy classes, plotting, or report formatting. Execution owns workspaces and resource admission. Verification reads the resolved original problem and returned witnesses/family evidence; it does not trust the strategy's success flag. Report rendering consumes saved records only.

The intended preparation path is `problem::prepare_strategy(resolved, strategy_registry, configuration, effective_family_request, requirements)`, followed by `execution::make_task(prepared.preparation(), ...)` and `Executor::run`. The effective family request is the same immutable request snapshot shown in the proposed signature above; admission must not silently supply or mutate its numerical policy, assurance, target, or output contract. `prepare_strategy` returns `PreparedResolvedStrategy`; `make_task` consumes its contained `registry::PreparedStrategy` through `.preparation()`. The prepared strategy retains the selected strategy, effective request, and provenance; the application retains the `ResolvedProblem` through verification and publication. This is an actual entry path, while the end-to-end diagram still contains proposed synthesis, family-query, verification, and comparison modules.

## Runnable now and the first end-to-end milestone

The [README quick start and examples](../../../README.md#quick-start) are runnable installed-package demonstrations of model construction, scenario-file loading, objective/program execution, and substitution between two real LP adapters. They demonstrate several current modules; they do not yet run a control-planning strategy, construct the full optimal trajectory relation, independently verify that family, or publish a synthesis comparison. The [current composition page](../../architecture/framework-composition.md#substitution-that-runs-today) lists these concrete examples and the missing glue.

The first end-to-end milestone starts when both proposed synthesis strategies can consume the same resolved supported problem and family request, return the same declared complete optimal-family target with consistent witnesses, pass independent original-problem checks, and produce comparable saved run records. A solver point, standalone backend swap, example evaluation of supplied controls, sampled witnesses, or partial/candidate relation is useful runnable progress but does not meet that milestone. Numerical runs are published from persisted data as HTML with raw measurements; rendering does not launch solvers. The owner-confirmed profile, evidence limits, and open design choices below still govern the scope, so this milestone does not claim support for every representable future model or assurance level.

## Class and module map

| Responsibility | Status and public seam | Request → result and evidence | Dependencies, replacement point, tickets |
|---|---|---|---|
| Scenario intake | **Implemented:** `input::load_scenario_file`, `LoadedScenario`, `HistoricalScenario`, `RequestedRun` in `include/csl/input/scenario_loader.hpp` | Versioned input bytes/options → loaded immutable problem description, source digest/provenance, and separately requested run settings; parse/schema/unsupported outcomes remain distinct. | Depends on problem/model value contracts. New file formats replace/add an intake adapter. [INP-01 #44](https://github.com/butahlecoq/controlled-systems-lab/issues/44) is closed; [INP-02 #75](https://github.com/butahlecoq/controlled-systems-lab/issues/75), [INP-03 #72](https://github.com/butahlecoq/controlled-systems-lab/issues/72) remain open. |
| Dynamics, observations, and sets | **Implemented data contracts:** `model::LinearSystem`, `SetData`, `SetHandle`, `HRepresentation`, `VRepresentation`, elementary sets. `SystemModel` supports affine discrete/continuous descriptions and observation schedules. | Authored model/set values → immutable snapshots with dimensions, stage and observation metadata. This publishes data; it does not establish solver support or reachability. | `CSL::model`, `CSL::sets`, `CSL::numeric`. New model classes or set representations need explicit operations and guarantees. [MODEL-01 #15](https://github.com/butahlecoq/controlled-systems-lab/issues/15), [GEO-01 #16](https://github.com/butahlecoq/controlled-systems-lab/issues/16). |
| Domains, initial/external information, and constraints | **Implemented data contracts:** `problem::ControlDomains`, `InitialData`, `ExternalData`, `Constraints`, including temporal data. | Scenario/model data → dimension-checked immutable values; unsupported algorithm profiles must remain a capability rejection. | Depends on model, sets, numeric snapshots. The model preserves optional state/control and temporal constraints, while the first experiments add none beyond source-documented domain bounds; strategies declare and enforce their admitted capability profile. [MODEL-02 #20](https://github.com/butahlecoq/controlled-systems-lab/issues/20) and [MODEL-03 #28](https://github.com/butahlecoq/controlled-systems-lab/issues/28) are closed; [TEST-03 #47](https://github.com/butahlecoq/controlled-systems-lab/issues/47) remains open. |
| Problem resolution and identity | **Implemented:** `problem::resolve`, `ResolvedProblem`, `PreparedResolvedStrategy`, `prepare_strategy` in `include/csl/problem/validator.hpp`. | `Problem` plus resolution context/content → resolved immutable problem and stable identity, then selected registry admission; resolution does not claim feasibility or optimality. | Depends on validated model/problem values and `StrategyRegistry`. Original resolved data is the authority for independent checking and saved-run binding. [MODEL-03 #28](https://github.com/butahlecoq/controlled-systems-lab/issues/28), [TEST-03 #47](https://github.com/butahlecoq/controlled-systems-lab/issues/47). |
| Module selection and fixed-request composition | **Implemented:** `Registry<Port>`, typed `Selection`, `CheckedPipeline`, `PreparedPipeline`, `StrategyRegistry`, `StrategyPlan`, `PreparedStrategy` in `include/csl/registry/registry.hpp`. | Concrete typed requests, module ID/version, requirements and producer transitions → checked rejection or owning preparation/workspace factory with actual provenance. Fixed pipeline checks happen before snapshots/factory creation. | Strategy planners declare typed dependencies using existing registrations. Replacement point for LP, convex, set-operation, conversion, approximation, selector, and strategy adapters. [CORE-04 #14](https://github.com/butahlecoq/controlled-systems-lab/issues/14), [REVIEW-01 #59](https://github.com/butahlecoq/controlled-systems-lab/issues/59). |
| Generated-request provider | **Implemented on `main` by merged PR #143:** `ProviderSelection`, `CheckedProviders`, `PreparedProvider`, `check_providers`, and provider-aware `compose_strategy` in `include/csl/registry/provider.hpp`. | A selected registration and frozen requirements produce an owning provider. Each generated concrete request is capability-checked against those frozen requirements before request snapshot/workspace creation. `PreparedProvider::prepare(request)` does not accept per-query requirement overrides. | Used when an algorithm generates different LP/geometry requests during execution. Provider admission is implemented and tested as a reusable module; reducer and strategy integrations are tracked separately. [OPT-05 #30](https://github.com/butahlecoq/controlled-systems-lab/issues/30); [PR #143](https://github.com/butahlecoq/controlled-systems-lab/pull/143). |
| LP-backed hull reducer | **Implemented on `main` by merged PR #144:** `registry::HullReducerPort`, `geometry::HullReducerWorkspace`, and `geometry::make_lp_hull_reducer_registration()` add method selection for `csl.hull.lp-membership@1.0.0`. `registry::RegisteredLPQueryRunner` owns a frozen `PreparedProvider<LPPort>` and admits every generated membership query. | `BoundWorkspace<HullReducerPort>::run_with(context, LPWorkspace&)` delegates to the selected reducer workspace. Passing `RegisteredLPQueryRunner` composes the selected reducer with per-query LP capability checks before each request-specific workspace factory. Closed query records retain request identity, selected provider provenance and bounded outcome metadata; rejection creates no workspace, and accepted execution forwards the caller's context sequentially. The reducer binds completed results to submitted program identities and composes/rechecks barycentric witnesses against retained points, restoring support when checks fail. | The caller-level composition tests cover separate reducer/provider selection, per-query admission, alternative providers, admission rejection, registry destruction before use, workspace isolation, cancellation/deadline and backend resource outcomes. The low-level `LPWorkspaceView` remains for direct borrowed solves; it is not the generated-request path. This is an independent-membership baseline, not modified-simplex basis reuse or general reachability. [PR #144](https://github.com/butahlecoq/controlled-systems-lab/pull/144); [OPT-05 #30](https://github.com/butahlecoq/controlled-systems-lab/issues/30). |
| LP and convex program contracts/adapters | **Implemented:** immutable `LinearProgram`/`ConvexProgram`, primal/dual evaluators, `LPPort`/`ConvexPort`, registry contracts, `highs_lp`, `highs_convex`; `phase-one-bland` is a specialized feasibility adapter. | Program + numerical/evidence requirements → program outcome, primal/dual residuals, optional bound/basis evidence, or unsupported status. | Strategies and geometry algorithms depend on ports; implementations remain replaceable. Phase I is not a general nonzero-objective simplex solver. [OPT-01 #17](https://github.com/butahlecoq/controlled-systems-lab/issues/17), [OPT-02 #18](https://github.com/butahlecoq/controlled-systems-lab/issues/18), [OPT-03 #21](https://github.com/butahlecoq/controlled-systems-lab/issues/21), [OPT-08 #22](https://github.com/butahlecoq/controlled-systems-lab/issues/22). |
| Historical and alternative optimization adapters | **Replaceable inventory; status is per method below.** Keep LP pivot kernels, hull-level candidate-reduction strategies, and smooth convex optimizers as distinct adapter families; “simplex variant” must not collapse these levels. | Same typed LP, hull, or convex request → method-specific result/certificates and counters, with method/version and source lineage in provenance. | `LPPort`, `HullReducer`/geometry operations, and `ConvexPort` are separate substitution seams. Candidate inventory and evidence are detailed below. |
| Saved report adapters and publication | **Partially implemented on `main`:** LP/convex report drivers and production catalogue schema v2; the current catalogue is not deployed. **Under draft PR #150 for issue #148:** `PublicationRecord`, registered report-kind adapters, saved-data HTML projection, and deterministic offline ZIP generation. | Validated LP/convex or typed OPT-05/GEO-03 records plus an immutable catalogue → one staged static site with numeric tables, scope/evidence limits, checked SVG/raw-data links, and per-report offline bundles. Unknown kinds, mismatched summaries, unsafe paths/SVG, and hash or provenance mismatches reject before staging; all dynamic plain text is contextually escaped for HTML, while SVG follows an allowlisted structured schema. | `adapt(bundle)` is the typed publication seam; adapters own native schema validation, while one `site.stage` path owns catalogue validation and deployment staging. Rendering reads saved records only and never runs a solver. Keep the common catalogue/envelope and explicit kind registry; do not add per-algorithm deployment pipelines. [REPORTS #148](https://github.com/butahlecoq/controlled-systems-lab/issues/148), [PR #150](https://github.com/butahlecoq/controlled-systems-lab/pull/150), [HTML-01 #123](https://github.com/butahlecoq/controlled-systems-lab/issues/123). |
| Geometry operations and representation conversion | **Implemented contracts, incomplete adapters:** `GeometryPort`, `ConversionPort`, `ApproximationPort`; operation/conversion/approximation request and result/evidence types. Set data supports H/V descriptions, but not every operation or conversion has an implementation. | Operation request → operation/support/containment result; conversion or approximation request → transformed set plus equivalent/inner/outer/heuristic relation and evidence. | Keep representation ID, guarantee direction, assumptions and evidence attached to every transform. Compatible implementations are chosen through typed registries. [GEO-02 #40](https://github.com/butahlecoq/controlled-systems-lab/issues/40), [GEO-03 #31](https://github.com/butahlecoq/controlled-systems-lab/issues/31), [GEO-04 #41](https://github.com/butahlecoq/controlled-systems-lab/issues/41), [GEO-05 #51](https://github.com/butahlecoq/controlled-systems-lab/issues/51). |
| Qhull H/V conversion adapter | **Implemented on `main`:** registered `ConversionPort` implementation for bounded native H/V polyhedra. It uses the caller-selected LP adapter for feasibility, boundedness, and relative-interior queries. Declared unsupported: nonempty V rays, unbounded H sets, ambiguous rank, and unsupported assurance; size policies are optional (no implicit dimension/row caps). Numerical residual audit is not an exact or validated global certificate. | Substitute for bounded H↔V conversion only within that profile; propagate explicit unsupported outcomes and numerical evidence. Do not imply general unbounded-polyhedron conversion. | [PR #145](https://github.com/butahlecoq/controlled-systems-lab/pull/145) is merged; [GEO-03 #31](https://github.com/butahlecoq/controlled-systems-lab/issues/31) remains open for published evidence and remaining acceptance. |
| Reachability and predecessor operations | **Proposed:** `ReachabilityStepper`, `PredecessorAlgorithm`, and a nominal transition/recovery contract. No public strategy-level implementation exists. | Resolved problem, stage, reachable/target relation, and selected exact operation capabilities → next reachable relation or predecessor plus coordinate/evidence mapping. | Depends on stagewise domain checks, geometry operations, selected LP where membership/projection requires it. A fast inverse path must declare nonsingularity; the general relation path must handle singular A. [SYN-01 #53](https://github.com/butahlecoq/controlled-systems-lab/issues/53), [GEO-05 #51](https://github.com/butahlecoq/controlled-systems-lab/issues/51), [TEST-10 #65](https://github.com/butahlecoq/controlled-systems-lab/issues/65). |
| Terminal optimum and minimizer set | **Proposed:** `TerminalOptimizer` returning optimum evidence and the complete supported minimizer relation, not one terminal point. | Reachable terminal relation + original objective → optimum/bounds and minimizer set, with attainment, target representation, and completeness scope. | Depends on objective module, LP/convex capability, and exact relation operations. Constant objectives, exposed faces, and degenerate quadratic/residual objectives must preserve ties or reject full coverage. [SYN-02 #61](https://github.com/butahlecoq/controlled-systems-lab/issues/61), [TEST-11 #69](https://github.com/butahlecoq/controlled-systems-lab/issues/69). |
| Strategy A: reachability and backward recovery | **Proposed adapter of implemented `StrategyPort`/`SynthesisWorkspace`:** compose forward stage reachability, terminal minimization, and backward predecessor/recovery. | Resolved problem + optimal-family request → joint state/control family, optimum evidence, assumptions, and timing spans. It must preserve all histories and terminal minimizers. | Depends on reachability/predecessor, terminal optimizer, family builder, geometry/LP adapters; shares input/output contract with Strategy B. [SYN-03 #66](https://github.com/butahlecoq/controlled-systems-lab/issues/66), [TEST-13 #77](https://github.com/butahlecoq/controlled-systems-lab/issues/77). |
| Strategy B: direct joint-trajectory optimization | **Proposed adapter of `StrategyPort`/`SynthesisWorkspace`:** a trajectory-program builder plus an optimal-relation extractor. | Resolved problem → sparse program for `x0…xT,u0…u(T-1)`, explicit source-to-program coordinate map, optimum relation, and problem/program evidence association. | Depends on immutable model/objective, LP or convex ports, terminal minimizer/family construction, and generated-request providers if the extractor needs additional solves. Must encode every transition and stage constraint and handle singular A. [SYN-04 #67](https://github.com/butahlecoq/controlled-systems-lab/issues/67), [TEST-12 #74](https://github.com/butahlecoq/controlled-systems-lab/issues/74). |
| Joint optimal-family representation | **Partially implemented, not final:** `JointCoordinates`, `JointRelation`, `OptimalFamily`, `FamilyTarget`, `FamilyEvidence`, `Witness` in `include/csl/contracts.hpp`; `OptimalFamily` currently keeps target and evidence as independent fields and can express contradictions. `JointRelationPayload` is opaque and has no query methods. | Proposed closed outcome variant over canonical `x0…xT,u0…u(T-1)` coordinates: complete claim with explicit numerical-support or validated-certificate assurance; partial relation with known coverage scope; candidate with explicit inner/outer/heuristic relation-to-target. Completeness evidence binds resolved-problem digest, effective objective/request, ordered coordinate schema, strategy/version and transformation lineage. | Proposed relation adapters preserve dependencies and answer declared queries without materializing unnecessarily large projections. A witness sample never proves family completeness. Replacing the current loose shape with validated typed outcomes is an implementation gap; this proposal is not an approved code interface. The shared strategy-boundary contract is tracked in [SYN-07 #155](https://github.com/butahlecoq/controlled-systems-lab/issues/155), with its expanded independent public-API suite in [TEST-24 #157](https://github.com/butahlecoq/controlled-systems-lab/issues/157). [SYN-02 #61](https://github.com/butahlecoq/controlled-systems-lab/issues/61), [SYN-03 #66](https://github.com/butahlecoq/controlled-systems-lab/issues/66), [SYN-04 #67](https://github.com/butahlecoq/controlled-systems-lab/issues/67). |
| Family queries and witness selection | **Partially implemented:** `registry::SelectorPort`/`WitnessSelectorWorkspace`, `WitnessRequest`, `WitnessSelection`. **Proposed evolution:** selection keeps that registered seam; mathematical projection uses `GeometryPort` with typed source-family binding. Membership and secondary optimization remain later query variants. | Optimal family + query → a consistent witness or explicitly labelled projected relation, target/evidence preservation, query provenance, counts, resource/cancellation outcome. A query never upgrades a partial/candidate family to complete; fewer distinct witnesses does not establish uniqueness. | Query adapters operate on the opaque joint relation and may use replaceable geometry/optimization providers. Report projection and witness selection use the same family identity/evidence contract. [SYN-05 #71](https://github.com/butahlecoq/controlled-systems-lab/issues/71), [TEST-13 #77](https://github.com/butahlecoq/controlled-systems-lab/issues/77), [VIZ-02 #91](https://github.com/butahlecoq/controlled-systems-lab/issues/91). |
| Independent trajectory/evidence verification | **Proposed:** replaceable numerical `TrajectoryVerifier` plus future validated-evidence adapter. Existing residual evaluators cover optimization programs; generic `check_family_evidence` is not a trajectory verifier. | Resolved original problem + witness/family + tolerance/assurance request → named dynamics, initial, control/state/temporal residuals, original objective, evidence-binding diagnostics, and explicit unsupported/validated status. | Must not call back into the synthesis strategy to establish correctness. Feasibility, objective optimality, family completeness, and validated proof are distinct claims. [SYN-06 #43](https://github.com/butahlecoq/controlled-systems-lab/issues/43), [REVIEW-04 #85](https://github.com/butahlecoq/controlled-systems-lab/issues/85). |
| Task execution and workspace isolation | **Implemented:** `execution::Task`, `make_task`, `Executor::run`, `ResourceUse`, `ExecutionContext`, bounded outer admission, cancellation and lifecycle observations. | Prepared typed/strategy work + resource declaration → per-task exclusive workspace, outcome, provenance, timing and enforcement report. Native solver threads are declared; OS-level thread enforcement is not promised. | Suitable for independent batches/scenarios and strategy invocations. No scheduler/task-group is injected into `SynthesisWorkspace`; nested/algorithm-internal parallel fan-out and total solver-thread coordination need a design decision. [RUN-01 #25](https://github.com/butahlecoq/controlled-systems-lab/issues/25) is closed; [RUN-02 #80](https://github.com/butahlecoq/controlled-systems-lab/issues/80), [OBS-02 #60](https://github.com/butahlecoq/controlled-systems-lab/issues/60), [REVIEW-05 #95](https://github.com/butahlecoq/controlled-systems-lab/issues/95). |
| Run observation and artifact publication | **Implemented foundations:** `SynthesisResult.spans`, `execution::observability::CollectionPlan`/`ObservationShard`, `artifacts::RunStatistics`, `FamilyRecord`, attachments, `publish_run`, `encode_run`/`decode_run`. These do not automatically instrument solver internals or create a comparison report. | One resolved problem/configuration/run + final result, collection, resource/execution observations and attachments → validated immutable portable run record and encoded bytes. | Collection consumes explicit observations; record codecs are independent of solver workspaces. Family payload may be an attachment or `FamilyWithoutExporter`, so a synthesis-family exporter remains to implement. [OBS-01 #49](https://github.com/butahlecoq/controlled-systems-lab/issues/49) is closed; [OBS-02 #60](https://github.com/butahlecoq/controlled-systems-lab/issues/60), [OBS-03 #79](https://github.com/butahlecoq/controlled-systems-lab/issues/79). |
| Comparison, visualization, and HTML reports | **Partially implemented:** LP/convex report drivers and static artifacts exist. Proposed seams: comparison-run coordinator/record, backend-neutral plot data, family exporter and offline report renderer. | Same resolved problem and normalized effective request plus paired runs/settings → aligned objective, residual, evidence, strategy/backend provenance, submodule timings/resources and witness differences. `ComparisonSpecId` identifies the immutable definition (problem, request/profile/tolerances, assurance/output scope, strategy/backend/resource configuration); `ComparisonRunId` identifies one executed paired comparison and derives from that spec plus its complete ordered `RunRecordRef` set. Each immutable content-addressed `RunRecordRef` retains one repetition and its outcome; preserve every requested repetition and terminal outcome. Use the same compatible backend/resource policy where possible; label exceptions. Performance comparisons alternate at least five tuned Release repetitions per strategy and report median/range plus separate limiter profiling. | Compare saved records; never rerun solvers during rendering. Raw inputs and schema allow regeneration; axes and projection guarantees are explicit. Fuel fixture state order: oxidizer flow (kg/s), oxidizer working-stock balance (kg), fuel flow (kg/s), fuel working-stock balance (kg); support every distinct in-range state-coordinate pair. Label each plot as witness coordinates, sample cloud, or mathematical projection. `u ∈ [-1,1]` is the owner-approved working assumption for baseline scenarios; it remains separate from B04 archival provenance and does not restore other missing historical inputs. [EXP-02 #94](https://github.com/butahlecoq/controlled-systems-lab/issues/94), [OBS-04 #83](https://github.com/butahlecoq/controlled-systems-lab/issues/83), [OBS-05 #86](https://github.com/butahlecoq/controlled-systems-lab/issues/86), [VIZ-01 #87](https://github.com/butahlecoq/controlled-systems-lab/issues/87), [VIZ-02 #91](https://github.com/butahlecoq/controlled-systems-lab/issues/91), [VIZ-03 #96](https://github.com/butahlecoq/controlled-systems-lab/issues/96). |

### Exact geometry and future representation adapters

`SetRepresentation`, `GeometryPort`, `ConversionPort`, and `ApproximationPort` remain separate seams: a mathematical set's representation, an exact operation/conversion, and an enclosure algorithm make different guarantees. The first paired strategy comparison admits only exact/equivalent geometry plans; it does not enable reachable-set approximations. The current bounded Qhull H/V converter is one implemented adapter, not a complete exact polyhedral operation algebra: intersection, projection, predecessor, and any other missing operation must be registered and reviewed before a strategy can claim that profile.

| Adapter family | Proposed role and mathematical scope | Status and gate |
|---|---|---|
| H/V polyhedral representations and operations | Exact reference representation for supported polyhedral intersections, affine images, projections, support/membership, and optimal faces; each operation has declared dimension/boundedness/capability requirements. | H/V data and operation contracts exist; current H/V conversion supports a bounded subset only. Finish and test the operations each strategy actually needs. Admission rejects missing operations; first comparison accepts only supported exact/equivalent plans. |
| Zonotope / constrained-zonotope representation | Preserve generator coordinates and shared factors for exact affine propagation where the input and operation permit it. Constrained zonotopes add equality-constrained factors to retain dependencies through some polytopic restrictions. | Future replaceable adapters. Exact affine propagation may be eligible for the first comparison only if the operation plan preserves the complete-family contract; zonotope reduction or any other reachable-set approximation remains excluded. The recovered fuel paper supports its stated nominal propagation case, not arbitrary intersections or a universal polyhedral solver. Preserve the joint-history dependence needed for optimal-family queries. |
| Parallelotope enclosure adapter | A replaceable `ApproximationPort` method returning a named inner or outer parallelotope and the operation-specific inclusion/evidence; expose orientation, generator reduction and resource/quality policy. | Future approximation family. A parallelotope is not presumed exact for arbitrary reachable sets, and its enclosure direction alone does not prove optimizer-family coverage. Excluded from the first comparison. |
| Ellipsoid and ellipsoidal-family adapters | Proposed `EllipsoidRepresentation` plus `EllipsoidalApproximationStrategy`; support explicit single-ellipsoid or composite directional-family results, with inner/outer direction, degeneracy, assumptions, and membership/support capabilities. | Future research adapter, not first comparison. The historical dossier cites Kurzhanski/Varaiya work; the likely software reference is the Kurzhanskiy/Varaiya Ellipsoidal Toolbox, but the supplied archive does not establish which library/version the owner used. Treat ET as an external, version-pinned comparison/reference only after compatibility review; do not make its MATLAB types the C++ contract. |
| Other inner/outer approximators | Additional methods register behind `ApproximationPort` with representation IDs, error/quality parameters, input-set identity, inclusion direction, and operation-specific evidence. | Extensible future seam, not an enum of built-in approximations. A finite directional sample or heuristic reduction remains labelled approximate; it cannot silently be promoted to an exact family. |

These representation candidates and their scientific caveats are catalogued in the [set-representation and ellipsoidal-toolbox review](../../architecture/set-representations-and-ellipsoidal-toolbox.md). No performance ranking or universal best representation is implied; the strategy planner selects only a method whose operations and guarantee composition satisfy the request.

### Replaceable optimization-method inventory

These are candidate adapters, not a claim that every historical listing is a maintained implementation. Archive citations and caveats are collected in [`algorithm-module-inventory.md`](../../research/algorithm-module-inventory.md), especially its sections on phase-I, basis reuse, ordered/grouped filtering, and Zoutendijk. The exact C++ implementation baseline was checked at `ab1c6ac`; source transcriptions are evidence, not executable product dependencies.

| Candidate slot | Repository evidence and status | Intended seam and scope | Ticket |
|---|---|---|---|
| Professor/source simplex lineage | **Archived mathematical description; exact professor-original program not identified.** The 1993 article (source-map L01; `phase-one-lineage.md`) describes a modified-simplex feasibility procedure and control reconstruction; related saved MATLAB/Pascal listings are not proven byte-for-byte or algorithm-for-algorithm to be the professor’s original release. | Baseline LP-feasibility adapter behind `LPPort`, with supported row/bound profile, termination, primal/basis evidence, and deterministic counters stated explicitly. Do not label the current kernel “the original professor implementation.” | [OPT-05 #30](https://github.com/butahlecoq/controlled-systems-lab/issues/30) establishes the LP-backed hull baseline; [OPT-04 #29](https://github.com/butahlecoq/controlled-systems-lab/issues/29) covers the bounded phase-I kernel. |
| Modified simplex / basis-informed hull reduction | **Archived and transcribed as research evidence; not a product adapter.** `algorithm-module-inventory.md` cites L07 §3.4 and archive MATLAB sources A15/A16, distinguishing within-solve bulk classification from cross-query warm starts. The implemented `phase-one-bland` kernel is a separate, bounded zero-objective equality feasibility implementation. | Preserve a replaceable hull-reduction adapter using valid information from a completed LP solve. Expose certificates/counters; verify bulk deletions and do not equate a feasible basis with globally extreme points without proof. | [OPT-06 #37](https://github.com/butahlecoq/controlled-systems-lab/issues/37). |
| Ordered/grouped method historically described as “divide-and-conquer” | **Archived/transcribed variants; none is literal recursive split-and-merge.** `algorithm-module-inventory.md` distinguishes L03/L07 and archive `QLPHULL.m` variants; active ordered/grouped filters end with LP reduction. | Separate hull-level ordering/grouping adapter over the hull-reduction seam. Keep this distinct from LP pivot rules and from recursive divide-and-conquer. | [OPT-07 #38](https://github.com/butahlecoq/controlled-systems-lab/issues/38). |
| Recursive split-and-merge hull strategy | **Proposed extension; no archived implementation claimed.** | Optional hull-level adapter `hull(hull(P₁) ∪ hull(P₂))`, with deterministic partitioning, shared resource budget, and independent hull-equality verification. | [OPT-11 #45](https://github.com/butahlecoq/controlled-systems-lab/issues/45). |
| Zoutendijk / feasible-directions projection | **Archived/transcribed Pascal procedure, not a supported C++ product adapter.** `algorithm-module-inventory.md` identifies A06 `btulshor.pas:766–886` (`ZODENTEK`) and its linearly constrained Euclidean projection role, unresolved dependencies, and step-bound concern. It is not evidence of a general smooth optimizer. | `ConvexPort` adapter initially for projection / equivalent smooth quadratic on a declared linearly constrained profile; report feasibility and stationarity/optimality evidence at the promised assurance level. Generic smooth objectives are a separate extension. | [OPT-09 #39](https://github.com/butahlecoq/controlled-systems-lab/issues/39), then [OPT-10 #50](https://github.com/butahlecoq/controlled-systems-lab/issues/50). |
| General LP backend (HiGHS) | **Implemented adapter:** `highs_lp` under the current LP port; adapter identity and source live in `src/adapters/lp/highs.cpp` and its registration/header. | Interchangeable general LP backend subject to declared capabilities and evidence actually exposed by the selected backend. It is not a historical simplex reproduction. | [OPT-02 #18](https://github.com/butahlecoq/controlled-systems-lab/issues/18); reusable adapter tests [TEST-05 #35](https://github.com/butahlecoq/controlled-systems-lab/issues/35). |
| Archival phase-I Bland feasibility kernel | **Implemented bounded adapter:** `phase-one-bland` in `include/csl/optimization/phase_one.hpp` and `src/optimization/phase_one/simplex.cpp`; code rejects nonzero objectives and profiles outside nonnegative variables/equality rows. | Specialized `LPPort` feasibility method. Keep its narrow profile visible and do not present it as a replacement for a general LP solver or all archived simplex variants. | [OPT-04 #29](https://github.com/butahlecoq/controlled-systems-lab/issues/29); [OPT-03 #21](https://github.com/butahlecoq/controlled-systems-lab/issues/21). |

## Strategy contracts and essential invariants

Both strategies receive the same resolved problem and request. Strategy selection and backend selection remain separate. Each planner first checks the declared method/version/capabilities and every known dependency; it snapshots requests and creates numeric/native work only after the whole plan is admissible. Generated-request providers are required where the algorithm discovers new programs during execution. No strategy receives an unchecked raw workspace or may silently weaken the requested relation.

### Remaining class-level gaps for the two-strategy comparison

The implemented registry, execution, LP/convex, and request-provider seams do not yet form either synthesis strategy. The following gaps remain explicit; this map does not assign them to unreviewed classes or assume that one strategy's internal representation fits the other.

1. **Strategy-level generated-request composition.** Merged #143 provides frozen `PreparedProvider` admission, and merged #144 composes it per query inside the hull reducer. This does not establish either synthesis strategy end to end. Strategy A/B still need reviewed composition plans for their generated LP and geometry requests, with typed provenance, requirement admission, cancellation/outcome propagation, and explicit workspace lifetime/reuse. The low-level `LPWorkspaceView` remains a direct borrowed-solve adapter, not the generated-request path.
2. **Reachability plus backward recovery.** Strategy A still needs executable forward reachable-set and predecessor operations, a terminal optimizer that preserves all minimizers, and a recovery relation that retains cross-time state/control dependence. `HullReducerPort` only removes redundant points from an already generated candidate cloud; it does not implement those operations. H/V conversion alone does not provide intersection, projection, or predecessor semantics.
3. **Direct joint optimization and complete relation extraction.** Strategy B still needs a source-to-program coordinate map, a trajectory program builder for every admitted constraint, and an extractor for the full optimal relation. Current LP/convex solve results and a single returned primal are not an optimal family. Constant or degenerate objectives must preserve all feasible minimizers, with completeness evidence separate from the optimum claim.
4. **Common verification and comparison path.** Neither strategy implementation currently returns the complete relation target required by the common contract. An independent verifier must check original dynamics, constraints, objective, and evidence binding; a comparison runner must hold request/profile and compatible backend fixed, retain unsupported/failure/cancellation outcomes, and persist the same family/evidence fields from each method. Existing run records and program-level reports do not provide this synthesis layer.

The two strategy tickets and their module tests remain the implementation path: [SYN-03 #66](https://github.com/butahlecoq/controlled-systems-lab/issues/66), [SYN-04 #67](https://github.com/butahlecoq/controlled-systems-lab/issues/67), [SYN-06 #43](https://github.com/butahlecoq/controlled-systems-lab/issues/43), [TEST-12 #74](https://github.com/butahlecoq/controlled-systems-lab/issues/74), and [TEST-13 #77](https://github.com/butahlecoq/controlled-systems-lab/issues/77). These are implementation gaps assigned to the proposed workspace/publisher flow above, not a claim that either algorithm supports the whole model contract.

For the two-stage integrator with `u0+u1=1`, the family must preserve that equation: the Cartesian product `[0,1] × [0,1]` is invalid because it admits `(0,0)` and `(1,1)`. Distinct selected witnesses such as `(0,1)` and `(1,0)` must retain their consistent state histories and equal primary objective. Constant objectives must retain every feasible trajectory. If the implementation only produces witnesses or a numerical candidate enclosure, it must report that target and its incomplete/relaxed evidence honestly.

The verifier recomputes initial conditions, every transition, all declared supported constraints, and the original objective from the immutable problem. Any program result used as evidence must be tied to its source problem and transformation map. Plots show selected witnesses or declared projections; they do not imply the full relation is visualized. Timing totals distinguish nested inclusive spans from additive work and report unavailable metrics explicitly.

## Scientific gates before complete-family acceptance

The callable interfaces above are proposed ticket defaults, not implementation approval. These scientific choices remain unresolved for the first workflow:

1. **Numerical coverage policy.** Review the complete-family characterization for each supported terminal objective and define the numerical coverage procedure, arithmetic/tolerance policy, and acceptance thresholds. No thresholds are invented here. Optimum diagnostics and witness residuals do not establish complete coverage. Coordinate/lineage binding and the `check_family_evidence`/T-V02 migration must ship with that reviewed policy.
2. **Exact-operation and capacity fixture.** Select the concrete H/V operation chain, supported dimensions/output-size limits, and analytic oracle fixtures for A's images, intersections, predecessor projections, and joint relation. H/V conversion and hull reduction alone are insufficient. Missing operations or coverage support produce unsupported/partial/candidate records and cannot pass T-X01.

Historical archive gate, separate from the first workflow: source B04's original bounds, conventions, and missing inputs before making that archival manifest executable. The owner-approved `u ∈ [-1,1]` bound applies only to new baselines and does not repair or redefine B04.

The nominal open-loop profile, deterministic initial point, absent/zero disturbance, continuous controls, supported terminal objectives, and no added state/temporal coupling constraints are confirmed scope. They do not require another owner-confirmation gate. Record/query identities, one publisher, existing-registry/provider composition, serial work within a task with outer-executor concurrency, and saved-data export are proposed defaults specified above. Future feedback/disturbance quantifiers, uncertain initial states, nonempty temporal couplings, hybrid/discrete relation support, validated arithmetic, and approximation adapters require separate capability review after this slice. They do not gate the nominal numerical workflow.

## Ticket alignment and review gates

The main workflow is tracked by [SYN-01 #53](https://github.com/butahlecoq/controlled-systems-lab/issues/53), [SYN-02 #61](https://github.com/butahlecoq/controlled-systems-lab/issues/61), [SYN-03 #66](https://github.com/butahlecoq/controlled-systems-lab/issues/66), [SYN-04 #67](https://github.com/butahlecoq/controlled-systems-lab/issues/67), [SYN-05 #71](https://github.com/butahlecoq/controlled-systems-lab/issues/71), and [SYN-06 #43](https://github.com/butahlecoq/controlled-systems-lab/issues/43). Module contract tests are tracked separately by [TEST-10 #65](https://github.com/butahlecoq/controlled-systems-lab/issues/65), [TEST-11 #69](https://github.com/butahlecoq/controlled-systems-lab/issues/69), [TEST-12 #74](https://github.com/butahlecoq/controlled-systems-lab/issues/74), and [TEST-13 #77](https://github.com/butahlecoq/controlled-systems-lab/issues/77), and shared outcome-boundary tests [TEST-24 #157](https://github.com/butahlecoq/controlled-systems-lab/issues/157). Independent whole-system reviews are [REVIEW-01 #59](https://github.com/butahlecoq/controlled-systems-lab/issues/59), [REVIEW-03 #82](https://github.com/butahlecoq/controlled-systems-lab/issues/82), and [REVIEW-06 #90](https://github.com/butahlecoq/controlled-systems-lab/issues/90). The architecture agreements remain open in [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8), and user feedback [#140](https://github.com/butahlecoq/controlled-systems-lab/issues/140); this draft is intended to make those reviews concrete, not to close them. Hybrid-system extension work is separately tracked by [EXT-07 #156](https://github.com/butahlecoq/controlled-systems-lab/issues/156).

The proposed interface/test ownership is concrete:

| Ticket seam | Acceptance through the caller-facing interface |
|---|---|
| #53 reachability, #51 geometry, #66 Strategy A | T-S01 joins recovery fibers to enforce `u0+u1=1`; singular dynamics need no inverse. Every admitted geometry step retains coordinate/guarantee lineage and output limits. |
| #61 terminal minimizers, #67 Strategy B | T-S02 keeps all trajectories for a constant objective; T-S03 keeps multiple control histories even with a unique terminal minimizer. Source-to-program row/coordinate maps preserve these cases through extraction. |
| #43 independent verification | T-V01 detects injected transition, control-domain, and original-objective errors using named numerical residuals and the configured policy. T-V02 audits assurance, scope, and all claim bindings independently of strategy status. |
| #155 shared synthesis boundary, #157 public-interface tests | Run both registered strategies through the migrated `StrategyPort`; reject contradictory family products and test distinct termination versus mathematical outcome. Force a late `PreparedProvider` rejection after valid evidence exists and assert the caller retains bounds, incumbents, scoped partial/candidate relation, request identity, and completed lineage. Verify numerical-policy identity mismatch rejects before execution. T-V02 independently checks all claim bindings and assurance. |
| #66/#67 comparison, #83 run statistics/artifacts | T-X01 runs both strategies on T-S01/02/03 with the same effective request and compatible backend. T-X02 round-trips every attempt, family/query identities, phase timings, resource/selector provenance, failed/stopped records, and explicitly limited exports through saved artifacts. |

T-S01's established analytic `[0,1]` control fixture remains its oracle; the new-baseline `[-1,1]` decision does not silently rewrite it. A sampled witness or objective agreement cannot pass T-X01. T-X02 verifies offline renderers using saved records with no solver/query/geometry execution. Future numerical adapters and representations add independent substitution tests when implemented.

## Self-review against issue #140 and owner decisions

- This map starts from the whole scenario-to-saved-result flow, rather than another individual numerical optimization.
- It keeps the first pair of approaches explicit and distinct, while allowing each strategy and numerical adapter to be replaced independently; fair comparison holds a compatible LP/convex backend fixed.
- It makes a complete joint state/control family an acceptance gate; partial relations and sampled witnesses remain labelled outcomes, not success.
- It distinguishes merged GEO-03 conversion and merged provider/reducer implementations #143/#144 from proposed end-to-end strategy composition. Per-query reducer/provider admission is implemented; A/B synthesis is not.
- It reserves future domains and guarantees without claiming current solver support; new baselines use the owner-approved control bound, archival cases retain source-only domain bounds, and verification is numerical-first.
- It identifies open seams and owners through existing issues without changing ticket scope or declaring any ticket complete.
