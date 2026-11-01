# Control-mode evidence for issue #824

## Shared TwoPoints adaptation

The reports below use the pinned `TwoPointsOnParallelLines` source at upstream
commit `f4d76c60f4003f50954174e96eafd8e514bd5441`, re-expressed as the same
three-stage discrete model. The state is
`(x1,x2,x3,x4)=(position_1,velocity_1,position_2,velocity_2)`, the initial
state is `(4.5,0,0,0)`, the control catalogue is `{-2.5,0,2.5}`, the
disturbance catalogue is `{-1,0,1}`, and the terminal objective is squared
position gap. The step is 0.1 seconds; this is a 0.3-second finite adaptation,
not the source's continuous-action ten-second RL task.

The phase-plane figures use `(x1,x2)` for player 1 and `(x3,x4)` for player 2.
The original [TwoPoints environment report](../../reports/algorithm-results/env717-two-points-pilot-v1/)
and its [finite-feedback companion](../../reports/algorithm-results/env717-two-points-feedback-v1/)
show forward reachable sets, backward-winning sets and intersections, and
replayed paths. The [causal minimax report](../../reports/algorithm-results/mpc05-causal-tree-pilot-v2/)
uses those same planes and independently checks its policy replay.

## Results by information pattern

| Mode | Information available when choosing control | Saved result | What the evidence establishes |
| --- | --- | --- | --- |
| Classic nominal open-loop | The opponent signal is fixed to `(1,1,1)`; the full control plan is chosen before execution. | Exact finite-catalog objective `13.92409225`. Box, zonotope, parallelotope and ellipsoid rows retain numerical candidate scores and selected nominal replays in the [nominal bundle](../../reports/algorithm-results/issue824-two-points-nominal-v1/). | The exact row enumerates all 27 control plans. Approximation scores are ranking estimates with no certified objective-bound direction. This is a different problem from minimax because the opponent signal is fixed. |
| Fixed-plan minimax open-loop | Choose the full control plan first; then maximize over all three-stage disturbance histories (`exists u, for all w`). | Exact finite-catalog value `14.58094225`; 27 plans and 27 histories per plan. The [box pilot](../../reports/algorithm-results/issue824-two-points-box-pilot-v4/), [zonotope/parallelotope comparison](../../reports/algorithm-results/issue824-two-points-zonotope-minimax-v2/), and [ellipsoid comparison](../../reports/algorithm-results/issue824-two-points-ellipsoid-minimax-v2/) retain approximation scores separately from full-history replay. | The selected plan is replayed against every listed disturbance history. Approximate terminal scores are numerical outer-enclosure estimates, not certified objective bounds. |
| Fixed-plan re-planning | Observe the current state, enumerate remaining fixed plans, execute the first action of a best remaining plan, then observe again. | Worst cost `14.58094225` in the [causal minimax report](../../reports/algorithm-results/mpc05-causal-tree-pilot-v2/). | This is an executed re-planning selector. Its value does not establish globally optimal causal control; the report's separate strict-gap fixture has re-planning cost `2` and causal value `1`. |
| Full-state causal minimax | Observe the exact current finite-game state, choose an action, then receive the disturbance vertex. The policy may depend on the observed state. | Bellman and full scenario-tree values `14.58094225`; HiGHS reports an optimal bound matching its incumbent, and the extracted policy is independently replayed over all disturbance branches. | This establishes cost-optimality only for the stated finite transition graph, action catalogue and disturbance vertices. The original continuous-control game is outside scope. |
| Finite-state robust feedback threshold | Choose an admissible action from the current scale-2000 integer state before the disturbance vertex is selected. | Minimum threshold `58,323,769 / 4,000,000 = 14.58094225` in the [finite-feedback bundle](../../reports/algorithm-results/env717-two-points-feedback-v1/). The independent checker reconstructs the graph, threshold minimality, winning states, actions and worst-case path. | The guarantee covers that finite graph and listed disturbance vertices. Its deterministic selector takes the first admissible action; actions are not cost-ranked at every state. This is not continuous-state feedback. |

