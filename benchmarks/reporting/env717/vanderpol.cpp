#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
using Json = nlohmann::json;
using State = std::array<double, 3>;
using Plan = std::array<std::size_t, 5>;

constexpr std::array<double, 3> actions{-1.0, 0.0, 1.0};
constexpr std::size_t stages = 5;
constexpr std::size_t outer_steps_per_stage = 22;
constexpr std::size_t inner_steps = 10;
constexpr double dt = 0.1;
constexpr double inner_dt = dt / static_cast<double>(inner_steps);
constexpr double terminal_time = 11.0;

State advance(State state, double control) {
    for (std::size_t step = 0; step < inner_steps; ++step) {
        const double time_rate = 1.0;
        const double position_rate = state[2];
        const double velocity_rate = (1.0 - state[1] * state[1]) * state[2] - state[1] + control;
        state[0] += time_rate * inner_dt;
        state[1] += position_rate * inner_dt;
        state[2] += velocity_rate * inner_dt;
    }
    return state;
}

struct Candidate {
    Plan indices;
    State terminal;
    std::array<State, stages> stage_states;
    std::vector<State> trajectory;
    double running_cost;
    double terminal_cost;
    double objective;
};

Candidate evaluate(Plan plan) {
    Candidate result{plan, {0.0, 1.0, 0.0}, {}, {{0.0, 1.0, 0.0}}, 0.0, 0.0, 0.0};
    for (std::size_t stage = 0; stage < stages; ++stage) {
        const double control = actions[plan[stage]];
        for (std::size_t step = 0; step < outer_steps_per_stage; ++step) {
            result.terminal = advance(result.terminal, control);
            result.trajectory.push_back(result.terminal);
            const std::size_t completed_steps = stage * outer_steps_per_stage + step + 1;
            if (completed_steps < stages * outer_steps_per_stage)
                result.running_cost += 0.05 * control * control * dt;
        }
        result.stage_states[stage] = result.terminal;
    }
    result.terminal_cost = result.terminal[1] * result.terminal[1] + result.terminal[2] * result.terminal[2];
    result.objective = result.running_cost + result.terminal_cost;
    return result;
}

Json state_json(const State& state) { return {state[0], state[1], state[2]}; }

Json make_result(const std::vector<Candidate>& candidates) {
    double minimum = INFINITY;
    for (const auto& candidate : candidates) minimum = std::min(minimum, candidate.objective);
    Json plans = Json::array();
    Json minimizers = Json::array();
    for (std::size_t row = 0; row < candidates.size(); ++row) {
        const auto& candidate = candidates[row];
        Json controls = Json::array();
        Json stages_json = Json::array();
        Json trajectory_json = Json::array();
        for (const auto index : candidate.indices) controls.push_back(actions[index]);
        for (const auto& state : candidate.stage_states) stages_json.push_back(state_json(state));
        for (const auto& state : candidate.trajectory) trajectory_json.push_back(state_json(state));
        plans.push_back({{"plan_index", row}, {"control_indices", candidate.indices},
            {"controls", controls}, {"stage_states", stages_json},
            {"trajectory", trajectory_json}, {"running_cost", candidate.running_cost},
            {"terminal_cost", candidate.terminal_cost}, {"objective", candidate.objective}});
        if (std::abs(candidate.objective - minimum) <= 1e-12) minimizers.push_back(row);
    }
    return {{"schema", "csl.env717-vanderpol/1"},
        {"scenario_id", "env717-vanderpol-equation-replay-finite-catalogue-v1"},
        {"reference_variant", "equation-replayed finite-action reference; not direct execution of the upstream class"},
        {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"source_file", "Environments/VanDerPol/VanDerPol.py"},
        {"source_file_blob", "4380ec05c9d100d8b4c1cf0b931a111bc5d419db"},
        {"source_notebook", "Environments/VanDerPol/VanDerPol.ipynb"},
        {"source_notebook_blob", "c1295c110edf68003f93991e531b072af13e5c8f"},
        {"source_license", "no license declared in upstream repository metadata"},
        {"source_execution_status", "step() raises NameError after state mutation because its return tuple references undefined _"},
        {"assumptions", {"the recorded derivative and reward equations define the intended transition despite the source return error",
            "one control from {-1,0,1} is held for 22 source steps in each of five report-level macro stages",
            "the final source step uses terminal cost instead of the nonterminal running penalty"}},
        {"state_order", {"time", "position", "velocity"}},
        {"source_parameters", {{"initial_state", {0.0, 1.0, 0.0}},
            {"terminal_time_seconds", terminal_time}, {"outer_step_seconds", dt},
            {"inner_euler_steps_per_outer_step", inner_steps}, {"inner_euler_step_seconds", inner_dt},
            {"control_bounds", {-1.0, 1.0}},
            {"dynamics", "time'=1; position'=velocity; velocity'=(1-position^2)*velocity-position+u"},
            {"running_cost", "0.05*u^2*dt for each nonterminal source step"},
            {"terminal_cost", "position^2+velocity^2"},
            {"source_execution_note", "upstream step mutates state then raises NameError because return value _ is undefined; this pilot independently re-expresses the recorded equations"}}},
        {"adaptation", {{"macro_stages", stages},
            {"source_steps_per_macro_stage", outer_steps_per_stage},
            {"total_source_steps", stages * outer_steps_per_stage},
            {"finite_control_catalogue", actions}, {"plan_count", candidates.size()},
            {"semantics", "one open-loop control selected per 2.2-second macro stage; all finite plans are enumerated"},
            {"claim_boundary", "minimum of this finite open-loop catalogue only; not the continuous-action optimum"}}},
        {"objective_value", minimum}, {"minimizing_plan_indices", minimizers},
        {"driver_sha256", CSL_ENV717_VANDERPOL_DRIVER_SHA256},
        {"source_commit", CSL_ENV717_VANDERPOL_SOURCE_COMMIT},
        {"capture_environment", {{"compiler", CSL_ENV717_VANDERPOL_COMPILER_ID},
            {"compiler_version", CSL_ENV717_VANDERPOL_COMPILER_VERSION},
            {"build_type", CSL_ENV717_VANDERPOL_BUILD_TYPE},
            {"architecture", CSL_ENV717_VANDERPOL_ARCHITECTURE}}},
        {"plans", plans}};
}
}

int main() {
    try {
        std::vector<Candidate> candidates;
        candidates.reserve(actions.size() * actions.size() * actions.size() * actions.size() * actions.size());
        for (std::size_t a = 0; a < actions.size(); ++a)
            for (std::size_t b = 0; b < actions.size(); ++b)
                for (std::size_t c = 0; c < actions.size(); ++c)
                    for (std::size_t d = 0; d < actions.size(); ++d)
                        for (std::size_t e = 0; e < actions.size(); ++e)
                            candidates.push_back(evaluate({a, b, c, d, e}));
        std::cout << make_result(candidates).dump(2) << '\n';
    } catch (const std::exception& error) {
        std::cerr << "Van der Pol pilot failed: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
