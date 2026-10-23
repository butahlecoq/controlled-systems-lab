#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/input/scenario_loader.hpp>
#include <csl/model/linear_system.hpp>
#include <csl/optimization/objectives.hpp>
#include <csl/sets/data.hpp>
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

bool has_box_bounds(const AdmissibleSet& set, const Vector& lower, const Vector& upper) {
    const auto* handle = std::get_if<SetHandle>(&set);
    if (!handle) return false;
    const auto result = sets::from_handle(*handle);
    if (!std::holds_alternative<sets::SetData>(result)) return false;
    const auto representation = std::get<sets::SetData>(result).representation();
    const auto* h = std::get_if<sets::HRepresentation>(&representation);
    if (!h || lower.size() != upper.size() || h->inequalities.cols() != lower.size() ||
        h->inequalities.rows() != 2 * lower.size() || h->equalities.rows() != 0)
        return false;

    for (std::size_t axis = 0; axis < lower.size(); ++axis) {
        bool found_lower = false;
        bool found_upper = false;
        for (std::size_t row = 0; row < h->inequalities.rows(); ++row) {
            bool unit_row = true;
            for (std::size_t column = 0; column < lower.size(); ++column) {
                const double expected = column == axis ? 1.0 : 0.0;
                unit_row &= h->inequalities(row, column) == expected ||
                    h->inequalities(row, column) == -expected;
            }
            if (!unit_row) continue;
            if (h->inequalities(row, axis) == 1.0 && h->upper_bounds[row] == upper[axis])
                found_upper = true;
            if (h->inequalities(row, axis) == -1.0 && h->upper_bounds[row] == -lower[axis])
                found_lower = true;
        }
        if (!found_lower || !found_upper) return false;
    }
    return true;
}

bool within(double value, double lower, double upper) {
    return lower <= value && value <= upper;
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
    const auto states = scenario.problem().constraints().states();
    REQUIRE(states->size() == 4);
    CHECK(std::get<Singleton>((*states)[0]).point == Vector{0, 0});
    CHECK(has_box_bounds((*states)[1], {0, -1}, {0.5, 1}));
    CHECK(has_box_bounds((*states)[2], {0, -1}, {1.5, 1}));
    CHECK(std::get<UniversalSet>((*states)[3]).dimension == 2);

    const auto control_description = scenario.problem().controls().description();
    REQUIRE(control_description);
    const auto* controls = std::get_if<ContinuousDomain>(control_description.get());
    REQUIRE(controls);
    REQUIRE(controls->stages.size() == 3);
    for (const auto& stage : controls->stages)
        CHECK(has_box_bounds(stage, {-1}, {1}));

    const auto x1 = step(scenario, 0, {0, 0}, {0.5});
    const auto x2 = step(scenario, 1, x1, {0});
    const auto x3 = step(scenario, 2, x2, {-0.25});
    CHECK(x1 == Vector{0.25, 0.5});
    CHECK(x2 == Vector{0.75, 0.5});
    CHECK(x3 == Vector{1.125, 0.25});

    CHECK(within(x1[0], 0, 0.5));
    CHECK(within(x1[1], -1, 1));
    CHECK(within(x2[0], 0, 1.5));
    CHECK(within(x2[1], -1, 1));
    CHECK(within(0.5, -1, 1));
    CHECK(within(0.0, -1, 1));
    CHECK(within(-0.25, -1, 1));
    CHECK(cost(scenario, x3) == doctest::Approx(0.078125));
}
