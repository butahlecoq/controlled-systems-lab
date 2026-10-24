#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/experiments/batch_runner.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>

using namespace csl;
namespace {

template<class T,class... R> T take(std::variant<T,R...> value) {
    if(!std::holds_alternative<T>(value))throw std::runtime_error("Unexpected fixture result");
    return std::get<T>(std::move(value));
}

SetHandle interval(std::string id,double lower,double upper) {
    const Matrix inequalities{2,1,{1,-1}};
    const Matrix equalities{0,1,{}};
    const sets::Description description{SetId{std::move(id)},1,std::vector<std::string>{"u"}};
    const sets::HRepresentation representation{take(numeric::snapshot(inequalities)),
        take(numeric::snapshot_vector(Vector{upper,-lower})),take(numeric::snapshot(equalities)),
        take(numeric::snapshot_vector(Vector{}))};
    return take(sets::make_h(description,representation)).as_handle();
}

problem::ResolvedProblem make_problem() {
    Matrix state_transition{1,1,{1}};
    Matrix control_transition{1,1,{1}};
    Matrix external_transition{1,0,{}};
    LinearStage transition{std::move(state_transition),std::move(control_transition),
        std::move(external_transition),Vector{0}};
    Dynamics dynamics{{1,1,0},TimeDomain::discrete,std::move(transition)};
    Problem p{};
    p.id={"sweep-ts01"};
    p.model=std::make_shared<const SystemModel>(SystemModel{std::move(dynamics),{}});
    p.times={0,1,2};
    p.initial=KnownInitial{Vector{0}};
    p.controls=ContinuousDomain{{interval("u0",0,1),interval("u1",0,1)}};
    p.states={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    p.information=InformationPattern::nominal_open_loop;
    p.objective=QuadraticTerminal{Matrix{1,1,{2}},Vector{-2},1};
    return std::get<problem::ResolvedProblem>(problem::resolve(p,
        {problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}

registry::PreparedStrategy prepare_strategy() {
    const auto resolved=make_problem();
    FamilyRequest family{"ts01_exact_integrator",resolved.identity(),FamilyTarget::exact_optimal_relation,
        {1e-8,1e-8},Assurance::numerical,{"csl.polyhedron.h"},{}};
    StrategyConfiguration configuration;
    configuration.strategy={"csl.synthesis.ts01-analytic"};
    configuration.representation={"csl.polyhedron.h"};
    registry::StrategyRegistry strategies;
    REQUIRE_FALSE(strategies.add(synthesis::strategy_ts01::make_registration()));
    registry::Requirements requirements;
    requirements.output.representation=family.representation;
    requirements.output.family=family.target;
    requirements.output.completeness=registry::Completeness::established;
    auto prepared=strategies.prepare({resolved,configuration,family,{},{ }},requirements);
    if(const auto* rejection=std::get_if<registry::Rejection>(&prepared))
        for(const auto& diagnostic:rejection->diagnostics) MESSAGE(diagnostic.field,": ",diagnostic.explanation);
    REQUIRE(std::holds_alternative<registry::PreparedStrategy>(prepared));
    return std::get<registry::PreparedStrategy>(std::move(prepared));
}

experiments::ScenarioSweepCase sweep_case(std::string scenario,std::string config,
    const registry::PreparedStrategy& strategy) {
    return {{std::move(scenario),artifacts::ConfigId{std::move(config)}},strategy,
        {1,"analytic strategy uses one caller lane",std::nullopt,execution::CallStopSupport::cooperative_boundaries},
        {2,0.0,{{1,-1},{-1,1}},19}};
}
}

TEST_CASE("a bounded sweep keeps whole scenario identities and deterministic selection settings") {
    const auto prepared=prepare_strategy();
    const std::vector<experiments::ScenarioSweepCase> cases{
        sweep_case("scenario-a","config-a",prepared),
        sweep_case("scenario-b","config-b",prepared)};
    const ResourcePolicy resources{2,2,1,std::nullopt};
    ExecutionContext context;
    context.resources=std::make_shared<const ResourcePolicy>(resources);
    context.run_id="sweep-run";

    std::optional<double> reference_optimum;
    for(const auto mode:{execution::Mode::sequential,execution::Mode::bounded_parallel}) {
        auto outcome=experiments::run_sweep(cases,resources,context,mode);
        if(const auto* diagnostics=std::get_if<Diagnostics>(&outcome))
            for(const auto& diagnostic:*diagnostics) MESSAGE(diagnostic.field,": ",diagnostic.explanation);
        REQUIRE(std::holds_alternative<experiments::SweepResult>(outcome));
        const auto& result=std::get<experiments::SweepResult>(outcome);
        REQUIRE(result.batch.tasks.size()==2);
        REQUIRE(result.cases.size()==2);
        CHECK(result.batch.tasks[0].id.value=="sweep-0");
        CHECK(result.batch.tasks[1].id.value=="sweep-1");
        CHECK(result.cases[0].identity==experiments::ScenarioConfigurationId{"scenario-a",{"config-a"}});
        CHECK(result.cases[1].identity==experiments::ScenarioConfigurationId{"scenario-b",{"config-b"}});
        REQUIRE(result.cases[0].selection);
        CHECK(result.cases[0].selection->count==2);
        CHECK(result.cases[0].selection->seed==19);
        CHECK(result.cases[0].selection->directions==std::vector<Vector>{{1,-1},{-1,1}});
        CHECK(result.batch.enforcement.outer_admission==execution::OuterAdmissionEnforcement::enforced);
        CHECK(result.batch.enforcement.native_threads==execution::NativeThreadEnforcement::declared_only);
        CHECK(result.batch.enforcement.memory==execution::MemoryEnforcement::unlimited_accounting);
        CHECK(result.batch.enforcement.peak_active_tasks>=1);
        CHECK(result.batch.enforcement.peak_active_tasks<=resources.outer_workers);
        for(const auto& task:result.batch.tasks) {
            REQUIRE(std::holds_alternative<execution::Returned<registry::StrategyPort>>(task.outcome));
            const auto& value=std::get<SynthesisResult>(std::get<execution::Returned<registry::StrategyPort>>(task.outcome).value);
            CHECK(value.termination==Termination::completed);
            CHECK(value.family.has_value());
            REQUIRE(value.objective.lower);
            REQUIRE(value.objective.upper);
            CHECK(value.objective.lower->value==doctest::Approx(0.0).epsilon(1e-12));
            CHECK(value.objective.upper->value==doctest::Approx(0.0).epsilon(1e-12));
            if(reference_optimum)
                CHECK(value.objective.upper->value==doctest::Approx(*reference_optimum).epsilon(1e-12));
            else reference_optimum=value.objective.upper->value;
        }
    }
}

TEST_CASE("a sweep rejects missing identity and invalid deterministic selection settings") {
    const auto prepared=prepare_strategy();
    auto item=sweep_case("","config",prepared);
    const ResourcePolicy resources{1,1,1,std::nullopt};
    ExecutionContext context;
    context.resources=std::make_shared<const ResourcePolicy>(resources);
    auto outcome=experiments::run_sweep(std::span{&item,1},resources,context,execution::Mode::sequential);
    REQUIRE(std::holds_alternative<Diagnostics>(outcome));
    CHECK(std::get<Diagnostics>(outcome).front().field=="sweep.cases[0].identity");

    item.identity.scenario="scenario";
    item.selection.count=0;
    outcome=experiments::run_sweep(std::span{&item,1},resources,context,execution::Mode::sequential);
    REQUIRE(std::holds_alternative<Diagnostics>(outcome));
    CHECK(std::get<Diagnostics>(outcome).front().field=="sweep.cases[0].selection");
}

TEST_CASE("a sweep keeps admitted and skipped scenario records together") {
    const auto prepared=prepare_strategy();
    const std::vector<experiments::ScenarioSweepCase> cases{
        sweep_case("scenario-a","config-a",prepared),
        sweep_case("scenario-b","config-b",prepared)};
    const ResourcePolicy resources{1,1,1,std::nullopt};
    ExecutionContext context;
    context.resources=std::make_shared<const ResourcePolicy>(resources);
    const auto outcome=experiments::run_sweep(cases,resources,context,execution::Mode::sequential,
        execution::AdmissionLimit{1});
    REQUIRE(std::holds_alternative<experiments::SweepResult>(outcome));
    const auto& result=std::get<experiments::SweepResult>(outcome);
    REQUIRE(result.batch.tasks.size()==2);
    REQUIRE(result.cases.size()==2);
    CHECK(std::holds_alternative<execution::Returned<registry::StrategyPort>>(result.batch.tasks[0].outcome));
    const auto* skipped=std::get_if<execution::Skipped>(&result.batch.tasks[1].outcome);
    REQUIRE(skipped);
    CHECK(skipped->reason==execution::SkipReason::task_limit);
    CHECK(result.cases[1].identity==experiments::ScenarioConfigurationId{"scenario-b",{"config-b"}});
    REQUIRE(result.cases[1].selection);
    CHECK(result.cases[1].selection->seed==19);
}
