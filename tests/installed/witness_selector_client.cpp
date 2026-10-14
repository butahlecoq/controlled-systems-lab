#include <csl/synthesis/witness_selector.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <csl/problem/validator.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <stdexcept>
#include <iostream>
using namespace csl;
using namespace csl::registry;
namespace {
template<class T,class... R> T take(std::variant<T,R...> value) {
    if(!std::holds_alternative<T>(value))throw std::runtime_error("Unexpected result variant");
    return std::get<T>(std::move(value));
}
SetHandle interval(std::string id,double lower,double upper) {
    Matrix inequalities{2,1,{1,-1}};
    Matrix equalities{0,1,{}};
    const sets::Description description{SetId{std::move(id)},1,std::vector<std::string>{"u"}};
    const sets::HRepresentation representation{take(numeric::snapshot(inequalities)),
        take(numeric::snapshot_vector(Vector{upper,-lower})),take(numeric::snapshot(equalities)),
        take(numeric::snapshot_vector(Vector{}))};
    return take(sets::make_h(description,representation)).as_handle();
}
void set_quadratic_objective(Problem& problem,double hessian_value,double linear_value,double constant) {
    problem.objective.emplace<QuadraticTerminal>();
    auto& objective=std::get<QuadraticTerminal>(problem.objective);
    objective.Q.rows=1;objective.Q.cols=1;objective.Q.values=Vector{hessian_value};
    objective.linear=Vector{linear_value};objective.offset=constant;
}
Problem source() {
    Matrix state_transition{};state_transition.rows=1;state_transition.cols=1;state_transition.values=Vector{1};
    Matrix control_transition{};control_transition.rows=1;control_transition.cols=1;control_transition.values=Vector{1};
    Matrix external_transition{};external_transition.rows=1;external_transition.cols=0;
    LinearStage transition{std::move(state_transition),std::move(control_transition),std::move(external_transition),Vector{0}};
    Dynamics dynamics{{1,1,0},TimeDomain::discrete,std::move(transition)};
    auto model=std::make_shared<const SystemModel>(SystemModel{std::move(dynamics),{}});
    Problem problem{};problem.id={"ts01"};problem.model=std::move(model);problem.times={0,1,2};
    problem.initial=KnownInitial{Vector{0}};
    problem.controls=ContinuousDomain{{interval("u0",0,1),interval("u1",0,1)}};
    problem.states={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    problem.information=InformationPattern::nominal_open_loop;
    set_quadratic_objective(problem,2,-2,1);
    return problem;
}
problem::ResolvedProblem resolve(Problem p) {
    return take(problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
StrategyRequest request(problem::ResolvedProblem p) {
    FamilyRequest family;family.profile="ts01_exact_integrator";family.objective=p.identity();
    family.target=FamilyTarget::exact_optimal_relation;family.assurance=Assurance::numerical;
    family.representation={"csl.polyhedron.h"};
    StrategyConfiguration configuration;configuration.strategy={"csl.synthesis.ts01-analytic"};
    configuration.representation=family.representation;
    return {std::move(p),configuration,std::move(family),{},{}};
}
ExecutionContext make_execution_context() {
    ExecutionContext result;result.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    return result;
}
SynthesisResult run(StrategyRequest request_) {
    StrategyRegistry strategies;
    if(strategies.add(synthesis::strategy_ts01::make_registration()))throw std::runtime_error("Registration failed");
    Requirements requirements;requirements.output.representation=request_.family.representation;
    requirements.output.family=request_.family.target;
    requirements.output.completeness=Completeness::established;
    auto prepared=take(strategies.prepare(request_,requirements));
    auto workspace=prepared.create();
    return take(workspace->run(make_execution_context()));
}
}

int main() {
    const auto result=run(request(resolve(source())));
    if(!result.family)return 1;
    Registry<LPPort> lp; if(lp.add(take(adapters::lp::make_highs_registration())))return 2;
    Requirements req;req.output.representation={"csl.program-result.v1"};
    auto provider=take(prepare_provider(select_provider(lp,Method{{"csl.lp.highs"},{}},req)));
    Registry<SelectorPort> selectors;if(selectors.add(synthesis::witness_selector::make_registration(provider)))return 3;
    SelectorRequest query{*result.family,{2,0,{{1,-1},{-1,1}},19}};
    Requirements out;out.output.representation={"csl.witness-batch.v1"};
    auto prepared=take(prepare_pipeline(select(selectors,Method{{synthesis::witness_selector::selector_id},{}},query,out)));
    auto workspaces=prepared.create();auto selection=take(std::get<0>(workspaces)->run(make_execution_context()));
    if(selection.termination!=Termination::completed||selection.batch.returned_count()!=2||selection.batch.distinct_count()!=2)return 4;
    if(selection.batch.witnesses[0].controls!=std::vector<Vector>{{0},{1}}||selection.batch.witnesses[1].controls!=std::vector<Vector>{{1},{0}})return 5;
    if(selection.batch.witnesses[0].states!=std::vector<Vector>{{0},{0},{1}}||selection.batch.witnesses[1].states!=std::vector<Vector>{{0},{1},{1}})return 6;
    if(selection.batch.witnesses[0].original_objective!=0||selection.batch.witnesses[1].original_objective!=0||selection.batch.source_family!=result.family->identity())return 7;
    std::cout<<"Installed witness selector: literal endpoints, histories and provenance passed\n";
}
