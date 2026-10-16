#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/finite_action_minimax.hpp>

using namespace csl;
using namespace csl::optimization;

namespace {
template<class T> T take(std::variant<T, Diagnostic> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
FiniteActionMinimaxRequest request(Vector actions = {0,1}, double safe_bound = 10) {
    const SystemModel authored{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,1,{1}},{0}}},{}};
    const auto system=take(model::snapshot(authored,Vector{0,1}));
    const auto initial=take(sets::make_singleton({{"x0"},1,{"x"}},
        take(numeric::snapshot_vector(Vector{0}))));
    const auto disturbance=take(sets::make_v({{"w"},1,{"w"}},
        {take(numeric::snapshot(Matrix{2,1,{0,2}})),
         take(numeric::snapshot(Matrix{0,1,{}}))}));
    const auto safe=take(sets::make_h({{"safe"},1,{"x"}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}})),
         take(numeric::snapshot_vector(Vector{safe_bound,safe_bound})),
         take(numeric::snapshot(Matrix{0,1,{}})),
         take(numeric::snapshot_vector(Vector{}))}));
    auto objective=std::get<Objective>(snapshot(QuadraticTerminal{{1,1,{2}},{-2},1}));
    std::vector<Vector> catalogue;
    for(double action:actions) catalogue.push_back({action});
    return {{"finite-example"},{"run-one"},system,initial,{1,std::move(catalogue)},
        {disturbance},{safe,safe},objective};
}
}

TEST_CASE("finite action minimax compares complete adversarial maxima and retains plan evidence") {
    const auto outcome=finite_action_minimax(request(),{2,2,0});
    REQUIRE(std::holds_alternative<FiniteMinimaxOptimal>(outcome));
    const auto& result=std::get<FiniteMinimaxOptimal>(outcome);
    CHECK(result.problem==ProblemId{"finite-example"});
    CHECK(result.request==RequestId{"run-one"});
    CHECK(result.value==1);
    CHECK(result.assurance==Assurance::numerical);
    CHECK(result.minimizing_plan_indices==std::vector<std::size_t>{0});
    REQUIRE(result.plans.size()==2);
    const auto& first=std::get<FinitePlanFeasible>(result.plans[0]);
    CHECK(first.action_indices==std::vector<std::size_t>{0});
    CHECK(first.worst_value==1);
    CHECK(first.maximizer==Vector{0});
    CHECK(first.evaluated_vertices==2);
    const auto& vertices=std::get<sets::VRepresentation>(first.terminal.representation()).vertices;
    REQUIRE(vertices.rows()==2);
    CHECK(vertices(0,0)==0);
    CHECK(vertices(1,0)==2);
    const auto& second=std::get<FinitePlanFeasible>(result.plans[1]);
    CHECK(second.action_indices==std::vector<std::size_t>{1});
    CHECK(second.worst_value==4);
    CHECK(second.maximizer==Vector{3});
}

TEST_CASE("duplicate catalogue rows remain separate tied plans") {
    const auto outcome=finite_action_minimax(request({0,0}),{2,2,0});
    REQUIRE(std::holds_alternative<FiniteMinimaxOptimal>(outcome));
    const auto& result=std::get<FiniteMinimaxOptimal>(outcome);
    CHECK(result.value==1);
    CHECK(result.minimizing_plan_indices==std::vector<std::size_t>{0,1});
    CHECK(std::get<FinitePlanFeasible>(result.plans[0]).terminal.metadata()->id !=
          std::get<FinitePlanFeasible>(result.plans[1]).terminal.metadata()->id);
}

TEST_CASE("all robust violations yield whole catalogue infeasible evidence") {
    const auto outcome=finite_action_minimax(request({0,1},0.5),{2,2,0});
    REQUIRE(std::holds_alternative<FiniteMinimaxInfeasible>(outcome));
    const auto& result=std::get<FiniteMinimaxInfeasible>(outcome);
    CHECK(result.problem==ProblemId{"finite-example"});
    REQUIRE(result.rejected_plans.size()==2);
    CHECK(result.rejected_plans[0].action_indices==std::vector<std::size_t>{0});
    CHECK(result.rejected_plans[0].stage==1);
    CHECK(result.rejected_plans[0].violating_successor==Vector{2});
    CHECK(result.rejected_plans[1].action_indices==std::vector<std::size_t>{1});
    CHECK(result.rejected_plans[1].violating_successor==Vector{1});
}

TEST_CASE("empty catalogue and absent adversarial paths have distinct statuses") {
    CHECK(std::holds_alternative<FiniteMinimaxEmptyCatalogue>(
        finite_action_minimax(request({}),{2,2,0})));
    auto empty=request();
    empty.disturbances[0]=take(sets::make_empty({{"empty-w"},1,{"w"}}));
    CHECK(std::holds_alternative<FiniteMinimaxNoScenarios>(
        finite_action_minimax(empty,{2,2,0})));
}

