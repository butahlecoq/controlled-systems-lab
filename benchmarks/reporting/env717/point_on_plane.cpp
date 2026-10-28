#include <csl/optimization/finite_action_minimax.hpp>
#include <nlohmann/json.hpp>

#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <variant>
#include <vector>

namespace {
using namespace csl;
using namespace csl::optimization;
using Json = nlohmann::json;
constexpr std::size_t state_n = 4;
constexpr std::size_t input_n = 2;
constexpr std::size_t horizon = 3;
constexpr std::size_t inner_steps = 10;
constexpr double dt = 0.05;
constexpr double inner_dt = dt / static_cast<double>(inner_steps);
constexpr double u_radius[]{6.0, 2.0};
constexpr double v_radius[]{2.0, 4.0};
constexpr std::array<std::array<double, 2>, 5> u_catalogue{{
    {{0.0, 0.0}}, {{6.0, 0.0}}, {{-6.0, 0.0}}, {{0.0, 2.0}}, {{0.0, -2.0}}}};
constexpr std::array<std::array<double, 2>, 5> v_catalogue{{
    {{0.0, 0.0}}, {{2.0, 0.0}}, {{-2.0, 0.0}}, {{0.0, 4.0}}, {{0.0, -4.0}}}};

template<class T> T take(std::variant<T, Diagnostic> value) {
    if(const auto* error = std::get_if<Diagnostic>(&value))
        throw std::runtime_error(error->field + ": " + error->explanation);
    return std::get<T>(std::move(value));
}

using Mat4 = std::array<double, state_n * state_n>;
using Mat4x2 = std::array<double, state_n * input_n>;
struct StageMap { Mat4 A; Mat4x2 B, E; };

Mat4 identity() {
    Mat4 result{};
    for(std::size_t i = 0; i < state_n; ++i) result[i * state_n + i] = 1.0;
    return result;
}
Mat4 multiply(const Mat4& left, const Mat4& right) {
    Mat4 result{};
    for(std::size_t i = 0; i < state_n; ++i)
        for(std::size_t k = 0; k < state_n; ++k)
            for(std::size_t j = 0; j < state_n; ++j)
                result[i * state_n + j] += left[i * state_n + k] * right[k * state_n + j];
    return result;
}
Mat4x2 multiply(const Mat4& left, const Mat4x2& right) {
    Mat4x2 result{};
    for(std::size_t i = 0; i < state_n; ++i)
        for(std::size_t k = 0; k < state_n; ++k)
            for(std::size_t j = 0; j < input_n; ++j)
                result[i * input_n + j] += left[i * state_n + k] * right[k * input_n + j];
    return result;
}

StageMap source_euler_stage(double& time) {
    Mat4 A = identity();
    Mat4x2 B{}, E{};
    for(std::size_t inner = 0; inner < inner_steps; ++inner) {
        const double scale = std::exp(time / 5.0);
        Mat4 dynamics{};
        dynamics[0 * state_n + 2] = 1.0;
        dynamics[1 * state_n + 3] = 1.0;
        dynamics[2 * state_n + 0] = -4.0 * scale;
        dynamics[2 * state_n + 2] = -0.1 * scale;
        dynamics[3 * state_n + 1] = -4.0 * scale;
        dynamics[3 * state_n + 3] = -0.1 * scale;
        Mat4 step = identity();
        for(std::size_t i = 0; i < step.size(); ++i) step[i] += inner_dt * dynamics[i];
        Mat4x2 control{}, disturbance{};
        control[2 * input_n] = -8.0;
        control[3 * input_n + 1] = -8.0;
        disturbance[2 * input_n] = 2.4 * scale;
        disturbance[3 * input_n + 1] = 2.4 * scale;
        B = multiply(step, B);
        E = multiply(step, E);
        for(std::size_t i = 0; i < B.size(); ++i) {
            B[i] += inner_dt * control[i];
            E[i] += inner_dt * disturbance[i];
        }
        A = multiply(step, A);
        time += inner_dt;
    }
    return {A, B, E};
}

sets::SetData vertices(std::string id, Matrix rows) {
    const auto dimension = rows.cols;
    return take(sets::make_v({{std::move(id)}, dimension, {}},
        {take(numeric::snapshot(std::move(rows))),
         take(numeric::snapshot(Matrix{0, dimension, {}}))}));
}

Json matrix_json(const Mat4& values) {
    Json rows = Json::array();
    for(std::size_t i = 0; i < state_n; ++i) {
        Json row = Json::array();
        for(std::size_t j = 0; j < state_n; ++j) row.push_back(values[i * state_n + j]);
        rows.push_back(std::move(row));
    }
    return rows;
}
Json input_matrix_json(const Mat4x2& values) {
    Json rows = Json::array();
    for(std::size_t i = 0; i < state_n; ++i) {
        Json row = Json::array();
        for(std::size_t j = 0; j < input_n; ++j) row.push_back(values[i * input_n + j]);
        rows.push_back(std::move(row));
    }
    return rows;
}

FiniteActionMinimaxRequest request(std::vector<StageMap>& stage_maps) {
    stage_maps.reserve(horizon);
    std::vector<LinearStage> dynamics;
    std::vector<double> times{0.0};
    double time = 0.0;
    for(std::size_t stage = 0; stage < horizon; ++stage) {
        stage_maps.push_back(source_euler_stage(time));
        const auto& map = stage_maps.back();
        dynamics.push_back({Matrix{state_n, state_n,
                std::vector<double>(map.A.begin(), map.A.end())},
            Matrix{state_n, input_n, std::vector<double>(map.B.begin(), map.B.end())},
            Matrix{state_n, input_n, std::vector<double>(map.E.begin(), map.E.end())},
            Vector(state_n, 0.0)});
        times.push_back(time);
    }
    const SystemModel authored{{{state_n, input_n, input_n}, TimeDomain::discrete,
        std::move(dynamics)}, {}};
    const auto system = take(model::snapshot(authored, times));

    std::vector<Vector> controls;
    std::vector<double> disturbance_rows;
    for(const auto& action : u_catalogue) {
        controls.push_back({action[0], action[1]});
    }
    for(const auto& action : v_catalogue) {
        disturbance_rows.push_back(action[0]);
        disturbance_rows.push_back(action[1]);
    }
    std::vector<sets::SetData> disturbances;
    for(std::size_t stage = 0; stage < horizon; ++stage)
        disturbances.push_back(vertices("point-on-plane-disturbances-" +
            std::to_string(stage), Matrix{v_catalogue.size(), input_n, disturbance_rows}));
    std::vector<sets::SetData> admissible;
    for(std::size_t stage = 0; stage <= horizon; ++stage)
        admissible.push_back(take(sets::make_universal(
            {{"point-on-plane-unconstrained-" + std::to_string(stage)}, state_n, {}})));
    const Matrix projection{2, state_n, {1.0, 0.0, 0.0, 0.0,
                                         0.0, 1.0, 0.0, 0.0}};
    const auto objective = std::get<Objective>(snapshot(
        ResidualNormTerminal{projection, {0.0, 0.0}}));
    return {{"env717-point-on-plane-finite-v1"}, {"env717-point-on-plane"}, system,
        vertices("point-on-plane-initial", Matrix{1, state_n, {0.0, 2.0, 2.0, 1.0}}),
        {input_n, std::move(controls)}, std::move(disturbances),
        std::move(admissible), objective};
}

Json result_record(const std::vector<StageMap>& stage_maps, const FiniteMinimaxOptimal& optimum,
                   std::int64_t measured_ns) {
    Json plans = Json::array(), minimizing = Json::array();
    for(std::size_t i = 0; i < optimum.plans.size(); ++i) {
        const auto* plan = std::get_if<FinitePlanFeasible>(&optimum.plans[i]);
        if(!plan || plan->action_indices.size() != horizon)
            throw std::runtime_error("unconstrained finite plan was rejected or malformed");
        Json actions = Json::array();
        for(const auto index : plan->action_indices) {
            if(index >= u_catalogue.size()) throw std::runtime_error("bad control action index");
            actions.push_back(u_catalogue[index]);
        }
        plans.push_back({{"plan_index", i}, {"control_indices", plan->action_indices},
            {"controls", std::move(actions)}, {"worst_terminal_norm", plan->worst_value},
            {"maximizing_terminal_state", plan->maximizer}});
    }
    for(const auto index : optimum.minimizing_plan_indices) minimizing.push_back(index);
    Json stages = Json::array();
    for(const auto& map : stage_maps)
        stages.push_back({{"A", matrix_json(map.A)}, {"B", input_matrix_json(map.B)},
            {"E", input_matrix_json(map.E)}});
    Json u = Json::array(), v = Json::array();
    for(std::size_t i = 0; i < u_catalogue.size(); ++i) {
        u.push_back(u_catalogue[i]);
        v.push_back(v_catalogue[i]);
    }
    return {{"schema", "csl.env717-point-on-plane/1"},
        {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"source_file_blob", "2552484d02afca759ff909aca5e5854686a651c4"},
        {"source_license", "no license declared in repository metadata"},
        {"state_order", {"position_x1", "position_x2", "velocity_x3", "velocity_x4"}},
        {"source_model", {{"initial_time_seconds", 0.0}, {"initial_state", {0.0, 2.0, 2.0, 1.0}},
            {"terminal_time_seconds", 4.0}, {"dt_seconds", dt}, {"inner_euler_steps", inner_steps},
            {"control_action_radii", {u_radius[0], u_radius[1]}},
            {"disturbance_action_radii", {v_radius[0], v_radius[1]}},
            {"dynamics", "p1'=v1; p2'=v2; vj'=-4 exp(t/5) pj-0.1 exp(t/5) vj-8 uj+2.4 exp(t/5) vj_disturbance"},
            {"reward", "Euclidean norm of terminal position (x1,x2)"}}},
        {"adaptation", {{"horizon_steps", horizon}, {"terminal_time_seconds", horizon * dt},
            {"control_catalogue", u}, {"disturbance_catalogue", v},
            {"action_scaling", "each catalogue point is zero or an axis endpoint of the source ellipsoid; clipping and normalization leave these selected actions unchanged"},
            {"information_pattern", "fixed open-loop control sequence versus a full adversarial disturbance sequence"},
            {"objective", "minimize worst terminal Euclidean position norm over the finite disturbance catalogue"}}},
        {"stage_transition_maps", stages}, {"horizon", horizon},
        {"controller_plan_count", plans.size()}, {"disturbance_sequence_count_per_plan", 125},
        {"objective_value", optimum.value}, {"near_optimal_tolerance", 1e-10},
        {"minimizing_plan_indices", minimizing}, {"plans", plans},
        {"timing", {{"warmup_calls", 0}, {"measured_calls", 1},
            {"measured_wall_ns", {measured_ns}},
            {"scope", "one finite_action_minimax call; model and result serialization excluded"},
            {"comparison_claim", false}, {"worker_threads_requested", 1},
            {"worker_threads_actual", 1}, {"native_threads_requested", 1},
            {"native_threads_actual", 1}, {"workspace_reuse", "none"},
            {"cache_state", "cold process; no prior solver call"}}},
        {"driver_sha256", CSL_ENV717_POINT_DRIVER_SHA256},
        {"algorithm_source_sha256", CSL_ENV717_POINT_ALGORITHM_SOURCE_SHA256},
        {"source_commit", CSL_ENV717_POINT_SOURCE_COMMIT},
        {"capture_environment", {{"compiler", CSL_ENV717_POINT_COMPILER_ID},
            {"compiler_version", CSL_ENV717_POINT_COMPILER_VERSION},
            {"build_type", CSL_ENV717_POINT_BUILD_TYPE},
            {"architecture", CSL_ENV717_POINT_ARCHITECTURE}}}};
}
}

int main() {
    try {
        std::vector<StageMap> stage_maps;
        const auto input = request(stage_maps);
        const auto start = std::chrono::steady_clock::now();
        const auto outcome = finite_action_minimax(input, {125, 125, 1e-10});
        const auto stop = std::chrono::steady_clock::now();
        const auto* optimum = std::get_if<FiniteMinimaxOptimal>(&outcome);
        if(!optimum || optimum->plans.size() != 125 || optimum->minimizing_plan_indices.empty())
            throw std::runtime_error("finite-action minimax did not enumerate the complete plan catalogue");
        const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count();
        std::cout << result_record(stage_maps, *optimum, elapsed).dump(2) << '\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr << "ENV-717 PointOnThePlane pilot failed: " << error.what() << '\n';
        return 1;
    }
}
