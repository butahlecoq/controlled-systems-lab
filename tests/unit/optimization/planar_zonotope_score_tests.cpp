#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/finite_action_zonotope_minimax.hpp>
#include <csl/reachability/finite_plan_zonotope.hpp>

#include "planar_zonotope_score.hpp"

#include <cmath>
#include <cstdint>
#include <limits>
#include <optional>
#include <vector>

using namespace csl;
using namespace csl::optimization;

namespace {

reachability::FinitePlanZonotopeTrace::Stage stage(Vector center, Matrix generators) {
    const auto factors = generators.cols;
    std::vector<sets::FactorId> ids(factors);
    for (std::size_t i = 0; i < factors; ++i)
        ids[i] = {std::string("planar-factor-") + std::to_string(i)};
    return {std::move(center), std::move(generators), std::move(ids)};
}

Objective residual_objective(Matrix map, Vector target, Vector weights = {}) {
    const auto value =
        snapshot(ResidualNormTerminal{std::move(map), std::move(target), std::move(weights)});
    REQUIRE(std::holds_alternative<Objective>(value));
    return std::get<Objective>(value);
}

Objective quadratic_objective(Matrix Q, Vector linear, double offset) {
    const auto value = snapshot(QuadraticTerminal{std::move(Q), std::move(linear), offset});
    REQUIRE(std::holds_alternative<Objective>(value));
    return std::get<Objective>(value);
}

double exhaustive_maximum(const reachability::FinitePlanZonotopeTrace::Stage &terminal,
                          const Objective &objective) {
    const auto n = terminal.center.size();
    const auto m = terminal.generators.cols;
    REQUIRE(m < 31);
    double best = -std::numeric_limits<double>::infinity();
    for (std::uint64_t mask = 0; mask < (std::uint64_t{1} << m); ++mask) {
        auto point = terminal.center;
        for (std::size_t j = 0; j < m; ++j)
            for (std::size_t i = 0; i < n; ++i)
                point[i] += ((mask >> j) & 1 ? 1.0 : -1.0) * terminal.generators.values[i * m + j];
        const auto value = evaluate(objective, point);
        REQUIRE(std::holds_alternative<double>(value));
        best = std::max(best, std::get<double>(value));
    }
    return best;
}

std::optional<detail::PlanarTerminalScore>
score(const reachability::FinitePlanZonotopeTrace::Stage &terminal, const Objective &objective,
      std::size_t limit = 4096) {
    const auto outcome = detail::try_planar_zonotope_score(terminal, objective, limit, [] {});
    if (!outcome) {
        CHECK_MESSAGE(false, "planar reduction was not admitted");
        return std::nullopt;
    }
    if (const auto *stop = std::get_if<OperationStopped>(&*outcome)) {
        CHECK_MESSAGE(false, "planar score stopped: " << stop->diagnostics);
        return std::nullopt;
    }
    return std::get<detail::PlanarTerminalScore>(*outcome);
}

} // namespace

TEST_CASE("planar residual sweep matches exhaustive corner enumeration") {
    const auto objective = residual_objective({2, 2, {1, 0, 0.5, 1}}, {0.5, -1.5}, {1, 0.25});
    const auto terminal =
        stage({0.25, -0.5}, {2, 6, {0.5, 0.25, -0.5, 1, 0.125, 0, 0, -0.75, 0.5, 0.25, 0, 0.375}});
    const auto exact = exhaustive_maximum(terminal, objective);
    const auto scored = score(terminal, objective);
    REQUIRE(scored);
    CHECK(scored->method == "exact-planar-residual-sweep/1");
    CHECK(scored->value >= exact);
    CHECK(scored->value == doctest::Approx(exact).epsilon(1e-14));
    CHECK(scored->visits == 2 * terminal.generators.cols + 1);
}

TEST_CASE("planar residual sweep preserves a rank-deficient residual image") {
    const auto objective = residual_objective({2, 2, {1, 0, 0, 0}}, {0.25, 0});
    for (const auto &generators : {Matrix{2, 3, {0.5, -0.25, 0.125, 0, -0.5, 0.75}},
                                   Matrix{2, 3, {0.5, -0.25, 0.5, 0, 0, 0}}}) {
        const auto terminal = stage({0.25, -2}, generators);
        const auto exact = exhaustive_maximum(terminal, objective);
        const auto scored = score(terminal, objective);
        REQUIRE(scored);
        CHECK(scored->value >= exact);
        CHECK(scored->value == doctest::Approx(exact).epsilon(1e-14));
    }
}

