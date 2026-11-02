#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/reachability/finite_plan_box.hpp>
#include <two_points_fixture.hpp>

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
sets::SetData universal(std::string id) {
    return take(sets::make_universal({{std::move(id)}, 1, {"x"}}));
}
FixedPlanRequest request() {
    SystemModel authored{{{1,1,1}, TimeDomain::discrete,
        LinearStage{{1,1,{1}}, {1,1,{1}}, {1,1,{1}}, {0}}}, {}};
    const Vector times{0,1,2};
    return {take(model::snapshot(authored, times)), vertices("initial", 1, Matrix{2,1,{0,1}}),
        {{0},{0}}, {vertices("d0", 1, Matrix{2,1,{-1,1}}), vertices("d1", 1, Matrix{2,1,{-1,1}})},
        {universal("s0"), universal("s1"), universal("s2")}, {"box-test"}};
}
FixedPlanRequest two_points_request() {
    const auto full = csl::issue824::fixture::two_points_request("two-points-plan");
    return {full.system, full.initial, {{-2.5},{-2.5},{-2.5}},
        full.disturbances, full.admissible_states, {"two-points-plan"}};
}
}

TEST_CASE("fixed-plan interval boxes enclose every disturbance-history successor at each stage") {
    const auto result = finite_plan_box(request());
    REQUIRE(std::holds_alternative<FinitePlanBoxTrace>(result));
    const auto& trace = std::get<FinitePlanBoxTrace>(result);
    CHECK(trace.relation == SetRelation::outer);
    REQUIRE(trace.stages.size() == 3);
    CHECK(trace.stages[0].lower[0] <= 0.0);
    CHECK(trace.stages[0].upper[0] >= 1.0);
    CHECK(trace.stages[1].lower[0] <= -1.0);
    CHECK(trace.stages[1].upper[0] >= 2.0);
    CHECK(trace.stages[2].lower[0] <= -2.0);
    CHECK(trace.stages[2].upper[0] >= 3.0);
}

TEST_CASE("fixed-plan boxes preserve an unsupported safety-set request explicitly") {
    auto input = request();
    input.admissible_states[1] = take(sets::make_h({{"bounded-safe"},1,{"x"}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}})), take(numeric::snapshot_vector(Vector{2,2})),
         take(numeric::snapshot(Matrix{0,1,{}})), take(numeric::snapshot_vector(Vector{}))}));
    const auto result = finite_plan_box(input);
    REQUIRE(std::holds_alternative<Unsupported>(result));
    CHECK(std::get<Unsupported>(result).diagnostics[0].field == "finite_plan_box.safe_sets");
}

TEST_CASE("stagewise four-state boxes enclose the pinned TwoPoints finite-game reference") {
    const auto input = two_points_request();
    const auto boxed = finite_plan_box(input);
    REQUIRE(std::holds_alternative<FinitePlanBoxTrace>(boxed));
    const auto exact = fixed_plan_disturbance(input, 27);
    REQUIRE(std::holds_alternative<FixedPlanReachable>(exact));
    const auto& enclosure = std::get<FinitePlanBoxTrace>(boxed);
    CHECK(enclosure.relation == SetRelation::outer);
    const auto& tube = std::get<FixedPlanReachable>(exact);
    REQUIRE(enclosure.stages.size() == tube.stages.size());
    for(std::size_t stage = 0; stage < tube.stages.size(); ++stage) {
        const auto rep = tube.stages[stage].representation();
        const auto* points = std::get_if<sets::VRepresentation>(&rep);
        REQUIRE(points != nullptr);
        for(std::size_t row = 0; row < points->vertices.rows(); ++row)
            for(std::size_t col = 0; col < points->vertices.cols(); ++col) {
                CHECK(enclosure.stages[stage].lower[col] <= points->vertices(row,col));
                CHECK(enclosure.stages[stage].upper[col] >= points->vertices(row,col));
            }
    }
}
