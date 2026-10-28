#include <csl/optimization/finite_action_minimax.hpp>
#include <nlohmann/json.hpp>

#include <array>
#include <chrono>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

namespace {
using namespace csl;
using namespace csl::optimization;
using Json = nlohmann::json;
constexpr std::size_t n = 10;
constexpr std::size_t state_n = n + 1;
constexpr double dt = 0.05;
constexpr std::size_t inner_n = 10;
constexpr std::size_t horizon = 3;
constexpr std::array<std::array<double, 2>, 5> u_catalogue{{
    {{0.0, 0.0}}, {{4.35, 0.0}}, {{-4.35, 0.0}}, {{0.0, 5.0}}, {{0.0, -5.0}}}};
constexpr std::array<std::array<double, 2>, 5> v_catalogue{{
    {{0.0, 0.0}}, {{0.66, 0.0}}, {{-0.66, 0.0}}, {{0.0, 1.0}}, {{0.0, -1.0}}}};

template<class T> T take(std::variant<T, Diagnostic> value) {
    if(const auto* error = std::get_if<Diagnostic>(&value))
        throw std::runtime_error(error->field + ": " + error->explanation);
    return std::get<T>(std::move(value));
}

using Mat10 = std::array<double, n * n>;
using Mat10x2 = std::array<double, n * 2>;

Mat10 identity() {
    Mat10 out{};
    for(std::size_t i = 0; i < n; ++i) out[i * n + i] = 1.0;
    return out;
}
Mat10 multiply(const Mat10& a, const Mat10& b) {
    Mat10 out{};
    for(std::size_t i = 0; i < n; ++i)
        for(std::size_t k = 0; k < n; ++k)
            for(std::size_t j = 0; j < n; ++j)
                out[i * n + j] += a[i * n + k] * b[k * n + j];
    return out;
}
Mat10x2 multiply(const Mat10& a, const Mat10x2& b) {
    Mat10x2 out{};
    for(std::size_t i = 0; i < n; ++i)
        for(std::size_t k = 0; k < n; ++k)
            for(std::size_t j = 0; j < 2; ++j)
                out[i * 2 + j] += a[i * n + k] * b[k * 2 + j];
    return out;
}

struct SourceStep { Mat10 A; Mat10x2 B; Mat10x2 C; };
SourceStep source_step() {
    Mat10 A{};
    A[0 * n + 1] = 1.0; A[1 * n + 2] = 1.0; A[2 * n + 2] = -1.0;
    A[3 * n + 4] = 1.0; A[4 * n + 5] = 1.0; A[5 * n + 5] = -1.0;
    A[6 * n + 7] = 1.0; A[8 * n + 9] = 1.0;
    Mat10x2 B{}; B[2 * 2] = 1.0; B[5 * 2 + 1] = 1.0;
    Mat10x2 C{}; C[7 * 2] = -1.0; C[9 * 2 + 1] = -1.0;
    Mat10 M = identity();
    for(std::size_t i = 0; i < M.size(); ++i) M[i] += (dt / inner_n) * A[i];
    Mat10 state = identity();
    Mat10x2 control{}, disturbance{};
    for(std::size_t step = 0; step < inner_n; ++step) {
        control = multiply(M, control);
        disturbance = multiply(M, disturbance);
        for(std::size_t i = 0; i < control.size(); ++i) {
            control[i] += (dt / inner_n) * B[i];
            disturbance[i] += (dt / inner_n) * C[i];
        }
        state = multiply(M, state);
    }
    return {state, control, disturbance};
}

sets::SetData vertices(std::string id, Matrix rows) {
    return take(sets::make_v({{std::move(id)}, rows.cols, {}},
        {take(numeric::snapshot(std::move(rows))),
         take(numeric::snapshot(Matrix{0, rows.cols, {}}))}));
}

FiniteActionMinimaxRequest request() {
    const auto step = source_step();
    std::vector<double> A(state_n * state_n, 0.0);
    std::vector<double> B(state_n * 2, 0.0), E(state_n * 2, 0.0);
    std::vector<double> offset(state_n, 0.0);
    A[0] = 1.0; offset[0] = dt;
    for(std::size_t i = 0; i < n; ++i) {
        for(std::size_t j = 0; j < n; ++j) A[(i + 1) * state_n + j + 1] = step.A[i * n + j];
        for(std::size_t j = 0; j < 2; ++j) {
            B[(i + 1) * 2 + j] = step.B[i * 2 + j];
            E[(i + 1) * 2 + j] = step.C[i * 2 + j];
        }
    }
    SystemModel authored{{{state_n, 2, 2}, TimeDomain::discrete,
        LinearStage{{state_n, state_n, std::move(A)}, {state_n, 2, std::move(B)},
            {state_n, 2, std::move(E)}, std::move(offset)}}, {}};
    Vector times{0.0, dt, 2.0 * dt, 3.0 * dt};
    const auto system = take(model::snapshot(authored, std::move(times)));

    std::vector<Vector> controls;
    std::vector<double> u_flat, v_flat;
    for(const auto& action : u_catalogue) {
        controls.push_back({action[0], action[1]});
        u_flat.push_back(action[0]); u_flat.push_back(action[1]);
    }
    for(const auto& action : v_catalogue) {
        v_flat.push_back(action[0]); v_flat.push_back(action[1]);
    }
    std::vector<sets::SetData> disturbances;
    for(std::size_t k = 0; k < horizon; ++k)
        disturbances.push_back(vertices("air-to-air-disturbances-" + std::to_string(k),
            Matrix{v_catalogue.size(), 2, v_flat}));
    std::vector<sets::SetData> admissible;
    for(std::size_t k = 0; k <= horizon; ++k)
        admissible.push_back(take(sets::make_universal(
            {{"air-to-air-unconstrained-" + std::to_string(k)}, state_n, {}})));

    Matrix L{2, state_n, std::vector<double>(2 * state_n, 0.0)};
    L.values[0 * state_n + 1] = 1.0;
    L.values[0 * state_n + 7] = -1.0;
    L.values[1 * state_n + 4] = 1.0;
    L.values[1 * state_n + 9] = -1.0;
    const auto objective = std::get<Objective>(snapshot(
        ResidualNormTerminal{std::move(L), {0.0, 0.0}}));
    const Vector initial{0.0, 0.0, 30.0, 0.0, 0.0, 80.0, 0.0,
        200.0, -70.0, 0.0, 80.0};
    return {{"env717-air-to-air-short-horizon-v1"}, {"env717-air-to-air"},
        system, vertices("air-to-air-initial", Matrix{1, state_n,
            std::vector<double>(initial.begin(), initial.end())}),
        {2, std::move(controls)},
        std::move(disturbances), std::move(admissible), objective};
}

Json result_record() {
    const auto input = request();
    constexpr double near_optimal_tolerance = 1e-10;
    Json u_actions = Json::array(), v_actions = Json::array();
    for(const auto& action : u_catalogue) u_actions.push_back(action);
    for(const auto& action : v_catalogue) v_actions.push_back(action);
    const auto start = std::chrono::steady_clock::now();
    const auto outcome = finite_action_minimax(input, {125, 125, near_optimal_tolerance});
    const auto stop = std::chrono::steady_clock::now();
    const auto* result = std::get_if<FiniteMinimaxOptimal>(&outcome);
    if(!result) throw std::runtime_error("finite-action minimax did not return an optimum");
    if(result->plans.size() != 125 || result->minimizing_plan_indices.empty())
        throw std::runtime_error("unexpected controller action-plan enumeration");
    Json plans = Json::array();
    for(std::size_t i = 0; i < result->plans.size(); ++i) {
        const auto* plan = std::get_if<FinitePlanFeasible>(&result->plans[i]);
        if(!plan || plan->action_indices.size() != horizon)
            throw std::runtime_error("unconstrained game rejected or malformed a plan");
        Json actions = Json::array();
        for(const auto index : plan->action_indices) {
            if(index >= u_catalogue.size()) throw std::runtime_error("invalid action index");
            actions.push_back(u_catalogue[index]);
        }
        plans.push_back({{"plan_index", i}, {"control_indices", plan->action_indices},
            {"controls", actions}, {"worst_terminal_range", plan->worst_value},
            {"maximizing_terminal_state", plan->maximizer}});
    }
    Json minimizing = Json::array();
    for(const auto i : result->minimizing_plan_indices) minimizing.push_back(i);
    return {{"schema", "csl.env717-air-to-air-pilot/1"},
        {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"source_file_blob", "9054c9fcd01e49f3dbfd8b8ee8d12e7365e1d9b5"},
        {"source_license", "no license declared in repository metadata"},
        {"source_model", {{"state_order", {"time", "interceptor_x", "interceptor_vx",
            "interceptor_ax", "interceptor_y", "interceptor_vy", "interceptor_ay",
            "target_x", "target_vx", "target_y", "target_vy"}},
            {"initial_state", {0.0, 0.0, 30.0, 0.0, 0.0, 80.0, 0.0, 200.0, -70.0, 0.0, 80.0}},
            {"terminal_time_seconds", 2.0}, {"dt_seconds", dt}, {"inner_euler_steps", inner_n},
            {"u_action_radii", {4.35, 5.0}}, {"v_action_radii", {0.66, 1.0}},
            {"reward", "Euclidean terminal relative position"}}},
        {"adaptation", {{"horizon_steps", horizon}, {"terminal_time_seconds", horizon * dt},
            {"u_catalogue", u_actions}, {"v_catalogue", v_actions},
            {"information_pattern", "open-loop three-action control plan against a full disturbance sequence"},
            {"objective", "minimize the worst terminal Euclidean separation over the finite disturbance catalogue"}}},
        {"horizon", horizon}, {"controller_plan_count", plans.size()},
        {"disturbance_sequence_count_per_plan", 125}, {"objective_value", result->value},
        {"near_optimal_tolerance", near_optimal_tolerance},
        {"minimizing_plan_indices", minimizing}, {"plans", plans},
        {"timing", {{"warmup_calls", 0}, {"measured_calls", 1},
            {"measured_wall_ns", {std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count()}},
            {"scope", "one finite_action_minimax call; request construction and JSON assembly excluded"},
            {"comparison_claim", false}, {"worker_threads_requested", 1},
            {"worker_threads_actual", 1}, {"native_threads_requested", 1},
            {"native_threads_actual", 1}, {"workspace_reuse", "none"},
            {"cache_state", "cold process; no prior solver call"}}},
        {"driver_sha256", CSL_ENV717_AIR_DRIVER_SHA256},
        {"algorithm_source_sha256", CSL_ENV717_ALGORITHM_SOURCE_SHA256},
        {"source_commit", CSL_ENV717_SOURCE_COMMIT},
        {"capture_environment", {{"compiler", CSL_ENV717_COMPILER_ID},
            {"compiler_version", CSL_ENV717_COMPILER_VERSION}, {"build_type", CSL_ENV717_BUILD_TYPE},
            {"architecture", CSL_ENV717_ARCHITECTURE}}}};
}
}

int main() {
    try { std::cout << result_record().dump(2) << '\n'; return 0; }
    catch(const std::exception& error) {
        std::cerr << "ENV-717 AirToAirInterception pilot failed: " << error.what() << '\n';
        return 1;
    }
}
