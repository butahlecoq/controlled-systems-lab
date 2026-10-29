# EXT-04 one-stage affine observation-policy synthesis

## Problem

The controller layer already evaluates a caller-authored `AffineObservationPolicy` over the complete convex hull of an authored `JointVUncertainty` V-representation. It checks linear state/action rows at every generator, reuses the observed-replay timing lifecycle, and returns per-step numerical evidence. It does not search for a policy. The next increment should synthesize an affine action law whose selected observations are available before the decision, and then pass it through that evaluator. A one-transition horizon keeps the policy coefficients linear in the fixed generator readings; multi-stage observation feedback can make later observation/state maps depend multiplicatively on earlier gains.

This is a genuine but bounded synthesis profile: the result is universal over every point of the authored joint hull, including every initial coordinate and its authored external/error correlations. It does not implement `exists initial state, for all disturbance/error`, policy optimization, or validated arithmetic. EXT-04 remains open after this increment.

## Usage

The caller supplies the joint V-domain, the observation components the controller may use at the single decision, linear state/action safety rows, and an admitted LP workspace. The workspace and execution context are explicit algorithm dependencies, matching other generated-LP operations in the repository.

```cpp
controllers::OneStageAffineSynthesisRequest request{
    .feasibility_program = {{"ext04-one-stage"}, {"feasibility"}},
    .domain = domain,
    .action_features = {controllers::ObservationComponentRef{{0}, {0}, 0}},
    .state_safety = {initial_rows, terminal_rows},
    .action_safety = {action_rows},
    .feasibility_tolerance = 1e-9,
};

auto result = controllers::synthesize_one_stage_affine_policy(
    system, request, lp_workspace, execution_context);
```

A successful result contains an `AffineObservationPolicy` and the existing `ContinuousPolicyEvidence` from a second full-domain evaluation. A near-boundary candidate, malformed LP result, numerical stop, or a solver-reported infeasibility without an independently verified certificate is inconclusive. It must not be reported as proof that no policy exists.

## Shape

```cpp
struct OneStageAffineSynthesisRequest {
    ProgramIdentity feasibility_program;
    JointVUncertainty domain;
    std::vector<ObservationComponentRef> action_features;
    std::vector<LinearSafetyConstraints> state_safety;
    std::vector<LinearSafetyConstraints> action_safety;
    double feasibility_tolerance{1e-9};
};

enum class AffineSynthesisInconclusiveReason {
    solver_reported_infeasible_without_certificate,
    solver_did_not_establish_feasibility,
    malformed_solver_result,
    candidate_violates_safety,
    candidate_within_tolerance_band
};

struct SynthesizedAffinePolicy {
    AffineObservationPolicy policy;
    ContinuousPolicyEvidence evaluation;
    ProgramResult feasibility_solve;
};

struct AffineSynthesisInconclusive {
    AffineSynthesisInconclusiveReason reason;
    std::optional<AffineObservationPolicy> candidate;
    std::optional<ProgramResult> feasibility_solve;
    std::optional<ContinuousPolicyEvidence> evaluation;
};

using OneStageAffineSynthesisResult = std::variant<
    SynthesizedAffinePolicy, AffineSynthesisInconclusive,
    Diagnostic, OperationStopped>;

OneStageAffineSynthesisResult synthesize_one_stage_affine_policy(
    const model::LinearSystem&,
    const OneStageAffineSynthesisRequest&,
    LPWorkspace&,
    const ExecutionContext&);
```

Validation requires a one-transition linear system, a nonempty list of unique observation-component features, each released by `before_decision(0)`, finite safety matrices with exactly two state slices and one action slice, a finite nonnegative tolerance, and a complete joint V-domain. The policy class is data-only; synthesized actions are affine in exactly the named measurements. The builder uses zero state-estimate maps, so no state-estimation accuracy is implied.

For each joint generator, the requested feature vector is fixed. The unknown vector contains the action gain and offset. Every action safety row and the terminal-state safety row therefore gives a linear inequality in these unknowns. Initial-state safety rows are checked on the same joint generators. Convert free gain/offset variables to positive-minus-negative variables and each inequality to an equality with a nonnegative slack. The generated zero-objective LP then uses the repository's nonnegative equality-feasibility profile.

The generated rows include a small strict margin greater than the evaluator tolerance and solver absolute tolerance. This helps phase one return a policy with positive safety slack instead of a vertex exactly on a closed safety boundary, which the evaluator would correctly call inconclusive. If the tightened rows are infeasible, numerical LP status still returns inconclusive; the margin does not support a no-policy claim.

The operation receives an `LPWorkspace` because generated requests belong to the existing provider pipeline. The caller supplies a nonempty `ProgramIdentity`; the operation records that identity and the complete `ProgramResult`, while the caller owns provider selection/provenance. It does not link a solver implementation into controllers. A conservative generated-LP storage estimate is checked against the execution memory budget before allocating generator constraints. Cancellation, deadline, resource, unsupported, and numerical outcomes remain visible at this boundary.

Only a completed solver result with a primal candidate proceeds. Reconstruct the policy, evaluate it with `evaluate_continuous_policy(scope=all_joint_uncertainty)`, and return success only when that independent replay has no violation and no tolerance-band margin. `Assurance::numerical` is retained. A solver's numerical infeasible status is not elevated to a no-policy theorem: the current phase-one adapter does not return an independently checked exact Farkas certificate. Such a case is `AffineSynthesisInconclusive`.

