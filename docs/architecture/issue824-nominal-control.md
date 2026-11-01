# Classic nominal control for issue #824

## Problem

Issue #824 milestone 3 adds classic nominal open-loop control beside fixed-plan minimax. The current minimax selectors enumerate fixed action plans, score finite disturbance histories or an outer enclosure, then replay a selected plan under the same disturbance catalogues. That does not define a nominal trajectory. A nominal comparison needs an authored initial state and one known disturbance vector per stage. It must keep the realized trajectory separate from an approximate enclosure score and from the minimax result.

This first profile uses the pinned three-stage `TwoPointsOnParallelLines` adaptation. It fixes the opponent input at `v=+1` at every stage, keeps the minimizing control catalogue `{-2.5, 0, 2.5}`, and minimizes the terminal squared position gap. The nonzero known input makes both player paths visible in the two phase-plane projections. It does not reproduce the source's continuous-action, ten-second RL task.

## Caller usage

The caller supplies every deterministic input and requests the complete profile set in one operation:

```cpp
FiniteActionNominalRequest request{
    .problem = {"env717-two-points-short-horizon-v1"},
    .request = {"issue824-two-points-nominal-v1"},
    .system = two_points_system(),
    .initial_state = {4.5, 0.0, 0.0, 0.0},
    .actions = {1, {{-2.5}, {0.0}, {2.5}}},
    .nominal_disturbances = {{1.0}, {1.0}, {1.0}},
    .admissible_states = universal_state_sets(4, 3),
    .objective = terminal_squared_position_gap(),
};

auto result = finite_action_nominal(request, limits);
```

The exact, box, zonotope, parallelotope, and ellipsoid tracks consume that same request. Each track retains its score attempt for every action plan. A track with a selected plan also returns an independently replayed nominal path.

The comparison report calls `finite_action_minimax` separately with the declared disturbance catalogue. It joins the two outcomes by the shared problem identity. The nominal request does not contain disturbance sets and cannot inherit minimax scenarios.

## Shape

The public request carries the explicit initial point, finite control catalogue, one nominal disturbance vector per transition, safe-state sets, and the existing terminal `Objective`. `FiniteActionNominalLimits` maps to the existing selectors’ plan, point, score-corner, generator and near-optimal budgets.

The outcome contains five canonical `NominalProfileResult` rows: exact polytope, box, zonotope, parallelotope, and ellipsoid. Each row distinguishes a selected candidate, no scored candidate, unsupported operation, or stopped operation. A selected row contains the plan-attempt table, search coverage, selected index, candidate score and score kind, deterministic `NominalTrajectory`, and a type-specific selected trace. Attempts preserve scored, rejected, unscored and stopped outcomes where the underlying selector exposes them. The API returns top-level `Unsupported` or `OperationStopped` for request-level failures.

The exact track selects a deterministic finite-catalog minimum under binary64 evaluation; it is not a validated real-arithmetic certificate. Approximation scores are floating-point outer-enclosure ranking estimates only. They establish no certified lower or upper objective bound. Selected replay values are always recomputed from the authored initial state and nominal disturbance vectors. These three quantities remain separate from the finite minimax result.

The function validates dimensions, finite values, horizon alignment, objective support, and plan limits at the boundary. It converts the authored point and disturbance vectors to singleton V sets only when it calls the existing fixed-plan propagators. The original vectors remain the input to nominal replay.

The exact track propagates each candidate plan through `fixed_plan_disturbance` and evaluates its terminal point. The four approximate tracks call their existing `finite_plan_*` propagators and score each terminal enclosure with the same representation score used by the corresponding minimax selector. These scores remain numerical enclosure estimates. They are not realized costs or validated bounds. Each track selects the lowest computed score, then a separate deterministic replay recomputes the selected path and objective from the authored vectors.

Completed selectors store their scored, rejected or unscored plan rows. The box, zonotope, parallelotope and ellipsoid selectors preserve per-plan stops; the exact selector exposes its existing stop behavior. Coverage remains explicit, and an incomplete profile cannot be described as complete nominal optimization. A replay failure invalidates that track's selected witness.

The report checker independently reconstructs every plan's nominal stage states using rational arithmetic from the authored model values. It checks every exact state against each saved approximation trace at every stage, recomputes each exact nominal objective, and verifies the selected path. The comparison report shows the exact nominal optimum, each approximation's candidate score and selected replay value, and the already-published fixed-plan minimax result as separate quantities.

The nominal disturbance is the source-adaptation opponent action `v=+1` at each stage, so both phase-plane paths are visible. The saved figure uses `(x1,x2)` and `(x3,x4)` and overlays the nominal trajectory on the existing minimax reachable/backward geometry and intersections. The nominal algorithm itself does not compute backward-winning sets; the figure identifies those as minimax evidence.

