#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/reachability/finite_plan_ellipsoid.hpp>
#include <csl/reachability/fixed_plan_disturbance.hpp>

#include "two_points_fixture.hpp"

#include <cmath>

using namespace csl;
using namespace csl::reachability;

namespace {
template <class T> T take(std::variant<T, Diagnostic> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
sets::SetData vertices(std::string id, std::size_t dimension, Matrix points) {
    return take(sets::make_v({{std::move(id)}, dimension, {}},
                             {take(numeric::snapshot(std::move(points))),
                              take(numeric::snapshot(Matrix{0, dimension, {}}))}));
}
sets::SetData universal(std::string id, std::size_t dimension) {
    return take(sets::make_universal({{std::move(id)}, dimension, {}}));
}
sets::SetData bounded(std::string id, double bound) {
    return take(sets::make_h({{std::move(id)}, 1, {"x"}},
                             {take(numeric::snapshot(Matrix{2, 1, {1, -1}})),
                              take(numeric::snapshot_vector(Vector{bound, bound})),
                              take(numeric::snapshot(Matrix{0, 1, {}})),
                              take(numeric::snapshot_vector(Vector{}))}));
}
FixedPlanRequest points_request() {
    const auto game = issue824::fixture::two_points_request("ellipsoid-test");
    return {game.system,       game.initial,           {{-2.5}, {-2.5}, {-2.5}},
            game.disturbances, game.admissible_states, {"ellipsoid-test"}};
}
bool contains(const FinitePlanEllipsoidTrace::Stage &ellipse, std::span<const double> point) {
    long double sum = 0.0L;
    for (std::size_t i = 0; i < point.size(); ++i) {
        if (ellipse.radii[i] == 0.0) {
            if (point[i] != ellipse.center[i])
                return false;
            continue;
        }
        const long double ratio =
            (static_cast<long double>(point[i]) - ellipse.center[i]) / ellipse.radii[i];
        sum += ratio * ratio;
    }
    return sum <= 1.0L;
}
}

TEST_CASE("stagewise ellipsoids contain the exact finite TwoPoints history sets") {
    const auto request = points_request();
    const auto enclosed = finite_plan_ellipsoid(request);
    REQUIRE(std::holds_alternative<FinitePlanEllipsoidTrace>(enclosed));
    const auto exact = fixed_plan_disturbance(request, 27);
    REQUIRE(std::holds_alternative<FixedPlanReachable>(exact));
    const auto &ellipsoids = std::get<FinitePlanEllipsoidTrace>(enclosed);
    CHECK(ellipsoids.relation == SetRelation::outer);
    const auto &stages = std::get<FixedPlanReachable>(exact).stages;
    REQUIRE(ellipsoids.stages.size() == stages.size());
    for (std::size_t stage = 0; stage < stages.size(); ++stage) {
        const auto representation = stages[stage].representation();
        const auto *vertices = std::get_if<sets::VRepresentation>(&representation);
        REQUIRE(vertices != nullptr);
        for (std::size_t row = 0; row < vertices->vertices.rows(); ++row) {
            Vector point(vertices->vertices.cols());
            for (std::size_t column = 0; column < point.size(); ++column)
                point[column] = vertices->vertices(row, column);
            CHECK(contains(ellipsoids.stages[stage], point));
        }
    }
}

TEST_CASE("ellipsoid propagation only accepts a bounded safe set when its outer shape fits") {
    const auto one = vertices("one", 1, Matrix{1, 1, {0.0}});
    const auto two = vertices("two", 1, Matrix{2, 1, {-1.0, 1.0}});
    const auto universal_set = universal("universal", 1);
    const SystemModel sys_model{{{1, 1, 1},
                                 TimeDomain::discrete,
                                 LinearStage{{1, 1, {1.0}}, {1, 1, {1.0}}, {1, 1, {1.0}}, {0.0}}},
                                {}};
    const auto system = take(model::snapshot(sys_model, Vector{0.0, 1.0}));
    auto input = FixedPlanRequest{
        system, one, {{0.0}}, {two}, {universal_set, bounded("wide-safe", 10)}, {"bounded-safe"}};
    CHECK(std::holds_alternative<FinitePlanEllipsoidTrace>(finite_plan_ellipsoid(input)));
    input.admissible_states[1] = bounded("narrow-safe", 0.5);
    const auto result = finite_plan_ellipsoid(input);
    REQUIRE(std::holds_alternative<Unsupported>(result));
    CHECK(std::get<Unsupported>(result).diagnostics[0].field == "finite_plan_ellipsoid.safe_sets");
}

TEST_CASE("ellipsoid admission preserves horizon precedence over initial dimension errors") {
    auto input = points_request();
    input.disturbances.pop_back();
    input.initial = take(sets::make_universal({{"wrong-initial-dimension"}, 2, {}}));
    const auto result = finite_plan_ellipsoid(input);
    REQUIRE(std::holds_alternative<Unsupported>(result));
    const auto &diagnostic = std::get<Unsupported>(result).diagnostics[0];
    CHECK(diagnostic.field == "finite_plan_ellipsoid.horizon");
    CHECK(diagnostic.explanation ==
          "Controls, disturbances and safe sets must match the model horizon.");
}

TEST_CASE("ellipsoid admission reports initial and safe-set dimension mismatches") {
    auto bad_initial = points_request();
    bad_initial.initial = take(sets::make_universal({{"wrong-initial-dimension"}, 2, {}}));
    auto initial_result = finite_plan_ellipsoid(bad_initial);
    REQUIRE(std::holds_alternative<Unsupported>(initial_result));
    CHECK(std::get<Unsupported>(initial_result).diagnostics[0].field ==
          "finite_plan_ellipsoid.initial");

    auto bad_safe = points_request();
    bad_safe.admissible_states[1] = take(sets::make_universal({{"wrong-safe-dimension"}, 2, {}}));
    auto safe_result = finite_plan_ellipsoid(bad_safe);
    REQUIRE(std::holds_alternative<Unsupported>(safe_result));
    CHECK(std::get<Unsupported>(safe_result).diagnostics[0].field ==
          "finite_plan_ellipsoid.safe_sets");
}
