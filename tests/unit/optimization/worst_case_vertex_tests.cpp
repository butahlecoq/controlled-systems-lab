#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/worst_case_vertex.hpp>

using namespace csl;

namespace {
template<class T> T take(std::variant<T, Diagnostic> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
template<class T> T take_objective(optimization::Result<T> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
sets::SetData points(std::string id, const Vector& values, std::size_t rows) {
    return take(sets::make_v({{std::move(id)}, 1, {"x"}},
        {take(numeric::snapshot(Matrix{rows, 1, values})),
         take(numeric::snapshot(Matrix{0, 1, {}}))}));
}
}

TEST_CASE("global convex worst case uses the endpoints, not the stationary midpoint") {
    const auto domain = points("interval", {0, 1, 2}, 3);
    const auto objective = take_objective(optimization::snapshot(
        QuadraticTerminal{{1, 1, {2}}, {-2}, 1}));
    const auto result = optimization::worst_case_vertex(domain, objective, 3);
    REQUIRE(std::holds_alternative<optimization::WorstCaseValue>(result));
    const auto& value = std::get<optimization::WorstCaseValue>(result);
    CHECK(value.value == doctest::Approx(1));
    CHECK(value.maximizer == Vector{0});
    CHECK(value.evaluated_vertices == 3);
}

TEST_CASE("empty and unbounded sets never publish a finite global worst case") {
    const auto objective = take_objective(optimization::snapshot(LinearTerminal{{1},0}));
    const auto empty = take(sets::make_empty({{"empty"},1,{"x"}}));
    CHECK(std::holds_alternative<optimization::WorstCaseEmpty>(
        optimization::worst_case_vertex(empty,objective,3)));
    const auto unbounded = take(sets::make_v({{"ray"},1,{"x"}},
        {take(numeric::snapshot(Matrix{1,1,{0}})),
         take(numeric::snapshot(Matrix{1,1,{1}}))}));
    CHECK(std::holds_alternative<Unsupported>(
        optimization::worst_case_vertex(unbounded,objective,3)));
}

TEST_CASE("capacity and unsupported representation reject before a value is published") {
    const auto objective = take_objective(optimization::snapshot(LinearTerminal{{1},0}));
    const auto domain = points("interval", {0, 2}, 2);
    CHECK(std::holds_alternative<Unsupported>(
        optimization::worst_case_vertex(domain,objective,1)));
    const auto h = take(sets::make_h({{"h"},1,{"x"}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}})),
         take(numeric::snapshot_vector(Vector{2,0})),
         take(numeric::snapshot(Matrix{0,1,{}})),
         take(numeric::snapshot_vector(Vector{}))}));
    CHECK(std::holds_alternative<Unsupported>(
        optimization::worst_case_vertex(h,objective,3)));
}

TEST_CASE("lower dimensional convex sets and singleton extrema retain their finite value") {
    const auto singleton=take(sets::make_singleton({{"one"},1,{"x"}},
        take(numeric::snapshot_vector(Vector{2}))));
    const auto objective=take_objective(optimization::snapshot(LinearTerminal{{3},1}));
    const auto result=optimization::worst_case_vertex(singleton,objective,1);
    REQUIRE(std::holds_alternative<optimization::WorstCaseValue>(result));
    CHECK(std::get<optimization::WorstCaseValue>(result).value==7);
    CHECK(std::get<optimization::WorstCaseValue>(result).maximizer==Vector{2});
}
