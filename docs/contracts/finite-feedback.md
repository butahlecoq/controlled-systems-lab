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

This result is exact for the supplied finite transition table. It does not certify that the table encloses a continuous model, implement the L13/A08 remaining-plan selector, establish a physical observation/model-error bridge, or compute a worst-case cost or global causal optimum. Finite disturbance samples cannot prove a continuum `forall w` claim without a separate enclosure argument. Output-only or noisy observations require an information-state game; querying separate exact states can assign different actions to states the controller cannot distinguish. See the [issue #5 handoff](../research/feedback-contract-followup.md) and [policy proof audit](../research/adaptive-policy-proof-audit.md).
