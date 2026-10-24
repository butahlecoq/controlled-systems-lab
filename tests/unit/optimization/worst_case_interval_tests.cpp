#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/worst_case_interval.hpp>
#include <cfenv>

using namespace csl;

namespace {
template<class T> T take(std::variant<T,Diagnostic> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
template<class T> T take_objective(optimization::Result<T> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
sets::SetData points(std::string id,const Vector& values,std::size_t rows) {
    return take(sets::make_v({{std::move(id)},1,{"x"}},
        {take(numeric::snapshot(Matrix{rows,1,values})),
         take(numeric::snapshot(Matrix{0,1,{}}))}));
}
optimization::WorstCaseIntervalRequest request(sets::SetData domain,
        optimization::Objective objective,std::string id="bound") {
    return {{"problem"},{std::move(id)},std::move(domain),std::move(objective),16};
}
}

TEST_CASE("outward bounds enclose the exact linear maximum on the stored convex hull") {
    auto domain=points("interval",{0,2},2);
    auto objective=take_objective(optimization::snapshot(LinearTerminal{{1},0}));
    const auto result=optimization::worst_case_interval(request(domain,objective));
    REQUIRE(std::holds_alternative<optimization::WorstCaseIntervalBounds>(result));
    const auto& bounds=std::get<optimization::WorstCaseIntervalBounds>(result);
    CHECK(bounds.problem()==ProblemId{"problem"});
    CHECK(bounds.request()==RequestId{"bound"});
    CHECK(bounds.domain()==SetId{"interval"});
    CHECK(bounds.lower()<=2.0);
    CHECK(bounds.upper()>=2.0);
    CHECK(bounds.upper()-bounds.lower()<1e-12);
}

TEST_CASE("quadratic box enclosure covers the L19 endpoint maximum despite dependency widening") {
    const auto domain=points("l19-interval",{0,1,2},3);
    const auto objective=take_objective(optimization::snapshot(
        QuadraticTerminal{{1,1,{2}},{-2},1}));
    const auto result=optimization::worst_case_interval(request(domain,objective));
    REQUIRE(std::holds_alternative<optimization::WorstCaseIntervalBounds>(result));
    const auto& bounds=std::get<optimization::WorstCaseIntervalBounds>(result);
    // Exact polynomial values at stored endpoints are both 1. Natural interval
    // evaluation over [0,2] is conservative because it loses x*x / x dependency.
    CHECK(bounds.lower()<=1.0);
    CHECK(bounds.upper()>=1.0);
    CHECK(bounds.upper()<=5.0+1e-12);
}

TEST_CASE("residual norm bound covers every point in the convex hull") {
    const auto domain=points("residual-interval",{0,2},2);
    const auto objective=take_objective(optimization::snapshot(
        ResidualNormTerminal{{1,1,{1}},{1}}));
    const auto result=optimization::worst_case_interval(request(domain,objective));
    REQUIRE(std::holds_alternative<optimization::WorstCaseIntervalBounds>(result));
    const auto& bounds=std::get<optimization::WorstCaseIntervalBounds>(result);
    CHECK(bounds.lower()<=1.0);
    CHECK(bounds.upper()>=1.0);
    CHECK(bounds.upper()-bounds.lower()<1e-12);
}

TEST_CASE("singleton extrema and empty or unbounded domains retain distinct outcomes") {
    const auto objective=take_objective(optimization::snapshot(LinearTerminal{{3},1}));
    const auto singleton=take(sets::make_singleton({{"point"},1,{"x"}},
        take(numeric::snapshot_vector(Vector{2}))));
    const auto singleton_result=optimization::worst_case_interval(
        request(singleton,objective,"singleton-run"));
    REQUIRE(std::holds_alternative<optimization::WorstCaseIntervalBounds>(singleton_result));
    CHECK(std::get<optimization::WorstCaseIntervalBounds>(singleton_result).lower()<=7.0);
    CHECK(std::get<optimization::WorstCaseIntervalBounds>(singleton_result).upper()>=7.0);
    const auto empty=take(sets::make_empty({{"empty"},1,{"x"}}));
    CHECK(std::holds_alternative<optimization::WorstCaseIntervalEmpty>(
        optimization::worst_case_interval(request(empty,objective))));
    const auto ray=take(sets::make_v({{"ray"},1,{"x"}},
        {take(numeric::snapshot(Matrix{1,1,{0}})),
         take(numeric::snapshot(Matrix{1,1,{1}}))}));
    CHECK(std::holds_alternative<Unsupported>(
        optimization::worst_case_interval(request(ray,objective))));
}

TEST_CASE("interval bound admission preserves capacity and identity failures") {
    const auto domain=points("two",{0,2},2);
    const auto objective=take_objective(optimization::snapshot(LinearTerminal{{1},0}));
    auto limited=request(domain,objective);
    limited.max_vertices=1;
    CHECK(std::holds_alternative<Unsupported>(optimization::worst_case_interval(limited)));
    auto unidentified=request(domain,objective);
    unidentified.request={};
    CHECK(std::holds_alternative<Unsupported>(optimization::worst_case_interval(unidentified)));
}

TEST_CASE("interval bounds reject a non-default hardware rounding mode") {
    const auto domain=points("rounding-mode",{0,2},2);
    const auto objective=take_objective(optimization::snapshot(LinearTerminal{{1},0}));
    const int previous=std::fegetround();
    REQUIRE(std::fesetround(FE_DOWNWARD)==0);
    const auto result=optimization::worst_case_interval(request(domain,objective));
    CHECK(std::holds_alternative<OperationStopped>(result));
    CHECK(std::fesetround(previous)==0);
}
