#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/artifacts/run_statistics.hpp>
#include <csl/execution/observability.hpp>
#include <csl/problem/validator.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <csl/sets/data.hpp>

using namespace csl;
namespace {
template<class T,class... R> T take(std::variant<T,R...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}
SetHandle interval(std::string id,double lower,double upper) {
    Matrix inequalities{2,1,{1,-1}};Matrix equalities{0,1,{}};
    const sets::Description description{SetId{std::move(id)},1,std::vector<std::string>{"u"}};
    const sets::HRepresentation representation{take(numeric::snapshot(inequalities)),
        take(numeric::snapshot_vector(Vector{upper,-lower})),take(numeric::snapshot(equalities)),
        take(numeric::snapshot_vector(Vector{}))};
    return take(sets::make_h(description,representation)).as_handle();
}
problem::ResolvedProblem exact_problem() {
    Matrix a{};a.rows=1;a.cols=1;a.values=Vector{1};
    Matrix b{};b.rows=1;b.cols=1;b.values=Vector{1};
    Matrix e{};e.rows=1;e.cols=0;
    const LinearStage transition{std::move(a),std::move(b),std::move(e),Vector{0}};
    const auto model=std::make_shared<const SystemModel>(SystemModel{Dynamics{{1,1,0},TimeDomain::discrete,transition},{}});
    Problem problem{};problem.id={"ts01-artifact"};problem.model=model;problem.times={0,1,2};
    problem.initial=KnownInitial{Vector{0}};
    problem.controls=ContinuousDomain{{interval("u0",0,1),interval("u1",0,1)}};
    problem.states={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    problem.information=InformationPattern::nominal_open_loop;
    problem.objective.emplace<QuadraticTerminal>();auto& objective=std::get<QuadraticTerminal>(problem.objective);
    objective.Q.rows=1;objective.Q.cols=1;objective.Q.values=Vector{2};objective.linear=Vector{-2};objective.offset=1;
    return take(problem::resolve(problem,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
registry::StrategyRequest strategy_request(const problem::ResolvedProblem& problem,const RepresentationId& representation) {
    FamilyRequest family;family.profile="ts01_exact_integrator";family.objective=problem.identity();
    family.target=FamilyTarget::exact_optimal_relation;family.assurance=Assurance::numerical;family.representation=representation;
    StrategyConfiguration configuration;configuration.strategy={"csl.synthesis.ts01-analytic"};configuration.representation=representation;
    return {problem,configuration,family,"1",{}};
}
artifacts::ResolvedConfiguration artifact_configuration(const RepresentationId& representation) {
    namespace ar=artifacts;
    const ModuleId strategy{"csl.synthesis.ts01-analytic"};const ModuleId lp{"unused-lp"};
    const ar::PinAvailability pin=ar::Unavailable{ar::MissingReason::not_instrumented,{}};
    ar::ConfigurationInput config;config.collection={false,ar::CollectionMode::detail,0,0,0,0};
    config.modules={{"lp",{lp,"1",pin},{}},{"strategy",{strategy,"1",pin},{}}};
    config.numerical={1e-8,1e-8};config.resources={1,1,1,{}};
    config.output={ar::OutputKind::synthesis,Assurance::numerical,FamilyTarget::exact_optimal_relation,
        representation,{1,0,{},{}}};
    config.selector={{"first"},"1",{}};
    config.strategy={strategy,lp,{},{},{},{},{},{"first"},representation};
    return take(ar::resolve_configuration(std::move(config)));
}
}

TEST_CASE("run-statistics v3 encoding fails closed for the live T-S01 proof variant") {
    namespace ar=artifacts;namespace ob=execution::observability;
    const RepresentationId representation{"csl.polyhedron.h"};
    const auto problem=exact_problem();const auto request=strategy_request(problem,representation);
    registry::StrategyRegistry strategies;REQUIRE_FALSE(strategies.add(synthesis::strategy_ts01::make_registration()).has_value());
    registry::Requirements requirements;requirements.output.family=FamilyTarget::exact_optimal_relation;
    requirements.output.completeness=registry::Completeness::established;requirements.output.representation=representation;
    auto prepared=take(strategies.prepare(request,requirements));
    auto workspace=prepared.create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=take(workspace->run(context));
    REQUIRE(result.family);
    const auto config=artifact_configuration(representation);
    const auto statistics=take(ob::merge_observations(take(ob::make_collection_plan(
        {problem,config,{"ts01-run"},{},{},0})),{}));
    const ar::Unavailable missing{ar::MissingReason::not_instrumented,{}};
    ar::RunRecord record{problem.identity(),{1,1,0},2,config,{"ts01-run"},ar::project_final(result),statistics,
        {missing,missing,missing,missing,true,ar::MemoryAccounting::unlimited},{},{},ar::ProblemProvenance::problem_revalidated};
    const auto published=ar::publish_run({problem,record});
    REQUIRE(std::holds_alternative<ar::RunStatistics>(published));
    const auto& owner=std::get<ar::RunStatistics>(published);
    const auto encoded=ar::encode_run(owner);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(encoded));
    CHECK(std::get<ar::ArtifactError>(encoded).code==ar::ArtifactErrorCode::unsupported);
    CHECK(std::get<ar::ArtifactError>(encoded).path=="run.final.family.completeness.support");
}
