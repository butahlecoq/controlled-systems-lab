#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/validated_finite_action_minimax_port.hpp>

using namespace csl;
using namespace csl::optimization;
using namespace csl::registry;

namespace {
template<class T> T take(std::variant<T,Diagnostic> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}

sets::SetData singleton(std::string id,double value) {
    return take(sets::make_singleton({{std::move(id)},1,{"x"}},
        take(numeric::snapshot_vector(Vector{value}))));
}

ValidatedFiniteActionMinimaxQuery query() {
    const SystemModel authored{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{0}},{1,1,{1}},{0}}}, {}};
    const auto system=take(model::snapshot(authored,Vector{0}));
    const auto universal=take(sets::make_universal({{"all"},1,{"x"}}));
    auto objective=optimization::snapshot(LinearTerminal{{1},0});
    REQUIRE(std::holds_alternative<optimization::Objective>(objective));
    ValidatedFiniteActionMinimaxRequest request{{"validated-problem"},{"validated-run"},
        system,singleton("x0",0),{1,{}},{},{universal},
        std::get<optimization::Objective>(std::move(objective))};
    return {std::move(request),{1,1,100}};
}

Method method() { return {{"csl.optimization.validated-finite-action-minimax"},"1.0.0"}; }

class RetainedWorkspace final : public ValidatedFiniteActionMinimaxWorkspace {
public:
    ValidatedFiniteActionMinimaxOutcome solve(const ValidatedFiniteActionMinimaxQuery& input,
            const ExecutionContext& context) override {
        return validated_finite_action_minimax(input.request,input.limits,context);
    }
};

enum class Tamper { bounds, infeasible, unresolved };
class WrongIdentityWorkspace final : public ValidatedFiniteActionMinimaxWorkspace {
public:
    explicit WrongIdentityWorkspace(Tamper kind):kind_(kind) {}
    ValidatedFiniteActionMinimaxOutcome solve(const ValidatedFiniteActionMinimaxQuery& input,
            const ExecutionContext& context) override {
        auto altered=input;
        altered.request.request={"other-run"};
        if(kind_==Tamper::infeasible)
            altered.request.safe_sets[0]=singleton("bad-point",1);
        if(kind_==Tamper::unresolved) {
            auto eq=take(sets::make_h({{"near-equality"},1,{"x"}},
                {take(numeric::snapshot(Matrix{0,1,{}})),
                 take(numeric::snapshot_vector(Vector{})),
                 take(numeric::snapshot(Matrix{1,1,{0.1}})),
                 take(numeric::snapshot_vector(Vector{0.01}))}));
            altered.request.initial=singleton("decimal-x0",0.1);
            altered.request.safe_sets[0]=std::move(eq);
        }
        return validated_finite_action_minimax(altered.request,altered.limits,context);
    }
private:
    Tamper kind_;
};
}

TEST_CASE("validated registration advertises only the validated bounds representation") {
    Registry<ValidatedFiniteActionMinimaxPort> registry;
    REQUIRE_FALSE(registry.add(make_validated_finite_action_minimax_registration()).has_value());
    const auto input=query();
    const auto requirements=validated_finite_action_minimax_requirements();
    CHECK(requirements.scalar==Scalar::binary64);
    CHECK(requirements.output.assurance==Assurance::validated);
    CHECK(requirements.output.representation==RepresentationId{
        "csl.optimization.validated-finite-action-minimax.bounds"});
    auto selected=prepare_pipeline(select(registry,method(),input,requirements));
    REQUIRE(std::holds_alternative<PreparedPipeline<ValidatedFiniteActionMinimaxPort>>(selected));
    auto pipeline=std::get<PreparedPipeline<ValidatedFiniteActionMinimaxPort>>(std::move(selected));
    const auto provenance=pipeline.provenance().at(0);
    CHECK(provenance.port=="validated-finite-action-minimax");
    CHECK(provenance.actual->version=="1.0.0");
    auto workspace=std::get<0>(pipeline.create());
    auto changed=input;
    changed.request.request={"mutated"};
    const auto result=workspace->run({});
    REQUIRE(std::holds_alternative<ValidatedMinimaxBounds>(result));
    CHECK(std::get<ValidatedMinimaxBounds>(result).request()==RequestId{"validated-run"});
}