TEST_CASE("empty scenarios cannot hide invalid later inputs or cancellation") {
    auto input=request();
    input.initial=take(sets::make_empty({{"empty-x0"},1,{"x"}}));
    input.disturbances[0]=take(sets::make_v({{"unbounded-w"},1,{"w"}},
        {take(numeric::snapshot(Matrix{1,1,{0}})),
         take(numeric::snapshot(Matrix{1,1,{1}}))}));
    const auto rejected=finite_action_minimax(input,{2,2,0});
    REQUIRE(std::holds_alternative<Unsupported>(rejected));
    CHECK(std::get<Unsupported>(rejected).diagnostics[0].field=="fixed_plan.bounded");

    input.disturbances[0]=take(sets::make_empty({{"empty-w"},1,{"w"}}));
    std::stop_source cancellation;
    cancellation.request_stop();
    ExecutionContext context{};
    context.cancellation=cancellation.get_token();
    const auto stopped=finite_action_minimax(input,{2,2,0},context);
    REQUIRE(std::holds_alternative<OperationStopped>(stopped));
    CHECK(std::get<OperationStopped>(stopped).reason==StopReason::cancelled);
}

TEST_CASE("a later empty disturbance is not masked by an earlier robust violation") {
    auto input=request({0},0.5);
    const SystemModel authored{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,1,{1}},{0}}},{}};
    input.system=take(model::snapshot(authored,Vector{0,1,2}));
    input.disturbances.push_back(take(sets::make_empty({{"empty-w1"},1,{"w"}})));
    input.admissible_states.push_back(input.admissible_states.back());
    CHECK(std::holds_alternative<FiniteMinimaxNoScenarios>(
        finite_action_minimax(input,{1,2,0})));
}

TEST_CASE("zero horizon has one empty action plan even with an empty catalogue") {
    auto input=request({});
    const SystemModel authored{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,1,{1}},{0}}},{}};
    input.system=take(model::snapshot(authored,Vector{0}));
    input.disturbances.clear();
    input.admissible_states.erase(input.admissible_states.begin()+1,
                                  input.admissible_states.end());
    const auto outcome=finite_action_minimax(input,{1,1,0});
    REQUIRE(std::holds_alternative<FiniteMinimaxOptimal>(outcome));
    const auto& result=std::get<FiniteMinimaxOptimal>(outcome);
    CHECK(result.value==1);
    CHECK(result.minimizing_plan_indices==std::vector<std::size_t>{0});
    CHECK(std::get<FinitePlanFeasible>(result.plans[0]).action_indices.empty());
}

TEST_CASE("capacity and unsupported representation never publish a completed optimum") {
    CHECK(std::holds_alternative<Unsupported>(finite_action_minimax(request(),{1,2,0})));
    auto unsupported=request();
    unsupported.disturbances[0]=take(sets::make_v({{"unbounded-w"},1,{"w"}},
        {take(numeric::snapshot(Matrix{1,1,{0}})),
         take(numeric::snapshot(Matrix{1,1,{1}}))}));
    CHECK(std::holds_alternative<Unsupported>(finite_action_minimax(unsupported,{2,2,0})));
    auto unsupported_safe=request({0,1},0.5);
    unsupported_safe.admissible_states[1]=take(sets::make_v({{"v-safe"},1,{"x"}},
        {take(numeric::snapshot(Matrix{2,1,{-1,1}})),
         take(numeric::snapshot(Matrix{0,1,{}}))}));
    CHECK(std::holds_alternative<Unsupported>(
        finite_action_minimax(unsupported_safe,{2,2,0})));
    CHECK(std::holds_alternative<Unsupported>(finite_action_minimax(request(),{2,2,-1})));
}

TEST_CASE("a cancelled catalogue search returns no partial optimum") {
    std::stop_source cancellation;
    cancellation.request_stop();
    ExecutionContext context{};
    context.cancellation=cancellation.get_token();
    const auto result=finite_action_minimax(request(),{2,2,0},context);
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::cancelled);
}

TEST_CASE("rounded B08 catalogue yields the full numerical finite-plan reference") {
    const SystemModel authored{{{4,1,2},TimeDomain::discrete,
        LinearStage{{4,4,{1,0,0,0,-25,1,0,0,0,0,1,0,0,0,-25,1}},
                    {4,1,{20.073,0,-10.473,0}},
                    {4,2,{1,0,0,0,0,-1,0,0}}, {0,0,0,0}}},{}};
    const auto system=take(model::snapshot(authored,Vector{0,1,2,3,4}));
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
    const auto objective=std::get<Objective>(snapshot(
        ResidualNormTerminal{{4,4,{1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1}},
                             {1200,0,450,0}}));
    const FiniteActionMinimaxRequest input{{"b08-rounded"},{"b08-enumeration"},
        system,initial,{1,{{0.6},{0.3},{0},{-0.3},{-0.6}}},
        disturbances,safe_sets,objective};
    const auto outcome=finite_action_minimax(input,{625,256,1e-8});
    REQUIRE(std::holds_alternative<FiniteMinimaxOptimal>(outcome));
    const auto& result=std::get<FiniteMinimaxOptimal>(outcome);
    CHECK(result.value==doctest::Approx(67.150601101407).epsilon(1e-10));
    CHECK(result.plans.size()==625);
    CHECK(result.minimizing_plan_indices==std::vector<std::size_t>{17,33,129});
    for(const auto& record:result.plans) {
        REQUIRE(std::holds_alternative<FinitePlanFeasible>(record));
        CHECK(std::get<FinitePlanFeasible>(record).evaluated_vertices==256);
    }
    for(const auto index:result.minimizing_plan_indices) {
        const auto& plan=std::get<FinitePlanFeasible>(result.plans[index]);
        CHECK(plan.evaluated_vertices==256);
        CHECK(plan.worst_value==doctest::Approx(67.150601101407).epsilon(1e-10));
    }
}
