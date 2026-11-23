#include <csl/optimization/finite_action_zonotope_minimax.hpp>

#include "exact_dyadic_sum.hpp"
#include "finite_action_plans.hpp"
#include "finite_action_replay.hpp"
#include "zonotope_corner_certificate.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <optional>
#include <span>
#include <string>

namespace csl::optimization {
namespace {
Unsupported unsupported(std::string field, std::string message) {
    return {{{DiagnosticCode::unsupported, std::move(field), std::move(message)}}};
}

std::optional<OperationStopped> scoring_stop(const ExecutionContext &context) {
    if (context.cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled, "Zonotope candidate scoring cancelled."};
    if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
        return OperationStopped{StopReason::deadline_expired,
                                "Zonotope candidate scoring deadline expired."};
    return std::nullopt;
}

int sign(const detail::ExactTripleSum &value) {
    return value.negative() ? -1 : (value.positive() ? 1 : 0);
}

} // namespace

detail::ZonotopeCornerCertificate
detail::certify_zonotope_corner(const reachability::FinitePlanZonotopeTrace::Stage &terminal,
                                const Objective &objective, const ExecutionContext &context) {
    // Bound dense coefficient storage and products even when the caller
    // permits more generators in the propagated set.
    constexpr std::size_t max_dimension = 64;
    constexpr std::size_t max_factors = 128;
    const auto n = terminal.center.size();
    const auto m = terminal.generators.cols;
    if (n > max_dimension || m > max_factors || n != objective.dimension() ||
        terminal.generators.rows != n || terminal.generators.values.size() != n * m ||
        objective.policy().assurance != Assurance::numerical)
        return {};
    if (const auto stop = scoring_stop(context))
        return *stop;
    const auto coefficients = objective.coefficients();
    const auto *quadratic = std::get_if<QuadraticCoefficients>(&coefficients);
    if (!quadratic)
        return {};
    for (std::size_t k = 0; k < n; ++k) {
        if (const auto stop = scoring_stop(context))
            return *stop;
        if (quadratic->Q(k, k) < 0)
            return {};
        for (std::size_t j = 0; j < n; ++j)
            if (k != j && quadratic->Q(k, j) != 0)
                return {};
    }

    std::vector<ExactTripleSum> gradient(m), radius(m), pair(m * m);
    const auto interaction = [&](std::size_t i, std::size_t j) -> ExactTripleSum & {
        return pair[std::min(i, j) * m + std::max(i, j)];
    };
    const auto &G = terminal.generators.values;
    for (std::size_t k = 0; k < n; ++k) {
        if (const auto stop = scoring_stop(context))
            return *stop;
        const auto q = quadratic->Q(k, k);
        const auto c = terminal.center[k];
        const auto generators = std::span<const double>(G).subspan(k * m, m);
        if (!std::isfinite(c) ||
            !std::ranges::all_of(generators, [](double value) { return std::isfinite(value); }))
            return OperationStopped{StopReason::numerical_failure,
                                    "Nonfinite zonotope factor model."};
        for (std::size_t i = 0; i < m; ++i) {
            const auto gi = generators[i];
            if (gi == 0)
                continue;
            gradient[i].add_product(quadratic->linear[k], gi);
            gradient[i].add_triple(q, c, gi);
            for (std::size_t j = i + 1; j < m; ++j)
                interaction(i, j).add_triple(q, gi, generators[j]);
        }
    }
    std::vector<int> coupling_signs(m * m);
    for (std::size_t i = 0; i < m; ++i) {
        if (const auto stop = scoring_stop(context))
            return *stop;
        for (std::size_t j = i + 1; j < m; ++j) {
            const auto &value = interaction(i, j);
            const auto polarity = sign(value);
            if (!polarity)
                continue;
            coupling_signs[i * m + j] = coupling_signs[j * m + i] = polarity;
            radius[i].add_sum(value, polarity < 0);
            radius[j].add_sum(value, polarity < 0);
        }
    }

    std::vector<int> assignment(m);
    bool changed;
    do {
        changed = false;
        for (std::size_t i = 0; i < m; ++i) {
            if (const auto stop = scoring_stop(context))
                return *stop;
            if (assignment[i])
                continue;
            const bool negative = gradient[i].negative();
            // The sign-flip coefficient lies in gradient[i] +/- radius[i].
            ExactTripleSum margin;
            margin.add_sum(gradient[i], negative);
            margin.add_sum(radius[i], true);
            if (margin.negative())
                continue;
            assignment[i] = negative ? -1 : 1;
            changed = true;
            for (std::size_t j = 0; j < m; ++j) {
                const auto polarity = coupling_signs[i * m + j];
                if (assignment[j] || !polarity)
                    continue;
                const auto &weight = interaction(i, j);
                radius[j].add_sum(weight, polarity > 0);
                gradient[j].add_sum(weight, negative);
            }
        }
    } while (changed);

    // A residual component attains the sum of absolute terms if each linear
    // and pair term can have the sign it prefers simultaneously.
    std::vector<int> relative(m);
    for (std::size_t root = 0; root < m; ++root) {
        if (assignment[root])
            continue;
        std::vector<std::size_t> component{root};
        relative[root] = 1;
        int root_sign = 0;
        for (std::size_t index = 0; index < component.size(); ++index) {
            if (const auto stop = scoring_stop(context))
                return *stop;
            const auto i = component[index];
            if (const auto unary = sign(gradient[i])) {
                const int required = unary * relative[i];
                if (root_sign && root_sign != required)
                    return {};
                root_sign = required;
            }
            for (std::size_t j = 0; j < m; ++j) {
                const auto polarity = coupling_signs[i * m + j];
                if (assignment[j] || !polarity)
                    continue;
                const int required = polarity * relative[i];
                if (!relative[j]) {
                    relative[j] = required;
                    component.push_back(j);
                } else if (relative[j] != required) {
                    return {};
                }
            }
        }
        for (const auto i : component)
            assignment[i] = (root_sign ? root_sign : 1) * relative[i];
    }
    return assignment;
}

namespace {

struct CornerScore {
    double maximum;
    std::size_t evaluated;
};

using CornerScoreOutcome = std::variant<CornerScore, Unsupported, OperationStopped>;

CornerScoreOutcome score_corners(const reachability::FinitePlanZonotopeTrace::Stage &terminal,
                                 const Objective &objective, std::size_t corner_limit,
                                 const ExecutionContext &context) {
    const auto dimension = terminal.center.size();
    const auto generators = terminal.generators.cols;
    if (terminal.generators.rows != dimension || terminal.factors.size() != generators)
        return unsupported("finite_zonotope_minimax.terminal",
                           "Terminal zonotope generator data are inconsistent.");
    auto evaluate_corner =
        [&](const auto &factor_sign) -> std::variant<double, Unsupported, OperationStopped> {
        Vector point = terminal.center;
        for (std::size_t column = 0; column < generators; ++column) {
            const double sign = factor_sign(column);
            for (std::size_t row = 0; row < dimension; ++row)
                point[row] += sign * terminal.generators.values[row * generators + column];
        }
        const auto value = evaluate(objective, point);
        if (const auto *error = std::get_if<Diagnostic>(&value))
            return unsupported(error->field, error->explanation);
        if (const auto *stop = std::get_if<OperationStopped>(&value))
            return *stop;
        return std::get<double>(value);
    };
    const auto capacity = std::numeric_limits<std::size_t>::digits;
    const auto count = generators < capacity ? std::size_t{1} << generators : 0;
    if (count == 0 || count > corner_limit) {
        if (corner_limit > 0) {
            auto certificate = detail::certify_zonotope_corner(terminal, objective, context);
            if (const auto *stop = std::get_if<OperationStopped>(&certificate))
                return *stop;
            if (const auto *signs = std::get_if<std::vector<int>>(&certificate)) {
                if (const auto stop = scoring_stop(context))
                    return *stop;
                const auto value =
                    evaluate_corner([&](std::size_t column) { return (*signs)[column]; });
                if (const auto *error = std::get_if<Unsupported>(&value))
                    return *error;
                if (const auto *stop = std::get_if<OperationStopped>(&value))
                    return *stop;
                return CornerScore{std::get<double>(value), 1};
            }
        }
        return unsupported("finite_zonotope_minimax.corners",
                           count == 0
                               ? "Terminal generator count exceeds corner enumeration capacity."
                               : "Terminal factor-corner count exceeds caller limit.");
    }
    double maximum = -std::numeric_limits<double>::infinity();
    for (std::size_t mask = 0; mask < count; ++mask) {
        if (const auto stop = scoring_stop(context))
            return *stop;
        const auto value = evaluate_corner([mask](std::size_t column) {
            return (mask & (std::size_t{1} << column)) ? 1.0 : -1.0;
        });
        if (const auto *error = std::get_if<Unsupported>(&value))
            return *error;
        if (const auto *stop = std::get_if<OperationStopped>(&value))
            return *stop;
        maximum = std::max(maximum, std::get<double>(value));
    }
    if (!std::isfinite(maximum))
        return unsupported("finite_zonotope_minimax.score",
                           "Terminal factor corners produced no finite score.");
    return CornerScore{maximum, count};
}
}

FiniteActionZonotopeMinimaxOutcome
finite_action_zonotope_minimax(const FiniteActionMinimaxRequest &request,
                               FiniteActionZonotopeMinimaxLimits limits,
                               const ExecutionContext &context) {
    const auto horizon = request.system.horizon();
    if (request.problem.value.empty() || request.request.value.empty())
        return unsupported("finite_zonotope_minimax.identity",
                           "Problem and request identities must be nonempty.");
    if (request.actions.catalogue.empty() && horizon != 0)
        return unsupported("finite_zonotope_minimax.actions",
                           "A nonempty finite action catalogue is required.");
    if (!detail::valid_candidate_action_indices(request))
        return unsupported(
            "finite_zonotope_minimax.candidate_plans",
            "Candidate action histories must be unique, full-horizon, and index the unchanged action catalogue.");
    const auto plan_count = detail::selected_plan_count(request);
    if (plan_count > limits.max_plans)
        return unsupported("finite_zonotope_minimax.plans",
                           "Action plan count exceeds caller limit.");
    if (request.objective.dimension() != request.system.dimensions().state ||
        request.actions.dimension != request.system.dimensions().control ||
        request.disturbances.size() != horizon || request.admissible_states.size() != horizon + 1)
        return unsupported("finite_zonotope_minimax.dimensions",
                           "Objective, catalogue or stage dimensions differ from the model.");

    std::vector<FiniteActionZonotopePlanAttempt> attempts;
    // Preserve one additional typed row for the stopped plan after the cap.
    const auto attempt_capacity =
        limits.max_candidate_attempts < plan_count ? limits.max_candidate_attempts + 1 : plan_count;
    attempts.reserve(attempt_capacity);
    bool complete = true;
    std::size_t selected_index = 0;
    double minimum = std::numeric_limits<double>::infinity();
    bool has_scored = false;
    const auto stop_search = [&](const std::vector<std::size_t> &choices, std::size_t plan_index,
                                 OperationStopped stopped) -> FiniteActionZonotopeMinimaxOutcome {
        attempts.emplace_back(ZonotopePlanStopped{choices, stopped});
        return FiniteActionZonotopeMinimaxResult{
            request.problem,
            request.request,
            std::move(attempts),
            CandidateSearchCoverage::incomplete,
            ZonotopeCandidateSearchStopped{plan_index, std::move(stopped)},
            Assurance::numerical};
    };
    for (std::size_t plan_index = 0; plan_index < plan_count; ++plan_index) {
        const auto choices = detail::selected_plan_indices(request, plan_index);
        if (plan_index >= limits.max_candidate_attempts)
            return stop_search(choices, plan_index,
                               {StopReason::resource_limit,
                                "Zonotope candidate-attempt limit reached before this plan."});
        if (context.cancellation.stop_requested())
            return stop_search(
                choices, plan_index,
                {StopReason::cancelled, "Zonotope finite minimax cancelled before this plan."});
        if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
            return stop_search(choices, plan_index,
                               {StopReason::deadline_expired,
                                "Zonotope finite minimax deadline expired before this plan."});
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
            {request.request.value + "/zonotope-plan/" + std::to_string(plan_index)}};
        auto propagated =
            reachability::finite_plan_zonotope(plan, {limits.max_generators_per_stage}, context);
        if (const auto *stop = std::get_if<OperationStopped>(&propagated))
            return stop_search(choices, plan_index, *stop);
        if (const auto *error = std::get_if<Unsupported>(&propagated)) {
            attempts.emplace_back(ZonotopePlanUnscored{choices, *error});
            complete = false;
            continue;
        }
        auto trace = std::get<reachability::FinitePlanZonotopeTrace>(std::move(propagated));
        auto scored = score_corners(trace.stages.back(), request.objective,
                                    limits.max_factor_corners, context);
        if (const auto *stop = std::get_if<OperationStopped>(&scored))
            return stop_search(choices, plan_index, *stop);
        if (const auto *error = std::get_if<Unsupported>(&scored)) {
            attempts.emplace_back(ZonotopePlanUnscored{choices, *error});
            complete = false;
            continue;
        }
        const auto score = std::get<CornerScore>(scored);
        attempts.emplace_back(
            ZonotopePlanScored{choices,
                               {score.maximum, trace.stages.back().generators.cols, score.evaluated,
                                std::move(trace)}});
        if (score.maximum < minimum) {
            minimum = score.maximum;
            selected_index = plan_index;
            has_scored = true;
        }
    }
    const auto coverage =
        complete ? CandidateSearchCoverage::complete : CandidateSearchCoverage::incomplete;
    if (!has_scored)
        return FiniteActionZonotopeMinimaxResult{request.problem,
                                                 request.request,
                                                 std::move(attempts),
                                                 coverage,
                                                 ZonotopeNoScoredCandidate{},
                                                 Assurance::numerical};

