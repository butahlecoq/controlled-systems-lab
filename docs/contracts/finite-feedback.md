# Exact finite feedback predecessor

`CSL::finite_feedback` evaluates a finite, explicitly enumerated surrogate game. `Game` names a nonempty finite state catalogue, one stage record per decision, terminal safety, and a terminal target. A stage names its current safe states, an ordered action catalogue (which may be empty), a nonempty disturbance catalogue, and every exact `next_state[state][action][disturbance]` index. Its fixed disturbance catalogue is available to the adversary **after** the controller chooses an action; the current state is known exactly before the choice. At the next stage the new state is known. Stage disturbances are independent across time. There is no numerical set membership or rounding in this table operation.

`solve` rejects malformed dimensions, an empty disturbance catalogue, and unknown successors as `invalid_input`. It returns `Policy::winning[t][x]` and all `Policy::admissible_actions[t][x]` in authored action order. Terminal winning states satisfy both terminal masks. Backward induction adds an action only when **every** disturbance successor is winning at the next stage and the current state is safe:

```text
winning[T][x] = terminal_safe[x] and terminal_target[x]
actions[t][x] = {u in catalogue order : safe[t][x]
                 and all w, winning[t+1][next_state[t][x][u][w]]}
winning[t][x] = actions[t][x] is nonempty
```

The first returned action is one deterministic causal selector on a winning state. On a finite discrete state space that selector is measurable. Retaining all feasible actions does not make each action cost optimal. An empty action catalogue or a state with no safe action yields an empty action list and `winning=false`. In particular, one disturbance reaching the target cannot rescue another disturbance reaching an unsafe state: intersection with the target is insufficient.

## Registered public route

`CSL::finite_feedback_port` adds the typed `registry::FiniteFeedbackPort` without changing the shared registry contract. The registered reference method is `csl.reachability.finite-feedback-table@1.0.0`. A `Request` binds a `ProblemId`, `RequestId`, and complete game; `finite_table_requirements()` requests representation `csl.feedback.finite-winning-table`. Capability admission checks both identities and the entire finite transition table before creating a workspace. Selection rejects an unknown method/version or incompatible representation. `run_registered` returns a policy, rejection, or stop with the original problem/request IDs and selected method provenance. A pre-cancelled or expired request stops before workspace creation.

The port is replaceable: another registration can supply a workspace under its own ID/version. `FiniteFeedbackPort::run` compares a proposed policy's complete winning and action tables to the exact reference recurrence before publishing it. A false provider table becomes `evidence_mismatch`; a provider's diagnostic or stop cannot be relabelled as a winning policy. The direct `solve` function remains a reference/query helper. The generic registry currently accepts only `Scalar::binary64` with `Assurance::numerical`; these are admission metadata from registry revision 1.1, not an assertion that the finite table uses floating arithmetic or that a continuous-model enclosure was validated.

Validation, recurrence, and registered reference comparison each visit the explicit transition entries; their time is linear in the table size plus returned action entries. The input stores every state/action/disturbance successor, and the result stores winning masks and every feasible action. This is a complete feasible-action table for the supplied finite game, not an optimal solution family; no geometric set conversion or approximation is performed. Large or implicit continuous state spaces are outside this representation. The [fixed-source public-port report plan](../../reports/algorithm-results/tooling/finite_feedback/README.md) defines the measurement and publication gate; CTest timings are functional test times only.

This result is exact for the supplied finite transition table. It does not certify that the table encloses a continuous model, implement the L13/A08 remaining-plan selector, establish a physical observation/model-error bridge, or compute a worst-case cost or global causal optimum. Finite disturbance samples cannot prove a continuum `forall w` claim without a separate enclosure argument. Output-only or noisy observations require an information-state game; querying separate exact states can assign different actions to states the controller cannot distinguish. See the [issue #5 handoff](../research/feedback-contract-followup.md) and [policy proof audit](../research/adaptive-policy-proof-audit.md).
