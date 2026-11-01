# Zonotope candidate selection for fixed-plan minimax

## Problem

Issue #824 needs the zonotope propagator to rank fixed open-loop action plans. The existing selector for boxes already shows the right boundary: it keeps enclosure candidate scores separate from the selected plan's finite-history replay. The zonotope propagator handles one plan, and the objective API has no support bound over a zonotope. Candidate scoring therefore needs an explicit finite budget and must not imply a verified upper bound.

## Usage

```cpp
const auto outcome = finite_action_zonotope_minimax(request,
    {27, 27, 27, 64, 1u << 16});
```

The first five limits are maximum action plans, points per replay stage, replay histories, generators per zonotope stage, and terminal factor corners. The optional sixth limit caps candidate attempts and defaults to the largest representable value. If it stops enumeration, the result retains completed rows and appends a typed resource-limit row for the next plan. A result otherwise contains one scored or unscored row per attempted action plan, the selected row when any candidate scored, and a separate selected-plan replay outcome. A complete candidate-score search means that every action plan received a score. It does not mean that the candidate scores are validated bounds or that the selected plan is globally minimax optimal.

## Shape

`FiniteActionZonotopeMinimaxLimits` bounds plan enumeration, factor-corner scoring, exact finite-catalogue propagation, recursive witness search, and zonotope generator growth. `FiniteActionZonotopePlanAttempt` is a sum type with a scored row or an unsupported row. The row preserves the action indices and the reason an attempt did not produce a candidate score.

```cpp
struct FiniteActionZonotopeMinimaxLimits {
    std::size_t max_plans;
    std::size_t max_points_per_stage;
    std::size_t max_replay_histories;
    std::size_t max_generators_per_stage;
    std::size_t max_factor_corners;
    std::size_t max_candidate_attempts{std::numeric_limits<std::size_t>::max()};
};

struct ZonotopeCandidateScore {
    double terminal_factor_corner_maximum;
    std::size_t terminal_generators;
    std::size_t factor_corners_evaluated;
    reachability::FinitePlanZonotopeTrace trace;
};

struct ZonotopePlanScored {
    std::vector<std::size_t> action_indices;
    ZonotopeCandidateScore score;
};

struct ZonotopePlanUnscored {
    std::vector<std::size_t> action_indices;
    Unsupported outcome;
};

struct ZonotopePlanStopped {
    std::vector<std::size_t> action_indices;
    OperationStopped outcome;
};

using FiniteActionZonotopePlanAttempt =
    std::variant<ZonotopePlanScored, ZonotopePlanUnscored, ZonotopePlanStopped>;

enum class CandidateSearchCoverage { complete, incomplete };

struct FiniteActionZonotopeReplay {
    double worst_value;
    Vector worst_terminal_state;
    std::vector<std::size_t> disturbance_indices;
    std::vector<Vector> disturbances;
    std::vector<Vector> path;
    sets::SetData terminal_catalogue;
};

struct ZonotopePlanSelected {
    std::size_t candidate_attempt_index;
    FiniteActionZonotopeReplay replay;
};
struct ZonotopePlanReplayRefused {
    std::size_t candidate_attempt_index;
    Unsupported outcome;
};
struct ZonotopePlanReplayStopped {
    std::size_t candidate_attempt_index;
    OperationStopped outcome;
};
struct ZonotopeCandidateSearchStopped {
    std::size_t candidate_attempt_index;
    OperationStopped outcome;
};
struct ZonotopeNoScoredCandidate {};

using FiniteActionZonotopeSelectionOutcome = std::variant<ZonotopePlanSelected,
    ZonotopePlanReplayRefused, ZonotopePlanReplayStopped,
    ZonotopeCandidateSearchStopped, ZonotopeNoScoredCandidate>;

struct FiniteActionZonotopeMinimaxResult {
    ProblemId problem;
    RequestId request;
    std::vector<FiniteActionZonotopePlanAttempt> plan_attempts;
    CandidateSearchCoverage candidate_search;
    FiniteActionZonotopeSelectionOutcome selection;
    Assurance assurance{Assurance::numerical};
};

using FiniteActionZonotopeMinimaxOutcome =
    std::variant<FiniteActionZonotopeMinimaxResult, Unsupported, OperationStopped>;

FiniteActionZonotopeMinimaxOutcome finite_action_zonotope_minimax(
    const FiniteActionMinimaxRequest& request,
    FiniteActionZonotopeMinimaxLimits limits,
    const ExecutionContext& context = {});
```

