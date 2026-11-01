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

reachability::FixedPlanRequest planar_zonotope_request() {
    using csl::issue824::fixture::take;
    const SystemModel authored{{{2,1,2}, TimeDomain::discrete,
        LinearStage{{2,2,{2.0,0.0,0.0,1.0}}, {2,1,{0.0,0.0}},
            {2,2,{0.0,0.0,0.0,0.0}}, {0.0,0.0}}}, {}};
    const auto system = take(model::snapshot(authored, Vector{0.0,1.0}));
    const auto initial = csl::issue824::fixture::vertices("planar-zonotope-initial", 2,
        Matrix{4,2,{-1.0,-1.0, 1.0,-1.0, 1.0,1.0, -1.0,1.0}});
    const auto disturbance = take(sets::make_singleton({{"planar-zonotope-zero-disturbance"},2,{}},
        take(numeric::snapshot_vector(Vector{0.0,0.0}))));
    const auto safe_initial = take(sets::make_universal({{"planar-zonotope-safe-initial"},2,{}}));
    const auto safe_terminal = take(sets::make_universal({{"planar-zonotope-safe-terminal"},2,{}}));
    return {system, initial, {{0.0}}, {disturbance}, {safe_initial, safe_terminal},
        {"issue824-planar-zonotope-example"}};
}

Json zonotope_stages_json(const reachability::FinitePlanZonotopeTrace& trace) {
    Json stages = Json::array();
    for(const auto& stage : trace.stages) {
        Json factors = Json::array();
        for(const auto& factor : stage.factors) factors.push_back(factor.value);
        stages.push_back({{"center",stage.center},
            {"generators",{{"rows",stage.generators.rows},{"cols",stage.generators.cols},
                {"values",stage.generators.values}}}, {"factors",std::move(factors)}});
    }
    return stages;
}

Json run() {
    const auto input = csl::issue824::fixture::two_points_request("issue824-two-points-box-v1");
    const auto approximate = finite_action_box_minimax(input, {27,27,27,16});
    const auto* result = std::get_if<FiniteActionBoxMinimaxResult>(&approximate);
    if(!result || result->candidate_search != CandidateSearchCoverage::complete ||
       result->plan_attempts.size() != 27)
        throw std::runtime_error("box minimax candidate search was incomplete");
    const auto* selection = std::get_if<BoxPlanSelected>(&result->selection);
    if(!selection) throw std::runtime_error("box minimax did not replay a selected plan");
    const auto& selected = std::get<BoxPlanScored>(
        result->plan_attempts.at(selection->candidate_attempt_index));
    const auto& replay = selection->replay;
    std::vector<Vector> selected_control_plan;
    selected_control_plan.reserve(selected.action_indices.size());
    for(const auto index : selected.action_indices)
        selected_control_plan.push_back(input.actions.catalogue.at(index));
    reachability::FixedPlanRequest zone_request{input.system, input.initial, selected_control_plan,
        input.disturbances, input.admissible_states, {"issue824-zonotope-shared-plan"}};
    const auto zonotope = reachability::finite_plan_zonotope(zone_request, {64});
    const auto* zonotope_trace = std::get_if<reachability::FinitePlanZonotopeTrace>(&zonotope);
    if(!zonotope_trace) throw std::runtime_error("zonotope propagation did not complete successfully");
    const auto planar_request = planar_zonotope_request();
    const auto planar_outcome = reachability::finite_plan_zonotope(planar_request, {64});
    const auto* planar_trace = std::get_if<reachability::FinitePlanZonotopeTrace>(&planar_outcome);
    if(!planar_trace) throw std::runtime_error("planar zonotope example did not complete successfully");
    const auto exact = finite_action_minimax(input, {27,27,0.0});
    const auto* reference = std::get_if<FiniteMinimaxOptimal>(&exact);
    if(!reference) throw std::runtime_error("exact finite minimax did not complete successfully");

    Json selected_controls = Json::array();
    for(const auto index : selected.action_indices)
        selected_controls.push_back(input.actions.catalogue.at(index).front());
    Json boxes = Json::array();
    for(const auto& stage : selected.trace.stages)
        boxes.push_back({{"lower",stage.lower},{"upper",stage.upper}});
    Json plan_scores = Json::array();
    Json plan_attempts = Json::array();
    for(const auto& attempt : result->plan_attempts) {
        if(const auto* scored = std::get_if<BoxPlanScored>(&attempt)) {
            plan_scores.push_back({{"action_indices",scored->action_indices},
                {"terminal_box_maximum",scored->terminal_box_maximum}});
            plan_attempts.push_back({{"status","scored"}, {"action_indices",scored->action_indices},
                {"terminal_box_maximum",scored->terminal_box_maximum}});
        } else if(const auto* unscored = std::get_if<BoxPlanUnscored>(&attempt)) {
            const auto& diagnostic = unscored->reason.diagnostics.front();
            plan_attempts.push_back({{"status","unsupported"}, {"action_indices",unscored->action_indices},
                {"field",diagnostic.field}, {"reason",diagnostic.explanation}});
        } else {
            const auto& stopped = std::get<BoxPlanStopped>(attempt);
            plan_attempts.push_back({{"status","stopped"}, {"action_indices",stopped.action_indices},
                {"reason",stopped.reason.diagnostics}});
        }
    }
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
            {"candidate_search_coverage","complete"}, {"selected_candidate_attempt_index",selection->candidate_attempt_index},
            {"selected_action_indices",selected.action_indices},
            {"selected_controls",selected_controls},
            {"terminal_box_maximum",selected.terminal_box_maximum},
            {"full_catalogue_replay_value",replay.worst_value},
            {"worst_disturbance_indices",replay.disturbance_indices},
            {"worst_disturbances",replay.disturbances},
            {"worst_case_path",replay.path}, {"stages",boxes},
            {"all_plan_scores",plan_scores}, {"plan_attempts",plan_attempts}}},
        {"zonotope_method",{{"status","numerical outer zonotope recurrence"},
            {"plan_source","same box-selected fixed open-loop plan"},
            {"relation","outer"}, {"max_generators_per_stage",64},
            {"stages",zonotope_stages_json(*zonotope_trace)}}},
        {"planar_example",{{"relation","outer"},
            {"dynamics","x_next = diag(2,1) * x"},
            {"initial_vertices",matrix_vertices(planar_request.initial)},
            {"exact_reachable_vertices",{{-2.0,-1.0},{2.0,-1.0},{2.0,1.0},{-2.0,1.0}}},
            {"stages",zonotope_stages_json(*planar_trace)}}},
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
