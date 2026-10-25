#include <csl/optimization/finite_action_minimax.hpp>
#include <nlohmann/json.hpp>

#include <array>
#include <chrono>
#include <cmath>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>
#include <variant>
#if defined(__linux__)
#include <sys/resource.h>
#endif

namespace {
using namespace csl;
using namespace csl::optimization;
using nlohmann::json;

template<class T> T take(std::variant<T, Diagnostic> result) {
    if (const auto* error = std::get_if<Diagnostic>(&result))
        throw std::runtime_error(error->field + ": " + error->explanation);
    return std::get<T>(std::move(result));
}

constexpr double K = 2.5;
constexpr double P = 30240.0;
constexpr double I = 360.0;
constexpr double c1 = 0.1;
constexpr double c2 = -6700.0;
constexpr double c3 = 900.0;
constexpr double c4 = -15.0;
constexpr double c5 = -12.0;
constexpr double t1 = 300.0;
constexpr double horizon = 4.0;
constexpr double dK = -0.03 * K;
const Vector choices{1,0.75,0.5,0.25,0,-0.25,-0.5,-0.75,-1};

Vector initial_state() {
    const double Km = K + dK;
    const double delta = Km - K;
    const double Pp = P + c2 * delta * delta + c3 * delta;
    const double Iu = I + c4 * delta * delta + c5 * delta;
    const double fuel_flow = Pp / Iu / (1.0 + Km);
    return {fuel_flow * Km, 18100.0, fuel_flow, 7150.0};
}

Vector input_column() {
    const double b1 = c1 * P / I / (1.0 + K) + c1 * c3 * K / I / (1.0 + K)
        - c1 * P * K / I / std::pow(1.0 + K, 2)
        - c1 * c5 * P * K / std::pow(I, 2) / (1.0 + K);
    const double b3 = -(c1 * P / I / std::pow(1.0 + K, 2)
        + c1 * c5 * P / std::pow(I, 2) / (1.0 + K)
        - c1 * c3 / I / (1.0 + K));
    return {b1, 0.0, b3, 0.0};
}

FiniteActionMinimaxRequest request(double lambda, const Vector& start, std::size_t stages) {
    Vector times;
    for (std::size_t stage=0; stage<=stages; ++stage) times.push_back(75.0*static_cast<double>(stage));
    const SystemModel authored{{{4, 1, 2}, TimeDomain::discrete,
        LinearStage{
            {4, 4, {1,0,0,0,-75,1,0,0,0,0,1,0,0,0,-75,1}},
            {4, 1, input_column()},
            {4, 2, {0.06,0,0,0,0,-0.06,0,0}},
            {0, 0, 0, 0}}}, {}};
    const auto system = take(model::snapshot(authored, times));
    const auto initial = take(sets::make_singleton({{"b09-a08-x0"}, 4,
        {"oxidizer_flow", "oxidizer_stock", "fuel_flow", "fuel_stock"}},
        take(numeric::snapshot_vector(start))));
    const auto disturbance = take(sets::make_v({{"b09-a08-disturbance"}, 2, {"w1", "w2"}},
        {take(numeric::snapshot(Matrix{4,2,{-1,-1,-1,1,1,-1,1,1}})),
         take(numeric::snapshot(Matrix{0,2,{}}))}));
    const Matrix normals{8,4,{1,0,0,0,-1,0,0,0,0,1,0,0,0,-1,0,0,
                              0,0,1,0,0,0,-1,0,0,0,0,1,0,0,0,-1}};
    const auto safe = take(sets::make_h({{"b09-a08-state-constraints"}, 4,
        {"oxidizer_flow", "oxidizer_stock", "fuel_flow", "fuel_stock"}},
        {take(numeric::snapshot(normals)),
         take(numeric::snapshot_vector(Vector{62.5,-57.5,20000,30,25,-23,8000,30})),
         take(numeric::snapshot(Matrix{0,4,{}})),
         take(numeric::snapshot_vector(Vector{}))}));
    std::vector<sets::SetData> disturbances(stages, disturbance);
    std::vector<sets::SetData> safe_sets(stages+1, safe);
    const Matrix Q{4,4,{2,0,0,0,0,2*(1+lambda),0,-5*lambda,
                        0,0,2,0,0,-5*lambda,0,2*(1+6.25*lambda)}};
    const auto objective = std::get<Objective>(snapshot(
        QuadraticTerminal{Q, {-120,0,-48,0}, 4176.0}));
    std::vector<Vector> catalogue;
    for (double value : choices) catalogue.push_back({value});
    return {{"b09-a08-source-revision-reference-v1"}, {"b09-a08-lambda-" + std::to_string(static_cast<int>(lambda))},
        system, initial, {1, std::move(catalogue)}, std::move(disturbances),
        std::move(safe_sets), objective};
}

Vector nonlinear_step(const Vector& state, double accumulated_control) {
    const double Km = K + dK + c1 * accumulated_control;
    const double delta = Km - K;
    const double Pp = P + c2 * delta * delta + c3 * delta;
    const double Iu = I + c4 * delta * delta + c5 * delta;
    const double fuel = Pp / Iu / (1.0 + Km);
    return {fuel * Km, state[1] - 75.0 * state[0], fuel, state[3] - 75.0 * state[2]};
}

std::vector<Vector> open_loop_replay(const std::vector<std::size_t>& action_indices) {
    Vector state = initial_state();
    double accumulated_control = 0.0;
    std::vector<Vector> states{state};
    for (const auto action_index : action_indices) {
        accumulated_control += choices.at(action_index);
        state = nonlinear_step(state,accumulated_control);
        states.push_back(state);
    }
    return states;
}

double criterion_squared(const Vector& state, double lambda) {
    const double sync = state[1] - 2.5 * state[3];
    return std::pow(state[0]-60.0,2) + std::pow(state[1],2) +
        std::pow(state[2]-24.0,2) + std::pow(state[3],2) + lambda*sync*sync;
}

std::pair<std::vector<std::size_t>,std::vector<Vector>> closed_loop_replay(double lambda) {
    Vector state = initial_state();
    double accumulated_control = 0.0;
    std::vector<std::size_t> actions;
    std::vector<Vector> states{state};
    for (std::size_t stage=0; stage<4; ++stage) {
        const auto outcome = finite_action_minimax(request(lambda,state,4-stage),
                                                   {static_cast<std::size_t>(std::pow(9.0,4-stage)),4096,1e-8});
        if (!std::holds_alternative<FiniteMinimaxOptimal>(outcome))
            throw std::runtime_error("A08 receding-horizon planner did not return an optimum");
        const auto& optimum = std::get<FiniteMinimaxOptimal>(outcome);
        if (optimum.minimizing_plan_indices.empty())
            throw std::runtime_error("A08 receding-horizon planner has no minimizing plan");
        const auto& plan = std::get<FinitePlanFeasible>(optimum.plans.at(optimum.minimizing_plan_indices.front()));
        const auto action_index = plan.action_indices.front();
        actions.push_back(action_index);
        accumulated_control += choices.at(action_index);
        state = nonlinear_step(state,accumulated_control);
        states.push_back(state);
    }
    return {actions,states};
}

json vertices(const sets::SetData& set) {
    const auto rep = set.representation();
    const auto* v = std::get_if<sets::VRepresentation>(&rep);
    if (!v || v->rays.rows() != 0) throw std::runtime_error("terminal result is not a bounded V set");
    json result = json::array();
    for (std::size_t row = 0; row < v->vertices.rows(); ++row) {
        json point = json::array();
        for (std::size_t column = 0; column < v->vertices.cols(); ++column)
            point.push_back(v->vertices(row, column));
        result.push_back(std::move(point));
    }
    return result;
}

std::size_t distinct_point_count(const json& points) {
    std::set<std::array<double, 4>> unique;
    for (const auto& point : points) {
        if (point.size() != 4) throw std::runtime_error("terminal point dimension mismatch");
        std::array<double, 4> value{};
        for (std::size_t i = 0; i < value.size(); ++i) value[i] = point.at(i).get<double>();
        unique.insert(value);
    }
    return unique.size();
}

json run(std::size_t batch, double lambda, bool geometry) {
    const auto started = std::chrono::steady_clock::now();
    const auto outcome = finite_action_minimax(request(lambda,initial_state(),4), {6561, 4096, 1e-8});
    const auto stopped = std::chrono::steady_clock::now();
    if (!std::holds_alternative<FiniteMinimaxOptimal>(outcome))
        throw std::runtime_error("A08 source-reference planner did not return an optimum");
    const auto& optimum = std::get<FiniteMinimaxOptimal>(outcome);
    if (optimum.plans.size() != 6561 || optimum.minimizing_plan_indices.empty())
        throw std::runtime_error("A08 plan catalogue count mismatch");
    const auto winner_index = optimum.minimizing_plan_indices.front();
    const auto& winner = std::get<FinitePlanFeasible>(optimum.plans.at(winner_index));
    json winner_sequences = json::array();
    for (const auto index : optimum.minimizing_plan_indices) {
        const auto* plan = std::get_if<FinitePlanFeasible>(&optimum.plans.at(index));
        if (!plan) throw std::runtime_error("a minimizing plan was rejected");
        winner_sequences.push_back(plan->action_indices);
    }
    json row = {{"schema", "csl.issue6-b09-a08-run/1"}, {"batch", batch},
        {"source_commit", CSL_ISSUE6_SOURCE_COMMIT},
        {"scenario_sha256", CSL_ISSUE6_FIXTURE_SHA256},
        {"driver_sha256", CSL_ISSUE6_DRIVER_SHA256},
        {"lambda", lambda}, {"status", "numerical_optimal"}, {"assurance", "numerical"},
        {"elapsed_ns", std::chrono::duration_cast<std::chrono::nanoseconds>(stopped-started).count()},
        {"plan_count", optimum.plans.size()}, {"minimizing_plan_indices", optimum.minimizing_plan_indices},
        {"winner_action_indices", winner.action_indices}, {"winner_action_sequences", winner_sequences},
        {"objective_squared", optimum.value},
        {"objective_norm", std::sqrt(optimum.value)}, {"winner_maximizer", winner.maximizer}};
#if defined(__linux__)
    rusage usage{};
    if (getrusage(RUSAGE_SELF, &usage) == 0) row["process_peak_rss_kib"] = usage.ru_maxrss;
    else row["process_peak_rss_kib"] = nullptr;
#else
    row["process_peak_rss_kib"] = nullptr;
#endif
    if (geometry) {
        const auto open_states = open_loop_replay(winner.action_indices);
        const auto [closed_actions,closed_states] = closed_loop_replay(lambda);
        const auto terminal = vertices(winner.terminal);
        row["winner_terminal_vertices_x1_x2_x3_x4"] = terminal;
        row["terminal_v_row_count"] = terminal.size();
        row["terminal_unique_point_count"] = distinct_point_count(terminal);
        row["open_loop_replay_states"] = open_states;
        row["open_loop_replay_terminal_state"] = open_states.back();
        row["open_loop_replay_objective_squared"] = criterion_squared(open_states.back(),lambda);
        row["open_loop_replay_objective_norm"] = std::sqrt(row["open_loop_replay_objective_squared"].get<double>());
        row["closed_loop_action_indices"] = closed_actions;
        row["closed_loop_replay_states"] = closed_states;
        row["closed_loop_replay_terminal_state"] = closed_states.back();
        row["closed_loop_replay_objective_squared"] = criterion_squared(closed_states.back(),lambda);
        row["closed_loop_replay_objective_norm"] = std::sqrt(row["closed_loop_replay_objective_squared"].get<double>());
    }
    return row;
}
}

int main(int argc, char** argv) {
    try {
        double lambda = 1.0;
        std::size_t measured = 0;
        bool geometry = false;
        for (int i=1; i<argc; ++i) {
            const std::string_view arg{argv[i]};
            if (arg == "--lambda" && i+1 < argc) lambda = std::stod(argv[++i]);
            else if (arg == "--measure" && i+1 < argc) measured = std::stoul(argv[++i]);
            else if (arg == "--geometry") geometry = true;
            else throw std::runtime_error("usage: csl_issue6_b09_report [--lambda 0|1] [--measure N] [--geometry]");
        }
        if ((lambda != 0.0 && lambda != 1.0) || measured > 25 || (geometry && measured != 0))
            throw std::runtime_error("lambda must be 0 or 1; measurements 0..25; geometry cannot be measured");
        if (geometry) std::cout << run(0, lambda, true).dump() << '\n';
        else for (std::size_t batch=0; batch<=measured; ++batch)
            std::cout << run(batch, lambda, false).dump() << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "B09 run rejected: " << error.what() << '\n';
        return 2;
    }
}
