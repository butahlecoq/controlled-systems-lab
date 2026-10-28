# Finite causal minimax design

## Problem

Issue #601 needs a cost-optimal causal controller for an exact finite game, checked against both a Bellman reference and a worst-case scenario-tree optimizer. The repository already has fixed-plan minimax, safety-only finite feedback, and replay of listed observation scenarios; none returns a cost-optimal causal policy. The central design problem is representing information correctly: the controller sees the current exact state before choosing an action, then the disturbance is revealed. The optimizer must not choose actions by disturbance history when two histories have the same available state.

## Usage

The caller supplies one finite, stage-layered model to the public Bellman solver. The optional comparison report uses the same authored case in a private HiGHS extensive-form model and independently replays its policy:

```cpp
using namespace csl::optimization::finite_causal_minimax;
const auto outcome = solve(make_finite_game(), Options{1e-12, 1e-12});
if(const auto* result = std::get_if<Result>(&outcome)) {
  const auto& initial = result->initial();
  // initial.value and initial.optimal_actions are the initial-state answer.
}
```

Correctness cases remain direct callers of the same operation:

```cpp
const auto strict_gap = solve(strict_gap_game(), Options{1e-12, 1e-12});
assert(strict_gap.initial().value == 1.0);
assert(strict_gap.initial().optimal_actions == expected_actions);
```

```cpp
const auto no_lookahead = solve(lookahead_counterexample(), Options{1e-12, 1e-12});
assert(no_lookahead.initial().value == expected_nonclairvoyant_value);
assert(no_lookahead.initial().optimal_actions == expected_nonclairvoyant_actions);
```

## Shape

The public domain type is a finite transition game. Its value structs are caller-owned and mutable; the solver reads them without mutation. Each stage contains counts for its canonical state catalogue, ordered action catalogue, finite disturbance catalogue, a safety mask, and a complete transition table. State identity uses semantic `StateId`s supplied by the model builder; exact coordinate vectors live in the source/report adapter. Equal exact observed states at the same stage must use the same ID. This avoids floating-point fuzzy merging and keeps the solver independent of physical units and plots.

```cpp
namespace csl::optimization::finite_causal_minimax {

struct StateId { std::size_t value; };
struct ActionId { std::size_t value; };

struct Stage {
  std::size_t state_count;
  std::size_t action_count;
  std::size_t disturbance_count;
  std::vector<bool> safe_states;
  // next_state[state][action][disturbance] -> StateId in the next stage.
  std::vector<std::vector<std::vector<StateId>>> next_state;
};

struct Terminal {
  std::size_t state_count;
  std::vector<bool> safe_states;
  std::vector<double> cost;
};

struct Game {
  std::vector<Stage> stages;
  Terminal terminal;
  StateId initial_state;
};

struct Options {
  double absolute_value_tolerance;
  double relative_value_tolerance;
};

struct StateValue {
  bool feasible;
  double value; // meaningful only when feasible
  std::vector<ActionId> optimal_actions; // every action tied within declared tolerance
};

struct Result {
  std::vector<std::vector<StateValue>> values_by_stage;
  StateId initial_state;
  const StateValue& initial() const;
};

using Outcome = std::variant<Result, Diagnostic>;
std::optional<Diagnostic> validate(const Game&, const Options&);
Outcome solve(const Game&, const Options&);
}
```

The public call hides Bellman table indexing and tie selection. Its inputs are the finite model and tie tolerances. The IDs are semantic model identities, not optimizer or report row indices. The optional comparison report owns tree expansion, MILP variables, nonanticipativity rows, solver status interpretation, and independent policy replay.

At the boundary, validate nonempty stages/actions/disturbances, matching dimensions, finite costs, valid initial and successor IDs, and safety-array lengths. Require a complete transition for every state/action/disturbance tuple. The contract is perfect exact state observation, stage-rectangular finite disturbances, Markov transitions, and terminal-state cost. Partial/noisy observation and history-dependent costs/resources are outside the contract; the solver does not silently approximate them.