TEST_CASE("registry admission rejects numerical assurance and over-limit catalogues") {
    Registry<ValidatedFiniteActionMinimaxPort> registry;
    auto entry=make_validated_finite_action_minimax_registration();
    int created=0;
    auto factory=entry.factory;
    entry.factory=[&](const ValidatedFiniteActionMinimaxQuery& input) {
        ++created;
        return factory(input);
    };
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    auto input=query();
    auto wrong=validated_finite_action_minimax_requirements();
    wrong.output.assurance=Assurance::numerical;
    auto rejected=prepare_pipeline(select(registry,method(),input,wrong));
    REQUIRE(std::holds_alternative<Rejection>(rejected));
    CHECK(std::get<Rejection>(rejected).diagnostics[0].field=="validated_minimax.requirements");
    CHECK(created==0);
    auto unsupported=query();
    const SystemModel authored{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{0}},{1,1,{1}},{0}}},{}};
    unsupported.request.system=take(model::snapshot(authored,Vector{0,1}));
    unsupported.request.disturbances={singleton("w",0)};
    unsupported.request.safe_sets={take(sets::make_universal({{"all0"},1,{"x"}})),
        take(sets::make_universal({{"all1"},1,{"x"}}))};
    unsupported.request.actions={{1},{{0},{1}}};
    unsupported.limits.max_plans=1;
    rejected=prepare_pipeline(select(registry,method(),unsupported,
        validated_finite_action_minimax_requirements()));
    REQUIRE(std::holds_alternative<Rejection>(rejected));
    CHECK(std::get<Rejection>(rejected).diagnostics[0].field=="validated_minimax.plans.limit");
    CHECK(created==0);
}

TEST_CASE("registry port rejects mismatched identity on every complete catalogue outcome") {
    const auto input=query();
    for(const auto kind:{Tamper::bounds,Tamper::infeasible,Tamper::unresolved}) {
        WrongIdentityWorkspace workspace{kind};
        const auto result=ValidatedFiniteActionMinimaxPort::run(workspace,input,{});
        REQUIRE(std::holds_alternative<Unsupported>(result));
        CHECK(std::get<Unsupported>(result).diagnostics[0].code==DiagnosticCode::evidence_mismatch);
        CHECK(std::get<Unsupported>(result).diagnostics[0].field=="validated_minimax.result.identity");
    }
}

TEST_CASE("empty and stopped status-only results survive registered execution") {
    auto input=query();
    Registry<ValidatedFiniteActionMinimaxPort> registry;
    REQUIRE_FALSE(registry.add(make_validated_finite_action_minimax_registration()).has_value());
    input.request.actions={{1},{}};
    input.request.system=take(model::snapshot(SystemModel{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{0}},{1,1,{1}},{0}}},{}},Vector{0,1}));
    input.request.disturbances={singleton("w",0)};
    input.request.safe_sets.resize(2,input.request.safe_sets[0]);
    auto selected=prepare_pipeline(select(registry,method(),input,
        validated_finite_action_minimax_requirements()));
    REQUIRE(std::holds_alternative<PreparedPipeline<ValidatedFiniteActionMinimaxPort>>(selected));
    auto workspace=std::get<0>(std::get<PreparedPipeline<ValidatedFiniteActionMinimaxPort>>(
        std::move(selected)).create());
    CHECK(std::holds_alternative<ValidatedMinimaxEmptyCatalogue>(workspace->run({})));
    input=query();
    input.limits.max_interval_operations=0;
    selected=prepare_pipeline(select(registry,method(),input,
        validated_finite_action_minimax_requirements()));
    REQUIRE(std::holds_alternative<PreparedPipeline<ValidatedFiniteActionMinimaxPort>>(selected));
    auto limited=std::get<0>(std::get<PreparedPipeline<ValidatedFiniteActionMinimaxPort>>(
        std::move(selected)).create());
    const auto stopped=limited->run({});
    REQUIRE(std::holds_alternative<OperationStopped>(stopped));
    CHECK(std::get<OperationStopped>(stopped).reason==StopReason::resource_limit);
}
