#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/input/scenario_loader.hpp>
#include <csl/model/linear_system.hpp>
#include <csl/optimization/objectives.hpp>
#include <filesystem>

namespace {
using namespace csl;
using namespace csl::input;

LoadedScenario load(const char* name) {
    const auto result = load_scenario_file(std::filesystem::path(CSL_SCENARIO_TEMPLATE_DIR) / name);
    if (const auto* failure = std::get_if<InputFailure>(&result))
        FAIL_CHECK("scenario rejected at " << failure->path << ": " << failure->observed);
    else if (const auto* unsupported = std::get_if<UnsupportedInput>(&result))
        FAIL_CHECK("scenario unsupported at " << unsupported->path << ": " << unsupported->feature);
    REQUIRE(std::holds_alternative<LoadedScenario>(result));
    return std::get<LoadedScenario>(result);
}

Vector step(const LoadedScenario& scenario, std::size_t stage, const Vector& state, const Vector& control) {
    const auto result = scenario.problem().model().step({stage}, state, control, {});
    REQUIRE(std::holds_alternative<Vector>(result));
    return std::get<Vector>(result);
}

double cost(const LoadedScenario& scenario, const Vector& state) {
    const auto result = optimization::evaluate(scenario.problem().objective(), state);
    REQUIRE(std::holds_alternative<double>(result));
    return std::get<double>(result);
}
}

TEST_CASE("minimal LTI linear-objective template loads and has a literal transition and cost") {
    const auto scenario = load("minimal-lti-linear.json");
    CHECK(scenario.problem().model().horizon() == 1);
    CHECK(scenario.metadata()->state_labels == std::vector<std::string>{"x"});
    CHECK(scenario.metadata()->control_labels == std::vector<std::string>{"u"});
    CHECK(scenario.metadata()->state_units == std::vector<std::string>{"dimensionless"});
    CHECK(scenario.metadata()->control_units == std::vector<std::string>{"dimensionless"});
    CHECK(step(scenario, 0, {0}, {0.5}) == Vector{0.5});
    CHECK(cost(scenario, {0.5}) == doctest::Approx(0.5));
}

TEST_CASE("state-constrained quadratic template retains its horizon and authored state slices") {
    const auto scenario = load("state-constrained-quadratic.json");
    CHECK(scenario.problem().model().horizon() == 2);
    CHECK(scenario.metadata()->state_labels == std::vector<std::string>{"x"});
    CHECK(scenario.metadata()->control_labels == std::vector<std::string>{"u"});
    CHECK(scenario.metadata()->state_units == std::vector<std::string>{"dimensionless"});
    CHECK(scenario.metadata()->control_units == std::vector<std::string>{"dimensionless"});
    CHECK(scenario.problem().constraints().states()->size() == 3);
    const auto x1 = step(scenario, 0, {0}, {0.25});
    const auto x2 = step(scenario, 1, x1, {0.75});
    CHECK(x1 == Vector{0.25});
    CHECK(x2 == Vector{1});
    CHECK(cost(scenario, x2) == doctest::Approx(0));
}

TEST_CASE("LTV residual-norm template evaluates every authored stage against a literal answer") {
    const auto scenario = load("ltv-residual-norm.json");
    CHECK(scenario.problem().model().horizon() == 2);
    CHECK(scenario.metadata()->state_labels == std::vector<std::string>{"x"});
    CHECK(scenario.metadata()->control_labels == std::vector<std::string>{"u"});
    CHECK(scenario.metadata()->state_units == std::vector<std::string>{"dimensionless"});
    CHECK(scenario.metadata()->control_units == std::vector<std::string>{"dimensionless"});
    const auto x1 = step(scenario, 0, {1}, {1});
    const auto x2 = step(scenario, 1, x1, {0});
    CHECK(x1 == Vector{2});
    CHECK(x2 == Vector{4});
    CHECK(cost(scenario, x2) == doctest::Approx(1));
}

TEST_CASE("double-integrator generality template has independently derived transitions and tracking cost") {
    const auto scenario = load("double-integrator-generality.json");
    CHECK(scenario.problem().model().horizon() == 3);
    CHECK(scenario.problem().model().dimensions() == Dimensions{2, 1, 0});
    CHECK(scenario.metadata()->time_unit == std::optional<std::string>{"s"});
    CHECK(scenario.metadata()->state_labels == std::vector<std::string>{"position", "velocity"});
    CHECK(scenario.metadata()->control_labels == std::vector<std::string>{"acceleration"});
    CHECK(scenario.metadata()->state_units == std::vector<std::string>{"m", "m/s"});
    CHECK(scenario.metadata()->control_units == std::vector<std::string>{"m/s^2"});
    REQUIRE(scenario.problem().constraints().states());
    CHECK(scenario.problem().constraints().states()->size() == 4);

    const auto x1 = step(scenario, 0, {0, 0}, {0.5});
    const auto x2 = step(scenario, 1, x1, {0});
    const auto x3 = step(scenario, 2, x2, {-0.25});
    CHECK(x1 == Vector{0.25, 0.5});
    CHECK(x2 == Vector{0.75, 0.5});
    CHECK(x3 == Vector{1.125, 0.25});

    CHECK(x1[0] >= 0);
    CHECK(x1[0] <= 0.5);
    CHECK(x1[1] >= -1);
    CHECK(x1[1] <= 1);
    CHECK(x2[0] >= 0);
    CHECK(x2[0] <= 1.5);
    CHECK(x2[1] >= -1);
    CHECK(x2[1] <= 1);
    CHECK(0.5 >= -1);
    CHECK(0.5 <= 1);
    CHECK(0.0 >= -1);
    CHECK(0.0 <= 1);
    CHECK(-0.25 >= -1);
    CHECK(-0.25 <= 1);
    CHECK(cost(scenario, x3) == doctest::Approx(0.078125));
}
