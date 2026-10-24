#include <csl/experiments/batch_runner.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#if CSL_INSTALLED_EXPERIMENTS_WITH_HIGHS
#include <csl/adapters/lp/highs.hpp>
#include <csl/synthesis/witness_selector.hpp>
#endif

#include <iostream>
#include <stdexcept>

using namespace csl;

namespace {
template<class T,class... R> T take(std::variant<T,R...> value) {
    if(!std::holds_alternative<T>(value))throw std::runtime_error("Unexpected installed client result");
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

registry::PreparedStrategy prepare_strategy() {
    Matrix state_transition{1,1,{1}};
    Matrix control_transition{1,1,{1}};
    Matrix external_transition{1,0,{}};
    LinearStage transition{std::move(state_transition),std::move(control_transition),
        std::move(external_transition),Vector{0}};
    Dynamics dynamics{{1,1,0},TimeDomain::discrete,std::move(transition)};
    Problem source{};
    source.id={"installed-query"};
    source.model=std::make_shared<const SystemModel>(SystemModel{std::move(dynamics),{}});
    source.times={0,1,2};
    source.initial=KnownInitial{Vector{0}};
    source.controls=ContinuousDomain{{interval("u0",0,1),interval("u1",0,1)}};
    source.states={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    source.information=InformationPattern::nominal_open_loop;
    source.objective=QuadraticTerminal{Matrix{1,1,{2}},Vector{-2},1};
    auto resolved=take(problem::resolve(source,
        {problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));

    FamilyRequest family{"ts01_exact_integrator",resolved.identity(),FamilyTarget::exact_optimal_relation,
        {1e-8,1e-8},Assurance::numerical,{"csl.polyhedron.h"},{}};
    StrategyConfiguration configuration;
    configuration.strategy={"csl.synthesis.ts01-analytic"};
    configuration.representation=family.representation;
    registry::StrategyRegistry strategies;
    if(strategies.add(synthesis::strategy_ts01::make_registration()))
        throw std::runtime_error("Could not register the installed TS01 strategy");
    registry::Requirements requirements;
    requirements.output.representation=family.representation;
    requirements.output.family=family.target;
    requirements.output.completeness=registry::Completeness::established;
    return take(strategies.prepare({std::move(resolved),configuration,family,{},{}},requirements));
}

#if CSL_INSTALLED_EXPERIMENTS_WITH_HIGHS
registry::PreparedProvider<registry::SelectorPort> prepare_selector() {
    registry::Registry<registry::LPPort> lp;
    if(lp.add(take(adapters::lp::make_highs_registration())))
        throw std::runtime_error("Could not register the installed HiGHS adapter");
    registry::Requirements lp_requirements;
    lp_requirements.output.representation={"csl.program-result.v1"};
    auto lp_provider=take(registry::prepare_provider(registry::select_provider(lp,
        registry::Method{{"csl.lp.highs"},{}},lp_requirements)));

    registry::Registry<registry::SelectorPort> selectors;
    if(selectors.add(synthesis::witness_selector::make_registration(std::move(lp_provider))))
        throw std::runtime_error("Could not register the installed witness selector");
    registry::Requirements selector_requirements;
    selector_requirements.output.representation={"csl.witness-batch.v1"};
    return take(registry::prepare_provider(registry::select_provider(selectors,
        registry::Method{{synthesis::witness_selector::selector_id},{}},selector_requirements)));
}
#else
class InstalledEchoSelector final : public WitnessSelectorWorkspace {
public:
    std::variant<WitnessSelection, Unsupported> select(const OptimalFamily& family,
        const WitnessRequest& request, const ExecutionContext&) override {
        WitnessBatch batch;
        batch.requested=request.count;
        batch.selector={"installed.echo-selector"};
        batch.seed=request.seed;
        batch.source_family=family.identity();
        batch.directions=request.directions;
        batch.distinctness_tolerance=request.distinctness_tolerance;
        return WitnessSelection{std::move(batch),Termination::resource_limit,
            "core-profile fixture verifies query plumbing without fabricating trajectories"};
    }
};

registry::PreparedProvider<registry::SelectorPort> prepare_selector() {
    registry::Registry<registry::SelectorPort> selectors;
    registry::Registration<registry::SelectorPort> registration{
        {{"installed.echo-selector"},"1"},
        [](const registry::SelectorRequest&, const registry::Requirements& requirements) -> registry::Capability {
            return registry::Offer{requirements.output};
        },
        [](const registry::SelectorRequest&) { return std::make_unique<InstalledEchoSelector>(); }};
    if(selectors.add(std::move(registration)))
        throw std::runtime_error("Could not register the installed fixture selector");
    registry::Requirements requirements;
    requirements.output.representation={"csl.witness-batch.v1"};
    return take(registry::prepare_provider(registry::select_provider(selectors,
        registry::Method{{"installed.echo-selector"},{}},requirements)));
}
#endif
}

int main() {
    const ResourcePolicy resources{1,1,1,std::nullopt};
    ExecutionContext context;
    context.run_id="installed-family-query";
    const auto strategy=prepare_strategy();
    const experiments::ScenarioSweepCase item{
        {{"installed-scenario"},{"installed-config"}},strategy,
        {1,"analytic strategy uses one caller lane",std::nullopt,execution::CallStopSupport::cooperative_boundaries},
        {2,0.0,{{1,-1},{-1,1}},19}};
    auto coarse=experiments::run_sweep(std::span{&item,1},resources,context,
        execution::Mode::sequential);
    auto sweep=take(std::move(coarse));

    const auto selector=prepare_selector();
    const execution::ResourceUse query_resources{1,"selector uses one caller lane",std::nullopt,
        execution::CallStopSupport::cooperative_boundaries};
    auto queried=experiments::run_family_queries(std::move(sweep),selector,resources,context,
        execution::Mode::sequential,query_resources);
    auto result=take(std::move(queried));
    if(result.queries.size()!=1||result.query_batch.tasks.size()!=1)
        throw std::runtime_error("Installed family query did not schedule one compatible case");
    const auto* scheduled=std::get_if<experiments::FamilyQueryScheduled>(&result.queries[0].status);
    if(!scheduled||scheduled->task_index!=0)
        throw std::runtime_error("Installed family query lost its scenario mapping");
    const auto* returned=std::get_if<execution::Returned<registry::SelectorPort>>(
        &result.query_batch.tasks[0].outcome);
    if(!returned)throw std::runtime_error("Installed family query did not return a selector outcome");
    const auto* selected=std::get_if<WitnessSelection>(&returned->value);
    if(!selected||selected->batch.requested!=2||selected->batch.source_family!=
        std::get<SynthesisResult>(std::get<execution::Returned<registry::StrategyPort>>(
            result.sweep.batch.tasks[0].outcome).value).family->identity())
        throw std::runtime_error("Installed family query lost its witness result or family provenance");
#if CSL_INSTALLED_EXPERIMENTS_WITH_HIGHS
    if(selected->termination!=Termination::completed||selected->batch.returned_count()!=2||
        selected->batch.distinct_count()!=2)
        throw std::runtime_error("Installed real selector did not return the two supported witnesses");
#else
    if(selected->termination!=Termination::resource_limit||selected->batch.returned_count()!=0)
        throw std::runtime_error("Core installed fixture should report no unverified witness trajectories");
#endif

    std::cout<<"Installed experiments client: coarse sweep and family query passed\n";
}
