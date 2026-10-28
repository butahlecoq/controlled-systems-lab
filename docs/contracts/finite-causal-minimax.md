# Finite causal minimax

`csl::optimization::finite_causal_minimax::solve` computes an exact finite-state, terminal-cost causal minimax result. At each stage it chooses a control from the currently observed exact state, then accounts for every disturbance in that stage's finite catalogue. It returns a Bellman value and every action tied within the caller's absolute and relative tolerances for every state layer.

This contract covers finite, stage-rectangular disturbance catalogues and a Markov transition table. It does not certify continuous disturbances, partial or noisy observations, history-dependent resources/costs, or an RL environment's continuous-control result. State IDs are stage-local semantic identities. Model builders must reuse an ID for all histories that produce the same exact observed state at the same stage.

## Game and quantifiers

For stage `t`, state `s`, control `u`, disturbance `w`, and transition `f_t`, the value is

```text
V_T(s) = terminal_cost(s), if terminal-safe; otherwise infeasible
V_t(s) = min_u max_w V_(t+1)(f_t(s,u,w))
```

The control is selected before the current disturbance. If any required successor is unsafe or infeasible, that control is infeasible. A state is infeasible if its safety predicate is false or every control is infeasible. The returned `optimal_actions` includes each action whose worst successor value differs from the exact minimum by at most

```text
absolute_tolerance + relative_tolerance * max(abs(candidate), abs(minimum))
```

The reported value remains the exact minimum among the finite action catalogue; tolerance only classifies tied actions.

## Input requirements

- At least one decision stage, state, action, and disturbance at each stage.
- A nonempty terminal state layer.
- Safety masks and complete transition rows matching the state, action, and disturbance counts.
- Every successor ID is valid for the next stage's state layer (or the terminal layer after the last decision).
- Every terminal cost is finite. Safety is represented by the safety masks, not sentinel costs.
- The initial state ID is valid in the first layer.
- Both tie tolerances are finite and nonnegative.

Malformed dimensions, values, or IDs return an `invalid_input` diagnostic. Partial/noisy observation, history-dependent costs/resources, and non-Markov models are outside the contract. The solver does not infer whether a source model meets its exact-state assumptions; that is an input-modeling obligation.

## Result

The result contains all stage/state values including the terminal layer and the initial state ID. Its `initial()` accessor refers to that state row without duplicating the value or action list. Each feasible state row contains the minimizing value and every tied action; infeasible rows have `feasible=false`, an unused numeric value, and no actions. Values for states that are unreachable from the selected initial state are still computed because the input is a complete layer-wise model.

The algorithm is a finite Bellman reference. A scenario-tree optimizer used in comparison reports is a separate implementation and must independently encode the same `min_u max_w` order, use explicit nonanticipativity equalities for repeated information states, and replay its selected policy over all disturbance branches. Agreement on a shared transition table does not verify that table against the originating physical model.

## Evidence limits

The L13 two-stage exact-rational fixture in `docs/research/finite-policy-class-reference.md` has finite-catalogue fixed-plan and executed-replanning worst squared cost `2`, and causal value `1`. The finite disturbance catalogue is `(-1,0,1)` at the first stage and `(0)` at the second. This product solver does not promote those finite-catalogue numbers to a continuous disturbance result. The analytic continuous-interval result is documented separately in `docs/research/adaptive-policy-proof-audit.md`.

The TwoPointsOnParallelLines application report uses a three-stage finite action/disturbance adaptation of an upstream continuous-control task. Its projections are player position–velocity planes `(x1,x2)` and `(x3,x4)`. Its existing finite-feedback report is safety-threshold geometry, not this cost-optimal causal contract.
