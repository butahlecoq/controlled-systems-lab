#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/execution/instrumented_operation.hpp>
#include <stdexcept>

using namespace csl;
namespace ar=csl::artifacts;
namespace ob=csl::execution::observability;
namespace {
template<class T> T accepted(ar::ArtifactResult<T> value) {
    REQUIRE(std::holds_alternative<T>(value));return std::get<T>(std::move(value));
}
class Clock final:public ob::TimingClock {
    std::int64_t tick_{};
public:
    ar::ClockDomain wall_domain() const override {
        return {{"wall"},ar::ClockMetric::steady_wall,"run",1,1000,
            ar::Available<std::uint64_t>{1},"operation-test"};
    }
    std::optional<ar::ClockDomain> cpu_domain() const override{return {};}
    ar::Metric<std::int64_t> wall_now() noexcept override {
        const auto result=tick_;tick_+=10;return ar::Available<std::int64_t>{result};
    }
    ar::Metric<std::int64_t> cpu_now() noexcept override {
        return ar::Unavailable{ar::MissingReason::not_supported,{}};
    }
};
struct Fixture {
    problem::ResolvedProblem problem;
    ar::ResolvedConfiguration configuration;
    ob::CollectionPlan plan;
    ob::OperationSpanIdentity identity;
};
Fixture fixture(ModuleId backend={"spy.geometry"},std::optional<std::uint64_t> input_size={},
    std::optional<std::uint64_t> output_size={}) {
    Problem source{{"operation-test"},std::make_shared<const SystemModel>(SystemModel{{
        {0,0,0},TimeDomain::discrete,LinearStage{{0,0,{}},{0,0,{}},{0,0,{}},{}}},{}}),{0},
        KnownInitial{{}},ContinuousDomain{{}},{UniversalSet{0}},{},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{},0}};
    auto resolution=problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolution));
    auto resolved=std::get<problem::ResolvedProblem>(std::move(resolution));
    ar::ConfigurationInput configuration;
    const ar::Unavailable missing{ar::MissingReason::not_instrumented,{}};
    configuration.collection={true,ar::CollectionMode::detail,8,4096,8,1024};
    configuration.modules={{"geometry",{backend,"1",missing},{}},
        {"strategy",{{"csl.synthesis.instrumented-test"},"1",missing},{}}};
    configuration.resources={1,1,1,{}};configuration.numerical={0,0};
    configuration.output={ar::OutputKind::synthesis,Assurance::numerical,
        FamilyTarget::candidate_relaxation,{"csl.polyhedron.h"},{1,0,{},{}}};
    configuration.selector={{"first"},"1",{}};
    configuration.strategy={{"csl.synthesis.instrumented-test"},{},{},{},backend,{},{},
        {"first"},{"csl.polyhedron.h"}};
    auto resolved_configuration=accepted(ar::resolve_configuration(configuration));
    ob::PlanInput input{resolved,resolved_configuration,{"run"},
        {{{"wall"},ar::ClockMetric::steady_wall,"run",1,1000,
            ar::Available<std::uint64_t>{1},"operation-test"}}, {},1};
    input.tasks={"run","projection-request"};
    input.operations={"operation.run","geometry.projection"};
    ar::SpanDescriptor root{};root.id={0};root.task="run";root.operation="operation.run";
    root.module=configuration.modules.back().implementation;root.clock={"wall"};
    root.requested_assurance=Assurance::numerical;
    root.applied_assurance=ar::Available<Assurance>{Assurance::numerical};
    input.spans.push_back(root);
    ar::SpanDescriptor operation{};operation.id={1};operation.parent=ar::SpanParent{{0},ar::ParentKind::nested};
    operation.task="projection-request";operation.operation="geometry.projection";
    operation.module=configuration.modules.back().implementation;
    operation.backend=std::make_shared<const ar::ModuleIdentity>(configuration.modules.front().implementation);
    operation.stage=0;operation.input_size=input_size;operation.output_size=output_size;
    operation.clock={"wall"};operation.requested_assurance=Assurance::numerical;
    operation.applied_assurance=ar::Available<Assurance>{Assurance::numerical};
    operation.observation_source="instrumented-operation-test";
    input.spans.push_back(operation);
    auto plan=accepted(ob::make_collection_plan(std::move(input)));
    return {std::move(resolved),std::move(resolved_configuration),std::move(plan),
        {"projection-request","geometry.projection",configuration.modules.back().implementation,
            configuration.modules.front().implementation,{},0,{}}};
}
std::shared_ptr<ob::TimingCollector> collector(const Fixture& f,std::shared_ptr<Clock> clock) {
    return accepted(ob::make_timing_collector(f.plan,std::move(clock),{0},{}));
}
}
TEST_CASE("instrumented operation binds timing to task, operation, stage and provider identity") {
    const auto f=fixture({"spy.geometry"},3,9);auto clock=std::make_shared<Clock>();auto timer=collector(f,clock);
    ExecutionContext context;context.run_id="run";context.timing=timer;
    auto root=accepted(timer->start({0},context));
    std::size_t calls{};
    const auto result=ob::run_instrumented_operation(context,f.identity,[&] {
        ++calls;return Termination::completed;
    },[](Termination termination) noexcept {return termination;},
        []() noexcept -> std::optional<std::uint64_t> {return 7;},
        [](const Termination&) noexcept -> std::optional<std::uint64_t> {return 0;});
    CHECK(result==Termination::completed);CHECK(calls==1);
    root.close(Termination::completed);
    const auto report=accepted(timer->snapshot());
    REQUIRE(report.spans.size()==2);
    REQUIRE(std::holds_alternative<ar::Available<std::uint64_t>>(report.spans[1].inclusive_wall_ticks));
    CHECK(std::get<ar::Available<std::uint64_t>>(report.spans[1].inclusive_wall_ticks).value==10);
    const auto& span=report.observations.description().spans[1];
    CHECK(span.descriptor.backend->id==ModuleId{"spy.geometry"});
    CHECK(span.descriptor.operation=="geometry.projection");
    CHECK(span.descriptor.input_size==7);
    CHECK(span.descriptor.output_size==0);
    CHECK(std::get<ar::ReturnedSpan>(span.status).termination==Termination::completed);
}

