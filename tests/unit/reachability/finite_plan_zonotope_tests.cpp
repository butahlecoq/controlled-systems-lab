#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/reachability/finite_plan_zonotope.hpp>
#include <two_points_fixture.hpp>

#include <cmath>
#include <limits>

using namespace csl;
using namespace csl::reachability;

namespace {
template<class T> T take(std::variant<T, Diagnostic> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}

sets::SetData vertices(std::string id, std::size_t dimension, Matrix points) {
    return take(sets::make_v({{std::move(id)}, dimension, {}},
        {take(numeric::snapshot(points)), take(numeric::snapshot(Matrix{0,dimension,{}}))}));
}

sets::SetData universal(std::string id, std::size_t dimension = 1) {
    return take(sets::make_universal({{std::move(id)}, dimension, {}}));
}

FixedPlanRequest scalar_request() {
    SystemModel authored{{{1,1,1}, TimeDomain::discrete,
        LinearStage{{1,1,{1}}, {1,1,{0}}, {1,1,{1}}, {0}}}, {}};
    return {take(model::snapshot(authored, Vector{0,1,2})),
        vertices("initial", 1, Matrix{2,1,{0,1}}), {{0},{0}},
        {vertices("d0", 1, Matrix{2,1,{-1,1}}), vertices("d1", 1, Matrix{2,1,{-1,1}})},
        {universal("s0"), universal("s1"), universal("s2")}, {"zonotope-scalar"}};
}

FixedPlanRequest two_points_request() {
    const auto full = csl::issue824::fixture::two_points_request("two-points-zonotope");
    return {full.system, full.initial, {{-2.5},{-2.5},{-2.5}},
        full.disturbances, full.admissible_states, {"two-points-zonotope"}};
}

FixedPlanRequest planar_box_request() {
    SystemModel authored{{{2,1,2}, TimeDomain::discrete,
        LinearStage{{2,2,{2,0,0,1}}, {2,1,{0,0}}, {2,2,{0,0,0,0}}, {0,0}}}, {}};
    const auto system = take(model::snapshot(authored, Vector{0,1}));
    const auto initial = vertices("planar-initial", 2,
        Matrix{4,2,{-1,-1, 1,-1, 1,1, -1,1}});
    const auto disturbance = take(sets::make_singleton({{"planar-disturbance"},2,{}},
        take(numeric::snapshot_vector(Vector{0,0}))));
    return {system, initial, {{0}}, {disturbance},
        {universal("planar-safe-0",2), universal("planar-safe-1",2)}, {"zonotope-planar"}};
}

std::pair<double,double> coordinate_bounds(const FinitePlanZonotopeTrace::Stage& stage,
                                            std::size_t coordinate) {
    double radius = 0.0;
    for(std::size_t column = 0; column < stage.generators.cols; ++column)
        radius += std::abs(stage.generators.values[coordinate * stage.generators.cols + column]);
    return {std::nextafter(stage.center[coordinate] - radius,
               -std::numeric_limits<double>::infinity()),
            std::nextafter(stage.center[coordinate] + radius,
                std::numeric_limits<double>::infinity())};
}
}

TEST_CASE("scalar zonotope propagation encloses every exact finite disturbance history") {
    const auto input = scalar_request();
    const auto result = finite_plan_zonotope(input, {64});
    REQUIRE(std::holds_alternative<FinitePlanZonotopeTrace>(result));
    const auto& trace = std::get<FinitePlanZonotopeTrace>(result);
    const auto exact = fixed_plan_disturbance(input, 16);
    REQUIRE(std::holds_alternative<FixedPlanReachable>(exact));
    const auto& stages = std::get<FixedPlanReachable>(exact).stages;
    REQUIRE(trace.stages.size() == stages.size());
    for(std::size_t stage = 0; stage < stages.size(); ++stage) {
        const auto representation = stages[stage].representation();
        const auto* points = std::get_if<sets::VRepresentation>(&representation);
        REQUIRE(points != nullptr);
        const auto [lower, upper] = coordinate_bounds(trace.stages[stage], 0);
        for(std::size_t row = 0; row < points->vertices.rows(); ++row) {
            CHECK(lower <= points->vertices(row, 0));
            CHECK(upper >= points->vertices(row, 0));
        }
    }
}

