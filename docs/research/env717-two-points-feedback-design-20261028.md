# TwoPoints finite feedback design

## Problem

The TwoPoints report runs CSL's fixed-plan minimax solver and CSL's `reachability::finite_feedback` solver on a separate finite vertex-game graph derived from the same three-stage source adaptation. The graph models the exact finite action and disturbance catalogues in the report. It does not claim a guarantee for the continuous disturbance hull or the original 10-second RL task.

## Usage

The C++ report driver builds a finite transition table, searches terminal-gap thresholds with `finite_feedback::solve`, and saves the policy and evidence. The Python checker rebuilds the physical graph from the pinned model and checks every transition and policy cell. The report plots both results in the player phase planes `(x1,x2)` and `(x3,x4)`.

```cpp
const auto graph = make_feedback_graph(model);
const auto result = solve_feedback_threshold(graph, initial_state);
```

```python
expected = reconstruct_feedback_graph(model_record)
verify_graph_and_policy(expected, saved_feedback_result)
```

## Shape

Keep the integration private to the TwoPoints report. Use a `FeedbackGraph` with sorted, unique integer-coordinate states for each time layer and one `finite_feedback::Game`. Let `N` be the largest layer size. Pad shorter layers to `N` with unsafe dummy states and complete transition rows. No real transition may target a dummy state.

Store coordinates as integer multiples of `1/2000`. For the source-derived map and current catalogues, the transitions are integral on this lattice. The builder will check every transition and fail if a division is not exact or an integer operation overflows. The scaled state is `(P1,V1,P2,V2)`, where each coordinate is the physical coordinate multiplied by 2000. Action codes `a` and disturbance codes `d` each range over `{-1,0,1}` and map to physical values `2.5a` and `d`. The exact integer transition is:

```text
P1' = P1 + V1 / 100 + 450a
V1' = 5000a
P2' = P2 + V2 / 10 + 9d
V2' = V2 + 200d
```

The initial state is `(9000,0,0,0)`. The physical terminal squared gap is `(P1-P2)^2 / 4,000,000`. Keep the numerator and denominator in the saved result. Also compare this integer map with the pinned implementation's ten binary64 Euler substeps and record the declared tolerance and observed maximum discrepancy.

For each distinct terminal squared-gap numerator, set the terminal target to states at or below that candidate. Call `finite_feedback::solve` and test whether the initial state wins. The first winning candidate is the minimum robust threshold for this finite graph. Keep the complete returned `Policy`, including all admissible actions. Use the first admissible action as the deterministic selector for the displayed feedback trajectory. Label it as a deterministic minimax-feasible selector, not an action chosen by the solver to optimize cost.

The Python checker independently constructs the integer state layers and transitions. It checks all real and dummy table cells, the selected threshold, every winning bit, every admissible action, and the causal witness. It also checks the source Euler-map discrepancy. Keep graph verification in Python. Do not declare a C++ verification API for a Python implementation.

Extend the existing two-panel figure. Retain stage-wise forward sets and backward winning intersections. Add the fixed-plan worst-case path and the feedback selector's worst-case path with distinct line styles and labels. The backward set belongs to the finite state graph and its threshold. It is not a complete continuous-state predecessor set.

## Synthesis decision

The design arena selected Candidate B's fixed scale and stage-local state catalogues. The cross-judge scored Candidate B 10/10 and Candidate A 9/10. Candidate B makes the solver's rectangular-state requirement explicit and hides state IDs and padding behind one report-local graph builder. This document corrects Candidate B's verifier boundary to place verification in the existing Python checker.

The implementation grafts four details from Candidate A: exact threshold fractions, integer-bound checks and overflow failure, the existing singleton initial state, and the Euler-map comparison. It rejects transitions to padded slots and verifies every padded row independently. The source's second-point velocity accumulates disturbance across stages, so the integer map retains `V2` in the update.

## Tradeoffs accepted

- The report uses an exact finite lattice graph. It does not represent every point in the continuous disturbance hull.
- The report runs the feedback solver once per distinct terminal threshold candidate. This keeps the solver responsible for reachability decisions and avoids a separate production recurrence.
- The first admissible action gives a reproducible trajectory. The solver returns the full feasible action set and does not rank those actions by cost.
- The checker duplicates the physical transition equations in Python. That gives an independent check of the C++ graph builder and requires a maintained cross-language source map.

## Alternatives considered

- A time-varying integer scale can keep all transitions integral, but it changes denominators at each stage and makes state IDs harder to inspect. The fixed scale is simpler for this model, provided every division and range check is explicit.
- An unmerged history tree avoids coordinate identity but duplicates the same physical state at a layer and expands the feedback table. The physical state is Markov for this model, so a sorted stage-local catalogue is sufficient.
- Rounded binary64 keys can merge distinct states. They are not used for state identity.
- A separate cost-optimal recurrence in the C++ producer would bypass the CSL reachability solver. The producer instead searches thresholds with `finite_feedback::solve`; Python uses its own recurrence only to verify the saved policy.

## Open questions and risks

The fixed scale works only while all selected model coefficients and catalogues keep transitions integral. The graph builder and independent checker must prove this for every generated state. If a later scenario breaks the divisibility condition, it needs a new exact representation rather than a rounding fallback.

The finite feedback result applies to listed disturbance vertices. It does not certify the convex hull between vertices because intermediate states can affect later feedback decisions. Keep that limitation visible in the report.

## Implementation status

Implemented in `benchmarks/reporting/env717/two_points.cpp` and `scripts/reports/env717/check_two_points.py`. The checker reconstructs all 345 terminal candidates, verifies the graph and complete policy, checks the threshold `58323769/4000000`, and compares each transition against the source's ten binary64 Euler substeps. The observed maximum absolute discrepancy is `3.552713678800501e-15` with tolerance `1e-10`. The saved report bundle is `reports/algorithm-results/env717-two-points-feedback-v1/`; the publication workflow retains both the original fixed-plan report route and this feedback route.
