#pragma once

#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/reachability/finite_plan_box.hpp>
#include <csl/reachability/finite_plan_ellipsoid.hpp>
#include <csl/reachability/finite_plan_parallelotope.hpp>
#include <csl/reachability/finite_plan_zonotope.hpp>

#include <string>

namespace csl::optimization {

// Running control penalties are evaluated on the original, absolute stage
// grid. The quadratic form is coefficient / normalization_horizon times
// sum_i weights[i] * ((u[i] - reference[i]) / scales[i])^2. Euclidean terms
// retain the source norm: coefficient * ||map * u + offset||_2.
struct QuadraticControlPenalty {
    Vector reference;
    Vector scales;
    Vector weights;
    double coefficient;
    std::size_t normalization_horizon;
};
struct EuclideanControlPenalty {
    Matrix map;
    Vector offset;
    double coefficient;
};
using ControlPenalty = std::variant<QuadraticControlPenalty, EuclideanControlPenalty>;
struct AbsoluteStageControlCost {
    std::size_t stage;
    std::vector<ControlPenalty> terms;
};
struct RunningControlCost {
    std::string objective_id;
    std::size_t original_horizon;
    std::vector<AbsoluteStageControlCost> stages;
};

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
    // Empty preserves terminal-only behavior. A shrinking-horizon request
    // keeps the complete source schedule and advances absolute_stage_offset.
    RunningControlCost running_cost{};
    std::size_t absolute_stage_offset{};
    // Optional deterministic subset of full-horizon action-index histories.
    // Every row spans the entire request horizon and indexes the untouched
    // source action catalogue. A proper subset yields incomplete coverage.
    std::vector<std::vector<std::size_t>> candidate_action_indices;
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
    numerical_outer_enclosure_estimate,
    // A numerical terminal enclosure estimate plus the exactly evaluated
    // source running-control cost; the sum remains a numerical rank estimate.
    numerical_outer_estimate_plus_exact_running_cost
};
enum class NominalSearchCoverage { complete, incomplete, stopped };

struct NominalPlanScored {
    std::vector<std::size_t> action_indices;
    double candidate_score;
    NominalScoreKind score_kind;
    double terminal_score{};
    double exact_running_cost{};
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
    double running_objective{};
    double total_objective{};
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
    std::string objective_id;
    std::size_t original_horizon{};
    std::size_t absolute_stage_offset{};
};
using FiniteActionNominalOutcome = std::variant<FiniteActionNominalResult,
    Unsupported, OperationStopped>;

// Compares exact and approximate fixed-plan selection for one deterministic
// nominal input. Approximate scores are enclosure estimates; each selected
// plan is separately replayed from the authored state and disturbance values.
FiniteActionNominalOutcome finite_action_nominal(
    const FiniteActionNominalRequest&, FiniteActionNominalLimits,
    const ExecutionContext& = {});

// Runs exactly one selected representation route. The all-five comparison
// overload above remains available to existing callers; a selected query does
// not execute inactive representation modules.
FiniteActionNominalOutcome finite_action_nominal_profile(
    const FiniteActionNominalRequest&, FiniteActionNominalLimits,
    NominalRepresentation, const ExecutionContext& = {});

} // namespace csl::optimization
