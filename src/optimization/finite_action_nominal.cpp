#include <csl/optimization/finite_action_nominal.hpp>
#include <csl/optimization/finite_action_box_minimax.hpp>
#include <csl/optimization/finite_action_ellipsoid_minimax.hpp>
#include <csl/optimization/finite_action_parallelotope_minimax.hpp>
#include <csl/optimization/finite_action_zonotope_minimax.hpp>

#include "finite_action_plans.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace csl::optimization {
namespace {

Unsupported unsupported(std::string field, std::string message) {
    return {{{DiagnosticCode::unsupported, std::move(field), std::move(message)}}};
}

using SetOutcome = std::variant<sets::SetData, Unsupported>;
SetOutcome singleton(std::string id, std::span<const double> values) {
    auto view = numeric::snapshot_vector(Vector(values.begin(), values.end()));
    if(const auto* error = std::get_if<Diagnostic>(&view))
        return unsupported(error->field, error->explanation);
    auto set = sets::make_singleton({{std::move(id)}, values.size(), {}},
        std::get<numeric::VectorView>(std::move(view)));
    if(const auto* error = std::get_if<Diagnostic>(&set))
        return unsupported(error->field, error->explanation);
    return std::get<sets::SetData>(std::move(set));
}

using RequestOutcome = std::variant<FiniteActionMinimaxRequest, Unsupported>;
RequestOutcome make_degenerate_request(const FiniteActionNominalRequest& request) {
    const auto horizon = request.system.horizon();
    const auto dimensions = request.system.dimensions();
    if(request.problem.value.empty() || request.request.value.empty())
        return unsupported("finite_nominal.identity", "Problem and request identities must be nonempty.");
    if(request.initial_state.size() != dimensions.state ||
       request.actions.dimension != dimensions.control ||
       request.nominal_disturbances.size() != horizon ||
       request.admissible_states.size() != horizon + 1 ||
       request.objective.dimension() != dimensions.state)
        return unsupported("finite_nominal.dimensions", "Nominal state, controls, disturbances, safe sets, or objective do not match the system.");
    if(horizon != 0 && request.actions.catalogue.empty())
        return unsupported("finite_nominal.actions", "A nonempty finite action catalogue is required.");
    if(!std::ranges::all_of(request.initial_state, [](double value) { return std::isfinite(value); }))
        return unsupported("finite_nominal.initial", "The authored nominal initial state must be finite.");
    auto initial = singleton("nominal-initial", request.initial_state);
    if(const auto* error = std::get_if<Unsupported>(&initial)) return *error;
    std::vector<sets::SetData> disturbances;
    disturbances.reserve(horizon);
    for(std::size_t stage = 0; stage < horizon; ++stage) {
        if(request.nominal_disturbances[stage].size() != dimensions.external ||
           !std::ranges::all_of(request.nominal_disturbances[stage], [](double value) { return std::isfinite(value); }))
            return unsupported("finite_nominal.disturbances", "Each nominal disturbance must be finite and match the external dimension.");
        auto point = singleton("nominal-disturbance-" + std::to_string(stage), request.nominal_disturbances[stage]);
        if(const auto* error = std::get_if<Unsupported>(&point)) return *error;
        disturbances.push_back(std::get<sets::SetData>(std::move(point)));
    }
    return FiniteActionMinimaxRequest{request.problem, request.request, request.system,
        std::get<sets::SetData>(std::move(initial)), request.actions,
        std::move(disturbances), request.admissible_states, request.objective};
}

std::size_t expected_plan_count(const FiniteActionMinimaxRequest& request) {
    std::size_t count = 1;
    const auto horizon = request.system.horizon();
    for(std::size_t stage = 0; stage < horizon; ++stage) {
        if(request.actions.catalogue.empty() || count > std::numeric_limits<std::size_t>::max() /
                request.actions.catalogue.size()) return std::numeric_limits<std::size_t>::max();
        count *= request.actions.catalogue.size();
    }
    return count;
}

std::vector<Vector> controls_for(const FiniteActionNominalRequest& request,
    const std::vector<std::size_t>& indices) {
    std::vector<Vector> controls;
    controls.reserve(indices.size());
    for(const auto index : indices) controls.push_back(request.actions.catalogue.at(index));
    return controls;
}

using ReplayOutcome = std::variant<NominalTrajectory, Unsupported, OperationStopped>;
ReplayOutcome replay_nominal(const FiniteActionNominalRequest& request,
    const std::vector<std::size_t>& indices, const ExecutionContext& context) {
    const auto controls = controls_for(request, indices);
    NominalTrajectory result;
    result.states.push_back(request.initial_state);
    result.controls = controls;
    result.disturbances = request.nominal_disturbances;
    for(std::size_t stage = 0; stage < controls.size(); ++stage) {
        if(context.cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled, "Nominal trajectory replay cancelled."};
        const auto next = request.system.step({stage}, result.states.back(),
            controls[stage], request.nominal_disturbances[stage]);
        if(const auto* error = std::get_if<Diagnostic>(&next))
            return unsupported(error->field, error->explanation);
        if(const auto* stopped = std::get_if<OperationStopped>(&next)) return *stopped;
        result.states.push_back(std::get<Vector>(next));
    }
    const auto value = evaluate(request.objective, result.states.back());
    if(const auto* error = std::get_if<Diagnostic>(&value)) return unsupported(error->field, error->explanation);
    result.terminal_objective = std::get<double>(value);
    return result;
}

using ExactOutcome = std::variant<NominalTrackSelected, NominalTrackNoScoredCandidate,
    NominalTrackUnsupported, NominalTrackStopped>;
ExactOutcome exact_track(const FiniteActionNominalRequest& nominal,
    const FiniteActionMinimaxRequest& request, FiniteActionNominalLimits limits,
    const ExecutionContext& context) {
    auto outcome = finite_action_minimax(request,
        {limits.max_plans, limits.max_points_per_stage, limits.near_optimal_tolerance}, context);
    if(const auto* error = std::get_if<Unsupported>(&outcome))
        return NominalTrackUnsupported{{}, NominalSearchCoverage::incomplete, *error};
    if(const auto* stop = std::get_if<OperationStopped>(&outcome))
        return NominalTrackStopped{{}, NominalSearchCoverage::stopped, *stop};
    const auto expected = expected_plan_count(request);
    if(const auto* infeasible = std::get_if<FiniteMinimaxInfeasible>(&outcome)) {
        std::vector<NominalPlanAttempt> attempts;
        attempts.reserve(infeasible->rejected_plans.size());
        for(const auto& plan : infeasible->rejected_plans)
            attempts.emplace_back(NominalPlanRejected{plan.action_indices, plan.stage, plan.violating_successor});
        return NominalTrackNoScoredCandidate{std::move(attempts),
            infeasible->rejected_plans.size() == expected ? NominalSearchCoverage::complete : NominalSearchCoverage::incomplete};
    }
    const auto* optimal = std::get_if<FiniteMinimaxOptimal>(&outcome);
    if(!optimal) return NominalTrackUnsupported{{}, NominalSearchCoverage::incomplete,
        unsupported("finite_nominal.exact", "Exact nominal selector returned an unsupported outcome.")};
    std::vector<NominalPlanAttempt> attempts;
    attempts.reserve(optimal->plans.size());
    for(const auto& plan : optimal->plans) {
        if(const auto* scored = std::get_if<FinitePlanFeasible>(&plan))
            attempts.emplace_back(NominalPlanScored{scored->action_indices, scored->worst_value,
                NominalScoreKind::exact_deterministic_objective});
        else {
            const auto& rejected = std::get<FinitePlanRejected>(plan);
            attempts.emplace_back(NominalPlanRejected{rejected.action_indices, rejected.stage,
                rejected.violating_successor});
        }
    }
    const auto coverage = optimal->plans.size() == expected ? NominalSearchCoverage::complete : NominalSearchCoverage::incomplete;
    if(optimal->minimizing_plan_indices.empty())
        return NominalTrackNoScoredCandidate{std::move(attempts), coverage};
    const auto selected = optimal->minimizing_plan_indices.front();
    const auto* selected_plan = std::get_if<FinitePlanFeasible>(&optimal->plans.at(selected));
    if(!selected_plan)
        return NominalTrackUnsupported{std::move(attempts), coverage,
            unsupported("finite_nominal.exact.selection", "Selected exact plan is not feasible.")};
    auto replay = replay_nominal(nominal, selected_plan->action_indices, context);
    if(const auto* error = std::get_if<Unsupported>(&replay))
        return NominalTrackUnsupported{std::move(attempts), coverage, *error};
    if(const auto* stop = std::get_if<OperationStopped>(&replay))
        return NominalTrackStopped{std::move(attempts), NominalSearchCoverage::stopped, *stop};
    auto trace_controls = controls_for(nominal, selected_plan->action_indices);
    reachability::FixedPlanRequest trace_request{request.system, request.initial,
        std::move(trace_controls), request.disturbances, request.admissible_states,
        {request.request.value + "/nominal-exact-trace"}};
    const auto trace = reachability::fixed_plan_disturbance(trace_request,
        limits.max_points_per_stage, context);
    if(const auto* error = std::get_if<Unsupported>(&trace))
        return NominalTrackUnsupported{std::move(attempts), coverage, *error};
    if(const auto* stop = std::get_if<OperationStopped>(&trace))
        return NominalTrackStopped{std::move(attempts), NominalSearchCoverage::stopped, *stop};
    const auto& trajectory = std::get<NominalTrajectory>(replay);
    // The selected exact score and deterministic replay should agree within
    // the request's numerical policy.
    const auto scale = std::max({1.0, std::abs(selected_plan->worst_value), std::abs(trajectory.terminal_objective)});
    const auto tolerance = context.numerical.absolute_tolerance + context.numerical.relative_tolerance * scale;
    if(std::abs(selected_plan->worst_value - trajectory.terminal_objective) > tolerance)
        return NominalTrackStopped{std::move(attempts), NominalSearchCoverage::stopped,
            {StopReason::numerical_failure, "Exact nominal score differs from its deterministic replay."}};
    return NominalTrackSelected{std::move(attempts), coverage, selected,
        selected_plan->worst_value, NominalScoreKind::exact_deterministic_objective,
        trajectory, std::get<reachability::FixedPlanReachable>(trace)};
}

using SelectedOutcome = std::variant<NominalTrackSelected, NominalTrackUnsupported,
    NominalTrackStopped>;
SelectedOutcome select_and_replay(const FiniteActionNominalRequest& request,
    std::vector<NominalPlanAttempt> attempts,
    NominalSearchCoverage coverage, std::size_t selected_attempt, double candidate_score,
    NominalScoreKind score_kind, NominalPlanTrace trace, const ExecutionContext& context) {
    if(selected_attempt >= attempts.size())
        return NominalTrackUnsupported{std::move(attempts), coverage,
            unsupported("finite_nominal.selection", "Selected plan index is outside the attempt table.")};
    const auto* scored = std::get_if<NominalPlanScored>(&attempts[selected_attempt]);
    if(!scored)
        return NominalTrackUnsupported{std::move(attempts), coverage,
            unsupported("finite_nominal.selection", "Selected plan has no candidate score.")};
    auto replay = replay_nominal(request, scored->action_indices, context);
    if(const auto* error = std::get_if<Unsupported>(&replay))
        return NominalTrackUnsupported{std::move(attempts), coverage, *error};
    if(const auto* stop = std::get_if<OperationStopped>(&replay))
        return NominalTrackStopped{std::move(attempts), NominalSearchCoverage::stopped, *stop};
    return NominalTrackSelected{std::move(attempts), coverage, selected_attempt,
        candidate_score, score_kind, std::get<NominalTrajectory>(std::move(replay)),
        std::move(trace)};
}

NominalSearchCoverage coverage_from(CandidateSearchCoverage coverage) {
    return coverage == CandidateSearchCoverage::complete ?
        NominalSearchCoverage::complete : NominalSearchCoverage::incomplete;
}

NominalTrackOutcome box_track(const FiniteActionNominalRequest& nominal,
    const FiniteActionMinimaxRequest& request, FiniteActionNominalLimits limits,
    const ExecutionContext& context) {
    const auto outcome = finite_action_box_minimax(request,
        {limits.max_plans, limits.max_points_per_stage, 1, limits.max_score_evaluations}, context);
    if(const auto* error = std::get_if<Unsupported>(&outcome))
        return NominalTrackUnsupported{{}, NominalSearchCoverage::incomplete, *error};
    if(const auto* stop = std::get_if<OperationStopped>(&outcome))
        return NominalTrackStopped{{}, NominalSearchCoverage::stopped, *stop};
    const auto& result = std::get<FiniteActionBoxMinimaxResult>(outcome);
    std::vector<NominalPlanAttempt> attempts;
    attempts.reserve(result.plan_attempts.size());
    for(const auto& attempt : result.plan_attempts) {
        if(const auto* scored = std::get_if<BoxPlanScored>(&attempt))
            attempts.emplace_back(NominalPlanScored{scored->action_indices,
                scored->terminal_box_maximum,
                NominalScoreKind::numerical_outer_enclosure_estimate});
        else if(const auto* unscored = std::get_if<BoxPlanUnscored>(&attempt))
            attempts.emplace_back(NominalPlanUnscored{unscored->action_indices, unscored->reason});
        else {
            const auto& stopped = std::get<BoxPlanStopped>(attempt);
            attempts.emplace_back(NominalPlanStopped{stopped.action_indices, stopped.reason});
        }
    }
    const auto coverage = coverage_from(result.candidate_search);
    if(const auto* selected = std::get_if<BoxPlanSelected>(&result.selection)) {
        if(selected->candidate_attempt_index >= result.plan_attempts.size())
            return NominalTrackUnsupported{std::move(attempts), coverage,
                unsupported("finite_nominal.box.selection", "Selected box attempt index is outside the attempt table.")};
        const auto* scored = std::get_if<BoxPlanScored>(
            &result.plan_attempts[selected->candidate_attempt_index]);
        if(!scored)
            return NominalTrackUnsupported{std::move(attempts), coverage,
                unsupported("finite_nominal.box.selection", "Selected box attempt has no candidate score.")};
        auto selection = select_and_replay(nominal, std::move(attempts), coverage,
            selected->candidate_attempt_index, scored->terminal_box_maximum,
            NominalScoreKind::numerical_outer_enclosure_estimate, scored->trace, context);
        if(auto* selected_outcome = std::get_if<NominalTrackSelected>(&selection)) return *selected_outcome;
        if(auto* error = std::get_if<NominalTrackUnsupported>(&selection)) return *error;
        return std::get<NominalTrackStopped>(std::move(selection));
    }
    if(const auto* refused = std::get_if<BoxPlanReplayRefused>(&result.selection))
        return NominalTrackUnsupported{std::move(attempts), coverage, refused->reason};
    if(const auto* stopped = std::get_if<BoxPlanReplayStopped>(&result.selection))
        return NominalTrackStopped{std::move(attempts), NominalSearchCoverage::stopped, stopped->reason};
    return NominalTrackNoScoredCandidate{std::move(attempts), coverage};
}

NominalTrackOutcome zonotope_track(const FiniteActionNominalRequest& nominal,
    const FiniteActionMinimaxRequest& request, FiniteActionNominalLimits limits,
    const ExecutionContext& context) {
    const auto outcome = finite_action_zonotope_minimax(request,
        {limits.max_plans, limits.max_points_per_stage, 1, limits.max_generators_per_stage,
         limits.max_score_evaluations, limits.max_plans}, context);
    if(const auto* error = std::get_if<Unsupported>(&outcome))
        return NominalTrackUnsupported{{}, NominalSearchCoverage::incomplete, *error};
    if(const auto* stop = std::get_if<OperationStopped>(&outcome))
        return NominalTrackStopped{{}, NominalSearchCoverage::stopped, *stop};
    const auto& result = std::get<FiniteActionZonotopeMinimaxResult>(outcome);
    std::vector<NominalPlanAttempt> attempts;
    attempts.reserve(result.plan_attempts.size());
    for(const auto& attempt : result.plan_attempts) {
        if(const auto* scored = std::get_if<ZonotopePlanScored>(&attempt))
            attempts.emplace_back(NominalPlanScored{scored->action_indices,
                scored->score.terminal_factor_corner_maximum,
                NominalScoreKind::numerical_outer_enclosure_estimate});
        else if(const auto* unscored = std::get_if<ZonotopePlanUnscored>(&attempt))
            attempts.emplace_back(NominalPlanUnscored{unscored->action_indices, unscored->outcome});
        else {
            const auto& stopped = std::get<ZonotopePlanStopped>(attempt);
            attempts.emplace_back(NominalPlanStopped{stopped.action_indices, stopped.outcome});
        }
    }
    const auto coverage = coverage_from(result.candidate_search);
    if(const auto* selected = std::get_if<ZonotopePlanSelected>(&result.selection)) {
        const auto index = selected->candidate_attempt_index;
        if(index >= result.plan_attempts.size() || !std::holds_alternative<ZonotopePlanScored>(result.plan_attempts[index]))
            return NominalTrackUnsupported{std::move(attempts), coverage,
                unsupported("finite_nominal.zonotope.selection", "Selected zonotope attempt has no score.")};
        const auto& score = std::get<ZonotopePlanScored>(result.plan_attempts[index]).score;
        auto outcome2 = select_and_replay(nominal,
            std::move(attempts), coverage, index, score.terminal_factor_corner_maximum,
            NominalScoreKind::numerical_outer_enclosure_estimate, score.trace, context);
        if(auto* good = std::get_if<NominalTrackSelected>(&outcome2)) return *good;
        if(auto* error = std::get_if<NominalTrackUnsupported>(&outcome2)) return *error;
        return std::get<NominalTrackStopped>(std::move(outcome2));
    }
    if(const auto* no_candidate = std::get_if<ZonotopeNoScoredCandidate>(&result.selection)) {
        (void)no_candidate;
        return NominalTrackNoScoredCandidate{std::move(attempts), coverage};
    }
    if(const auto* refused = std::get_if<ZonotopePlanReplayRefused>(&result.selection))
        return NominalTrackUnsupported{std::move(attempts), coverage, refused->outcome};
    if(const auto* replay_stopped = std::get_if<ZonotopePlanReplayStopped>(&result.selection))
        return NominalTrackStopped{std::move(attempts), NominalSearchCoverage::stopped, replay_stopped->outcome};
    const auto& search_stopped = std::get<ZonotopeCandidateSearchStopped>(result.selection);
    return NominalTrackStopped{std::move(attempts), NominalSearchCoverage::stopped, search_stopped.outcome};
}

NominalTrackOutcome parallelotope_track(const FiniteActionNominalRequest& nominal,
    const FiniteActionMinimaxRequest& request, FiniteActionNominalLimits limits,
    const ExecutionContext& context) {
    const auto outcome = finite_action_parallelotope_minimax(request,
        {limits.max_plans, limits.max_points_per_stage, 1, limits.max_plans}, context);
    if(const auto* error = std::get_if<Unsupported>(&outcome))
        return NominalTrackUnsupported{{}, NominalSearchCoverage::incomplete, *error};
    if(const auto* stop = std::get_if<OperationStopped>(&outcome))
        return NominalTrackStopped{{}, NominalSearchCoverage::stopped, *stop};
    const auto& result = std::get<FiniteActionParallelotopeMinimaxResult>(outcome);
    std::vector<NominalPlanAttempt> attempts;
    attempts.reserve(result.plan_attempts.size());
    for(const auto& attempt : result.plan_attempts) {
        if(const auto* scored = std::get_if<ParallelotopePlanScored>(&attempt))
            attempts.emplace_back(NominalPlanScored{scored->action_indices,
                scored->score.terminal_frame_box_corner_maximum,
                NominalScoreKind::numerical_outer_enclosure_estimate});
        else if(const auto* unscored = std::get_if<ParallelotopePlanUnscored>(&attempt))
            attempts.emplace_back(NominalPlanUnscored{unscored->action_indices, unscored->outcome});
        else {
            const auto& stopped = std::get<ParallelotopePlanStopped>(attempt);
            attempts.emplace_back(NominalPlanStopped{stopped.action_indices, stopped.outcome});
        }
    }
    const auto coverage = coverage_from(result.candidate_search);
    if(const auto* selected = std::get_if<ParallelotopePlanSelected>(&result.selection)) {
        const auto index = selected->candidate_attempt_index;
        if(index >= result.plan_attempts.size() || !std::holds_alternative<ParallelotopePlanScored>(result.plan_attempts[index]))
            return NominalTrackUnsupported{std::move(attempts), coverage,
                unsupported("finite_nominal.parallelotope.selection", "Selected parallelotope attempt has no score.")};
        const auto& score = std::get<ParallelotopePlanScored>(result.plan_attempts[index]).score;
        auto outcome2 = select_and_replay(nominal,
            std::move(attempts), coverage, index, score.terminal_frame_box_corner_maximum,
            NominalScoreKind::numerical_outer_enclosure_estimate, score.trace, context);
        if(auto* good = std::get_if<NominalTrackSelected>(&outcome2)) return *good;
        if(auto* error = std::get_if<NominalTrackUnsupported>(&outcome2)) return *error;
        return std::get<NominalTrackStopped>(std::move(outcome2));
    }
    if(std::holds_alternative<ParallelotopeNoScoredCandidate>(result.selection))
        return NominalTrackNoScoredCandidate{std::move(attempts), coverage};
    if(const auto* refused = std::get_if<ParallelotopePlanReplayRefused>(&result.selection))
        return NominalTrackUnsupported{std::move(attempts), coverage, refused->outcome};
    if(const auto* replay_stopped = std::get_if<ParallelotopePlanReplayStopped>(&result.selection))
        return NominalTrackStopped{std::move(attempts), NominalSearchCoverage::stopped, replay_stopped->outcome};
    const auto& search_stopped = std::get<ParallelotopeCandidateSearchStopped>(result.selection);
    return NominalTrackStopped{std::move(attempts), NominalSearchCoverage::stopped, search_stopped.outcome};
}

NominalTrackOutcome ellipsoid_track(const FiniteActionNominalRequest& nominal,
    const FiniteActionMinimaxRequest& request, FiniteActionNominalLimits limits,
    const ExecutionContext& context) {
    const auto outcome = finite_action_ellipsoid_minimax(request,
        {limits.max_plans, limits.max_points_per_stage, 1, limits.max_plans}, context);
    if(const auto* error = std::get_if<Unsupported>(&outcome))
        return NominalTrackUnsupported{{}, NominalSearchCoverage::incomplete, *error};
    if(const auto* stop = std::get_if<OperationStopped>(&outcome))
        return NominalTrackStopped{{}, NominalSearchCoverage::stopped, *stop};
    const auto& result = std::get<FiniteActionEllipsoidMinimaxResult>(outcome);
    std::vector<NominalPlanAttempt> attempts;
    attempts.reserve(result.plan_attempts.size());
    for(const auto& attempt : result.plan_attempts) {
        if(const auto* scored = std::get_if<EllipsoidPlanScored>(&attempt))
            attempts.emplace_back(NominalPlanScored{scored->action_indices,
                scored->score.terminal_support_estimate,
                NominalScoreKind::numerical_outer_enclosure_estimate});
        else if(const auto* unscored = std::get_if<EllipsoidPlanUnscored>(&attempt))
            attempts.emplace_back(NominalPlanUnscored{unscored->action_indices, unscored->outcome});
        else {
            const auto& stopped = std::get<EllipsoidPlanStopped>(attempt);
            attempts.emplace_back(NominalPlanStopped{stopped.action_indices, stopped.outcome});
        }
    }
    const auto coverage = coverage_from(result.candidate_search);
    if(const auto* selected = std::get_if<EllipsoidPlanSelected>(&result.selection)) {
        const auto index = selected->candidate_attempt_index;
        if(index >= result.plan_attempts.size() || !std::holds_alternative<EllipsoidPlanScored>(result.plan_attempts[index]))
            return NominalTrackUnsupported{std::move(attempts), coverage,
                unsupported("finite_nominal.ellipsoid.selection", "Selected ellipsoid attempt has no score.")};
        const auto& score = std::get<EllipsoidPlanScored>(result.plan_attempts[index]).score;
        auto outcome2 = select_and_replay(nominal,
            std::move(attempts), coverage, index, score.terminal_support_estimate,
            NominalScoreKind::numerical_outer_enclosure_estimate, score.trace, context);
        if(auto* good = std::get_if<NominalTrackSelected>(&outcome2)) return *good;
        if(auto* error = std::get_if<NominalTrackUnsupported>(&outcome2)) return *error;
        return std::get<NominalTrackStopped>(std::move(outcome2));
    }
    if(std::holds_alternative<EllipsoidNoScoredCandidate>(result.selection))
        return NominalTrackNoScoredCandidate{std::move(attempts), coverage};
    if(const auto* refused = std::get_if<EllipsoidPlanReplayRefused>(&result.selection))
        return NominalTrackUnsupported{std::move(attempts), coverage, refused->outcome};
    if(const auto* replay_stopped = std::get_if<EllipsoidPlanReplayStopped>(&result.selection))
        return NominalTrackStopped{std::move(attempts), NominalSearchCoverage::stopped, replay_stopped->outcome};
    const auto& search_stopped = std::get<EllipsoidCandidateSearchStopped>(result.selection);
    return NominalTrackStopped{std::move(attempts), NominalSearchCoverage::stopped, search_stopped.outcome};
}

} // namespace

FiniteActionNominalOutcome finite_action_nominal(const FiniteActionNominalRequest& request,
    FiniteActionNominalLimits limits, const ExecutionContext& context) {
    auto built = make_degenerate_request(request);
    if(const auto* error = std::get_if<Unsupported>(&built)) return *error;
    const auto& minimax_request = std::get<FiniteActionMinimaxRequest>(built);
    FiniteActionNominalResult result{request.problem, request.request, {}, Assurance::numerical};
    result.tracks.reserve(5);
    result.tracks.push_back({NominalRepresentation::exact_polytope,
        exact_track(request, minimax_request, limits, context)});
    result.tracks.push_back({NominalRepresentation::box,
        box_track(request, minimax_request, limits, context)});
    result.tracks.push_back({NominalRepresentation::zonotope,
        zonotope_track(request, minimax_request, limits, context)});
    result.tracks.push_back({NominalRepresentation::parallelotope,
        parallelotope_track(request, minimax_request, limits, context)});
    result.tracks.push_back({NominalRepresentation::ellipsoid,
        ellipsoid_track(request, minimax_request, limits, context)});
    return result;
}

} // namespace csl::optimization