`terminal_factor_corner_maximum` evaluates the convex objective at every sign assignment of the stored terminal generator columns. This is the numerical maximum over the represented factor cube for the stored binary64 data. It is a candidate score, not an outward-rounded objective bound. The 4D TwoPoints report checks coordinate bounds for its exact finite-catalogue states; it does not claim full zonotope membership.

The optimizer module owns action-plan enumeration, candidate coverage, score comparison, and selected-plan replay. The reachability module remains responsible for the one-plan zonotope trace. A private replay helper owns the existing recursive worst-history search so the box and zonotope selectors use the same witness logic. Exact finite-catalogue propagation still runs separately to check safe sets and provide the complete terminal V catalogue.

The selector returns a result when candidate attempts finish, even when individual plans are unsupported or selected replay is refused. If cancellation, a deadline, or the candidate-attempt limit stops search, the result retains completed rows, adds a typed stopped row for the interrupted/next plan, marks coverage incomplete, and records the stopped selection outcome. Request-wide validation failures remain `Unsupported`; context stops before any candidate attempt can begin remain top-level `OperationStopped`.

## Synthesis decision

Both design candidates selected one optimizer-level `finite_action_zonotope_minimax` operation and a per-plan outcome table. Candidate B is the base because `ScoredPlan` and `UnscoredPlan` encode whether a score exists, and its search-coverage field prevents a best-of-subset result from looking complete. Candidate A contributed the repository-shaped signature with the existing `FiniteActionMinimaxRequest`, separate limits, and `ExecutionContext`, plus explicit terminal factor and corner counts. The designs converged on an integrated selector. A different-family cross-judge was unavailable during this design pass.

## Tradeoffs accepted

- We accept exhaustive factor-corner scoring in exchange for an objective score over every sign corner of the stored zonotope, with a caller limit on exponential work.
- We accept an incomplete candidate-search result when any plan cannot be scored, even if another plan has a finite score.
- We accept that selected-plan replay may be refused after a candidate is scored. Candidate evidence remains available, while the replay field records its own outcome.
- We accept numerical candidate scores because the current objective evaluator does not return outward-rounded values.

## Alternatives considered

- Add a zonotope scoring callback to `finite_action_minimax`. This would mix exact finite-catalogue ranking with enclosure-based candidate ranking inside one operation.
- Require callers to enumerate plans and coordinate propagation, scoring, coverage, tie handling, and replay. That would expose selector policy and make consistent evidence records harder.
- Materialize zonotope corners as an ordinary V set and pass it to `worst_case_vertex`. The zonotope is not the exact finite-catalogue terminal set, and that conversion would hide the corner budget at the wrong API boundary.

## Open questions and risks

The factor-corner count grows exponentially with the terminal generator count. The explicit limit returns an unscored plan rather than switching to an unbounded computation or a sampled estimate. The report must call the numerical factor-corner maximum a candidate score and identify any incomplete plan coverage.

## Implementation status

The selector, shared finite-history replay helper, analytic fixture, and pinned TwoPoints tests are implemented. The report driver checks all 27 candidates and emits projections in both player phase planes. Focused optimizer, installed-client, report-smoke, and independent exact-check evidence is collected separately. Any descriptive timing in the pilot is reported without a winner or speedup claim.
