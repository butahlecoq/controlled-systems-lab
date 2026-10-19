#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/simulation/nonlinear_replay.hpp>
#include <algorithm>
#include <limits>
#include <stdexcept>
#include <stop_token>

using namespace csl;
using namespace csl::simulation;

namespace {
Plant analytic_toy() {
    Plant plant;
    plant.identity = {"analytic.quadratic-step", "1", "EXP-04 literal toy"};
    plant.parameters = std::vector<PlantParameter>{{"quadratic_gain", 1.0, "dimensionless"}};
    plant.initial_state = Vector{0.0};
    plant.times = std::vector<double>{0.0, 1.0, 2.0};
    plant.state_units = {"dimensionless"};
    plant.control_units = {"dimensionless"};
    plant.objective_name = "terminal state";
    plant.objective_unit = "dimensionless";
    plant.integration = IntegrationMethod::exact_discrete_map;
    plant.hold = ControlHold::constant_on_interval;
    plant.numerical = NumericalPolicy{1e-12, 1e-12};
    plant.transition = [](std::span<const double> state, std::span<const double> control,
        std::span<const PlantParameter> parameters, double, double) {
        return Vector{state[0] + control[0] + parameters[0].value * control[0] * control[0]};
    };
    plant.objective = [](std::span<const double> terminal, std::span<const PlantParameter>) {
        return terminal[0];
    };
    return plant;
}
bool missing(const ReplayRecord& record, const std::string& field) {
    return std::find(record.missing_prerequisites.begin(),
        record.missing_prerequisites.end(), field) != record.missing_prerequisites.end();
}
}

TEST_CASE("two tied linear control sums have different independent nonlinear replay") {
    const auto plant = analytic_toy();
    const std::vector<Vector> first{{0.0}, {1.0}};
    const std::vector<Vector> second{{0.5}, {0.5}};
    const auto a = replay(plant, first);
    const auto b = replay(plant, second);
    REQUIRE(a.status == ReplayStatus::complete);
    REQUIRE(b.status == ReplayStatus::complete);
    CHECK(first[0][0] + first[1][0] == 1.0);
    CHECK(second[0][0] + second[1][0] == 1.0);
    CHECK(a.states == std::vector<Vector>{{0.0}, {0.0}, {2.0}});
    CHECK(b.states == std::vector<Vector>{{0.0}, {0.75}, {1.5}});
    REQUIRE(a.original_objective.has_value());
    REQUIRE(b.original_objective.has_value());
    CHECK(*a.original_objective == 2.0);
    CHECK(*b.original_objective == 1.5);
    CHECK(a.plant.name == "analytic.quadratic-step");
    CHECK(a.plant.source == "EXP-04 literal toy");
    CHECK(a.parameters[0].value == 1.0);
    CHECK(a.declared_initial_state == Vector{0.0});
    CHECK(a.times == std::vector<double>{0.0, 1.0, 2.0});
    CHECK(a.controls == first);
    CHECK(a.state_units == std::vector<std::string>{"dimensionless"});
    CHECK(a.objective_name == "terminal state");
    CHECK(a.integration == IntegrationMethod::exact_discrete_map);
    CHECK(a.hold == ControlHold::constant_on_interval);
    CHECK(a.replay_time >= std::chrono::steady_clock::duration::zero());
}

TEST_CASE("declared physical intervals and control order determine replay") {
    auto plant = analytic_toy();
    plant.initial_state = Vector{0.0, 0.0};
    plant.times = std::vector<double>{0.0, 1.0, 3.0};
    plant.state_units = {"length", "action"};
    plant.objective_name = "terminal length";
    plant.objective_unit = "length";
    plant.transition = [](std::span<const double> state, std::span<const double> control,
        std::span<const PlantParameter> parameters, double start, double end) {
        const double u = control[0];
        return Vector{state[0] + (end-start)*u + parameters[0].value*u*u, state[1]+u};
    };
    const std::vector<Vector> first{{0.0}, {1.0}};
    const std::vector<Vector> swapped{{1.0}, {0.0}};
    const auto a = replay(plant, first);
    const auto b = replay(plant, swapped);
    REQUIRE(a.status == ReplayStatus::complete);
    REQUIRE(b.status == ReplayStatus::complete);
    CHECK(a.states.back() == Vector{3.0, 1.0});
    CHECK(b.states.back() == Vector{2.0, 1.0});
    CHECK(a.objective_unit == "length");
}

