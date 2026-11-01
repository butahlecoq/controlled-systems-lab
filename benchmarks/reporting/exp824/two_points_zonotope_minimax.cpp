#include <csl/optimization/finite_action_box_minimax.hpp>
#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/optimization/finite_action_zonotope_minimax.hpp>
#include <csl/optimization/finite_action_parallelotope_minimax.hpp>
#include <csl/reachability/finite_plan_zonotope.hpp>
#include <csl/reachability/finite_plan_parallelotope.hpp>
#include "two_points_fixture.hpp"
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string_view>

namespace {
using namespace csl;
using namespace csl::optimization;
using Json = nlohmann::json;

Json matrix_vertices(const sets::SetData& set) {
    Json result = Json::array();
    const auto representation = set.representation();
    if(const auto* vertices = std::get_if<sets::VRepresentation>(&representation))
        for(std::size_t row = 0; row < vertices->vertices.rows(); ++row) {
            Json point = Json::array();
            for(std::size_t column = 0; column < vertices->vertices.cols(); ++column)
                point.push_back(vertices->vertices(row, column));
            result.push_back(std::move(point));
        }
    return result;
}

Json trace_json(const reachability::FinitePlanZonotopeTrace& trace) {
    Json stages = Json::array();
    for(const auto& stage : trace.stages) {
        Json factors = Json::array();
        for(const auto& factor : stage.factors) factors.push_back(factor.value);
        stages.push_back({{"center", stage.center},
            {"generators", {{"rows", stage.generators.rows},
                {"cols", stage.generators.cols}, {"values", stage.generators.values}}},
            {"factors", std::move(factors)}});
    }
    return stages;
}

Json parallelotope_trace_json(const reachability::FinitePlanParallelotopeTrace& trace) {
    Json stages = Json::array();
    for(const auto& stage : trace.stages)
        stages.push_back({{"lower", stage.lower}, {"upper", stage.upper}});
    return {{"frame", {{"rows", trace.frame.rows}, {"cols", trace.frame.cols},
        {"values", trace.frame.values}}}, {"stages", std::move(stages)}};
}

Json diagnostics_json(const Unsupported& outcome) {
    Json diagnostics = Json::array();
    for(const auto& diagnostic : outcome.diagnostics)
        diagnostics.push_back({{"field", diagnostic.field}, {"explanation", diagnostic.explanation}});
    return diagnostics;
}

const char* stop_reason_name(StopReason reason) {
    switch(reason) {
    case StopReason::cancelled: return "cancelled";
    case StopReason::deadline_expired: return "deadline_expired";
    case StopReason::resource_limit: return "resource_limit";
    case StopReason::numerical_failure: return "numerical_failure";
    }
    return "unknown";
}

Json attempts_json(const FiniteActionZonotopeMinimaxResult& result) {
    Json attempts = Json::array();
    for(const auto& attempt : result.plan_attempts) {
        if(const auto* scored = std::get_if<ZonotopePlanScored>(&attempt)) {
            attempts.push_back({{"status", "scored"},
                {"action_indices", scored->action_indices},
                {"candidate_score", scored->score.terminal_factor_corner_maximum},
                {"terminal_generators", scored->score.terminal_generators},
                {"factor_corners_evaluated", scored->score.factor_corners_evaluated},
                {"stages", trace_json(scored->score.trace)}});
        } else if(const auto* unscored = std::get_if<ZonotopePlanUnscored>(&attempt)) {
            attempts.push_back({{"status", "unscored"},
                {"action_indices", unscored->action_indices},
                {"diagnostics", diagnostics_json(unscored->outcome)}});
        } else {
            const auto& stopped = std::get<ZonotopePlanStopped>(attempt);
            attempts.push_back({{"status", "stopped"},
                {"action_indices", stopped.action_indices},
                {"stop_reason", stop_reason_name(stopped.outcome.reason)},
                {"diagnostics", stopped.outcome.diagnostics}});
        }
    }
    return attempts;
}

Json parallelotope_attempts_json(const FiniteActionParallelotopeMinimaxResult& result) {
    Json attempts = Json::array();
    for(const auto& attempt : result.plan_attempts) {
        if(const auto* scored = std::get_if<ParallelotopePlanScored>(&attempt))
            attempts.push_back({{"status", "scored"}, {"action_indices", scored->action_indices},
                {"candidate_score", scored->score.terminal_frame_box_corner_maximum},
                {"corners_evaluated", scored->score.corners_evaluated},
                {"stages", parallelotope_trace_json(scored->score.trace)}});
        else if(const auto* unscored = std::get_if<ParallelotopePlanUnscored>(&attempt))
            attempts.push_back({{"status", "unscored"}, {"action_indices", unscored->action_indices},
                {"diagnostics", diagnostics_json(unscored->outcome)}});
        else {
            const auto& stopped = std::get<ParallelotopePlanStopped>(attempt);
            attempts.push_back({{"status", "stopped"}, {"action_indices", stopped.action_indices},
                {"stop_reason", stop_reason_name(stopped.outcome.reason)},
                {"diagnostics", stopped.outcome.diagnostics}});
        }
    }
    return attempts;
}

reachability::FixedPlanRequest planar_zonotope_request() {
    using csl::issue824::fixture::take;
    const SystemModel authored{{{2, 1, 1}, TimeDomain::discrete,
        LinearStage{{2, 2, {1.0, 0.0, 0.0, 1.0}},
            {2, 1, {1.0, 0.0}}, {2, 1, {0.0, 1.0}}, {0.0, 0.0}}}, {}};
    const auto system = take(model::snapshot(authored, Vector{0.0, 0.1}));
    const auto initial = take(sets::make_singleton({{"selector-example-initial"}, 2, {"x1", "x2"}},
        take(numeric::snapshot_vector(Vector{0.0, 0.0}))));
    const auto disturbance = csl::issue824::fixture::vertices("selector-example-disturbance", 1,
        Matrix{3, 1, {-1.0, 0.0, 1.0}});
    const auto safe_initial = take(sets::make_universal({{"selector-example-safe-initial"}, 2, {}}));
    const auto safe_terminal = take(sets::make_universal({{"selector-example-safe-terminal"}, 2, {}}));
    return {system, initial, {{-1.0}}, {disturbance}, {safe_initial, safe_terminal},
        {"issue824-zonotope-selector-planar-example"}};
}

FiniteActionMinimaxRequest planar_selector_request() {
    auto plan = planar_zonotope_request();
    const auto objective = std::get<Objective>(snapshot(QuadraticTerminal{
        {2, 2, {2.0, 0.0, 0.0, 2.0}}, {0.0, 0.0}, 0.0}));
    return {{"issue824-planar-zonotope-selector"}, {"issue824-planar-zonotope-selector-run"},
        plan.system, plan.initial, {1, {{-1.0}, {0.0}, {1.0}}}, plan.disturbances,
        plan.admissible_states, objective};
}

Json planar_selector_json() {
    const auto request = planar_selector_request();
    const auto selected = finite_action_zonotope_minimax(request, {3, 3, 3, 8, 16});
    const auto* result = std::get_if<FiniteActionZonotopeMinimaxResult>(&selected);
    if(!result) throw std::runtime_error("planar zonotope selector did not return a result");
    const auto* selection = std::get_if<ZonotopePlanSelected>(&result->selection);
    if(!selection) throw std::runtime_error("planar zonotope selector did not replay a candidate");
    Json plans = Json::array();
    for(const auto& attempt : result->plan_attempts) {
        const auto* scored = std::get_if<ZonotopePlanScored>(&attempt);
        if(!scored) throw std::runtime_error("planar zonotope candidate was not scored");
        plans.push_back({{"action_indices", scored->action_indices},
            {"control", request.actions.catalogue[scored->action_indices.front()].front()},
            {"candidate_score", scored->score.terminal_factor_corner_maximum},
            {"terminal_generators", scored->score.terminal_generators},
            {"factor_corners_evaluated", scored->score.factor_corners_evaluated},
            {"stages", trace_json(scored->score.trace)}});
    }
    const auto exact = finite_action_minimax(request, {3, 3, 0.0});
    const auto* reference = std::get_if<FiniteMinimaxOptimal>(&exact);
    if(!reference) throw std::runtime_error("planar exact minimax did not complete");
    return {{"relation", "outer"}, {"dynamics", "x_next = x + (u, w)"},
        {"objective", "x1 squared + x2 squared"}, {"initial_state", {0.0, 0.0}},
        {"control_catalogue", {-1.0, 0.0, 1.0}}, {"disturbance_catalogue", {-1.0, 0.0, 1.0}},
        {"terminal_catalogue_by_control", {{{-1.0, -1.0}, {-1.0, 0.0}, {-1.0, 1.0}},
            {{0.0, -1.0}, {0.0, 0.0}, {0.0, 1.0}},
            {{1.0, -1.0}, {1.0, 0.0}, {1.0, 1.0}}}},
        {"candidate_search_coverage", result->candidate_search == CandidateSearchCoverage::complete
            ? "complete" : "incomplete"},
        {"plans", std::move(plans)},
        {"selected_candidate_attempt_index", selection->candidate_attempt_index},
        {"selected_action_indices", std::get<ZonotopePlanScored>(
            result->plan_attempts[selection->candidate_attempt_index]).action_indices},
        {"selected_replay_value", selection->replay.worst_value},
        {"selected_replay_path", selection->replay.path},
        {"exact_finite_minimax_value", reference->value}};
}

double run_timed_method(std::size_t method, const FiniteActionMinimaxRequest& input) {
    if(method == 0) {
        const auto exact = finite_action_minimax(input, {27, 27, 0.0});
        const auto* result = std::get_if<FiniteMinimaxOptimal>(&exact);
        if(!result) throw std::runtime_error("timed exact finite minimax did not complete");
        return result->value;
    }
    if(method == 1) {
        const auto box = finite_action_box_minimax(input, {27, 27, 27, 16});
        const auto* result = std::get_if<FiniteActionBoxMinimaxResult>(&box);
        if(!result) throw std::runtime_error("timed box selector did not complete");
        return result->selected_replay_value;
    }
    const auto zonotope = finite_action_zonotope_minimax(input, {27, 27, 27, 64, 32768});
    const auto* result = std::get_if<FiniteActionZonotopeMinimaxResult>(&zonotope);
    if(!result) throw std::runtime_error("timed zonotope selector did not complete");
    if(result->candidate_search != CandidateSearchCoverage::complete || result->plan_attempts.size() != 27)
        throw std::runtime_error("timed zonotope selector did not score all 27 plans");
    if(method == 2) {
        const auto* selected = std::get_if<ZonotopePlanSelected>(&result->selection);
        if(!selected) throw std::runtime_error("timed zonotope selector did not replay its selected plan");
        return selected->replay.worst_value;
    }
    const auto parallelotope = finite_action_parallelotope_minimax(input, {27, 27, 27});
    const auto* parallel_result = std::get_if<FiniteActionParallelotopeMinimaxResult>(&parallelotope);
    if(!parallel_result || parallel_result->candidate_search != CandidateSearchCoverage::complete ||
       parallel_result->plan_attempts.size() != 27)
        throw std::runtime_error("timed parallelotope selector did not score all 27 plans");
    const auto* selected = std::get_if<ParallelotopePlanSelected>(&parallel_result->selection);
    if(!selected) throw std::runtime_error("timed parallelotope selector did not replay its selected plan");
    return selected->replay.worst_value;
}

Json timing_json(const FiniteActionMinimaxRequest& input) {
    constexpr std::size_t repetitions = 7;
    constexpr std::array<std::string_view, 4> names{
        "exact_finite_minimax", "outer_box_selector", "zonotope_selector", "parallelotope_selector"};
    for(std::size_t method = 0; method < names.size(); ++method)
        if(!std::isfinite(run_timed_method(method, input)))
            throw std::runtime_error("a timed warmup returned a non-finite value");

    Json samples = Json::array();
    std::array<std::vector<std::int64_t>, names.size()> durations;
    for(std::size_t repetition = 0; repetition < repetitions; ++repetition) {
        for(std::size_t offset = 0; offset < names.size(); ++offset) {
            const auto method = (repetition + offset) % names.size();
            const auto start = std::chrono::steady_clock::now();
            const auto value = run_timed_method(method, input);
            const auto stop = std::chrono::steady_clock::now();
            const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count();
            durations[method].push_back(elapsed);
            samples.push_back({{"repetition", repetition}, {"order_in_repetition", offset},
                {"method", names[method]}, {"elapsed_ns", elapsed}, {"returned_value", value},
                {"status", "completed"}});
        }
    }

    Json summaries = Json::array();
    for(std::size_t method = 0; method < names.size(); ++method) {
        auto sorted = durations[method];
        std::sort(sorted.begin(), sorted.end());
        summaries.push_back({{"method", names[method]}, {"repetitions", repetitions},
            {"failures", 0}, {"minimum_ns", sorted.front()},
            {"median_ns", sorted[sorted.size() / 2]}, {"maximum_ns", sorted.back()}});
    }
    return {{"schema", "csl.issue824-zonotope-minimax-timing/1"},
        {"warmup_runs_per_method", 1}, {"measurement_repetitions_per_method", repetitions},
        {"order_policy", "four methods rotate order across each repetition"},
        {"interval", "complete public algorithm call; request construction and JSON serialization excluded"},
        {"input_policy", "one immutable request reused; fixture setup is outside timing"},
        {"warm_state_policy", "one excluded warmup per method; no algorithm workspace reused"},
        {"arithmetic", "binary64"}, {"absolute_tolerance", 1e-8},
        {"relative_tolerance", 1e-8}, {"seed", "none; deterministic finite catalogues"},
        {"workers", {{"requested", 1}, {"actual", 1}, {"native_threads", 1}}},
        {"limiter_profile", "not collected: perf and strace are unavailable; descriptive timing only"},
        {"summaries", std::move(summaries)}, {"samples", std::move(samples)}};
}

Json run() {
    const auto input = csl::issue824::fixture::two_points_request("issue824-two-points-zonotope-minimax-v1");
    const auto timing = timing_json(input);
    const auto exact = finite_action_minimax(input, {27, 27, 0.0});
    const auto* exact_result = std::get_if<FiniteMinimaxOptimal>(&exact);
    if(!exact_result) throw std::runtime_error("exact finite minimax did not complete");
    const auto box = finite_action_box_minimax(input, {27, 27, 27, 16});
    const auto* box_result = std::get_if<FiniteActionBoxMinimaxResult>(&box);
    if(!box_result) throw std::runtime_error("box minimax did not complete");
    const auto zonotope = finite_action_zonotope_minimax(input, {27, 27, 27, 64, 32768});
    const auto* zonotope_result = std::get_if<FiniteActionZonotopeMinimaxResult>(&zonotope);
    if(!zonotope_result) throw std::runtime_error("zonotope minimax did not return a result");
    if(zonotope_result->candidate_search != CandidateSearchCoverage::complete ||
       zonotope_result->plan_attempts.size() != 27)
        throw std::runtime_error("zonotope minimax candidate search was incomplete");
    const auto* selected = std::get_if<ZonotopePlanSelected>(&zonotope_result->selection);
    if(!selected) throw std::runtime_error("zonotope minimax did not replay a selected candidate");

    const auto parallelotope = finite_action_parallelotope_minimax(input, {27, 27, 27});
    const auto* parallelotope_result = std::get_if<FiniteActionParallelotopeMinimaxResult>(&parallelotope);
    if(!parallelotope_result || parallelotope_result->candidate_search != CandidateSearchCoverage::complete ||
       parallelotope_result->plan_attempts.size() != 27)
        throw std::runtime_error("parallelotope minimax candidate search was incomplete");
    const auto* parallelotope_selected = std::get_if<ParallelotopePlanSelected>(&parallelotope_result->selection);
    if(!parallelotope_selected) throw std::runtime_error("parallelotope minimax did not replay a selected candidate");
    const auto& parallelotope_scored = std::get<ParallelotopePlanScored>(
        parallelotope_result->plan_attempts[parallelotope_selected->candidate_attempt_index]);

    std::vector<Vector> box_controls;
    for(const auto index : box_result->selected_action_indices)
        box_controls.push_back(input.actions.catalogue.at(index));
    reachability::FixedPlanRequest box_zone_request{input.system, input.initial, std::move(box_controls),
        input.disturbances, input.admissible_states, {"issue824-zonotope-box-selected-plan"}};
    const auto box_zone = reachability::finite_plan_zonotope(box_zone_request, {64});
    const auto* box_zone_trace = std::get_if<reachability::FinitePlanZonotopeTrace>(&box_zone);
    if(!box_zone_trace) throw std::runtime_error("box-selected plan zonotope did not complete");

    Json box_scores = Json::array();
    for(const auto& score : box_result->plan_scores)
        box_scores.push_back({{"action_indices", score.action_indices},
            {"terminal_box_maximum", score.terminal_box_maximum}});
    Json box_stages = Json::array();
    for(const auto& stage : box_result->selected_box_trace.stages)
        box_stages.push_back({{"lower", stage.lower}, {"upper", stage.upper}});
    Json exact_controls = Json::array();
    Json exact_action_indices = Json::array();
    for(const auto index : std::get<FinitePlanFeasible>(
            exact_result->plans[exact_result->minimizing_plan_indices.front()]).action_indices) {
        exact_action_indices.push_back(index);
        exact_controls.push_back(input.actions.catalogue[index].front());
    }

    return {{"schema", "csl.issue824-two-points-zonotope-minimax/1"},
        {"timing", timing},
        {"environment", "TwoPointsOnParallelLines"},
        {"source_identity", {{"repository", "optimal_control/Environments"},
            {"commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"}}},
        {"adaptation", {{"state_order", {"x1", "x2", "x3", "x4"}},
            {"initial_state", {4.5, 0.0, 0.0, 0.0}}, {"horizon_steps", 3},
            {"step_seconds", 0.1}, {"control_catalogue", {-2.5, 0.0, 2.5}},
            {"disturbance_catalogue", {-1.0, 0.0, 1.0}},
            {"information_pattern", "open-loop fixed plan, then finite disturbance history"},
            {"objective", "minimize worst terminal squared position gap"},
            {"guarantee_scope", "finite catalogs and this discrete adaptation; not continuous RL"}}},
        {"exact_reference", {{"finite_minimax_value", exact_result->value},
            {"selected_action_indices", std::move(exact_action_indices)},
            {"selected_controls", exact_controls}}},
        {"box_method", {{"status", "numerical outer interval box"},
            {"selected_action_indices", box_result->selected_action_indices},
            {"selected_controls", [&] { Json values = Json::array();
                for(const auto index : box_result->selected_action_indices)
                    values.push_back(input.actions.catalogue[index].front());
                return values; }()},
            {"terminal_box_maximum", box_result->selected_box_score},
            {"full_catalogue_replay_value", box_result->selected_replay_value},
            {"worst_disturbance_indices", box_result->replayed_worst_disturbance_indices},
            {"worst_disturbances", box_result->replayed_worst_disturbance_values},
            {"worst_case_path", box_result->replayed_worst_path},
            {"stages", std::move(box_stages)}, {"all_plan_scores", std::move(box_scores)}}},
        {"zonotope_method", {{"status", "numerical outer zonotope recurrence"},
            {"plan_source", "box-selected fixed open-loop plan"}, {"relation", "outer"},
            {"max_generators_per_stage", 64}, {"stages", trace_json(*box_zone_trace)}}},
        {"parallelotope_method", {{"status", "numerical outer fixed-frame parallelotope recurrence"},
            {"plan_source", "parallelotope-selected fixed open-loop plan"}, {"relation", "outer"},
            {"coordinate_frame", "x = Q y; Q is a fixed unit-upper-triangular dyadic shear"},
            {"stages", parallelotope_trace_json(parallelotope_scored.score.trace)}}},
        {"parallelotope_minimax_method", {{"status", "numerical frame-box-corner candidate scoring"},
            {"candidate_search_coverage", "complete"}, {"corners_evaluated_per_candidate", 16},
            {"plan_attempts", parallelotope_attempts_json(*parallelotope_result)},
            {"selected_candidate_attempt_index", parallelotope_selected->candidate_attempt_index},
            {"selected_action_indices", parallelotope_scored.action_indices},
            {"selected_candidate_score", parallelotope_scored.score.terminal_frame_box_corner_maximum},
            {"selected_replay", {{"worst_value", parallelotope_selected->replay.worst_value},
                {"worst_terminal_state", parallelotope_selected->replay.worst_terminal_state},
                {"disturbance_indices", parallelotope_selected->replay.disturbance_indices},
                {"disturbances", parallelotope_selected->replay.disturbances},
                {"path", parallelotope_selected->replay.path}}}}},
        {"zonotope_minimax_method", {{"status", "numerical factor-corner candidate scoring"},
            {"candidate_search_coverage", "complete"}, {"max_generators_per_stage", 64},
            {"max_factor_corners", 32768}, {"plan_attempts", attempts_json(*zonotope_result)},
            {"selected_candidate_attempt_index", selected->candidate_attempt_index},
            {"selected_action_indices", std::get<ZonotopePlanScored>(
                zonotope_result->plan_attempts[selected->candidate_attempt_index]).action_indices},
            {"selected_candidate_score", std::get<ZonotopePlanScored>(
                zonotope_result->plan_attempts[selected->candidate_attempt_index]).score.terminal_factor_corner_maximum},
            {"selected_replay", {{"worst_value", selected->replay.worst_value},
                {"worst_terminal_state", selected->replay.worst_terminal_state},
                {"disturbance_indices", selected->replay.disturbance_indices},
                {"disturbances", selected->replay.disturbances}, {"path", selected->replay.path},
                {"terminal_vertices", matrix_vertices(selected->replay.terminal_catalogue)}}}}},
        {"planar_selector_example", planar_selector_json()}};
}
}

int main() {
    try {
        std::cout << run().dump(2) << '\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr << "issue824 zonotope minimax report failed: " << error.what() << '\n';
        return 1;
    }
}