The synthesis call hides coefficient indexing, LP row construction, policy materialization, and full-generator replay. It exposes the solver workspace and finite safety/domain inputs because those are real caller choices. It does not add a generic policy-optimization framework, objective contract, or separate trajectory format. The policy-evaluation API now has a separate H-domain operation; that does not extend this V-domain synthesis request.

## Synthesis decision

Candidate 2 is the base: it directly synthesizes continuous affine feedback over the existing joint V-domain and reuses its evaluation evidence. The cross-judge verified that one-step rows are affine in the policy gains when observations are fixed before the only action. Candidate 1's explicit coverage and search-completeness discipline is grafted as status discipline: this operation always declares `all_joint_uncertainty`; tolerance-band and solver uncertainty are inconclusive; no unchecked infeasible/no-policy conclusion is returned.

Candidate 1's finite action catalogue, scenario-tree search, and shared mutable replay cursor are rejected for this change. They are a legitimate future feature but only quantify over enumerated concrete rows, so they do not advance the open continuous initial-set gap as directly. The policy-table representation also cannot be passed to `evaluate_continuous_policy`, which accepts a data-only affine law.

## Tradeoffs accepted

- We accept a one-transition horizon in exchange for linear feasibility in policy coefficients; multi-stage synthesis needs a separately justified causal parameterization.
- We accept universal coverage of the complete authored joint hull, not existential-initial/universal-environment quantifier alternation.
- We accept a joint V-representation and its caller-authored completeness in exchange for the existing convex-hull generator argument.
- We accept numerical assurance and tolerance-band inconclusive results; ordinary floating-point replay is not a validated proof.
- We accept feasibility-only output; no policy cost or optimality claim is made.
- We accept explicit LP workspace/context parameters to preserve solver injection, execution budgets, and provider layering.

## Alternatives considered

- **Finite scenario-tree synthesis:** adds a finite action catalogue and constructs nonanticipative table policies, but only proves the supplied rows and does not solve continuous initial-set policy synthesis. This should be a separately scoped feature.
- **Multi-stage affine-gain synthesis:** unknown earlier gains affect later observations and states, creating products among decision coefficients. A naive LP would be unsound; a causal reparameterization or restricted profile is required first.
- **Implicitly construct the phase-one solver inside controllers:** hides a solver from callers but cuts across the provider architecture, loses method choice and provenance, and bypasses caller execution/resource setup.
- **Return `Infeasible` directly from a numerical LP status:** hides the absence of an independent infeasibility certificate. Numerical solver status alone cannot prove no policy exists.

## Open questions and risks

- Does every required execution path already have a prepared LP workspace that can solve a generated nonnegative equality-feasibility request with the chosen assurance profile?
- Should a later extension add an exact-checked infeasibility certificate before exposing a distinct `no_policy_exists` result?
- Which affine feature sets and row counts are practical under the caller's `ExecutionContext` budgets?

## Implemented slice and remaining scope

The request validation, one-step coefficient-row builder, injected-workspace solve, affine policy materialization and all-generator evaluator check are implemented for joint V-domains. Contract tests cover universal success, after-decision rejection, solver infeasibility without a certificate, memory-budget stop and unsupported longer horizon. The result still has numerical assurance, and infeasibility remains inconclusive.

## Joint H-domain policy evaluation

`make_joint_h_uncertainty` accepts one H-represented set whose coordinates jointly contain the initial state, each stage's external inputs, and every scheduled measurement-error coordinate. Inequalities and equalities are retained, so correlations across those coordinate groups stay in the mathematical domain. The constructor checks representation shape and the system coordinate layout; it does not prove that the H-set is nonempty.

`evaluate_h_continuous_policy` first obtains a feasible point for the domain and verifies every stored H row exactly as binary64 dyadic values. It then derives each supplied safety-row activity as an affine function of the joint coordinates and constructs the dual LP for its support maximum. A support result is recorded only when a returned dual vector has nonnegative inequality multipliers, exact dyadic stationarity, and an exact dyadic objective strictly below the requested safety margin. A numerical LP residual alone is not a support certificate, including on unbounded H-domains. If the dual does not prove safety, a primal support LP searches for a violating point; a candidate counts only when it exactly satisfies the H rows and exactly violates the safety margin. The activity coefficients still come from floating-point replay, so the evaluator retains numerical assurance and makes no whole-operation validated-arithmetic claim. Empty or unverified domains, missing exact witnesses, unbounded support, and tolerance-band results remain inconclusive.

Before solving, the operation accounts for its generated LP buffers and retained size-dependent evidence: per-row dual and possible primal solution vectors, caller-derived solve-identity copies in outcome/objective/residual records, fixed local verifier tags, safety coefficients, and worst-case replay records. `ResourcePolicy.memory_bytes` remains admission/accounting rather than a hard process-memory limit. Provider-internal allocations and unbounded provider-returned text metadata (raw diagnostics, support explanations, assumptions, and verifier IDs) are outside this estimate because providers expose no size bound for them.

The H operation evaluates a caller-authored fixed affine policy; it does not synthesize one. The one-stage synthesis request above still uses the joint V-representation. Robust H-domain synthesis needs a separate coefficient-level dualization contract and tests. Both H evaluation and V synthesis leave EXT-04 open for existential/all-initial quantifiers, multi-stage lifecycle synthesis, partial/noisy scenario separation, and universal disturbance/error certificates beyond the authored domain.
