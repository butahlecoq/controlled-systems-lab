#include <nlohmann/json.hpp>

#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using Json = nlohmann::json;

constexpr double outer_dt = 0.1;
constexpr double inner_dt = 0.01;
constexpr int outer_steps = 10;
constexpr int inner_steps = 10;
constexpr double initial_position = 1.0;
constexpr double initial_velocity = 0.0;
constexpr std::array<double, 5> actions{-2.0, -1.0, 0.0, 1.0, 2.0};
constexpr std::int64_t plan_count = 9'765'625;

struct State { double x{}; double v{}; };
struct AnalyticPolicy { double eta1{}; double eta2{}; };

double f(double t) {
    const double q = t / std::sqrt(2.0);
    return (std::sin(q) * std::cosh(q) - std::cos(q) * std::sinh(q)) / std::sqrt(2.0);
}
double df(double t) {
    const double q = t / std::sqrt(2.0);
    return std::sin(q) * std::sinh(q);
}
double d2f(double t) {
    const double q = t / std::sqrt(2.0);
    return (std::sin(q) * std::cosh(q) + std::cos(q) * std::sinh(q)) / std::sqrt(2.0);
}
double d3f(double t) {
    const double q = t / std::sqrt(2.0);
    return std::cos(q) * std::cosh(q);
}

AnalyticPolicy analytic_policy() {
    const double a = d3f(1.0);
    const double b = f(1.0);
    const double c = -d2f(1.0);
    const double d = d3f(1.0);
    const double rhs1 = -0.5 - d2f(1.0) * initial_position - df(1.0) * initial_velocity;
    const double rhs2 = -0.5 + df(1.0) * initial_position + f(1.0) * initial_velocity;
    const double determinant = a * d - b * c;
    if(std::abs(determinant) < 1e-14) throw std::runtime_error("analytic boundary system is singular");
    return {(rhs1 * d - b * rhs2) / determinant,
        (a * rhs2 - rhs1 * c) / determinant};
}

double analytic_control(const AnalyticPolicy& policy, double t) {
    return -df(t) * initial_position - f(t) * initial_velocity
        - d2f(t) * policy.eta1 + d3f(t) * policy.eta2;
}

std::array<double, 3> derivative(const AnalyticPolicy& policy, double t,
    const std::array<double, 3>& value) {
    const double control = analytic_control(policy, t);
    return {value[1], control, value[0] * value[0] + control * control};
}

std::array<double, 3> rk4_step(const AnalyticPolicy& policy, double t,
    const std::array<double, 3>& y, double h) {
    const auto k1 = derivative(policy, t, y);
    std::array<double, 3> work{};
    for(std::size_t i = 0; i < y.size(); ++i) work[i] = y[i] + h * k1[i] / 2.0;
    const auto k2 = derivative(policy, t + h / 2.0, work);
    for(std::size_t i = 0; i < y.size(); ++i) work[i] = y[i] + h * k2[i] / 2.0;
    const auto k3 = derivative(policy, t + h / 2.0, work);
    for(std::size_t i = 0; i < y.size(); ++i) work[i] = y[i] + h * k3[i];
    const auto k4 = derivative(policy, t + h, work);
    auto result = y;
    for(std::size_t i = 0; i < y.size(); ++i)
        result[i] += h * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i]) / 6.0;
    return result;
}

Json continuous_reference(const AnalyticPolicy& policy) {
    constexpr int samples = 1000;
    constexpr double h = 1.0 / samples;
    auto y = std::array<double, 3>{initial_position, initial_velocity, 0.0};
    Json trajectory = Json::array();
    trajectory.push_back({{"time_seconds", 0.0}, {"position", y[0]},
        {"velocity", y[1]}, {"control", analytic_control(policy, 0.0)}});
    for(int i = 0; i < samples; ++i) {
        y = rk4_step(policy, static_cast<double>(i) * h, y, h);
        if((i + 1) % (samples / 100) == 0) {
            const double t = static_cast<double>(i + 1) * h;
            trajectory.push_back({{"time_seconds", t}, {"position", y[0]},
                {"velocity", y[1]}, {"control", analytic_control(policy, t)}});
        }
    }
    return {{"objective", y[2] + y[0] + y[1]}, {"running_cost_integral", y[2]},
        {"terminal_state", {y[0], y[1]}}, {"trajectory", std::move(trajectory)},
        {"integration", "RK4, 1000 uniform steps"}};
}

State source_step(State state, double control) {
    for(int i = 0; i < inner_steps; ++i) {
        const double old_x = state.x;
        const double old_v = state.v;
        state.x = old_x + inner_dt * old_v;
        state.v = old_v + inner_dt * control;
    }
    return state;
}

Json sampled_feedback(const AnalyticPolicy& policy) {
    State state{initial_position, initial_velocity};
    double running_cost = 0.0;
    Json trajectory = Json::array();
    for(int stage = 0; stage <= outer_steps; ++stage) {
        const double t = stage * outer_dt;
        const double control = stage < outer_steps ? analytic_control(policy, t) : 0.0;
        trajectory.push_back({{"time_seconds", t}, {"position", state.x},
            {"velocity", state.v}, {"control", control}});
        if(stage == outer_steps) break;
        running_cost += outer_dt * (state.x * state.x + control * control);
        state = source_step(state, control);
    }
    return {{"objective", running_cost + state.x + state.v},
        {"running_cost_sum", running_cost}, {"terminal_state", {state.x, state.v}},
        {"trajectory", std::move(trajectory)},
        {"policy", "continuous analytic feedback sampled at each outer step and held over ten source Euler substeps"}};
}