TEST_CASE("instrumented operation leaves a different provider unmeasured") {
    const auto f=fixture();auto clock=std::make_shared<Clock>();auto timer=collector(f,clock);
    ExecutionContext context;context.run_id="run";context.timing=timer;
    auto root=accepted(timer->start({0},context));
    auto wrong=f.identity;wrong.backend=ar::ModuleIdentity{{"other.geometry"},"1",{}};
    std::size_t calls{};
    ob::run_instrumented_operation(context,wrong,[&] {
        ++calls;return Termination::completed;
    },[](Termination termination) noexcept {return termination;});
    CHECK(calls==1);
    root.close(Termination::completed);
    const auto report=accepted(timer->snapshot());
    REQUIRE(report.spans.size()==2);
    CHECK(std::holds_alternative<ar::Unavailable>(report.spans[1].inclusive_wall_ticks));
    CHECK(std::holds_alternative<ar::IncompleteSpan>(report.observations.description().spans[1].status));
}

TEST_CASE("instrumented operation retains the input size and leaves failed output unavailable") {
    const auto f=fixture({"spy.geometry"},3,9);auto clock=std::make_shared<Clock>();auto timer=collector(f,clock);
    ExecutionContext context;context.run_id="run";context.timing=timer;
    auto root=accepted(timer->start({0},context));
    CHECK_THROWS(ob::run_instrumented_operation(context,f.identity,[]() -> int {
        throw std::runtime_error("provider failure");
    },[](const int&) noexcept {return Termination::completed;},
        []() noexcept -> std::optional<std::uint64_t> {return 4;},
        [](const int&) noexcept -> std::optional<std::uint64_t> {return 4;}));
    root.close(Termination::completed);
    const auto report=accepted(timer->snapshot());
    const auto& span=report.observations.description().spans[1];
    CHECK(span.descriptor.input_size==4);
    CHECK_FALSE(span.descriptor.output_size);
    CHECK(std::holds_alternative<ar::FailedSpan>(span.status));
}