The Bellman reference is a pure backward recursion:

```text
V_T(s) = terminal_cost(s)                         if terminal-safe
       = infeasible                               otherwise

Q_t(s,u) = max_d V_(t+1)(next(t,s,u,d))            if state is safe and
                                                     every disturbance branch is feasible
          = infeasible                             otherwise

V_t(s) = min_u Q_t(s,u)
optimal_actions_t(s) = all u tied under abs + rel value tolerance
```

This order enforces `min action` before `max disturbance`. If any required branch is unsafe or infeasible, that action is rejected; no branch is clipped. Strict-gap and lookahead fixtures establish the information semantics and retain every tied Bellman action.

The extensive-form optimizer belongs to the optional comparison report, not the installed library API. The report target uses the existing HiGHS dependency directly, following the MPC-03 report precedent; it adds no public MIP backend or package dependency. It expands the complete disturbance history tree from the initial state. Each decision occurrence has an action variable. When two occurrences have the same `(stage, StateId)`, explicit nonanticipativity equalities force their action variables to match. Thus equal available states cannot receive history-dependent actions, while distinct exactly observed states may branch. Every disturbance successor is included. Safety constraints exclude any action whose required successor is unsafe; a terminal epigraph bounds every reachable leaf cost. Minimize the root epigraph value. Extract one minimizing policy, then independently replay all disturbance branches and recompute its maximum terminal cost before reporting it.

