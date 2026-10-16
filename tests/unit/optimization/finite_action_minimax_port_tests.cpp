#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/finite_action_minimax_port.hpp>

using namespace csl;
using namespace csl::optimization;
using namespace csl::registry;

namespace {
template<class T> T take(std::variant<T,Diagnostic> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
FiniteActionMinimaxQuery query() {
    const SystemModel authored{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,1,{1}},{0}}},{}};
    auto system=take(model::snapshot(authored,Vector{0,1}));
    auto initial=take(sets::make_singleton({{"x0"},1,{"x"}},
        take(numeric::snapshot_vector(Vector{0}))));
    auto disturbance=take(sets::make_v({{"w"},1,{"w"}},
        {take(numeric::snapshot(Matrix{2,1,{0,2}})),
         take(numeric::snapshot(Matrix{0,1,{}}))}));
    auto safe=take(sets::make_h({{"safe"},1,{"x"}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}})),
         take(numeric::snapshot_vector(Vector{10,10})),
         take(numeric::snapshot(Matrix{0,1,{}})),
         take(numeric::snapshot_vector(Vector{}))}));
    auto objective=std::get<Objective>(snapshot(QuadraticTerminal{{1,1,{2}},{-2},1}));
    return {{{"finite-example"},{"run-one"},system,initial,{1,{{0},{1}}},
        {disturbance},{safe,safe},objective},{2,2,0}};
}
Method method() {return {{"csl.optimization.finite-action-minimax"},"1.0.0"};}
FiniteActionMinimaxOutcome run(Registry<FiniteActionMinimaxPort>& registry,
        const FiniteActionMinimaxQuery& input,const ExecutionContext& context={}) {
    auto selected=prepare_pipeline(select(registry,method(),input,finite_action_minimax_requirements()));
    REQUIRE(std::holds_alternative<PreparedPipeline<FiniteActionMinimaxPort>>(selected));
    auto workspace=std::get<0>(std::get<PreparedPipeline<FiniteActionMinimaxPort>>(selected).create());
    return workspace->run(context);
}
class WrongIdentityWorkspace final : public FiniteActionMinimaxWorkspace {
public:
    FiniteActionMinimaxOutcome solve(const FiniteActionMinimaxQuery& input,
        const ExecutionContext& context) override {
        auto answer=finite_action_minimax(input.request,input.limits,context);
        if(auto* optimal=std::get_if<FiniteMinimaxOptimal>(&answer))optimal->request={"stale-run"};
        return answer;
    }
};
}

TEST_CASE("registered numerical oracle retains the scalar optimum, plan replay and selected identity") {
    Registry<FiniteActionMinimaxPort> registry;
    REQUIRE_FALSE(registry.add(make_finite_action_minimax_registration()).has_value());
    auto input=query();
    auto selected=prepare_pipeline(select(registry,method(),input,finite_action_minimax_requirements()));
    REQUIRE(std::holds_alternative<PreparedPipeline<FiniteActionMinimaxPort>>(selected));
    auto pipeline=std::get<PreparedPipeline<FiniteActionMinimaxPort>>(std::move(selected));
    const auto provenance=pipeline.provenance()[0];
    CHECK(provenance.port=="finite-action-minimax");
    CHECK(provenance.requested.id==method().id);
    CHECK(provenance.requested.version==method().version);
    REQUIRE(provenance.actual.has_value());
    CHECK(provenance.actual->id==method().id);
    CHECK(provenance.actual->version=="1.0.0");
    auto workspace=std::get<0>(pipeline.create());
    input.request.request={"mutated-after-prepare"};
    input.request.actions.catalogue={{9}};
    auto outcome=workspace->run({});
    REQUIRE(std::holds_alternative<FiniteMinimaxOptimal>(outcome));
    const auto& result=std::get<FiniteMinimaxOptimal>(outcome);
    CHECK(result.problem==ProblemId{"finite-example"});
    CHECK(result.request==RequestId{"run-one"});
    CHECK(result.value==1);
    CHECK(result.assurance==Assurance::numerical);
    CHECK(result.minimizing_plan_indices==std::vector<std::size_t>{0});
    REQUIRE(result.plans.size()==2);
    CHECK(std::get<FinitePlanFeasible>(result.plans[0]).worst_value==1);
    CHECK(std::get<FinitePlanFeasible>(result.plans[1]).worst_value==4);
    std::stop_source stop;
    stop.request_stop();
    ExecutionContext cancelled{};
    cancelled.cancellation=stop.get_token();
    const auto stopped=workspace->run(cancelled);
    REQUIRE(std::holds_alternative<OperationStopped>(stopped));
    CHECK(std::get<OperationStopped>(stopped).reason==StopReason::cancelled);
    CHECK(std::holds_alternative<FiniteMinimaxOptimal>(workspace->run({})));
}

