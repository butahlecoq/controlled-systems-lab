#include <csl/optimization/finite_action_box_minimax.hpp>
#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/optimization/finite_action_zonotope_minimax.hpp>
#include <csl/reachability/finite_plan_zonotope.hpp>
#include "two_points_fixture.hpp"
#include <nlohmann/json.hpp>

#include <iostream>
#include <stdexcept>

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

Json diagnostics_json(const Unsupported& outcome) {
    Json diagnostics = Json::array();
    for(const auto& diagnostic : outcome.diagnostics)
        diagnostics.push_back({{"field", diagnostic.field}, {"explanation", diagnostic.explanation}});
    return diagnostics;
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
        } else {
            const auto& unscored = std::get<ZonotopePlanUnscored>(attempt);
            attempts.push_back({{"status", "unscored"},
                {"action_indices", unscored.action_indices},
                {"diagnostics", diagnostics_json(unscored.outcome)}});
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

Json run() {
    const auto input = csl::issue824::fixture::two_points_request("issue824-two-points-zonotope-minimax-v1");
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
