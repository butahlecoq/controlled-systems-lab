#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/experiments/batch_runner.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>

#include <fstream>
#include <iterator>

using namespace csl;
namespace {

template<class T,class... R> T take(std::variant<T,R...> value) {
    if(!std::holds_alternative<T>(value))throw std::runtime_error("Unexpected fixture result");
    return std::get<T>(std::move(value));
}

std::string read_sweep_run_fixture() {
    std::ifstream input(CSL_SWEEP_RUN_FIXTURE, std::ios::binary);
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}

artifacts::RecordedRunArtifact recorded_sweep_run() {
    auto decoded = take(artifacts::decode_run(read_sweep_run_fixture()));
    return take(artifacts::encode_recorded_run(decoded));
}

problem::ResolvedContent sweep_spec() {
    constexpr std::string_view text{"{\"schema\":\"csl.scenario-sweep-spec/1\"}"};
    std::vector<std::byte> bytes;
    for (const unsigned char value : text) bytes.push_back(static_cast<std::byte>(value));
    return take(problem::snapshot_content(bytes));
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

class EchoSelector final : public WitnessSelectorWorkspace {
public:
    std::variant<WitnessSelection, Unsupported> select(const OptimalFamily& family,
        const WitnessRequest& request, const ExecutionContext&) override {
        WitnessBatch batch;
        batch.requested=request.count;
        batch.selector={"test.selector"};
        batch.seed=request.seed;
        batch.source_family=family.identity();
        batch.directions=request.directions;
        batch.distinctness_tolerance=request.distinctness_tolerance;
        return WitnessSelection{std::move(batch),Termination::completed,{}};
    }
};

registry::PreparedProvider<registry::SelectorPort> prepare_selector_provider(bool reject_seed_twenty=false) {
    registry::Registry<registry::SelectorPort> selectors;
    registry::Registration<registry::SelectorPort> registration{
        {{"test.selector"},"1"},
        [reject_seed_twenty](const registry::SelectorRequest& request, const registry::Requirements& requirements)
            -> registry::Capability {
            if(reject_seed_twenty&&request.selection.seed==20)
                return Diagnostics{{DiagnosticCode::unsupported,"test.selector.seed","seed 20 rejected by fixture"}};
            return registry::Offer{requirements.output};
        },
        [](const registry::SelectorRequest&) { return std::make_unique<EchoSelector>(); }};
    REQUIRE_FALSE(selectors.add(std::move(registration)));
    registry::Requirements requirements;
    requirements.output.representation={"csl.witness-batch.v1"};
    auto prepared=registry::prepare_provider(registry::select_provider(selectors,
        registry::Method{{"test.selector"},{}},requirements));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::SelectorPort>>(prepared));
    return std::get<registry::PreparedProvider<registry::SelectorPort>>(std::move(prepared));
}

experiments::ScenarioSweepCase sweep_case(std::string scenario,std::string config,
    const registry::PreparedStrategy& strategy) {
    return {{experiments::ScenarioId{std::move(scenario)},artifacts::ConfigId{std::move(config)}},strategy,
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
        CHECK(result.cases[0].identity==experiments::ScenarioConfigurationId{{"scenario-a"},{"config-a"}});
        CHECK(result.cases[1].identity==experiments::ScenarioConfigurationId{{"scenario-b"},{"config-b"}});
        REQUIRE(result.cases[0].selection);
        CHECK(result.cases[0].selection->count==2);
        CHECK(result.cases[0].selection->seed==19);
        CHECK(result.cases[0].selection->directions==std::vector<Vector>{{1,-1},{-1,1}});
        CHECK(result.batch.enforcement.outer_admission==execution::OuterAdmissionEnforcement::enforced);
        CHECK(result.batch.enforcement.native_threads==execution::NativeThreadEnforcement::declared_only);
        CHECK(result.batch.enforcement.memory==execution::MemoryEnforcement::unlimited_accounting);
        CHECK(result.batch.enforcement.peak_active_tasks>=1);
        CHECK(result.batch.enforcement.peak_active_tasks<=resources.outer_workers);
        CHECK(result.batch.enforcement.outer_worker_threads_started==
            (mode==execution::Mode::bounded_parallel ? 2U : 0U));
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

    item.identity.scenario.value="scenario";
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
    context.run_id="sweep-admission";
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
    CHECK(result.cases[1].identity==experiments::ScenarioConfigurationId{{"scenario-b"},{"config-b"}});
    REQUIRE(result.cases[1].selection);
    CHECK(result.cases[1].selection->seed==19);
}

TEST_CASE("family queries preserve coarse results and map deterministic requests by case") {
    const auto prepared=prepare_strategy();
    std::vector<experiments::ScenarioSweepCase> cases{
        sweep_case("scenario-a","config-a",prepared),
        sweep_case("scenario-b","config-b",prepared)};
    cases[1].selection.seed=20;
    const ResourcePolicy resources{2,2,1,std::nullopt};
    ExecutionContext context;
    context.run_id="family-query-run";
    const auto selector=prepare_selector_provider(true);
    const execution::ResourceUse query_resources{1,"one selector workspace per case",std::nullopt,
        execution::CallStopSupport::cooperative_boundaries};

    for(const auto mode:{execution::Mode::sequential,execution::Mode::bounded_parallel}) {
        auto coarse=experiments::run_sweep(cases,resources,context,mode);
        REQUIRE(std::holds_alternative<experiments::SweepResult>(coarse));
        auto sweep=std::get<experiments::SweepResult>(std::move(coarse));
        auto queried=experiments::run_family_queries(std::move(sweep),selector,resources,context,
            mode,query_resources);
        REQUIRE(std::holds_alternative<experiments::FamilyQueryResult>(queried));
        const auto& result=std::get<experiments::FamilyQueryResult>(queried);
        REQUIRE(result.sweep.batch.tasks.size()==2);
        REQUIRE(result.queries.size()==2);
        REQUIRE(result.query_batch.tasks.size()==1);
        CHECK(result.queries[0].identity==experiments::ScenarioConfigurationId{{"scenario-a"},{"config-a"}});
        CHECK(result.queries[1].identity==experiments::ScenarioConfigurationId{{"scenario-b"},{"config-b"}});
        const auto* first=std::get_if<experiments::FamilyQueryScheduled>(&result.queries[0].status);
        REQUIRE(first);
        CHECK(first->task_index==0);
        const auto* rejected=std::get_if<experiments::FamilyQueryRejected>(&result.queries[1].status);
        REQUIRE(rejected);
        REQUIRE(rejected->diagnostics.size()==1);
        CHECK(rejected->diagnostics[0].field=="test.selector.seed");
        CHECK(result.query_batch.tasks[0].id.value=="family-query-0");
        REQUIRE(result.query_batch.tasks[0].provenance.size()==1);
        REQUIRE(result.query_batch.tasks[0].provenance[0].actual);
        CHECK(result.query_batch.tasks[0].provenance[0].actual->id.value=="test.selector");
        const auto* returned=std::get_if<execution::Returned<registry::SelectorPort>>(
            &result.query_batch.tasks[0].outcome);
        REQUIRE(returned);
        const auto* selected=std::get_if<WitnessSelection>(&returned->value);
        REQUIRE(selected);
        CHECK(selected->batch.requested==2);
        CHECK(selected->batch.seed==19);
        CHECK(selected->batch.directions==std::vector<Vector>{{1,-1},{-1,1}});
        CHECK(selected->batch.distinctness_tolerance==0.0);
        CHECK(result.sweep.batch.run_id=="family-query-run");
        CHECK(result.query_batch.run_id==result.sweep.batch.run_id);
        CHECK(result.query_batch.timing.started_at>=result.sweep.batch.timing.completed_at);
    }
}

TEST_CASE("family query dispositions retain cases whose coarse strategy was skipped") {
    const auto prepared=prepare_strategy();
    const std::vector<experiments::ScenarioSweepCase> cases{
        sweep_case("scenario-a","config-a",prepared),
        sweep_case("scenario-b","config-b",prepared)};
    const ResourcePolicy resources{1,1,1,std::nullopt};
    ExecutionContext context;
    context.run_id="family-query-skip";
    auto coarse=experiments::run_sweep(cases,resources,context,execution::Mode::sequential,
        execution::AdmissionLimit{1});
    REQUIRE(std::holds_alternative<experiments::SweepResult>(coarse));
    auto sweep=std::get<experiments::SweepResult>(std::move(coarse));
    const auto selector=prepare_selector_provider();
    const execution::ResourceUse query_resources{1,"one selector workspace",std::nullopt,
        execution::CallStopSupport::cooperative_boundaries};

    auto queried=experiments::run_family_queries(std::move(sweep),selector,resources,context,
        execution::Mode::sequential,query_resources);
    REQUIRE(std::holds_alternative<experiments::FamilyQueryResult>(queried));
    const auto& result=std::get<experiments::FamilyQueryResult>(queried);
    REQUIRE(result.queries.size()==2);
    REQUIRE(result.query_batch.tasks.size()==1);
    CHECK(std::holds_alternative<experiments::FamilyQueryScheduled>(result.queries[0].status));
    const auto* not_run=std::get_if<experiments::FamilyQueryNotRun>(&result.queries[1].status);
    REQUIRE(not_run);
    CHECK(not_run->reason==experiments::QueryNotRunReason::strategy_skipped);
    CHECK(std::get<execution::Skipped>(result.sweep.batch.tasks[1].outcome).reason==execution::SkipReason::task_limit);
}

TEST_CASE("family query dispositions explain unavailable strategy families") {
    const auto prepared=prepare_strategy();
    const auto selector=prepare_selector_provider();
    const auto item=sweep_case("scenario","config",prepared);
    const ResourcePolicy resources{1,1,1,std::nullopt};
    ExecutionContext context;
    context.run_id="family-query-ineligible";
    const execution::ResourceUse query_resources{1,"one selector workspace",std::nullopt,
        execution::CallStopSupport::cooperative_boundaries};

    auto make_sweep=[&] {
        auto outcome=experiments::run_sweep(std::span{&item,1},resources,context,execution::Mode::sequential);
        REQUIRE(std::holds_alternative<experiments::SweepResult>(outcome));
        return std::get<experiments::SweepResult>(std::move(outcome));
    };

    auto no_family=make_sweep();
    auto& no_family_result=std::get<SynthesisResult>(
        std::get<execution::Returned<registry::StrategyPort>>(no_family.batch.tasks[0].outcome).value);
    no_family_result.family.reset();
    auto no_family_query=experiments::run_family_queries(std::move(no_family),selector,resources,context,
        execution::Mode::sequential,query_resources);
    REQUIRE(std::holds_alternative<experiments::FamilyQueryResult>(no_family_query));
    const auto& no_family_output=std::get<experiments::FamilyQueryResult>(no_family_query);
    CHECK(std::get<experiments::FamilyQueryNotRun>(no_family_output.queries[0].status).reason==
        experiments::QueryNotRunReason::family_unavailable);
    CHECK(no_family_output.query_batch.tasks.empty());

    auto unsupported=make_sweep();
    std::get<execution::Returned<registry::StrategyPort>>(unsupported.batch.tasks[0].outcome).value=
        Unsupported{{{DiagnosticCode::unsupported,"strategy.fixture","fixture not supported"}}};
    auto unsupported_query=experiments::run_family_queries(std::move(unsupported),selector,resources,context,
        execution::Mode::sequential,query_resources);
    REQUIRE(std::holds_alternative<experiments::FamilyQueryResult>(unsupported_query));
    const auto& unsupported_output=std::get<experiments::FamilyQueryResult>(unsupported_query);
    CHECK(std::get<experiments::FamilyQueryNotRun>(unsupported_output.queries[0].status).reason==
        experiments::QueryNotRunReason::strategy_unsupported);
    CHECK(unsupported_output.query_batch.tasks.empty());

    auto failed=make_sweep();
    failed.batch.tasks[0].outcome=execution::TaskFailure{execution::FailureStage::invoke,
        execution::FailureKind::adapter_exception,std::make_exception_ptr(std::runtime_error("fixture failure"))};
    auto failed_query=experiments::run_family_queries(std::move(failed),selector,resources,context,
        execution::Mode::sequential,query_resources);
    REQUIRE(std::holds_alternative<experiments::FamilyQueryResult>(failed_query));
    const auto& failed_output=std::get<experiments::FamilyQueryResult>(failed_query);
    CHECK(std::get<experiments::FamilyQueryNotRun>(failed_output.queries[0].status).reason==
        experiments::QueryNotRunReason::strategy_failed);
    CHECK(std::holds_alternative<execution::TaskFailure>(failed_output.sweep.batch.tasks[0].outcome));
}

TEST_CASE("query setup diagnostics leave the completed coarse sweep available to the caller") {
    const auto prepared=prepare_strategy();
    const auto item=sweep_case("scenario","config",prepared);
    const ResourcePolicy resources{1,1,1,std::nullopt};
    ExecutionContext context;
    context.run_id="family-query-setup-error";
    auto outcome=experiments::run_sweep(std::span{&item,1},resources,context,execution::Mode::sequential);
    REQUIRE(std::holds_alternative<experiments::SweepResult>(outcome));
    auto sweep=std::get<experiments::SweepResult>(std::move(outcome));
    const auto selector=prepare_selector_provider();
    const execution::ResourceUse invalid_query_resources{2,"exceeds policy lane",std::nullopt,
        execution::CallStopSupport::cooperative_boundaries};

    auto changed_context=context;
    changed_context.run_id="different-run";
    auto mismatched=experiments::run_family_queries(std::move(sweep),selector,resources,changed_context,
        execution::Mode::sequential,invalid_query_resources);
    REQUIRE(std::holds_alternative<Diagnostics>(mismatched));
    CHECK(std::get<Diagnostics>(mismatched).front().field=="family_queries.run_id");
    REQUIRE(sweep.batch.tasks.size()==1);

    auto queried=experiments::run_family_queries(std::move(sweep),selector,resources,context,
        execution::Mode::sequential,invalid_query_resources);
    REQUIRE(std::holds_alternative<Diagnostics>(queried));
    CHECK(std::get<Diagnostics>(queried).front().field=="execution.task.family-query-0.threads");
    REQUIRE(sweep.batch.tasks.size()==1);
    const auto* returned=std::get_if<execution::Returned<registry::StrategyPort>>(&sweep.batch.tasks[0].outcome);
    REQUIRE(returned);
    CHECK(std::get<SynthesisResult>(returned->value).family.has_value());
}

TEST_CASE("a completed family query sweep records aligned runs and measured phase resources") {
    const auto prepared = prepare_strategy();
    constexpr std::string_view configuration{"csl.config.v1.sha256:e27f771c2d04bb72827ad27eeaa4123a4df58eaea22aaac4b789ee36033e5abf"};
    std::vector<experiments::ScenarioSweepCase> cases{
        sweep_case("scenario-a", std::string(configuration), prepared),
        sweep_case("scenario-b", std::string(configuration), prepared)};
    for (auto& item : cases) {
        item.resources.workspace_reservation_bytes = 20;
        item.resources.retained_result_reservation_bytes = 15;
    }
    cases[1].selection.seed = 20;
    const ResourcePolicy resources{2,2,1,100};
    ExecutionContext context;
    context.run_id = "recorded-sweep";
    const auto selector = prepare_selector_provider(true);
    const execution::ResourceUse query_resources{1,"one selector workspace",10,
        execution::CallStopSupport::cooperative_boundaries,5};
    auto coarse = experiments::run_sweep(cases, resources, context, execution::Mode::bounded_parallel);
    REQUIRE(std::holds_alternative<experiments::SweepResult>(coarse));
    auto queried = experiments::run_family_queries(std::get<experiments::SweepResult>(std::move(coarse)),
        selector, resources, context, execution::Mode::bounded_parallel, query_resources);
    REQUIRE(std::holds_alternative<experiments::FamilyQueryResult>(queried));

    const auto recorded = recorded_sweep_run();
    const std::vector<artifacts::RecordedRunArtifact> coarse_records{recorded, recorded};
    std::vector<std::optional<artifacts::RecordedRunArtifact>> query_records{recorded, std::nullopt};
    const auto archive = experiments::record_family_query_sweep(sweep_spec(),
        std::get<experiments::FamilyQueryResult>(queried), coarse_records, query_records);
    REQUIRE(std::holds_alternative<artifacts::RecordedSweepArtifact>(archive));
    const auto bytes = std::get<artifacts::RecordedSweepArtifact>(archive).content().bytes();
    const std::string wire(reinterpret_cast<const char*>(bytes.data()), bytes.size());
    CHECK(wire.find("\"schema\":\"csl.scenario-sweep/1\"") != std::string::npos);
    CHECK(wire.find("\"scenario_id\":\"scenario-a\"") != std::string::npos);
    CHECK(wire.find("\"kind\":\"rejected\"") != std::string::npos);
    CHECK(wire.find("\"executor_worker_threads_started\":2") != std::string::npos);
    CHECK(wire.find("\"executor_worker_threads_started\":1") != std::string::npos);
    CHECK(wire.find("\"backend_threads\":null") != std::string::npos);
    CHECK(wire.find("\"memory_support\":\"active_and_retained_reservations\"") != std::string::npos);
    CHECK(wire.find("\"enforced_memory_reservation_budget_bytes\":100") != std::string::npos);
    CHECK(wire.find("\"retained_result_reservation_bytes\":35") != std::string::npos);
    CHECK(std::get<experiments::FamilyQueryResult>(queried).sweep.retained_result_reservation_bytes==30);
    CHECK(std::get<experiments::FamilyQueryResult>(queried).query_result_reservation_bytes==5);
    query_records[1] = recorded;
    const auto mismatched_query = experiments::record_family_query_sweep(sweep_spec(),
        std::get<experiments::FamilyQueryResult>(queried), coarse_records, query_records);
    REQUIRE(std::holds_alternative<artifacts::ArtifactError>(mismatched_query));
    CHECK(std::get<artifacts::ArtifactError>(mismatched_query).path=="sweep.cases[1].query");
}

TEST_CASE("finite sweep budgets reserve retained coarse and query results before admission") {
    const auto prepared = prepare_strategy();
    auto item = sweep_case("scenario-a","config-a",prepared);
    item.resources.workspace_reservation_bytes = 1;
    const ResourcePolicy resources{1,1,1,10};
    ExecutionContext context;
    context.run_id = "retained-budget";
    auto missing = experiments::run_sweep(std::span{&item,1},resources,context,execution::Mode::sequential);
    REQUIRE(std::holds_alternative<Diagnostics>(missing));
    CHECK(std::get<Diagnostics>(missing).front().field=="sweep.cases[0].retained_result_memory");

    item.resources.retained_result_reservation_bytes = 8;
    auto coarse = experiments::run_sweep(std::span{&item,1},resources,context,execution::Mode::sequential);
    REQUIRE(std::holds_alternative<experiments::SweepResult>(coarse));
    CHECK(std::get<experiments::SweepResult>(coarse).retained_result_reservation_bytes==8);
    const auto selector = prepare_selector_provider();
    const execution::ResourceUse query_resources{1,"selector workspace",1,
        execution::CallStopSupport::cooperative_boundaries,3};
    auto over_budget = experiments::run_family_queries(std::get<experiments::SweepResult>(std::move(coarse)),
        selector,resources,context,execution::Mode::sequential,query_resources);
    REQUIRE(std::holds_alternative<Diagnostics>(over_budget));
    CHECK(std::get<Diagnostics>(over_budget).front().field=="family_queries.retained_result_memory");
}