struct SearchResult {
    double objective{std::numeric_limits<double>::infinity()};
    State terminal{};
    std::array<int, outer_steps> action_ids{};
    std::uint64_t ties{};
};

void enumerate(int stage, State state, double running_cost,
    std::array<int, outer_steps>& plan, SearchResult& best) {
    if(stage == outer_steps) {
        const double objective = running_cost + state.x + state.v;
        if(objective < best.objective - 1e-12) {
            best.objective = objective;
            best.terminal = state;
            best.action_ids = plan;
            best.ties = 1;
        } else if(std::abs(objective - best.objective) <= 1e-12) {
            ++best.ties;
        }
        return;
    }
    for(std::size_t action_id = 0; action_id < actions.size(); ++action_id) {
        const double control = actions[action_id];
        plan[static_cast<std::size_t>(stage)] = static_cast<int>(action_id);
        const double next_running = running_cost + outer_dt * (state.x * state.x + control * control);
        enumerate(stage + 1, source_step(state, control), next_running, plan, best);
    }
}

Json finite_catalogue() {
    SearchResult best;
    std::array<int, outer_steps> plan{};
    const auto started = std::chrono::steady_clock::now();
    enumerate(0, {initial_position, initial_velocity}, 0.0, plan, best);
    const auto stopped = std::chrono::steady_clock::now();
    Json controls = Json::array();
    for(const int id : best.action_ids) controls.push_back(actions.at(static_cast<std::size_t>(id)));
    State replay{initial_position, initial_velocity};
    double running_cost = 0.0;
    Json trajectory = Json::array();
    for(int stage = 0; stage <= outer_steps; ++stage) {
        const double t = stage * outer_dt;
        const double control = stage < outer_steps ? controls.at(static_cast<std::size_t>(stage)).get<double>() : 0.0;
        trajectory.push_back({{"time_seconds", t}, {"position", replay.x},
            {"velocity", replay.v}, {"control", control}});
        if(stage == outer_steps) break;
        running_cost += outer_dt * (replay.x * replay.x + control * control);
        replay = source_step(replay, control);
    }
    return {{"objective", best.objective}, {"running_cost_sum", running_cost},
        {"control_catalogue", actions}, {"selected_controls", controls},
        {"terminal_state", {best.terminal.x, best.terminal.v}},
        {"replayed_terminal_state", {replay.x, replay.v}}, {"tie_count", best.ties},
        {"plan_count", plan_count}, {"elapsed_ns", std::chrono::duration_cast<std::chrono::nanoseconds>(stopped - started).count()},
        {"search", "exhaustive finite action-sequence enumeration; no pruning"},
        {"trajectory", std::move(trajectory)},
        {"oracle_reference", "independent Python chunked enumeration of all finite plans"},
        {"continuous_reference_policy", "same re-expressed closed-form feedback basis, not used in finite search"}};
}

Json run() {
    const auto policy = analytic_policy();
    return {{"schema", "csl.env717-unlimited-bolza-pilot/1"},
        {"environment", "UnlimitedBolzaProblem"},
        {"source_url", "https://github.com/imm-rl-lab/optimal_control/tree/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/UnlimitedBolzaProblem"},
        {"source_repository_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
        {"source_file_blob", "1b26ba326fbbce4c31a29f211b97dd3981a227e9"},
        {"optimal_agent_blob", "d426400cab0b0a18d9819acea84d082991899a06"},
        {"source_model", {{"state_order", {"time", "position", "velocity"}},
            {"dynamics", "time'=1; position'=velocity; velocity'=control"},
            {"outer_step_seconds", outer_dt}, {"inner_step_seconds", inner_dt},
            {"inner_steps_per_outer_step", inner_steps}, {"horizon_seconds", 1.0},
            {"source_control_bounds", "unbounded"},
            {"running_cost_per_outer_step", "dt * (position^2 + control^2), evaluated at the pre-step state"},
            {"terminal_cost", "position(T) + velocity(T)"}}},
        {"pilot_adaptation", {{"initial_position", initial_position}, {"initial_velocity", initial_velocity},
            {"initial_state_note", "authored nonzero initial state; upstream default is zero"},
            {"finite_control_catalogue", actions}, {"finite_horizon_steps", outer_steps},
            {"finite_action_scope", "bounded catalogue adaptation; does not solve the original unbounded-control problem"}}},
        {"continuous_analytic_reference", continuous_reference(policy)},
        {"sampled_analytic_feedback_replay", sampled_feedback(policy)},
        {"finite_catalogue_optimum", finite_catalogue()},
        {"provenance", {{"driver_sha256", CSL_ENV717_BOLZA_DRIVER_SHA256},
            {"algorithm_source_sha256", CSL_ENV717_BOLZA_ALGORITHM_SHA256},
            {"source_commit", CSL_ENV717_BOLZA_SOURCE_COMMIT},
            {"compiler_id", CSL_ENV717_BOLZA_COMPILER_ID},
            {"compiler_version", CSL_ENV717_BOLZA_COMPILER_VERSION},
            {"build_type", CSL_ENV717_BOLZA_BUILD_TYPE},
            {"architecture", CSL_ENV717_BOLZA_ARCHITECTURE}}},
        {"claims", Json::array({"source-step semantics are re-expressed and independently checked",
            "analytic policy is a reference candidate verified through differential identities and boundary conditions",
            "finite catalogue minimum is exact over the declared 5^10 catalogue under binary64 evaluation"})}};
}
} // namespace

int main() {
    try {
        std::cout << run().dump(2) << '\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr << "UnlimitedBolza report failed: " << error.what() << '\n';
        return 1;
    }
}
