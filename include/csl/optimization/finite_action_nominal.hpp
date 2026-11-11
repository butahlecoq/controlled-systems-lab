#pragma once

#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/reachability/finite_plan_box.hpp>
#include <csl/reachability/finite_plan_ellipsoid.hpp>
#include <csl/reachability/finite_plan_parallelotope.hpp>
#include <csl/reachability/finite_plan_zonotope.hpp>

namespace csl::optimization {

struct FiniteActionNominalRequest {
    ProblemId problem;
    RequestId request;
    model::LinearSystem system;
    Vector initial_state;
    FiniteDomain actions;
    // One authored deterministic external input for each state transition.
    std::vector<Vector> nominal_disturbances;
    std::vector<sets::SetData> admissible_states;
    Objective objective;
};

struct FiniteActionNominalLimits {
    std::size_t max_plans;
    std::size_t max_points_per_stage;
    std::size_t max_score_evaluations;
    std::size_t max_generators_per_stage;
    double near_optimal_tolerance;
};

enum class NominalRepresentation { exact_polytope, box, zonotope, parallelotope, ellipsoid };
enum class NominalScoreKind {
    exact_deterministic_objective,
    // Floating-point enclosure-derived ranking score; no certified objective
    // bound is established in either direction.
    numerical_outer_enclosure_estimate
};
enum class NominalSearchCoverage { complete, incomplete, stopped };

struct NominalPlanScored {
    std::vector<std::size_t> action_indices;
    double candidate_score;
    NominalScoreKind score_kind;
};
struct NominalPlanRejected {
    std::vector<std::size_t> action_indices;
    std::size_t stage;
    Vector violating_state;
};
struct NominalPlanUnscored {
    std::vector<std::size_t> action_indices;
    Unsupported reason;
};
struct NominalPlanStopped {
    std::vector<std::size_t> action_indices;
    OperationStopped reason;
};
using NominalPlanAttempt = std::variant<NominalPlanScored, NominalPlanRejected,
    NominalPlanUnscored, NominalPlanStopped>;

struct NominalTrajectory {
    std::vector<Vector> states; // Includes the authored state at stage zero.
    std::vector<Vector> controls;
    std::vector<Vector> disturbances;
    double terminal_objective;
};
using NominalPlanTrace = std::variant<reachability::FixedPlanReachable,
    reachability::FinitePlanBoxTrace, reachability::FinitePlanZonotopeTrace,
    reachability::FinitePlanParallelotopeTrace, reachability::FinitePlanEllipsoidTrace>;

struct NominalTrackSelected {
    std::vector<NominalPlanAttempt> attempts;
    NominalSearchCoverage coverage;
    std::size_t selected_attempt;
    double candidate_score;
    NominalScoreKind score_kind;
    NominalTrajectory replay;
    NominalPlanTrace selected_trace;
};
struct NominalTrackNoScoredCandidate {
    std::vector<NominalPlanAttempt> attempts;
    NominalSearchCoverage coverage;
};
struct NominalTrackUnsupported {
    std::vector<NominalPlanAttempt> attempts;
    NominalSearchCoverage coverage;
    Unsupported reason;
};
struct NominalTrackStopped {
    std::vector<NominalPlanAttempt> attempts;
    NominalSearchCoverage coverage;
    OperationStopped reason;
};
using NominalTrackOutcome = std::variant<NominalTrackSelected,
    NominalTrackNoScoredCandidate, NominalTrackUnsupported, NominalTrackStopped>;

struct NominalProfileResult {
    NominalRepresentation representation;
    NominalTrackOutcome outcome;
};
struct FiniteActionNominalResult {
    ProblemId problem;
    RequestId request;
    std::vector<NominalProfileResult> tracks; // Exact, box, zonotope, parallelotope, ellipsoid.
    Assurance assurance{Assurance::numerical};
};
using FiniteActionNominalOutcome = std::variant<FiniteActionNominalResult,
    Unsupported, OperationStopped>;

// Compares exact and approximate fixed-plan selection for one deterministic
// nominal input. Approximate scores are enclosure estimates; each selected
// plan is separately replayed from the authored state and disturbance values.
FiniteActionNominalOutcome finite_action_nominal(
    const FiniteActionNominalRequest&, FiniteActionNominalLimits,
    const ExecutionContext& = {});

} // namespace csl::optimization
