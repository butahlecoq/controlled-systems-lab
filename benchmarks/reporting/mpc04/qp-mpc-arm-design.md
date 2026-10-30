# MPC-04 linear QP arm design

## Problem

The report already compares nominal and finite-minimax policies through an executed full-state replanning loop. Its remaining standard linear QP arm must preserve the source task's terminal-only squared max-coordinate objective and finite-disturbance interpretation while using continuous controls. That action domain differs from the existing binary catalogue, so the report will state the difference directly. The controller and adapter stay private to the report executable.

## Usage

The report selects one planner for each episode set and reuses the existing loop:

```cpp
auto nominal = episode("linear_qp_nominal_linf", qp, histories);
auto robust = episode("linear_qp_finite_history_linf", qp, histories);
```

At every observed state the QP controller solves the remaining-horizon problem, records the plan and solver result, and returns only its first control. The loop applies the control, then advances the source model with that episode's disturbance. The next decision sees the new full state.

## Shape

Keep a private `QpMpcController` in `max_coordinate_replanning.cpp`, backed by the existing `ConvexPort` and HiGHS adapter. A `QpPlanRequest` contains the observed `(time,y,z)` state, remaining horizon, and either nominal-zero or finite-binary disturbance mode. A successful `QpPlan` contains the continuous control sequence, primary QP optimum, independently recomputed worst terminal cost, primary and tie solve durations, and provider identity. Stopped and failed solves remain distinct outcomes and are converted to the episode's already-recorded zero-action fallback only at the episode boundary.

For a fixed control sequence and disturbance history, the terminal `(y,z)` is affine in the controls. Use decision vector `(u_0,\ldots,u_{H-1},r)`, bounds `u_i in [-1,1]`, `r >= 0`, and constraints `r >= +/- y_H`, `r >= +/- z_H`. In nominal mode there is one all-zero disturbance history. In robust mode the same control sequence is constrained against every complete history in `{-1,+1}^H`. Minimize `r^2` with a quadratic objective containing only the epigraph variable. This matches the source `max(|y_H|,|z_H|)^2` terminal objective.

Because several control sequences can share the primary optimum, solve a second strictly convex QP minimizing `sum(u_i^2)` subject to the same terminal rows and `r <= r_primary + tau`. Report the selected sequence's recomputed worst terminal objective, and fail the plan if it exceeds the primary optimum beyond the declared numerical tolerance. This secondary solve chooses a reproducible plan; it does not replace the reported terminal objective. Each plan gets a fresh workspace; warm starts are disabled. The existing episode owns reset, observation-before-action, timeout fallback, disturbance application, and episode accounting.

The primary QP builds one shared control vector across all planned disturbance histories. It does not synthesize an in-horizon causal policy. The complete executed episodes are still enumerated and replayed over the finite disturbance histories, and no continuous-game, globally causal-optimal, recursive-feasibility, or stability claim follows.

The caller surface is private and small: `QpMpcController::plan(QpPlanRequest) -> QpPlanResult`. It hides scenario enumeration, sparse constraint construction, provider preparation, both solves, tie selection, status checks, and terminal-cost recomputation. `episode` remains the one owner of controller timing and fallback semantics. This follows the existing report boundary and avoids a public library API or new dependency.

## Synthesis decision

Candidate A is the base. It received scores 5, 5, 4, 5, 5 on objective fidelity, policy semantics, tie/solver correctness, integration, and evidence disclosure. The independent arena judge recommended the same design. Candidate B's finite scenario-tree QP received 5, 2, 4, 3, 4: its separate future controls at each disturbance-history node introduce in-horizon causal feedback and a different robust controller class. That is outside the standard QP arm for #600. The selected design keeps a common open-loop plan inside each MPC solve and executes only its first action before replanning from the next observation.

The useful verification point from Candidate B is retained: keep disturbance histories explicit and independently replay each complete episode. Candidate B's tree variables and history-merging rules are rejected for this comparison.

## Tradeoffs accepted

- Two QP solves per decision are accepted to retain the terminal-only primary objective while selecting a unique minimum-norm control sequence.
- Continuous QP controls are accepted even though the finite minimax arm uses `{-1,+1}`; report both domains as separate arms.
- Finite-history enumeration is exact for the declared binary disturbance set but grows exponentially with the remaining horizon.
- Fresh workspaces and no warm start simplify reset behavior and make setup visible in the per-decision timing.

## Alternatives considered

- A scenario-tree QP with a distinct decision variable at every future disturbance history would optimize causal feedback inside the MPC horizon. It changes the optimizer's policy class and enlarges the problem, so it is not substituted for standard open-loop QP MPC here.
- Adding a small control penalty to the primary QP would select a unique plan in one solve, but it changes the source terminal-only objective. It is rejected for the matched arm.
- A Euclidean terminal tracking cost is a conventional QP objective but differs from the source objective. It may be added later as a separately named variant, not used to claim a matched comparison.

## Open questions and risks

- HiGHS provides numerical binary64 evidence rather than exact certificates; each plan must retain statuses, residual checks, and the recomputed terminal objective.
- The tie tolerance must be included in report metadata and in the independent replay's accepted numerical bound.
- The finite robust QP shares its planned controls across all future histories; the report must keep that explicit so it is not read as a causal-game optimum.

## Next implementation step

Construct a one-stage nominal epigraph program and verify its chosen action and objective against a hand-calculated terminal-state minimization before adding robust histories.