The native driver also records one excluded warmup and seven batches of ten serial API calls. Each timer surrounds `finite_action_nominal` for all five tracks, including result construction and selected-path replays. Caller status/coverage checks and score consumption happen after each timed interval. Fixture construction, the separate minimax reference, serialization, the independent checker, build, and rendering are outside the timed region. The independent checker runs on the saved untimed result. The timing is a descriptive single-adapter observation. No competing implementation is timed, no speedup or scalability claim is made, and a separate limiter profile was not available (`perf` and `strace` are absent on the host).

## Interface depth and ownership

`finite_action_nominal` owns plan enumeration, profile dispatch, attempt retention, score selection, and nominal replay. The propagators own their representation recurrences. The report driver owns the TwoPoints fixture, result serialization, and comparison with the separate minimax result. The Python checker owns independent numerical evidence. The route stager verifies the immutable bundle and the main-only workflow publishes it.

This single comparison operation keeps the profile list and common input in one place. The type-specific trace is a variant of existing public trace types, so callers can inspect the evidence without converting an ellipsoid or zonotope into an unrelated `SetData` representation. The function does not expose internal scorer callbacks or overload the minimax request with a nominal mode.

## Synthesis decision

Candidate 1 is the base because its per-plan attempt table preserves scored, rejected, unsupported, and stopped outcomes across each profile. Candidate 2 proposed a clearer deterministic request shape and a separate replay checker. Those parts are included here. Candidate 2's result held only the selected candidate per profile, which cannot prove complete search coverage. Its generic `SetData` enclosure field also cannot represent every approximation trace. Candidate 1's extra disturbance catalogues and function-pointer objective are removed; the nominal request uses only authored deterministic inputs and the existing `Objective` type.

The arena rubric scored each candidate from 1 to 5 on six criteria: explicit nominal inputs, identical inputs across profiles, separation of score and replay semantics, retention of per-plan outcomes, API depth with shared machinery, and report evidence.

| Criterion | Candidate 1 | Candidate 2 |
| --- | ---: | ---: |
| Explicit nominal inputs | 5 | 5 |
| Identical inputs across profiles | 5 | 5 |
| Separate score, replay, and minimax semantics | 5 | 5 |
| Per-plan outcome retention | 5 | 2 |
| API depth and shared machinery | 4 | 4 |
| Report evidence | 4 | 5 |
| **Total** | **28** | **26** |

Candidate 1 won because its attempt table preserves every plan outcome. Candidate 2's stronger deterministic request shape and checker contract were grafted into the selected design.

The cross-judge was skipped. The configured runner and judge pools contain only `gpt-6-luna`, the same model family as the parent, and the available collaboration tool offers no different-family model.

## Alternatives considered

- Five public selectors would make each method visible, but force every caller to keep inputs, attempt coverage, tie-breaking, and replay aligned. The comparison operation owns those rules instead.
- A nominal flag on `FiniteActionMinimaxRequest` would mix a deterministic input sequence with adversarial disturbance sets and spread semantic branches through the current result types. Separate request and result types preserve the existing minimax contract.
- Reusing enclosure centers as nominal states would not establish that those centers are realizable. The API replays from the authored state and disturbance values.

## Tradeoffs accepted

- The result exposes a trace variant so callers can verify every representation's actual output. This keeps evidence inspectable and couples the variant to the five public trace types.
- Approximate profiles select from floating-point enclosure ranking estimates. Those scores establish no certified lower or upper objective bound. Their selected nominal replay is a feasible finite-catalog witness, not proof of global optimality.
- The five-profile comparison runs all tracks together. A caller that needs one representation still pays for the full comparison, which prevents a report from silently omitting a required track.
- The initial fixture is deterministic and point-valued. The four approximation profiles test degenerate-set handling here; they do not demonstrate approximation quality on nontrivial uncertainty.

## Open questions and risks

- The existing representation score routines are private to their minimax selectors. Their shared logic may need a small internal extraction so nominal and minimax cannot drift.
- Numerical roundoff can make an approximate trace non-degenerate even for point inputs. The report must preserve each candidate score and compare it with exact replay rather than call the estimate an exact nominal cost.
- The current exact finite-action path rejects a plan if any stage violates a safe set. Approximation tracks cannot prove the same feasibility from an outer set unless their supported relation supplies that evidence. This first TwoPoints profile uses universal safe sets.

## Implementation status

The typed deterministic request, five-track selector, independent TwoPoints replay checker, installed public client, and combined nominal/minimax visualization are implemented in the #824 worktree. The report keeps approximation scores, nominal replay, and minimax value as distinct fields.