TEST_CASE("planar residual sweep handles tied and opposite generator directions") {
    const auto objective = residual_objective({2, 2, {1, 0, 0, 1}}, {1, 1});
    const auto terminal = stage({0.5, -0.5}, {2, 5, {1, 2, -1, 0, 3, 0, 0, 0, 1, -3}});
    const auto exact = exhaustive_maximum(terminal, objective);
    const auto scored = score(terminal, objective);
    REQUIRE(scored);
    CHECK(scored->value >= exact);
    CHECK(scored->value == doctest::Approx(exact).epsilon(1e-14));
}

TEST_CASE("separable diagonal quadratic scores independent stored factor blocks") {
    const auto objective = quadratic_objective(
        {4, 4, {2, 0, 0, 0, 0, 1.5, 0, 0, 0, 0, 3, 0, 0, 0, 0, 1}}, {0.5, -0.25, 1, -0.5}, 0.75);
    const auto terminal =
        stage({0.5, -1, 0.25, 2},
              {4, 6, {1, 2, 0, 0, 0, 0, 1, -1, 0, 0, 0, 0, 0, 0, 1, -2, 1, 0, 0, 0, 2, 1, 0, 1}});
    const auto exact = exhaustive_maximum(terminal, objective);
    const auto scored = score(terminal, objective);
    REQUIRE(scored);
    CHECK(scored->method == "exact-separable-quadratic-sweep/1");
    CHECK(scored->value >= exact);
    CHECK(scored->value == doctest::Approx(exact).epsilon(1e-14));
}

TEST_CASE("planar admission refuses structures it cannot certify") {
    const auto residual = residual_objective({3, 2, {1, 0, 0, 1, 0.5, 0}}, {0.5, -0.5, 0});
    const auto terminal = stage({0.5, -0.5}, {2, 2, {1, 0, 0, 1}});
    const auto outcome = detail::try_planar_zonotope_score(terminal, residual, 4096, [] {});
    CHECK_FALSE(outcome);

    const auto mixed_quadratic = quadratic_objective(
        {4, 4, {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1}}, {0, 0, 0, 0}, 0);
    const auto mixed = stage({0, 0, 0, 0}, {4, 1, {1, 0, 1, 1}});
    CHECK_FALSE(detail::try_planar_zonotope_score(mixed, mixed_quadratic, 4096, [] {}));

    const auto coupled_quadratic = quadratic_objective({2, 2, {1, 0.5, 0.5, 1}}, {0, 0}, 0);
    const auto coupled = stage({0, 0}, {2, 2, {1, 0, 0, 1}});
    CHECK_FALSE(detail::try_planar_zonotope_score(coupled, coupled_quadratic, 4096, [] {}));

    const auto independent = quadratic_objective(
        {4, 4, {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1}}, {0, 0, 0, 0}, 0);
    const auto crossed = stage({0, 0, 0, 0}, {4, 2, {1, 1, 1, 0, 0, 1, 0, 0}});
    CHECK_FALSE(detail::try_planar_zonotope_score(crossed, independent, 4096, [] {}));
}

TEST_CASE("planar score preserves resource and nonfinite refusals") {
    const auto objective = residual_objective({2, 2, {1, 0, 0, 1}}, {0.5, -0.5});
    const auto terminal = stage({0.5, -0.5}, {2, 3, {1, 0, 0.5, 0, 1, 0.25}});
    const auto limited = detail::try_planar_zonotope_score(terminal, objective, 3, [] {});
    REQUIRE(limited);
    REQUIRE(std::holds_alternative<OperationStopped>(*limited));
    CHECK(std::get<OperationStopped>(*limited).reason == StopReason::resource_limit);

    auto nonfinite = terminal;
    nonfinite.generators.values[0] = std::numeric_limits<double>::infinity();
    const auto refused = detail::try_planar_zonotope_score(nonfinite, objective, 4096, [] {});
    REQUIRE(refused);
    REQUIRE(std::holds_alternative<OperationStopped>(*refused));
    CHECK(std::get<OperationStopped>(*refused).reason == StopReason::numerical_failure);
}

TEST_CASE("cancellation propagates out of the planar sweep") {
    const auto objective = residual_objective({2, 2, {1, 0, 0, 1}}, {0.5, -0.5});
    const auto terminal = stage({0.5, -0.5}, {2, 2, {1, 0, 0, 1}});
    std::stop_source cancellation;
    cancellation.request_stop();
    ExecutionContext context;
    context.cancellation = cancellation.get_token();
    const auto outcome = detail::try_planar_zonotope_score(terminal, objective, 4096, [&] {
        if (context.cancellation.stop_requested())
            throw OperationStopped{StopReason::cancelled, "planar score cancelled"};
    });
    REQUIRE(outcome);
    REQUIRE(std::holds_alternative<OperationStopped>(*outcome));
    CHECK(std::get<OperationStopped>(*outcome).reason == StopReason::cancelled);
}
