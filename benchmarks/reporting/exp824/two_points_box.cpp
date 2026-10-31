#include <csl/optimization/finite_action_box_minimax.hpp>
#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/reachability/finite_plan_zonotope.hpp>
#include "two_points_fixture.hpp"
#include <nlohmann/json.hpp>

#include <array>
#include <iostream>
#include <stdexcept>

namespace {
using namespace csl;
using namespace csl::optimization;
using Json = nlohmann::json;

Json matrix_vertices(const sets::SetData& set) {
    Json result = Json::array();
    const auto rep = set.representation();
    if(const auto* vertices = std::get_if<sets::VRepresentation>(&rep))
        for(std::size_t row = 0; row < vertices->vertices.rows(); ++row) {
            Json point = Json::array();
            for(std::size_t col = 0; col < vertices->vertices.cols(); ++col)
                point.push_back(vertices->vertices(row,col));
            result.push_back(std::move(point));
        }
    return result;
}

Json run() {
    const auto input = csl::issue824::fixture::two_points_request("issue824-two-points-box-v1");
    const auto approximate = finite_action_box_minimax(input, {27,27,27,16});
    const auto* selected = std::get_if<FiniteActionBoxMinimaxResult>(&approximate);
    if(!selected) throw std::runtime_error("box minimax did not complete successfully");
    std::vector<Vector> selected_control_plan;
    selected_control_plan.reserve(selected->selected_action_indices.size());
    for(const auto index : selected->selected_action_indices)
        selected_control_plan.push_back(input.actions.catalogue.at(index));
    reachability::FixedPlanRequest zone_request{input.system, input.initial, selected_control_plan,
        input.disturbances, input.admissible_states, {"issue824-zonotope-shared-plan"}};
    const auto zonotope = reachability::finite_plan_zonotope(zone_request, {64});
    const auto* zonotope_trace = std::get_if<reachability::FinitePlanZonotopeTrace>(&zonotope);
    if(!zonotope_trace) throw std::runtime_error("zonotope propagation did not complete successfully");
    const auto exact = finite_action_minimax(input, {27,27,0.0});
    const auto* reference = std::get_if<FiniteMinimaxOptimal>(&exact);
    if(!reference) throw std::runtime_error("exact finite minimax did not complete successfully");

    Json selected_controls = Json::array();
    for(const auto index : selected->selected_action_indices)
        selected_controls.push_back(input.actions.catalogue.at(index).front());
    Json boxes = Json::array();
    for(const auto& stage : selected->selected_box_trace.stages)
        boxes.push_back({{"lower",stage.lower},{"upper",stage.upper}});
    Json zonotope_stages = Json::array();
    for(const auto& stage : zonotope_trace->stages) {
        Json stage_factors = Json::array();
        for(const auto& factor : stage.factors) stage_factors.push_back(factor.value);
        zonotope_stages.push_back({{"center",stage.center},
            {"generators",{{"rows",stage.generators.rows},{"cols",stage.generators.cols},
                {"values",stage.generators.values}}}, {"factors",std::move(stage_factors)}});
    }
    Json plan_scores = Json::array();
    for(const auto& plan : selected->plan_scores)
        plan_scores.push_back({{"action_indices",plan.action_indices},
            {"terminal_box_maximum",plan.terminal_box_maximum}});
    const auto exact_plan_index = reference->minimizing_plan_indices.front();
    const auto& exact_plan = std::get<FinitePlanFeasible>(reference->plans[exact_plan_index]);
    return {{"schema","csl.issue824-two-points-box-minimax/2"},
        {"environment","TwoPointsOnParallelLines"},
        {"source_identity",{{"repository","optimal_control/Environments"},
            {"commit","f4d76c60f4003f50954174e96eafd8e514bd5441"}}},
        {"adaptation",{{"state_order",{"x1","x2","x3","x4"}},
            {"initial_state",{4.5,0.0,0.0,0.0}}, {"horizon_steps",3},
            {"step_seconds",0.1}, {"control_catalogue",{-2.5,0.0,2.5}},
            {"disturbance_catalogue",{-1.0,0.0,1.0}},
            {"information_pattern","open-loop fixed plan, then finite disturbance history"},
            {"objective","minimize worst terminal squared position gap"},
            {"guarantee_scope","finite catalogs and this discrete adaptation; not continuous RL"}}},
        {"box_method",{{"status","numerical outer interval box"},
            {"selected_action_indices",selected->selected_action_indices},
            {"selected_controls",selected_controls},
            {"terminal_box_maximum",selected->selected_box_score},
            {"full_catalogue_replay_value",selected->selected_replay_value},
            {"worst_disturbance_indices",selected->replayed_worst_disturbance_indices},
            {"worst_disturbances",selected->replayed_worst_disturbance_values},
            {"worst_case_path",selected->replayed_worst_path}, {"stages",boxes},
            {"all_plan_scores",plan_scores}}},
        {"zonotope_method",{{"status","numerical outer zonotope recurrence"},
            {"plan_source","same box-selected fixed open-loop plan"},
            {"relation","outer"}, {"max_generators_per_stage",64},
            {"stages",std::move(zonotope_stages)}}},
        {"exact_reference",{{"finite_minimax_value",reference->value},
            {"selected_action_indices",exact_plan.action_indices},
            {"terminal_vertices",matrix_vertices(exact_plan.terminal)},
            {"assurance","numerical exhaustive finite-catalog reference"}}}};
}
}

int main() {
    try {
        std::cout << run().dump(2) << '\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr << "issue824 TwoPoints box report failed: " << error.what() << '\n';
        return 1;
    }
}
