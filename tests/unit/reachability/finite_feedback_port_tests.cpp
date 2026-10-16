#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/reachability/finite_feedback_port.hpp>

using namespace csl;
using namespace csl::reachability::finite_feedback;
using namespace csl::registry;

namespace {
Request request() {
    return {{"finite-fixture"},{"winning-query"},
        Game{3,{Stage{{true,true,true},2,2,{
            {{StateIndex{1},StateIndex{2}},{StateIndex{1},StateIndex{1}}},
            {{StateIndex{1},StateIndex{1}},{StateIndex{1},StateIndex{1}}},
            {{StateIndex{1},StateIndex{1}},{StateIndex{1},StateIndex{1}}}
        }}},{true,true,true},{false,true,false}}};
}
Method reference_method() {
    return {{"csl.reachability.finite-feedback-table"},"1.0.0"};
}
class EchoWorkspace final : public Workspace {
public:
    PortResult compute(const Request& request,const ExecutionContext&) override {
        auto result=solve(request.game);
        if(const auto* error=std::get_if<Diagnostic>(&result))return *error;
        return std::get<Policy>(std::move(result));
    }
};
class BogusWorkspace final : public Workspace {
public:
    PortResult compute(const Request& request,const ExecutionContext&) override {
        Policy policy;
        policy.winning.assign(request.game.stages.size()+1,
            std::vector<bool>(request.game.state_count,true));
        policy.admissible_actions.assign(request.game.stages.size(),
            std::vector<std::vector<ActionIndex>>(request.game.state_count));
        return policy;
    }
};
}

TEST_CASE("registered finite-table predecessor binds exact result to selected method") {
    Registry<FiniteFeedbackPort> registry;
    REQUIRE_FALSE(registry.add(make_registration()).has_value());
    const auto result=run_registered(registry,reference_method(),request(),finite_table_requirements(),{});
    REQUIRE(std::holds_alternative<RegisteredPolicy>(result));
    const auto& completed=std::get<RegisteredPolicy>(result);
    CHECK(completed.problem==ProblemId{"finite-fixture"});
    CHECK(completed.request==RequestId{"winning-query"});
    REQUIRE(completed.provider.actual.has_value());
    CHECK(completed.provider.actual->id==ModuleId{"csl.reachability.finite-feedback-table"});
    CHECK(completed.provider.actual->version=="1.0.0");
    CHECK(completed.policy.winning[0]==std::vector<bool>{true,true,true});
    CHECK(completed.policy.admissible_actions[0][0]==std::vector<ActionIndex>{ActionIndex{1}});
}

TEST_CASE("invalid table and wrong method version reject before workspace creation") {
    Registry<FiniteFeedbackPort> registry;
    auto entry=make_registration();
    int factories=0;
    auto factory=entry.factory;
    entry.factory=[&](const Request& value) {
        ++factories;
        return factory(value);
    };
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    auto bad=request();
    bad.game.stages[0].disturbance_count=0;
    const auto invalid=run_registered(registry,reference_method(),bad,finite_table_requirements(),{});
    REQUIRE(std::holds_alternative<RegisteredFailure>(invalid));
    CHECK(std::get<RegisteredFailure>(invalid).diagnostics[0].code==DiagnosticCode::invalid_input);
    CHECK(factories==0);

    const auto wrong_version=run_registered(registry,
        {{"csl.reachability.finite-feedback-table"},"2.0.0"},request(),finite_table_requirements(),{});
    REQUIRE(std::holds_alternative<RegisteredFailure>(wrong_version));
    CHECK(std::get<RegisteredFailure>(wrong_version).diagnostics[0].field=="method.version");
    CHECK(factories==0);
}

TEST_CASE("another registered provider can supply the same verified table") {
    Registry<FiniteFeedbackPort> registry;
    auto entry=make_registration();
    entry.identity={{"csl.reachability.finite-feedback-echo"},"7.0.0"};
    entry.factory=[](const Request&) -> std::unique_ptr<Workspace> {
        return std::make_unique<EchoWorkspace>();
    };
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    const auto result=run_registered(registry,
        {{"csl.reachability.finite-feedback-echo"},"7.0.0"},request(),finite_table_requirements(),{});
    REQUIRE(std::holds_alternative<RegisteredPolicy>(result));
    const auto& completed=std::get<RegisteredPolicy>(result);
    REQUIRE(completed.provider.actual.has_value());
    CHECK(completed.provider.actual->id==ModuleId{"csl.reachability.finite-feedback-echo"});
    CHECK(completed.policy.admissible_actions[0][0]==std::vector<ActionIndex>{ActionIndex{1}});
}

TEST_CASE("a provider cannot publish a false winning table") {
    Registry<FiniteFeedbackPort> registry;
    auto entry=make_registration();
    entry.identity={{"csl.reachability.finite-feedback-bogus"},"1.0.0"};
    entry.factory=[](const Request&) -> std::unique_ptr<Workspace> {
        return std::make_unique<BogusWorkspace>();
    };
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    const auto result=run_registered(registry,
        {{"csl.reachability.finite-feedback-bogus"},"1.0.0"},request(),finite_table_requirements(),{});
    REQUIRE(std::holds_alternative<RegisteredFailure>(result));
    const auto& failure=std::get<RegisteredFailure>(result);
    REQUIRE(failure.provider.actual.has_value());
    CHECK(failure.provider.actual->id==ModuleId{"csl.reachability.finite-feedback-bogus"});
    CHECK(failure.diagnostics[0].code==DiagnosticCode::evidence_mismatch);
}

TEST_CASE("pre-cancelled request retains identity and never creates a workspace") {
    Registry<FiniteFeedbackPort> registry;
    auto entry=make_registration();
    int factories=0;
    auto factory=entry.factory;
    entry.factory=[&](const Request& value) {
        ++factories;
        return factory(value);
    };
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    std::stop_source stop;
    stop.request_stop();
    ExecutionContext context;
    context.cancellation=stop.get_token();
    const auto result=run_registered(registry,reference_method(),request(),
        finite_table_requirements(),context);
    REQUIRE(std::holds_alternative<RegisteredStopped>(result));
    const auto& stopped=std::get<RegisteredStopped>(result);
    CHECK(stopped.problem==ProblemId{"finite-fixture"});
    CHECK(stopped.request==RequestId{"winning-query"});
    CHECK(stopped.stop.reason==StopReason::cancelled);
    REQUIRE(stopped.provider.actual.has_value());
    CHECK(stopped.provider.actual->version=="1.0.0");
    CHECK(factories==0);
}
