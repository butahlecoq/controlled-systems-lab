#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/reachability/fixed_plan_disturbance.hpp>
#include <csl/optimization/worst_case_vertex.hpp>
#include <cmath>
#include <limits>

using namespace csl;
using namespace csl::reachability;

namespace {
template<class T> T take(std::variant<T, Diagnostic> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
sets::SetData interval(std::string id,double lo,double hi,std::string label) {
    return take(sets::make_v({{std::move(id)},1,{std::move(label)}},
        {take(numeric::snapshot(Matrix{2,1,{lo,hi}})),take(numeric::snapshot(Matrix{0,1,{}}))}));
}
sets::SetData safe(double lo,double hi) {
    return take(sets::make_h({{"safe"},1,{"x"}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}})),take(numeric::snapshot_vector(Vector{hi,-lo})),
         take(numeric::snapshot(Matrix{0,1,{}})),take(numeric::snapshot_vector(Vector{}))}));
}
FixedPlanRequest request(double intermediate_bound) {
    SystemModel authored{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,1,{1}},{0}}},{}};
    const Vector times{0,1,2};
    return {take(model::snapshot(authored,times)),
        take(sets::make_singleton({{"x0"},1,{"x"}},take(numeric::snapshot_vector(Vector{0})))),
        {{0},{0}}, {interval("w0",-1,1,"w"),interval("w1",-1,1,"w")},
        {safe(-3,3),safe(-intermediate_bound,intermediate_bound),safe(-3,3)},
        {"unit-plan"}};
}
}

TEST_CASE("fixed plan propagates every disturbance history and scores the global terminal worst case") {
    const auto result=fixed_plan_disturbance(request(3),8);
    REQUIRE(std::holds_alternative<FixedPlanReachable>(result));
    const auto& tube=std::get<FixedPlanReachable>(result);
    REQUIRE(tube.stages.size()==3);
    CHECK(tube.assurance==Assurance::numerical);
    const auto rep=tube.stages.back().representation();
    const auto& v=std::get<sets::VRepresentation>(rep);
    REQUIRE(v.vertices.rows()==4);
    CHECK(v.vertices(0,0)==-2);
    CHECK(v.vertices(1,0)==0);
    CHECK(v.vertices(2,0)==0);
    CHECK(v.vertices(3,0)==2);
    const auto objective=std::get<optimization::Objective>(optimization::snapshot(
        QuadraticTerminal{{1,1,{2}},{0},0}));
    const auto worst=optimization::worst_case_vertex(tube.stages.back(),objective,8);
    REQUIRE(std::holds_alternative<optimization::WorstCaseValue>(worst));
    CHECK(std::get<optimization::WorstCaseValue>(worst).value==4);
}

TEST_CASE("a nonempty clipped intersection does not make a fixed plan robustly feasible") {
    const auto result=fixed_plan_disturbance(request(0.5),8);
    REQUIRE(std::holds_alternative<FixedPlanViolation>(result));
    const auto& violation=std::get<FixedPlanViolation>(result);
    CHECK(violation.stage==1);
    CHECK(violation.violating_successor==Vector{-1});
}

TEST_CASE("point budget rejects growth without publishing a truncated reachable set") {
    const auto result=fixed_plan_disturbance(request(3),2);
    REQUIRE(std::holds_alternative<Unsupported>(result));
    CHECK(std::get<Unsupported>(result).diagnostics[0].field=="fixed_plan.capacity");
}

TEST_CASE("distinct fixed-plan requests cannot reuse reachable set identities") {
    auto first=request(3);
    auto second=request(3);
    first.request={"plan-a"};
    second.request={"plan-b"};
    second.controls[0]={1};
    const auto left=fixed_plan_disturbance(first,8);
    const auto right=fixed_plan_disturbance(second,8);
    REQUIRE(std::holds_alternative<FixedPlanReachable>(left));
    REQUIRE(std::holds_alternative<FixedPlanReachable>(right));
    CHECK(std::get<FixedPlanReachable>(left).stages.back().metadata()->id !=
          std::get<FixedPlanReachable>(right).stages.back().metadata()->id);
}

TEST_CASE("all catalogued fixed plans are robustly infeasible under a narrow safe set") {
    for(const double control:Vector{-1,0,1}) {
        auto plan=request(0.5);
        plan.controls[0]={control};
        const auto result=fixed_plan_disturbance(plan,8);
        REQUIRE(std::holds_alternative<FixedPlanViolation>(result));
        CHECK(std::get<FixedPlanViolation>(result).stage==1);
    }
}