TEST_CASE("missing independent plant data and incomplete controls name prerequisites") {
    auto plant = analytic_toy();
    plant.parameters.reset();
    plant.times.reset();
    plant.objective = {};
    const std::vector<Vector> one{{0.0}};
    const auto absent = replay(plant, one);
    CHECK(absent.status == ReplayStatus::unavailable);
    CHECK(missing(absent, "plant.parameters"));
    CHECK(missing(absent, "plant.times"));
    CHECK(missing(absent, "plant.objective"));
    CHECK(absent.declared_initial_state == Vector{0.0});
    CHECK(absent.states.empty());

    plant = analytic_toy();
    const auto incomplete = replay(plant, one);
    CHECK(incomplete.status == ReplayStatus::unavailable);
    CHECK(missing(incomplete, "controls.complete_history"));
}

TEST_CASE("invalid numeric inputs and callback failures retain distinct outcomes") {
    auto plant = analytic_toy();
    const std::vector<Vector> nan_control{{0.0}, {std::numeric_limits<double>::quiet_NaN()}};
    CHECK(replay(plant, nan_control).status == ReplayStatus::invalid_input);
    plant = analytic_toy();
    plant.transition = [](std::span<const double>, std::span<const double>,
        std::span<const PlantParameter>, double, double) {
        return Vector{std::numeric_limits<double>::infinity()};
    };
    const std::vector<Vector> controls{{0.0}, {1.0}};
    const auto nonfinite = replay(plant, controls);
    CHECK(nonfinite.status == ReplayStatus::numerical_failure);
    CHECK(nonfinite.states.size() == 1);
    plant.transition = [](std::span<const double>, std::span<const double>,
        std::span<const PlantParameter>, double, double) -> Vector {
        throw std::runtime_error("plant stopped");
    };
    CHECK(replay(plant, controls).status == ReplayStatus::callback_failure);
}

TEST_CASE("unsupported declarations, cancellation and deadline do not create a completed objective") {
    auto plant = analytic_toy();
    const std::vector<Vector> controls{{0.0}, {1.0}};
    plant.times = std::vector<double>{0.0, 1.0, 1.0};
    CHECK(replay(plant, controls).status == ReplayStatus::invalid_input);
    plant = analytic_toy();
    plant.integration = static_cast<IntegrationMethod>(99);
    CHECK(replay(plant, controls).status == ReplayStatus::invalid_input);
    plant = analytic_toy();
    plant.objective = [](std::span<const double>, std::span<const PlantParameter>) {
        return std::numeric_limits<double>::infinity();
    };
    const auto invalid_cost = replay(plant, controls);
    CHECK(invalid_cost.status == ReplayStatus::numerical_failure);
    CHECK_FALSE(invalid_cost.original_objective.has_value());
    CHECK(invalid_cost.states.size() == 3);

    plant = analytic_toy();
    std::stop_source source;
    source.request_stop();
    ExecutionContext cancelled;
    cancelled.cancellation = source.get_token();
    const auto stopped = replay(plant, controls, cancelled);
    CHECK(stopped.status == ReplayStatus::cancelled);
    CHECK(stopped.states == std::vector<Vector>{{0.0}});
    CHECK_FALSE(stopped.original_objective.has_value());

    ExecutionContext expired;
    expired.deadline = std::chrono::steady_clock::now() - std::chrono::seconds(1);
    const auto limited = replay(plant, controls, expired);
    CHECK(limited.status == ReplayStatus::resource_limit);
    CHECK(limited.states == std::vector<Vector>{{0.0}});
    CHECK_FALSE(limited.original_objective.has_value());
}

TEST_CASE("context exhaustion inside the final callbacks cannot report completion") {
    const std::vector<Vector> controls{{0.0}, {1.0}};
    auto plant = analytic_toy();
    std::stop_source source;
    ExecutionContext cancelled;
    cancelled.cancellation = source.get_token();
    plant.transition = [&source](std::span<const double> state,
        std::span<const double> control, std::span<const PlantParameter> parameters,
        double, double) {
        if (control[0] == 1.0) source.request_stop();
        return Vector{state[0] + control[0] + parameters[0].value * control[0] * control[0]};
    };
    const auto stopped = replay(plant, controls, cancelled);
    CHECK(stopped.status == ReplayStatus::cancelled);
    CHECK(stopped.states == std::vector<Vector>{{0.0}, {0.0}});
    CHECK_FALSE(stopped.original_objective.has_value());

    plant = analytic_toy();
    ExecutionContext expired;
    plant.objective = [&expired](std::span<const double> terminal,
        std::span<const PlantParameter>) {
        expired.deadline = std::chrono::steady_clock::now() - std::chrono::seconds(1);
        return terminal[0];
    };
    const auto limited = replay(plant, controls, expired);
    CHECK(limited.status == ReplayStatus::resource_limit);
    CHECK(limited.states == std::vector<Vector>{{0.0}, {0.0}, {2.0}});
    CHECK_FALSE(limited.original_objective.has_value());
}
