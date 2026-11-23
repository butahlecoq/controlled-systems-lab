#include <csl/optimization/finite_action_box_minimax.hpp>

#include "exact_dyadic_sum.hpp"
#include "finite_action_replay.hpp"
#include "finite_action_plans.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <optional>

namespace csl::optimization {
namespace {
Unsupported unsupported(std::string field, std::string message) {
    return {{{DiagnosticCode::unsupported, std::move(field), std::move(message)}}};
}

using SeparableQuadratic = std::variant<std::monostate, QuadraticCoefficients, OperationStopped>;

std::optional<OperationStopped> scoring_stop(const ExecutionContext &context) {
    if (context.cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled, "Terminal box scoring cancelled."};
    if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
        return OperationStopped{StopReason::deadline_expired,
                                "Terminal box scoring deadline expired."};
    return std::nullopt;
}

SeparableQuadratic separable_quadratic(const Objective &objective,
                                       const ExecutionContext &context) {
    if (objective.policy().assurance != Assurance::numerical)
        return {};
    const auto coefficients = objective.coefficients();
    const auto *quadratic = std::get_if<QuadraticCoefficients>(&coefficients);
    if (!quadratic)
        return {};
    for (std::size_t i = 0; i < objective.dimension(); ++i) {
        if (const auto stop = scoring_stop(context))
            return *stop;
        if (quadratic->Q(i, i) < 0)
            return {};
        for (std::size_t j = 0; j < objective.dimension(); ++j)
            if (i != j && quadratic->Q(i, j) != 0)
                return {};
    }
    return *quadratic;
}

WorstCaseVertexOutcome score_separable_box(const reachability::BoxStage &box,
                                           const Objective &objective,
                                           const QuadraticCoefficients &quadratic,
                                           const ExecutionContext &context) {
    auto corner = box.lower;
    for (std::size_t i = 0; i < corner.size(); ++i) {
        if (const auto stop = scoring_stop(context))
            return *stop;
        const auto lo = box.lower[i], hi = box.upper[i];
        if (!std::isfinite(lo) || !std::isfinite(hi))
            return OperationStopped{StopReason::numerical_failure,
                                    "Nonfinite terminal box endpoint."};
        if (lo == hi)
            continue;
        // Twice the difference in coordinate objectives is (hi-lo) times
        // [Q_ii*(hi+lo) + 2*q_i]. Compare the bracket's sign without rounding.
        detail::ExactDyadicSum difference;
        difference.add_product(quadratic.Q(i, i), lo);
        difference.add_product(quadratic.Q(i, i), hi);
        difference.add(quadratic.linear[i]);
        difference.add(quadratic.linear[i]);
        if (difference.positive())
            corner[i] = hi;
    }
    auto point = numeric::snapshot_vector(std::move(corner));
    if (const auto *error = std::get_if<Diagnostic>(&point))
        return unsupported(error->field, error->explanation);
    auto set = sets::make_singleton({{"finite-box-separable-corner"}, objective.dimension(), {}},
                                    std::get<numeric::VectorView>(std::move(point)));
    if (const auto *error = std::get_if<Diagnostic>(&set))
        return unsupported(error->field, error->explanation);
    return worst_case_vertex(std::get<sets::SetData>(set), objective, 1, context);
}

std::variant<sets::SetData, Unsupported> terminal_box(const reachability::BoxStage &box,
                                                      std::size_t corner_limit) {
    const auto dimension = box.lower.size();
    if (dimension >= std::numeric_limits<std::size_t>::digits)
        return unsupported("finite_box_minimax.dimension",
                           "Terminal dimension exceeds corner enumeration capacity.");
    const auto count = std::size_t{1} << dimension;
    if (count > corner_limit)
        return unsupported("finite_box_minimax.corners",
                           "Terminal box corner count exceeds caller limit.");
    if (dimension != 0 && count > std::numeric_limits<std::size_t>::max() / dimension)
        return unsupported("finite_box_minimax.capacity",
                           "Terminal corner storage size overflows.");
    Matrix corners{count, dimension, Vector(count * dimension)};
    for (std::size_t mask = 0; mask < count; ++mask)
        for (std::size_t coordinate = 0; coordinate < dimension; ++coordinate)
            corners.values[mask * dimension + coordinate] = (mask & (std::size_t{1} << coordinate))
                                                                ? box.upper[coordinate]
                                                                : box.lower[coordinate];
    auto vertices = numeric::snapshot(std::move(corners));
    if (const auto *error = std::get_if<Diagnostic>(&vertices))
        return unsupported(error->field, error->explanation);
    Matrix rays{0, dimension, {}};
    auto ray_view = numeric::snapshot(std::move(rays));
    if (const auto *error = std::get_if<Diagnostic>(&ray_view))
        return unsupported(error->field, error->explanation);
    auto set = sets::make_v({{"finite-box-terminal-corners"}, dimension, {}},
                            {std::get<numeric::MatrixView>(std::move(vertices)),
                             std::get<numeric::MatrixView>(std::move(ray_view))});
    if (const auto *error = std::get_if<Diagnostic>(&set))
        return unsupported(error->field, error->explanation);
    return std::get<sets::SetData>(std::move(set));
}

WorstCaseVertexOutcome score_terminal_box(const reachability::BoxStage &box,
                                          const Objective &objective, std::size_t corner_limit,
                                          const SeparableQuadratic &separable,
                                          const ExecutionContext &context) {
    if (const auto *stopped = std::get_if<OperationStopped>(&separable))
        return *stopped;
    if (const auto *quadratic = std::get_if<QuadraticCoefficients>(&separable))
        return score_separable_box(box, objective, *quadratic, context);
    auto corners = terminal_box(box, corner_limit);
    if (const auto *error = std::get_if<Unsupported>(&corners))
        return *error;
    return worst_case_vertex(std::get<sets::SetData>(corners), objective, corner_limit, context);
}
}

FiniteActionBoxMinimaxOutcome finite_action_box_minimax(const FiniteActionMinimaxRequest &request,
                                                        FiniteActionBoxMinimaxLimits limits,
                                                        const ExecutionContext &context) {
    const auto horizon = request.system.horizon();
    if (request.problem.value.empty() || request.request.value.empty())
        return unsupported("finite_box_minimax.identity",
                           "Problem and request identities must be nonempty.");
    if (request.actions.catalogue.empty() && horizon != 0)
        return unsupported("finite_box_minimax.actions",
                           "A nonempty finite action catalogue is required.");
    if (!detail::valid_candidate_action_indices(request))
        return unsupported(
            "finite_box_minimax.candidate_plans",
            "Candidate action histories must be unique, full-horizon, and index the unchanged action catalogue.");
    const auto plan_count = detail::selected_plan_count(request);
    if (plan_count > limits.max_plans)
        return unsupported("finite_box_minimax.plans", "Action plan count exceeds caller limit.");
    if (request.objective.dimension() != request.system.dimensions().state ||
        request.actions.dimension != request.system.dimensions().control ||
        request.disturbances.size() != horizon || request.admissible_states.size() != horizon + 1)
        return unsupported("finite_box_minimax.dimensions",
                           "Objective, catalogue or stage dimensions differ from the model.");

    std::vector<FiniteActionBoxPlanAttempt> attempts;
    attempts.reserve(plan_count);
    std::optional<SeparableQuadratic> separable;
    std::optional<std::size_t> selected_index;
    double minimum = std::numeric_limits<double>::infinity();
    bool search_stopped = false;
    for (std::size_t plan_index = 0; plan_index < plan_count; ++plan_index) {
        const auto choices = detail::selected_plan_indices(request, plan_index);
        if (context.cancellation.stop_requested()) {
            attempts.emplace_back(BoxPlanStopped{
                choices, {StopReason::cancelled, "Approximate finite minimax cancelled."}});
            search_stopped = true;
            break;
        }
        std::vector<Vector> controls;
        controls.reserve(horizon);
        for (const auto choice : choices)
            controls.push_back(request.actions.catalogue[choice]);
        reachability::FixedPlanRequest plan{
            request.system,
            request.initial,
            std::move(controls),
            request.disturbances,
            request.admissible_states,
            {request.request.value + "/box-plan/" + std::to_string(plan_index)}};
        auto propagated = reachability::finite_plan_box(plan, context);
        if (const auto *error = std::get_if<Unsupported>(&propagated)) {
            attempts.emplace_back(BoxPlanUnscored{choices, *error});
            continue;
        }
        if (const auto *stop = std::get_if<OperationStopped>(&propagated)) {
            attempts.emplace_back(BoxPlanStopped{choices, *stop});
            search_stopped = true;
            break;
        }
        auto trace = std::get<reachability::FinitePlanBoxTrace>(std::move(propagated));
        if (!separable)
            separable.emplace(limits.max_box_corners == 0
                                  ? SeparableQuadratic{}
                                  : separable_quadratic(request.objective, context));
        const auto score = score_terminal_box(trace.stages.back(), request.objective,
                                              limits.max_box_corners, *separable, context);
        if (const auto *error = std::get_if<Unsupported>(&score)) {
            attempts.emplace_back(BoxPlanUnscored{choices, *error});
            continue;
        }
        if (const auto *stop = std::get_if<OperationStopped>(&score)) {
            attempts.emplace_back(BoxPlanStopped{choices, *stop});
            search_stopped = true;
            break;
        }
        if (std::holds_alternative<WorstCaseEmpty>(score)) {
            attempts.emplace_back(
                BoxPlanUnscored{choices, unsupported("finite_box_minimax.empty",
                                                     "An empty terminal box cannot be scored.")});
            continue;
        }
        const auto value = std::get<WorstCaseValue>(score).value;
        const auto attempt_index = attempts.size();
        attempts.emplace_back(BoxPlanScored{choices, value, std::move(trace)});
        if (value < minimum) {
            minimum = value;
            selected_index = attempt_index;
        }
    }

    const auto coverage =
        !search_stopped && attempts.size() == plan_count &&
                std::all_of(attempts.begin(), attempts.end(),
                            [](const auto &attempt) {
                                return std::holds_alternative<BoxPlanScored>(attempt);
                            })
            ? CandidateSearchCoverage::complete
            : CandidateSearchCoverage::incomplete;
    if (!selected_index)
        return FiniteActionBoxMinimaxResult{
            request.problem,        request.request,
            std::move(attempts),    CandidateSearchCoverage::incomplete,
            BoxNoScoredCandidate{}, Assurance::numerical};

    const auto selected_choices = std::get<BoxPlanScored>(attempts[*selected_index]).action_indices;
    std::vector<Vector> controls;
    controls.reserve(horizon);
    for (const auto choice : selected_choices)
        controls.push_back(request.actions.catalogue[choice]);
    reachability::FixedPlanRequest replay_request{request.system,
                                                  request.initial,
                                                  std::move(controls),
                                                  request.disturbances,
                                                  request.admissible_states,
                                                  {request.request.value + "/box-selected-replay"}};
    const auto replay = detail::replay_finite_action_plan(
        replay_request, request.objective, limits.max_points_per_stage, limits.max_replay_histories,
        "finite_box_minimax", context);
    if (const auto *error = std::get_if<Unsupported>(&replay))
        return FiniteActionBoxMinimaxResult{request.problem,
                                            request.request,
                                            std::move(attempts),
                                            coverage,
                                            BoxPlanReplayRefused{*selected_index, *error},
                                            Assurance::numerical};
    if (const auto *stop = std::get_if<OperationStopped>(&replay))
        return FiniteActionBoxMinimaxResult{request.problem,
                                            request.request,
                                            std::move(attempts),
                                            coverage,
                                            BoxPlanReplayStopped{*selected_index, *stop},
                                            Assurance::numerical};
    const auto &replayed = std::get<detail::FiniteActionReplay>(replay);
    return FiniteActionBoxMinimaxResult{
        request.problem,
        request.request,
        std::move(attempts),
        coverage,
        BoxPlanSelected{*selected_index,
                        {replayed.value, replayed.terminal_state, replayed.disturbance_indices,
                         replayed.disturbances, replayed.path, replayed.terminal_catalogue}},
        Assurance::numerical};
}
} // namespace csl::optimization