The comparator also evaluates a separately executed fixed-plan re-planning selector: at each exactly observed state it enumerates all remaining fixed action sequences, chooses the first action of a least-worst sequence, observes the next state, and replans. On the strict-gap fixture, initial fixed-plan value and executed re-planning worst cost are both 2; causal Bellman/tree value is 1. The source has no do-mpc adapter. The current official [multi-stage formulation](https://www.do-mpc.com/en/latest/theory_mpc.html) uses a weighted sum of scenario costs and allows a shorter robust branching horizon. An exact worst-case objective requires replacing the sum with a shared worst-leaf epigraph and keeping complete horizon branching. The report records this as “unsupported unchanged” and implements the explicit full-tree MIP instead; it does not claim that custom do-mpc formulation is impossible.

The public Bellman solver is the result-producing library algorithm. The report's scenario-tree model independently walks the same finite game and records decision occurrences, canonical state nodes, equality count, leaf count, global bound, incumbent, and gap. Fixture transition maps are authored independently. For a source-derived environment, reconstruct the transition map from its pinned equations and verify the saved map separately to catch a common model-input error. An interrupted optimizer incumbent is not a global minimax result.

## Applied example: TwoPointsOnParallelLines

Use the existing #717 finite adaptation as the applied geometric case. Its physical coordinates are `(x1,x2,x3,x4)=(position_1, velocity_1, position_2, velocity_2)`, so report panels are `(x1,x2)` and `(x3,x4)`, the two player phase planes. The existing report already contains forward reachable polytopes, finite feedback-winning intersections, and a replayed worst-case minimax path in those panels. The new causal policy replay selects the same worst-case path for this adaptation. The existing feedback output is a terminal-gap safety threshold with a feasible selector, not a cost-optimal causal policy.

The existing adaptation has three stages, action/disturbance catalogues of size three, and exact layer sizes `1, 9, 81, 345`; its unmerged disturbance-history tree has at most `1+9+81+729=820` nodes. That is suitable for a complete causal cost solve and one visual report. Recompute causal cost-to-go values and policy branches; do not relabel the existing safety threshold as the new cost result. The existing fixed-plan and safety-threshold values coincide for this adaptation, so use the strict-gap fixture to show a causal-versus-open-loop value difference and TwoPoints to show the algorithms on a 4D differential-game model.

The report must identify the upstream commit/blob and no-code-copy policy; state that the original environment uses continuous controls over 10 seconds while this is a three-stage finite-catalogue, 0.3-second adaptation; list the exact action/disturbance catalogues and terminal squared position-gap cost; and scope the result to exact state observation and the listed finite disturbances. Do not claim an RL reproduction, continuous-game guarantee, or fuel-axis interpretation. The existing deployed report is [TwoPointsOnParallelLines](https://butahlecoq.github.io/controlled-systems-lab/env717-two-points-4fbedf73c6f198fd57e2/index.html).

## Synthesis decision

Candidate B is the base: it offers one comparison operation, hides node/MILP details, records global optimizer evidence and replay, and evaluates the TwoPoints graph concretely. Candidate A scored 13/15; Candidate B scored 15/15, matching the independent cross-judge. Graft from A: semantic state IDs rather than floating-point state equality, absolute and relative tie tolerances, and explicit nonanticipativity equalities with emitted counts. Candidate B's binary64 state-vector keys and a caller-supplied Markov boolean were rejected: state identity belongs to the exact model builder, and a boolean alone does not validate model sufficiency.

The compiled graph may be used for model storage and audit, but the scenario-tree solver must retain one action variable per information occurrence and literal equalities for repeated `(stage, StateId)` nodes. A shared variable is semantically equivalent, but explicit rows make the issue's nonanticipativity requirement directly auditable. The Bellman solver and tree solver must traverse transitions independently. Their input model is common; source-model transition reconstruction is a separate check against common-mode input errors.

## Tradeoffs accepted

- We accept a finite exact-state graph and finite disturbance catalogues in exchange for a complete, auditable tree without unsupported continuum claims.
- We accept caller-owned semantic state IDs in exchange for avoiding unsafe float-based or tolerance-based identity decisions inside the solver.
- We accept two value tolerances for tie classification in exchange for ties that scale sensibly across the strict-gap fixture and physical terminal costs; both values must be reported.
- We accept one optimizer policy witness while Bellman returns all statewise tied actions in exchange for keeping the extensive-form output compact.
- We accept a potentially exponential tree because issue #601 requires a complete finite tree for exact small instances; report node/leaf counts and preserve an explicit resource limit.
- We accept that the scenario-tree optimizer is an optional report implementation, not an installed library backend, in exchange for avoiding a new public MILP dependency and preserving the existing package boundary.
- We accept that source-model reconstruction is separate from solver comparison in exchange for keeping the public API application-independent.

## Alternatives considered

- **Bellman plus a canonical state-DAG MILP with shared decision variables:** this is smaller and avoids duplicated action variables, but it hides the scenario-tree nonanticipativity rows the issue asks to audit. The selected design retains the compact domain model but materializes occurrence variables and equality rows privately.
- **Caller constructs a policy tree and equality map:** rejected because it leaks optimizer structure and asks each report caller to implement the information pattern. The selected `compare` operation owns these decisions.
- **Threshold-search through the existing safety solver:** rejected because it returns feasible actions, not cost-to-go values or cost-optimal ties, and would expose repeated threshold solves to callers. Keep it as a separate reachability result.
- **TwoPoints as the only correctness fixture:** rejected because this finite adaptation's open-loop and feedback threshold values coincide. Retain strict-gap and no-lookahead fixtures for solver semantics and use TwoPoints for geometric relevance.

## Open questions and risks

- Should a later release expose the extensive-form optimizer as a product API, or should it remain a comparison/report implementation until a reusable MIP port exists?
- What default node/leaf limit is practical while preserving an explicit complete-tree result rather than silently pruning?
- For terminal costs with near ties, which declared absolute/relative tolerances should the report use, and how should tolerance-induced ties be described?
- Does the TwoPoints upstream reward/sign mapping match the selected terminal squared-gap objective in the current source-derived adaptation? Preserve the report's explicit monotone-equivalence argument and units.

## Next implementation step

Add the public finite game/result contract and Bellman recursion, then implement the optional independent complete-tree epigraph report against the strict-gap, no-lookahead, all-ties, and unsafe-branch cases before connecting the TwoPoints figure.