The equal TwoPoints objective values do not demonstrate that the information
patterns are interchangeable. The separate strict-gap fixture in the causal
report establishes a case where causal optimization improves the value. No
performance ranking follows from these objective values.

## Representation support boundary

| State-set track | Forward propagation and relation | Predecessor / feedback support | Fixed-plan control result | Independent inclusion evidence and limits |
| --- | --- | --- | --- | --- |
| Exact finite catalogue / transition graph | Exact for the pinned finite transition graph and declared catalogues | Cost-optimal full-state policy on that graph in the finite causal Bellman/tree profile; no general set-predecessor API | Complete finite-catalog nominal and fixed-plan minimax searches | Exact integer transitions and rational objectives cover the enumerated finite graph; this is not a continuous-game or generic polytope predecessor guarantee |
| Box | Stagewise numerical outer interval box | Unsupported | Fixed-plan nominal and minimax candidate selectors; selected plans are replayed separately | For the selected plan, the checker reconstructs every distinct finite-history state at every stage and checks its coordinates against the recorded box. This evidence is specific to the stored binary64 fixture; box-corner scores are not validated objective bounds |
| Parallelotope | Stagewise numerical outer enclosure in the pinned fixed four-state frame | Unsupported | Fixed-plan nominal and minimax candidate selectors; selected plans are replayed separately | The checker transforms each exact finite-history state into the fixed frame and checks all four frame-coordinate bounds for every scored plan. No orientation optimization is performed |
| Zonotope | Stagewise numerical outer zonotope | Unsupported | Fixed-plan nominal and minimax candidate selectors; selected plans are replayed separately | The v2 checker interprets stored binary64 centers and generators as exact dyadic rationals, checks every facet inequality including lower-dimensional affine spans, and covers every finite-history state for every plan. Candidate scores remain unvalidated estimates |
| Ellipsoid | Stagewise numerical outer axis-aligned ellipsoid | Unsupported | Fixed-plan nominal and minimax candidate selectors; selected plans are replayed separately | The v2 checker uses exact rational membership checks for every finite-history state, stage, and candidate plan. Candidate support scores remain unvalidated estimates |

Here “outer” describes the declared propagation direction for the numerical
recurrence. Inclusion evidence is limited to the pinned finite fixture and
stored binary64 inputs; it is not a validated-arithmetic guarantee for
arbitrary inputs. Failed or budget-stopped selector attempts remain explicit
rows in the zonotope, parallelotope, ellipsoid, and nominal result models and
make search coverage incomplete. The box minimax result now follows the same
contract with a `FiniteActionBoxPlanAttempt` sum type and a separate selection
outcome; request-wide validation failures remain top-level `Unsupported` or
`OperationStopped`. A selected-plan replay is a feasible witness, not proof
that an approximate selector found the globally optimal plan.

The finite-state threshold policy is a separate exact-graph result; it must
not be described as a closed-loop version of the box, parallelotope, zonotope,
or ellipsoid selector. Current approximation scores cannot be converted into a
realizable feedback policy or a predecessor guarantee.

## Source records

- [Classic nominal record](../../reports/algorithm-results/issue824-two-points-nominal-v1/result.json)
- [Classic nominal limiter and end-to-end evidence](../../reports/algorithm-results/issue824-two-points-nominal-v2/README.md)
- [Fixed-plan box record](../../reports/algorithm-results/issue824-two-points-box-pilot-v4/result.json)
- [Fixed-plan zonotope/parallelotope record](../../reports/algorithm-results/issue824-two-points-zonotope-minimax-v2/result.json)
- [Fixed-plan ellipsoid record](../../reports/algorithm-results/issue824-two-points-ellipsoid-minimax-v2/result.json)
- [Finite feedback record](../../reports/algorithm-results/env717-two-points-feedback-v1/result.json)
- [Causal minimax record](../../reports/algorithm-results/mpc05-causal-tree-pilot-v2/result.json)

These are distinct saved result bundles with their own source identities and
independent checks. This matrix joins only the shared finite-game inputs and
the semantics explicitly recorded by each bundle; it introduces no new
measurement or claim that the continuous RL task was reproduced.