    const auto &selected_attempt = std::get<ZonotopePlanScored>(attempts[selected_index]);
    std::vector<Vector> controls;
    controls.reserve(horizon);
    for (const auto choice : selected_attempt.action_indices)
        controls.push_back(request.actions.catalogue[choice]);
    reachability::FixedPlanRequest replay_request{
        request.system,
        request.initial,
        std::move(controls),
        request.disturbances,
        request.admissible_states,
        {request.request.value + "/zonotope-selected-replay"}};
    const auto replay = detail::replay_finite_action_plan(
        replay_request, request.objective, limits.max_points_per_stage, limits.max_replay_histories,
        "finite_zonotope_minimax", context);
    if (const auto *error = std::get_if<Unsupported>(&replay))
        return FiniteActionZonotopeMinimaxResult{request.problem,
                                                 request.request,
                                                 std::move(attempts),
                                                 coverage,
                                                 ZonotopePlanReplayRefused{selected_index, *error},
                                                 Assurance::numerical};
    if (const auto *stop = std::get_if<OperationStopped>(&replay))
        return FiniteActionZonotopeMinimaxResult{request.problem,
                                                 request.request,
                                                 std::move(attempts),
                                                 coverage,
                                                 ZonotopePlanReplayStopped{selected_index, *stop},
                                                 Assurance::numerical};
    const auto &realized = std::get<detail::FiniteActionReplay>(replay);
    FiniteActionZonotopeReplay replay_result{
        realized.value,        realized.terminal_state, realized.disturbance_indices,
        realized.disturbances, realized.path,           realized.terminal_catalogue};
    return FiniteActionZonotopeMinimaxResult{
        request.problem,
        request.request,
        std::move(attempts),
        coverage,
        ZonotopePlanSelected{selected_index, std::move(replay_result)},
        Assurance::numerical};
}
} // namespace csl::optimization