TEST_CASE("later unsupported data takes precedence over an earlier robust violation") {
    auto plan=request(3);
    plan.admissible_states[0]=safe(1,2); // x0=0 already violates this set.
    plan.disturbances[1]=take(sets::make_v({{"unbounded-w1"},1,{"w"}},
        {take(numeric::snapshot(Matrix{1,1,{0}})),
         take(numeric::snapshot(Matrix{1,1,{1}}))}));
    const auto unbounded=fixed_plan_disturbance(plan,8);
    REQUIRE(std::holds_alternative<Unsupported>(unbounded));
    CHECK(std::get<Unsupported>(unbounded).diagnostics[0].field=="fixed_plan.bounded");

    plan.disturbances[1]=interval("w1",-1,1,"w");
    plan.admissible_states[2]=interval("unsupported-safe",-3,3,"x");
    const auto later_safe=fixed_plan_disturbance(plan,8);
    REQUIRE(std::holds_alternative<Unsupported>(later_safe));
    CHECK(std::get<Unsupported>(later_safe).diagnostics[0].field=="fixed_plan.safe.representation");

    plan.admissible_states[2]=safe(-3,3);
    const auto later_capacity=fixed_plan_disturbance(plan,2);
    REQUIRE(std::holds_alternative<Unsupported>(later_capacity));
    CHECK(std::get<Unsupported>(later_capacity).diagnostics[0].field=="fixed_plan.capacity");
}

TEST_CASE("B08 displayed rounded model gives the independent finite-plan reference") {
    SystemModel authored{{{4,1,2},TimeDomain::discrete,
        LinearStage{{4,4,{1,0,0,0,-25,1,0,0,0,0,1,0,0,0,-25,1}},
                    {4,1,{20.073,0,-10.473,0}},
                    {4,2,{1,0,0,0,0,-1,0,0}}, {0,0,0,0}}},{}};
    const Vector times{0,1,2,3,4};
    const auto system=take(model::snapshot(authored,times));
    const auto initial=take(sets::make_singleton({{"b08-x0"},4,{}},
        take(numeric::snapshot_vector(Vector{1182.074,119560,459.832,45260}))));
    std::vector<sets::SetData> disturbances;
    for(std::size_t stage=0;stage<4;++stage) {
        const double a=0.1+0.1*stage,b=0.1+0.3*stage;
        disturbances.push_back(take(sets::make_v({{"b08-w"+std::to_string(stage)},2,{}},
            {take(numeric::snapshot(Matrix{4,2,{-a,-b,-a,b,a,-b,a,b}})),
             take(numeric::snapshot(Matrix{0,2,{}}))})));
    }
    std::vector<sets::SetData> safe_sets;
    for(std::size_t stage=0;stage<5;++stage)
        safe_sets.push_back(take(sets::make_universal({{"b08-safe"+std::to_string(stage)},4,{}})));
    const auto objective=std::get<optimization::Objective>(optimization::snapshot(
        ResidualNormTerminal{{4,4,{1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1}},
                             {1200,0,450,0}}));
    const Vector actions{0.6,0.3,0,-0.3,-0.6};
    double best=std::numeric_limits<double>::infinity();
    std::size_t ties=0;
    std::size_t plan_number=0;
    for(const auto u0:actions)for(const auto u1:actions)
      for(const auto u2:actions)for(const auto u3:actions) {
        const FixedPlanRequest plan{system,initial,{{u0},{u1},{u2},{u3}},disturbances,safe_sets,
                                    {"b08-plan-"+std::to_string(plan_number++)}};
        const auto propagated=fixed_plan_disturbance(plan,256);
        REQUIRE(std::holds_alternative<FixedPlanReachable>(propagated));
        const auto worst=optimization::worst_case_vertex(
            std::get<FixedPlanReachable>(propagated).stages.back(),objective,256);
        REQUIRE(std::holds_alternative<optimization::WorstCaseValue>(worst));
        const auto value=std::get<optimization::WorstCaseValue>(worst).value;
        if(value<best-1e-8) {best=value;ties=1;}
        else if(std::abs(value-best)<=1e-8)++ties;
    }
    CHECK(best==doctest::Approx(67.150601101407).epsilon(1e-10));
    CHECK(ties==3);
}