TEST_CASE("planar box fixture has a complete axis-aligned inclusion check") {
    const auto input = planar_box_request();
    const auto result = finite_plan_zonotope(input, {64});
    REQUIRE(std::holds_alternative<FinitePlanZonotopeTrace>(result));
    const auto exact = fixed_plan_disturbance(input, 8);
    REQUIRE(std::holds_alternative<FixedPlanReachable>(exact));
    const auto& trace = std::get<FinitePlanZonotopeTrace>(result);
    const auto& stages = std::get<FixedPlanReachable>(exact).stages;
    REQUIRE(trace.stages.size() == stages.size());
    for(std::size_t stage = 0; stage < stages.size(); ++stage) {
        const auto representation = stages[stage].representation();
        const auto* points = std::get_if<sets::VRepresentation>(&representation);
        REQUIRE(points != nullptr);
        const auto& zonotope = trace.stages[stage];
        for(std::size_t coordinate = 0; coordinate < 2; ++coordinate) {
            const auto [lower, upper] = coordinate_bounds(zonotope, coordinate);
            for(std::size_t row = 0; row < points->vertices.rows(); ++row) {
                CHECK(lower <= points->vertices(row, coordinate));
                CHECK(upper >= points->vertices(row, coordinate));
            }
        }
        for(std::size_t column = 0; column < zonotope.generators.cols; ++column) {
            std::size_t nonzero_coordinates = 0;
            for(std::size_t coordinate = 0; coordinate < 2; ++coordinate)
                nonzero_coordinates += zonotope.generators.values[
                    coordinate * zonotope.generators.cols + column] != 0.0;
            CHECK(nonzero_coordinates <= 1);
        }
    }
}

TEST_CASE("the four-state TwoPoints pilot retains stagewise outer coordinate bounds") {
    const auto input = two_points_request();
    const auto result = finite_plan_zonotope(input, {64});
    REQUIRE(std::holds_alternative<FinitePlanZonotopeTrace>(result));
    const auto exact = fixed_plan_disturbance(input, 27);
    REQUIRE(std::holds_alternative<FixedPlanReachable>(exact));
    const auto& trace = std::get<FinitePlanZonotopeTrace>(result);
    const auto& stages = std::get<FixedPlanReachable>(exact).stages;
    REQUIRE(trace.stages.size() == stages.size());
    for(std::size_t stage = 0; stage < stages.size(); ++stage) {
        const auto representation = stages[stage].representation();
        const auto* points = std::get_if<sets::VRepresentation>(&representation);
        REQUIRE(points != nullptr);
        REQUIRE(trace.stages[stage].generators.cols == trace.stages[stage].factors.size());
        for(std::size_t coordinate = 0; coordinate < points->vertices.cols(); ++coordinate) {
            const auto [lower, upper] = coordinate_bounds(trace.stages[stage], coordinate);
            for(std::size_t row = 0; row < points->vertices.rows(); ++row) {
                CHECK(lower <= points->vertices(row, coordinate));
                CHECK(upper >= points->vertices(row, coordinate));
            }
        }
    }
}

TEST_CASE("zonotope propagation preserves unsupported state constraints") {
    auto input = scalar_request();
    input.admissible_states[1] = take(sets::make_h({{"bounded-safe"},1,{}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}})), take(numeric::snapshot_vector(Vector{2,2})),
         take(numeric::snapshot(Matrix{0,1,{}})), take(numeric::snapshot_vector(Vector{}))}));
    const auto result = finite_plan_zonotope(input, {64});
    REQUIRE(std::holds_alternative<Unsupported>(result));
    CHECK(std::get<Unsupported>(result).diagnostics[0].field == "finite_plan_zonotope.safe_sets");
}

TEST_CASE("zonotope generator growth stops explicitly at the caller limit") {
    const auto result = finite_plan_zonotope(scalar_request(), {2});
    REQUIRE(std::holds_alternative<Unsupported>(result));
    CHECK(std::get<Unsupported>(result).diagnostics[0].field ==
        "finite_plan_zonotope.generators.limit");
}
