#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using Json = nlohmann::json;
using State = std::array<double, 4>;
using Plan = std::array<std::size_t, 3>;

constexpr std::array<double, 5> action_catalogue{-0.5, -0.125, 0.25, 0.625, 1.0};
constexpr std::size_t macro_stages = 3;
constexpr std::size_t outer_steps_per_stage = 21;
constexpr std::size_t inner_steps = 20;
constexpr double dt = 0.1;
constexpr double inner_dt = dt / static_cast<double>(inner_steps);
constexpr double terminal_time = 2.0 * 3.141592653589793238462643383279502884;
constexpr std::array<double, 3> target{4.0, 0.0,
    0.75 * 3.141592653589793238462643383279502884};

State source_step(State state, double control) {
    for(std::size_t inner = 0; inner < inner_steps; ++inner) {
        state[1] += std::cos(state[3]) * inner_dt;
        state[2] += std::sin(state[3]) * inner_dt;
        state[3] += control * inner_dt;
        state[0] += inner_dt;
    }
    return state;
}

double terminal_loss(const State& state) {
    const auto dx = state[1] - target[0];
    const auto dy = state[2] - target[1];
    const auto dtheta = state[3] - target[2];
    return dx * dx + dy * dy + dtheta * dtheta;
}

struct Candidate {
    Plan indices;
    State state;
    std::array<State, macro_stages> stage_states;
    double loss;
};

Candidate evaluate(Plan plan) {
    Candidate result{plan, {0.0, 0.0, 0.0, 0.0}, {}, 0.0};
    for(std::size_t stage = 0; stage < macro_stages; ++stage) {
        for(std::size_t step = 0; step < outer_steps_per_stage; ++step)
            result.state = source_step(result.state, action_catalogue[plan[stage]]);
        result.stage_states[stage] = result.state;
    }
    result.loss = terminal_loss(result.state);
    return result;
}

Json state_json(const State& state) {
    return {state[0], state[1], state[2], state[3]};
}

Json result_record(const std::vector<Candidate>& candidates) {
    double minimum = INFINITY;
    for(const auto& candidate : candidates) minimum = std::min(minimum, candidate.loss);
    Json plans = Json::array();
    Json minimizers = Json::array();
    for(std::size_t row = 0; row < candidates.size(); ++row) {
        const auto& candidate = candidates[row];
        Json controls = Json::array();
        Json stages = Json::array();
        for(const auto index : candidate.indices) controls.push_back(action_catalogue[index]);
        for(const auto& stage_state : candidate.stage_states) stages.push_back(state_json(stage_state));
        plans.push_back({{"plan_index", row}, {"control_indices", candidate.indices},
            {"controls", std::move(controls)}, {"stage_states", std::move(stages)},
            {"terminal_state", state_json(candidate.state)}, {"terminal_loss", candidate.loss}});
        if(std::abs(candidate.loss - minimum) <= 1e-12) minimizers.push_back(row);
    }
    return {{"schema", "csl.env717-dubins-car/1"},
        {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"source_file", "Environments/DubinsCar/DubinsCar_Terminal.py"},
        {"source_file_blob", "98c7cda22d81248a25e22374e144ce8d605c45c2"},
        {"source_license", "no license declared in upstream repository metadata"},
        {"state_order", {"time", "x", "y", "heading"}},
        {"source_parameters", {{"initial_state", {0.0, 0.0, 0.0, 0.0}},
            {"terminal_time_seconds", terminal_time}, {"dt_seconds", dt},
            {"inner_euler_steps_per_source_action", inner_steps},
            {"inner_euler_step_seconds", inner_dt}, {"action_bounds", {-0.5, 1.0}},
            {"target", target}, {"terminal_loss", "(x-4)^2+y^2+(heading-3*pi/4)^2"},
            {"source_update", "20 explicit-Euler steps of x'=cos(heading), y'=sin(heading), heading'=u"}}},
        {"adaptation", {{"macro_stages", macro_stages},
            {"source_action_steps_per_macro_stage", outer_steps_per_stage},
            {"source_action_steps_total", macro_stages * outer_steps_per_stage},
            {"finite_control_catalogue", action_catalogue},
            {"plan_count", candidates.size()},
            {"semantics", "one open-loop control chosen per macro stage and held for 21 source action steps; all 125 finite plans are enumerated"},
            {"claim_boundary", "exact minimizer of this finite catalogue only; not the continuous-action source problem"}}},
        {"objective_value", minimum}, {"minimizing_plan_indices", minimizers},
        {"driver_sha256", CSL_ENV717_DUBINS_DRIVER_SHA256},
        {"source_commit", CSL_ENV717_DUBINS_SOURCE_COMMIT},
        {"capture_environment", {{"compiler", CSL_ENV717_DUBINS_COMPILER_ID},
            {"compiler_version", CSL_ENV717_DUBINS_COMPILER_VERSION},
            {"build_type", CSL_ENV717_DUBINS_BUILD_TYPE},
            {"architecture", CSL_ENV717_DUBINS_ARCHITECTURE}}},
        {"plans", std::move(plans)}};
}
}

int main() {
    try {
        std::vector<Candidate> candidates;
        candidates.reserve(action_catalogue.size() * action_catalogue.size() * action_catalogue.size());
        for(std::size_t first = 0; first < action_catalogue.size(); ++first)
            for(std::size_t second = 0; second < action_catalogue.size(); ++second)
                for(std::size_t third = 0; third < action_catalogue.size(); ++third)
                    candidates.push_back(evaluate({first, second, third}));
        std::cout << result_record(candidates).dump(2) << '\n';
    } catch(const std::exception& error) {
        std::cerr << "DubinsCar pilot failed: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
