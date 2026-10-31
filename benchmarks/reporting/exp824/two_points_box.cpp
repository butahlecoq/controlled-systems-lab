#include <csl/optimization/finite_action_box_minimax.hpp>
#include <csl/optimization/finite_action_minimax.hpp>
#include <nlohmann/json.hpp>

#include <array>
#include <iostream>
#include <stdexcept>

namespace {
using namespace csl;
using namespace csl::optimization;
using Json = nlohmann::json;

template<class T> T take(std::variant<T, Diagnostic> value) {
    if(const auto* error = std::get_if<Diagnostic>(&value))
        throw std::runtime_error(error->field + ": " + error->explanation);
    return std::get<T>(std::move(value));
}

sets::SetData vertices(std::string id, std::size_t dimension, Matrix points) {
    return take(sets::make_v({{std::move(id)}, dimension, {}},
        {take(numeric::snapshot(std::move(points))),
         take(numeric::snapshot(Matrix{0,dimension,{}}))}));
}

FiniteActionMinimaxRequest request() {
    constexpr std::size_t horizon = 3;
    const SystemModel source_model{{{4,1,1}, TimeDomain::discrete,
        LinearStage{{4,4,{1.0,0.01,0.0,0.0, 0.0,0.0,0.0,0.0,
                          0.0,0.0,1.0,0.1, 0.0,0.0,0.0,1.0}},
                    {4,1,{0.09,1.0,0.0,0.0}}, {4,1,{0.0,0.0,0.0045,0.1}},
                    {0.0,0.0,0.0,0.0}}}, {}};
    const auto system = take(model::snapshot(source_model, Vector{0.0,0.1,0.2,0.3}));
    std::vector<sets::SetData> disturbances(horizon,
        vertices("disturbances", 1, Matrix{3,1,{-1.0,0.0,1.0}}));
    std::vector<sets::SetData> safe;
    for(std::size_t stage = 0; stage <= horizon; ++stage)
        safe.push_back(take(sets::make_universal({{"unconstrained-" + std::to_string(stage)},4,{}})));
    const auto objective = std::get<Objective>(snapshot(QuadraticTerminal{
        {4,4,{2.0,0.0,-2.0,0.0, 0.0,0.0,0.0,0.0,
              -2.0,0.0,2.0,0.0, 0.0,0.0,0.0,0.0}}, {0.0,0.0,0.0,0.0}, 0.0}));
    return {{"env717-two-points-short-horizon-v1"}, {"issue824-two-points-box-v1"}, system,
        vertices("initial", 4, Matrix{1,4,{4.5,0.0,0.0,0.0}}),
        {1,{{-2.5},{0.0},{2.5}}}, std::move(disturbances), std::move(safe), objective};
}

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
    const auto input = request();
    const auto approximate = finite_action_box_minimax(input, {27,27,27,16});
    const auto* selected = std::get_if<FiniteActionBoxMinimaxResult>(&approximate);
    if(!selected) throw std::runtime_error("box minimax did not complete successfully");
    const auto exact = finite_action_minimax(input, {27,27,0.0});
    const auto* reference = std::get_if<FiniteMinimaxOptimal>(&exact);
    if(!reference) throw std::runtime_error("exact finite minimax did not complete successfully");

    Json selected_controls = Json::array();
    constexpr std::array<double,3> actions{-2.5,0.0,2.5};
    for(const auto index : selected->selected_action_indices) selected_controls.push_back(actions.at(index));
    Json boxes = Json::array();
    for(const auto& stage : selected->selected_box_trace.stages)
        boxes.push_back({{"lower",stage.lower},{"upper",stage.upper}});
    Json plan_scores = Json::array();
    for(const auto& plan : selected->plan_scores)
        plan_scores.push_back({{"action_indices",plan.action_indices},
            {"terminal_box_maximum",plan.terminal_box_maximum}});
    const auto exact_plan_index = reference->minimizing_plan_indices.front();
    const auto& exact_plan = std::get<FinitePlanFeasible>(reference->plans[exact_plan_index]);
    return {{"schema","csl.issue824-two-points-box-minimax/1"},
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