TEST_CASE("fresh workspaces and repeated runs do not reuse an earlier result") {
    Registry<FiniteActionMinimaxPort> registry;
    REQUIRE_FALSE(registry.add(make_finite_action_minimax_registration()).has_value());
    auto first=query();
    auto second=query();
    second.request.request={"run-two"};
    second.request.actions.catalogue={{1}};
    auto first_result=run(registry,first);
    auto second_result=run(registry,second);
    REQUIRE(std::holds_alternative<FiniteMinimaxOptimal>(first_result));
    REQUIRE(std::holds_alternative<FiniteMinimaxOptimal>(second_result));
    CHECK(std::get<FiniteMinimaxOptimal>(first_result).request==RequestId{"run-one"});
    CHECK(std::get<FiniteMinimaxOptimal>(second_result).request==RequestId{"run-two"});
    CHECK(std::get<FiniteMinimaxOptimal>(second_result).value==4);
    std::stop_source stop;
    stop.request_stop();
    ExecutionContext cancelled{};
    cancelled.cancellation=stop.get_token();
    CHECK(std::holds_alternative<OperationStopped>(run(registry,second,cancelled)));
    CHECK(std::get<FiniteMinimaxOptimal>(first_result).value==1);
}

TEST_CASE("all distinct solver statuses survive registered execution") {
    Registry<FiniteActionMinimaxPort> registry;
    REQUIRE_FALSE(registry.add(make_finite_action_minimax_registration()).has_value());
    auto input=query();
    input.request.admissible_states[1]=take(sets::make_empty({{"unsafe"},1,{"x"}}));
    auto infeasible=run(registry,input);
    REQUIRE(std::holds_alternative<FiniteMinimaxInfeasible>(infeasible));
    CHECK(std::get<FiniteMinimaxInfeasible>(infeasible).rejected_plans.size()==2);
    input.request.actions.catalogue.clear();
    CHECK(std::holds_alternative<FiniteMinimaxEmptyCatalogue>(run(registry,input)));
    input=query();
    input.request.disturbances[0]=take(sets::make_empty({{"no-w"},1,{"w"}}));
    CHECK(std::holds_alternative<FiniteMinimaxNoScenarios>(run(registry,input)));
    input=query();
    input.limits.max_plans=1;
    CHECK(std::holds_alternative<Unsupported>(run(registry,input)));
}

TEST_CASE("capability rejects out-of-scope inputs before workspace creation with provenance") {
    Registry<FiniteActionMinimaxPort> registry;
    auto entry=make_finite_action_minimax_registration();
    int created=0;
    auto factory=entry.factory;
    entry.factory=[&](const FiniteActionMinimaxQuery& input) {
        ++created;
        return factory(input);
    };
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    auto input=query();
    input.request.disturbances[0]=take(sets::make_h({{"h-w"},1,{"w"}},
        {take(numeric::snapshot(Matrix{1,1,{1}})),
         take(numeric::snapshot_vector(Vector{2})),
         take(numeric::snapshot(Matrix{0,1,{}})),
         take(numeric::snapshot_vector(Vector{}))}));
    auto rejected=prepare_pipeline(select(registry,method(),input,finite_action_minimax_requirements()));
    REQUIRE(std::holds_alternative<Rejection>(rejected));
    const auto& failure=std::get<Rejection>(rejected);
    CHECK(failure.provenance.requested.id==method().id);
    REQUIRE(failure.provenance.actual.has_value());
    CHECK(failure.provenance.actual->version=="1.0.0");
    CHECK(failure.diagnostics[0].field=="finite_minimax.disturbance.representation");
    CHECK(created==0);
    auto valid=query();
    auto required=finite_action_minimax_requirements();
    required.output.assurance=Assurance::validated;
    CHECK(std::holds_alternative<Rejection>(prepare_pipeline(select(registry,method(),valid,required))));
    auto wrong_version=prepare_pipeline(select(registry,
        Method{{"csl.optimization.finite-action-minimax"},"2.0.0"},
        valid,finite_action_minimax_requirements()));
    REQUIRE(std::holds_alternative<Rejection>(wrong_version));
    const auto& mismatch=std::get<Rejection>(wrong_version);
    CHECK(mismatch.provenance.requested.version==std::optional<std::string>{"2.0.0"});
    REQUIRE(mismatch.provenance.actual.has_value());
    CHECK(mismatch.provenance.actual->version=="1.0.0");
    CHECK(mismatch.diagnostics[0].field=="method.version");
    CHECK(created==0);
}

TEST_CASE("port rejects a completed result with another request identity") {
    auto input=query();
    WrongIdentityWorkspace workspace;
    const auto answer=FiniteActionMinimaxPort::run(workspace,input,{});
    REQUIRE(std::holds_alternative<Unsupported>(answer));
    CHECK(std::get<Unsupported>(answer).diagnostics[0].code==DiagnosticCode::evidence_mismatch);
}
