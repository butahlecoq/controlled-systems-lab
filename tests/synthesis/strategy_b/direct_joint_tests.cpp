#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/synthesis/strategy_b/direct_joint.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <csl/optimization/convex_backend.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/convex/highs.hpp>
#include "compiled_verifiers.hpp"
#include <algorithm>
#include <cmath>
using namespace csl;
using namespace csl::synthesis::strategy_b;
namespace {
bool feasible(const JointProgram&,const Vector&);
template<class T, class... R> T accepted(std::variant<T,R...> value) {
    REQUIRE(std::holds_alternative<T>(value)); return std::get<T>(std::move(value));
}
sets::SetData interval(double upper) {
    return accepted(sets::make_h({{"interval"},1,{}},
        {accepted(numeric::snapshot(Matrix{2,1,{1,-1}})),
         accepted(numeric::snapshot_vector(Vector{upper,0})),
         accepted(numeric::snapshot(Matrix{0,1,{}})),
         accepted(numeric::snapshot_vector(Vector{}))}));
}
Problem integrator(TerminalObjective objective = QuadraticTerminal{{1,1,{2}},{-2},1}) {
    const auto unit=interval(1).as_handle();
    return {{"integrator"},std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}},{}}),
        {0,1,2},KnownInitial{{0}},ContinuousDomain{{unit,unit}},
        {UniversalSet{1},UniversalSet{1},UniversalSet{1}},{},{},
        InformationPattern::nominal_open_loop,std::move(objective)};
}
problem::ResolvedProblem resolve(const Problem& p) {
    return accepted(problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
FamilyRequest request(const problem::ResolvedProblem& p) {
    FamilyRequest r; r.objective=p.identity(); r.profile="nominal_open_loop";
    r.representation={"csl.polyhedron.h"}; return r;
}
TEST_CASE("initial intermediate and terminal constraints survive the sparse lift") {
    auto input=integrator(); input.states={Singleton{{0}},interval(0.5).as_handle(),Singleton{{1}}};
    const auto p=resolve(input);const auto q=accepted(build_joint_program(p,request(p)));
    CHECK(feasible(q,{0,0.25,1,0.25,0.75}));
    CHECK_FALSE(feasible(q,{0,0.75,1,0.75,0.25}));
    CHECK_FALSE(feasible(q,{0,0.25,0.5,0.25,0.25}));
    CHECK_FALSE(feasible(q,{0.1,0.25,1,0.15,0.75}));
}
TEST_CASE("singular dynamics and affine stage offsets require no inverse") {
    auto input=integrator(); input.model=std::make_shared<const SystemModel>(SystemModel{
        {{1,1,0},TimeDomain::discrete,std::vector<LinearStage>{
            {{1,1,{0}},{1,1,{1}},{1,0,{}},{2}},
            {{1,1,{0}},{1,1,{1}},{1,0,{}},{-1}}}}, {}});
    const auto p=resolve(input); const auto q=accepted(build_joint_program(p,request(p)));
    CHECK(feasible(q,{0,2.5,-0.25,0.5,0.75}));
    CHECK_FALSE(feasible(q,{0,2.5,2.25,0.5,0.75}));
}
TEST_CASE("temporal rows keep their authored joint coordinates and row lineage") {
    auto input=integrator();input.temporal=TemporalConstraints{{1,5,{0,2},{3,4},{1,1}},{{0.5,0.5}}};
    const auto p=resolve(input);const auto q=accepted(build_joint_program(p,request(p)));
    CHECK(feasible(q,{0,0.25,0.5,0.25,0.25}));
    CHECK_FALSE(feasible(q,{0,0.25,1,0.25,0.75}));
    REQUIRE_FALSE(q.rows.empty());CHECK(q.rows.back().source==RowSource::temporal);
    CHECK(q.rows.back().source_row==0);
}
bool feasible(const JointProgram& p,const Vector& x) {
    for(std::size_t i=0;i<p.constraints.rows;++i) {
        double v=0;for(auto j=p.constraints.row_offsets[i];j<p.constraints.row_offsets[i+1];++j)
            v+=p.constraints.values[j]*x[p.constraints.column_indices[j]];
        if(p.bounds[i].lower&&v<*p.bounds[i].lower-1e-10)return false;
        if(p.bounds[i].upper&&v>*p.bounds[i].upper+1e-10)return false;
    }return true;
}
bool contains(const sets::SetData& set,const Vector& x) {
    const auto h=std::get<sets::HRepresentation>(set.representation());
    for(std::size_t i=0;i<h.inequalities.rows();++i) {double v=0;for(std::size_t j=0;j<x.size();++j)v+=h.inequalities(i,j)*x[j];if(v>h.upper_bounds[i]+1e-10)return false;}
    for(std::size_t i=0;i<h.equalities.rows();++i) {double v=0;for(std::size_t j=0;j<x.size();++j)v+=h.equalities(i,j)*x[j];if(std::abs(v-h.equality_values[i])>1e-10)return false;}
    return true;
}
template<class Program,class Base> class OracleWorkspace final:public Base {
    Vector anchor_;double value_;bool wrong_;Termination termination_;std::stop_source* stop_;
    ProgramOutcome do_solve(const Program& p,const ExecutionContext&) override {
        auto id=p.identity();if(wrong_)id.program={"foreign"};
        EvidenceSupport support=SymbolicArgument{"literal-joint-oracle","Hand-minimized objective on the authored joint relation."};
        ProgramObjectiveBound bound{value_,{id,support,{}}};
        if(stop_)stop_->request_stop();
        return ProgramResult{termination_,{id,MathematicalOutcome::optimal,support,{}},anchor_,{bound,bound},"independent analytic oracle"};
    }
public: OracleWorkspace(Vector a,double v,bool wrong,Termination term,std::stop_source* stop):anchor_(std::move(a)),value_(v),wrong_(wrong),termination_(term),stop_(stop){}
};
DirectJointWorkspace oracle(Vector anchor,double value,bool wrong=false,bool reject=false,Termination term=Termination::completed,std::stop_source* stop=nullptr) {
    registry::Registry<registry::LPPort> lp;registry::Registry<registry::ConvexPort> qp;
    registry::Requirements requirements;requirements.output.representation={"csl.program-result.v1"};
    const auto offer=[=](const auto&,const registry::Requirements&)->registry::Capability {
        if(reject)return Diagnostics{{DiagnosticCode::unsupported,"oracle.capacity","Generated program rejected by injected provider."}};
        return registry::Offer{requirements.output};
    };
    lp.add({{{"oracle-lp"},"1"},offer,[=](const LinearProgram&){return std::make_unique<OracleWorkspace<LinearProgram,LPWorkspace>>(anchor,value,wrong,term,stop);}});
    qp.add({{{"oracle-qp"},"1"},offer,[=](const ConvexProgram&){return std::make_unique<OracleWorkspace<ConvexProgram,ConvexWorkspace>>(anchor,value,wrong,term,stop);}});
    return {accepted(registry::prepare_provider(registry::select_provider(lp,registry::Method{{"oracle-lp"},{}},requirements))),
        accepted(registry::prepare_provider(registry::select_provider(qp,registry::Method{{"oracle-qp"},{}},requirements)))};
}
const DirectJointPayload& payload(const SynthesisResult& r) {
    REQUIRE(r.family);CHECK(r.family->target()==FamilyTarget::candidate_relaxation);
    const auto& candidate=std::get<CandidateFamily>(r.family->outcome());
    const auto cast=std::dynamic_pointer_cast<const DirectJointPayload>(candidate.relation.payload);REQUIRE(cast);return *cast;
}
registry::PreparedStrategy registered_prepared(const problem::ResolvedProblem& p,const FamilyRequest& q,
    bool foreign_provider=false,Termination solver_termination=Termination::completed) {
    registry::Registry<registry::LPPort> lp;registry::Registry<registry::ConvexPort> qp;registry::StrategyRegistry strategies;
    auto linear=accepted(adapters::lp::make_highs_registration());auto convex=accepted(adapters::convex::make_highs_registration());
    if(foreign_provider) {
        registry::Requirements program_requirements;program_requirements.output.representation={"csl.program-result.v1"};
        const auto offer=[=](const auto&,const registry::Requirements&)->registry::Capability{return registry::Offer{program_requirements.output};};
        linear={{{"oracle-lp"},"1"},offer,[](const LinearProgram&){return std::make_unique<OracleWorkspace<LinearProgram,LPWorkspace>>(Vector{0,0.25,1,0.25,0.75},0,true,Termination::completed,nullptr);}};
        convex={{{"oracle-qp"},"1"},offer,[](const ConvexProgram&){return std::make_unique<OracleWorkspace<ConvexProgram,ConvexWorkspace>>(Vector{0,0.25,1,0.25,0.75},0,true,Termination::completed,nullptr);}};
    } else if(solver_termination!=Termination::completed) {
        registry::Requirements program_requirements;program_requirements.output.representation={"csl.program-result.v1"};
        const auto offer=[=](const auto&,const registry::Requirements&)->registry::Capability{return registry::Offer{program_requirements.output};};
        linear={{{"oracle-lp"},"1"},offer,[=](const LinearProgram&){return std::make_unique<OracleWorkspace<LinearProgram,LPWorkspace>>(Vector{0,0.25,1,0.25,0.75},0,false,solver_termination,nullptr);}};
        convex={{{"oracle-qp"},"1"},offer,[=](const ConvexProgram&){return std::make_unique<OracleWorkspace<ConvexProgram,ConvexWorkspace>>(Vector{0,0.25,1,0.25,0.75},0,false,solver_termination,nullptr);}};
    }
    const auto lid=linear.identity.id,qid=convex.identity.id;lp.add(std::move(linear));qp.add(std::move(convex));
    CHECK_FALSE(strategies.add(make_registration(lp,qp)));
    StrategyConfiguration configuration;configuration.strategy={"csl.synthesis.strategy-b"};configuration.lp=lid;configuration.convex=qid;
    configuration.representation={"csl.polyhedron.h"};
    registry::Requirements requirements;requirements.output.representation={"csl.polyhedron.h"};
    requirements.output.family=FamilyTarget::candidate_relaxation;requirements.output.completeness=registry::Completeness::unestablished;
    return accepted(strategies.prepare({p,configuration,q,"1"},requirements));
}
}
TEST_CASE("joint program preserves the two-step integrator and original terminal objective") {
    const auto p=resolve(integrator()); const auto program=accepted(build_joint_program(p,request(p)));
    CHECK(feasible(program,{0,0,1,0,1})); CHECK(feasible(program,{0,1,1,1,0}));
    CHECK_FALSE(feasible(program,{0,0,1,1,0}));
    const auto& qp=std::get<ConvexProgram>(program.program);
    const auto e=accepted(optimization::evaluate_primal(qp,Vector{0,1,2,1,1},{1e-8,1e-8},{{"oracle"},"1"}));
    CHECK(e.original_objective==1); CHECK(program.rows.size()==program.constraints.rows);
    CHECK(program.source_to_program==std::vector<std::size_t>{0,1,2,3,4});
}
TEST_CASE("T-S01 extracts all correlated optimal histories without claiming completeness") {
    const auto p=resolve(integrator());const auto r=oracle({0,0.25,1,0.25,0.75},0).solve(p,request(p),{});
    const auto& data=payload(r);CHECK(contains(data.relation,{0,0,1,0,1}));
    CHECK(contains(data.relation,{0,1,1,1,0}));CHECK(contains(data.relation,{0,0.5,1,0.5,0.5}));
    CHECK_FALSE(contains(data.relation,{0,1,2,1,1}));CHECK_FALSE(contains(data.relation,{0,0,1,1,0}));
    REQUIRE(data.optimization);CHECK(data.optimization->objective.lower->value==0);
    CHECK(r.outcome.value==MathematicalOutcome::undetermined);CHECK_FALSE(r.objective.lower);
    REQUIRE(r.objective.upper);CHECK(r.objective.upper->value==0);REQUIRE(r.incumbents.size()==1);
    CHECK(r.incumbents[0].witness.original_objective==0);
}
TEST_CASE("T-S02 constant objective retains every feasible history and terminal point") {
    for(const TerminalObjective objective:std::vector<TerminalObjective>{LinearTerminal{{0},3},QuadraticTerminal{{1,1,{0}},{0},3},ResidualNormTerminal{{1,1,{0}},{3}}}) {
        const auto p=resolve(integrator(objective));const auto r=oracle({0,0,0,0,0},3).solve(p,request(p),{});
        const auto& data=payload(r);CHECK(contains(data.relation,{0,0,0,0,0}));CHECK(contains(data.relation,{0,1,2,1,1}));
        CHECK(contains(data.relation,{0,0.3,1.1,0.3,0.8}));CHECK_FALSE(contains(data.relation,{0,0,1,1,0}));
    }
}
TEST_CASE("T-S03 singular A preserves earlier controls at a unique terminal optimum") {
    auto input=integrator(QuadraticTerminal{{1,1,{2}},{-1},0.25});
    auto model=*input.model;std::get<LinearStage>(model.dynamics.stages).A.values={0};input.model=std::make_shared<const SystemModel>(model);
    const auto p=resolve(input);const auto r=oracle({0,0.25,0.5,0.25,0.5},0).solve(p,request(p),{});
    const auto& data=payload(r);CHECK(contains(data.relation,{0,0,0.5,0,0.5}));CHECK(contains(data.relation,{0,1,0.5,1,0.5}));
    CHECK_FALSE(contains(data.relation,{0,0,1,0,1}));
}
TEST_CASE("provider rejection retains the feasible candidate and scoped request provenance") {
    const auto p=resolve(integrator());const auto r=oracle({0,0.25,1,0.25,0.75},0,false,true).solve(p,request(p),{});
    CHECK(r.termination==Termination::operation_rejected);const auto& data=payload(r);CHECK_FALSE(data.optimization);
    CHECK(contains(data.relation,{0,1,2,1,1}));REQUIRE(std::holds_alternative<ScopedRequestRejection>(r.stop));
    const auto& stop=std::get<ScopedRequestRejection>(r.stop);CHECK(stop.request.port=="convex");
    CHECK(stop.retained.partial_or_candidate_family);CHECK_FALSE(stop.completed_lineage.empty());
}
TEST_CASE("foreign solver evidence cannot refine or promote the candidate") {
    const auto p=resolve(integrator());const auto r=oracle({0,0.25,1,0.25,0.75},0,true).solve(p,request(p),{});
    CHECK(r.termination==Termination::contract_rejected);const auto& data=payload(r);CHECK_FALSE(data.optimization);
    CHECK(contains(data.relation,{0,1,2,1,1}));CHECK(r.incumbents.empty());CHECK_FALSE(r.objective.upper);
}
TEST_CASE("stopped solver evidence remains scoped while valid incumbent and candidate survive") {
    const auto p=resolve(integrator());const auto r=oracle({0,0.25,1,0.25,0.75},0,false,false,Termination::resource_limit).solve(p,request(p),{});
    CHECK(r.termination==Termination::resource_limit);const auto& data=payload(r);REQUIRE(data.optimization);
    CHECK(contains(data.relation,{0,1,1,1,0}));REQUIRE(r.objective.upper);CHECK(r.objective.upper->value==0);
    CHECK(r.incumbents.size()==1);
}
TEST_CASE("numerical failure preserves the caller-visible incumbent bound and candidate") {
    const auto p=resolve(integrator());
    const auto prepared=registered_prepared(p,request(p),false,Termination::numerical_failure);
    auto workspace=prepared.create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=accepted(workspace->run(context));
    CHECK(result.termination==Termination::numerical_failure);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK(result.spans.empty());
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(result.stop));
    const auto& stop=std::get<ScopedOperationStopped>(result.stop);
    CHECK(stop.stop.reason==StopReason::numerical_failure);
    CHECK(stop.stop.diagnostics=="independent analytic oracle");
    CHECK(stop.request.request==RequestId{"syn04-joint:"+p.identity().value});
    CHECK(stop.request.port=="convex");
    CHECK(stop.request.requested_module==ModuleId{"oracle-qp"});
    CHECK_FALSE(stop.request.requested_version);
    CHECK(stop.request.actual_module==ModuleId{"oracle-qp"});
    CHECK(stop.request.actual_version=="1");

    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    REQUIRE(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    const auto& data=payload(result);
    CHECK(contains(data.relation,{0,0.25,1,0.25,0.75}));
    REQUIRE(data.optimization);
    CHECK(data.optimization->termination==Termination::numerical_failure);
    CHECK(data.optimization->raw_diagnostics=="independent analytic oracle");
    REQUIRE(data.optimization->objective.lower);
    CHECK(data.optimization->objective.lower->value==0);
    CHECK(data.optimization->objective.lower->evidence.subject==data.optimization->outcome.subject);
    CHECK(std::holds_alternative<SymbolicArgument>(data.optimization->objective.lower->evidence.support));
    REQUIRE(data.optimization->objective.upper);
    CHECK(data.optimization->objective.upper->value==0);
    CHECK(data.optimization->objective.upper->evidence.subject==data.optimization->outcome.subject);
    CHECK(std::holds_alternative<SymbolicArgument>(data.optimization->objective.upper->evidence.support));
    REQUIRE(result.incumbents.size()==1);
    CHECK(result.incumbents.front().feasibility.problem==p.identity());
    CHECK(std::holds_alternative<NumericalCheck>(result.incumbents.front().feasibility.support));
    REQUIRE(result.objective.upper);
    CHECK(result.objective.upper->value==0);
    CHECK(result.objective.upper->evidence.problem==p.identity());
    CHECK(std::holds_alternative<NumericalCheck>(result.objective.upper->evidence.support));
    CHECK(stop.retained.upper_bound);
    CHECK(stop.retained.incumbents==1);
    CHECK(stop.retained.partial_or_candidate_family);
}

TEST_CASE("registered Strategy B publishes complete T-S01 evidence only through the exact profile gate") {
    const auto p=resolve(integrator());
    auto exact=request(p);exact.profile=synthesis::strategy_ts01::profile_id;exact.target=FamilyTarget::exact_optimal_relation;
    registry::Registry<registry::LPPort> lp;registry::Registry<registry::ConvexPort> qp;registry::StrategyRegistry strategies;
    auto lp_registration=accepted(adapters::lp::make_highs_registration());
    auto convex_registration=accepted(adapters::convex::make_highs_registration());
    const auto lp_id=lp_registration.identity.id,convex_id=convex_registration.identity.id;
    REQUIRE_FALSE(lp.add(std::move(lp_registration)));
    REQUIRE_FALSE(qp.add(std::move(convex_registration)));
    REQUIRE_FALSE(strategies.add(make_registration(lp,qp)));
    StrategyConfiguration configuration;configuration.strategy={"csl.synthesis.strategy-b"};
    configuration.lp=lp_id;configuration.convex=convex_id;configuration.representation={"csl.polyhedron.h"};
    registry::Requirements requirements;requirements.output.representation={"csl.polyhedron.h"};
    requirements.output.assurance=Assurance::numerical;requirements.output.family=FamilyTarget::exact_optimal_relation;
    requirements.output.completeness=registry::Completeness::established;
    auto prepared=strategies.prepare({p,configuration,exact,"1"},requirements);
    REQUIRE(std::holds_alternative<registry::PreparedStrategy>(prepared));
    auto workspace=std::get<registry::PreparedStrategy>(std::move(prepared)).create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    context.numerical=exact.numerical;
    const auto result=accepted(workspace->run(context));
    REQUIRE(result.termination==Termination::completed);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
    CHECK(result.family->registry_verified());
    CHECK(result.outcome.value==MathematicalOutcome::optimal);
    const auto& identity=result.family->identity();
    CHECK(identity.strategy==ModuleId{"csl.synthesis.strategy-b"});
    CHECK(identity.strategy_version=="1");
    REQUIRE(identity.lineage.size()==2);
    CHECK(identity.lineage[0].request==RequestId{"syn04-build:"+p.identity().value});
    CHECK(identity.lineage[1].request==RequestId{"syn04-extract:"+p.identity().value});
    const SetId feasible_id{"syn04-feasible:"+p.identity().value};
    const SetId optimal_id{"syn04-optimal-level:"+p.identity().value};
    const std::vector<TransformStepIdentity> expected_lineage{
        {{"syn04-build:"+p.identity().value},{p.identity().value},feasible_id,{"csl.synthesis.strategy-b"},"1"},
        {{"syn04-extract:"+p.identity().value},feasible_id,optimal_id,{"csl.synthesis.strategy-b"},"1"}};
    CHECK(identity.lineage==expected_lineage);
    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    const auto relation=std::dynamic_pointer_cast<const synthesis::strategy_ts01::ExactJointRelation>(complete.relation.payload);
    REQUIRE(relation);
    CHECK(relation->contains(Vector{0,0.5,1,0.5,0.5}));
    CHECK(relation->contains(Vector{0,0.75,1,0.75,0.25}));
    CHECK_FALSE(relation->contains(Vector{0,0.5,1,0.5,0.25}));

    const registry::StrategyRequest frozen{p,configuration,exact,"1",expected_lineage};
    const CompleteFamilyProposal proposal{identity,complete};
    const auto verifier=registry::detail::find_compiled_verifier({"csl.verifier.ts01-analytic"},"1");
    REQUIRE(verifier);
    CHECK(verifier->verify(frozen,proposal).empty());
    auto wrong_request=frozen;wrong_request.lineage[1].version="foreign";
    CHECK_FALSE(verifier->verify(wrong_request,proposal).empty());
    auto wrong_proposal=proposal;wrong_proposal.identity.lineage[1].version="foreign";
    wrong_proposal.family.completeness.binding=wrong_proposal.identity;
    CHECK_FALSE(verifier->verify(frozen,wrong_proposal).empty());

    const auto neighboring=resolve(integrator(QuadraticTerminal{{1,1,{2}},{-1},0.25}));
    auto unsupported=request(neighboring);unsupported.profile=synthesis::strategy_ts01::profile_id;
    unsupported.target=FamilyTarget::exact_optimal_relation;
    CHECK(std::holds_alternative<registry::Rejection>(strategies.prepare({neighboring,configuration,unsupported,"1"},requirements)));
}
TEST_CASE("late T-S01 provider rejection retains a typed candidate relation and executed lineage") {
    const auto p=resolve(integrator());
    auto exact=request(p);exact.profile=synthesis::strategy_ts01::profile_id;
    exact.target=FamilyTarget::exact_optimal_relation;
    registry::Registry<registry::LPPort> lp;registry::Registry<registry::ConvexPort> qp;
    registry::StrategyRegistry strategies;
    auto lp_registration=accepted(adapters::lp::make_highs_registration());
    auto convex_registration=accepted(adapters::convex::make_highs_registration());
    const auto lp_id=lp_registration.identity.id,convex_id=convex_registration.identity.id;
    convex_registration.capabilities=[](const ConvexProgram&,const registry::Requirements&)->registry::Capability {
        return Diagnostics{{DiagnosticCode::unsupported,"injected.late_rejection","Rejected after joint construction."}};
    };
    REQUIRE_FALSE(lp.add(std::move(lp_registration)));
    REQUIRE_FALSE(qp.add(std::move(convex_registration)));
    REQUIRE_FALSE(strategies.add(make_registration(lp,qp)));
    StrategyConfiguration configuration;configuration.strategy={"csl.synthesis.strategy-b"};
    configuration.lp=lp_id;configuration.convex=convex_id;configuration.representation={"csl.polyhedron.h"};
    registry::Requirements requirements;requirements.output.representation={"csl.polyhedron.h"};
    requirements.output.assurance=Assurance::numerical;
    requirements.output.family=FamilyTarget::exact_optimal_relation;
    requirements.output.completeness=registry::Completeness::established;
    auto prepared=strategies.prepare({p,configuration,exact,"1"},requirements);
    REQUIRE(std::holds_alternative<registry::PreparedStrategy>(prepared));
    auto workspace=std::get<registry::PreparedStrategy>(std::move(prepared)).create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    context.numerical=exact.numerical;
    const auto result=accepted(workspace->run(context));
    CHECK(result.termination==Termination::operation_rejected);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK_FALSE(result.family->registry_verified());
    REQUIRE(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    const auto& identity=result.family->identity();
    CHECK(identity.problem==p.identity());
    CHECK(identity.request==exact);
    CHECK(identity.strategy==ModuleId{"csl.synthesis.strategy-b"});
    CHECK(identity.strategy_version=="1");
    REQUIRE(identity.lineage.size()==1);
    CHECK(identity.lineage[0].request==RequestId{"syn04-build:"+p.identity().value});
    const auto& candidate=std::get<CandidateFamily>(result.family->outcome());
    CHECK(candidate.relation.representation==RepresentationId{"csl.polyhedron.h"});
    CHECK(std::holds_alternative<HeuristicRelationEvidence>(candidate.relation_to_target));
    CHECK(std::holds_alternative<Unestablished>(candidate.feasibility));
    const auto retained_payload=std::dynamic_pointer_cast<const DirectJointPayload>(candidate.relation.payload);
    REQUIRE(retained_payload);
    CHECK_FALSE(retained_payload->optimization);
    CHECK(contains(retained_payload->relation,{0,0,1,0,1}));
    CHECK(contains(retained_payload->relation,{0,1,1,1,0}));
    CHECK_FALSE(result.objective.lower);
    CHECK_FALSE(result.objective.upper);
    CHECK(result.incumbents.empty());
    REQUIRE(std::holds_alternative<ScopedRequestRejection>(result.stop));
    const auto& stop=std::get<ScopedRequestRejection>(result.stop);
    CHECK(stop.completed_lineage==identity.lineage);
    CHECK(stop.retained.partial_or_candidate_family);
    CHECK_FALSE(stop.retained.lower_bound);
    CHECK_FALSE(stop.retained.upper_bound);
    CHECK(stop.retained.incumbents==0);
}
TEST_CASE("unsupported assurance targets and policy mismatch fail before solving") {
    const auto p=resolve(integrator());auto workspace=oracle({0,0.25,1,0.25,0.75},0);
    for(auto target:{FamilyTarget::exact_optimal_relation,FamilyTarget::partial_relation}) {
        auto q=request(p);q.target=target;const auto r=workspace.solve(p,q,{});CHECK(r.termination==Termination::operation_rejected);CHECK_FALSE(r.family);
    }
    auto q=request(p);q.assurance=Assurance::validated;auto r=workspace.solve(p,q,{});CHECK(r.termination==Termination::operation_rejected);CHECK_FALSE(r.family);
    q=request(p);ExecutionContext context;context.numerical={1e-3,1e-3};r=workspace.solve(p,q,context);
    CHECK(r.termination==Termination::contract_rejected);CHECK_FALSE(r.family);
}
TEST_CASE("existing StrategyRegistry snapshots admitted native providers and returns the constant-objective relation") {
    const auto p=resolve(integrator(LinearTerminal{{0},3}));
    const auto prepared=registered_prepared(p,request(p));CHECK(prepared.provenance().size()==3);
    auto workspace=prepared.create();ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=accepted(workspace->run(context));const auto& data=payload(result);
    CHECK(contains(data.relation,{0,0,0,0,0}));CHECK(contains(data.relation,{0,1,2,1,1}));
    REQUIRE(data.provider);CHECK(data.provider->actual->id.value!="oracle-lp");
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);CHECK(result.family->identity().request==request(p));
    CHECK(result.family->identity().lineage.size()==2);REQUIRE(result.objective.upper);CHECK(result.objective.upper->value==3);
}
TEST_CASE("registered Strategy B candidate identity mismatches are rejected by the caller boundary") {
    const auto p=resolve(integrator(LinearTerminal{{0},3}));
    const auto prepared=registered_prepared(p,request(p));
    auto workspace=prepared.create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=accepted(workspace->run(context));
    REQUIRE(result.family);
    const auto& family=*result.family;
    const SynthesisIdentityExpectation expected{p.identity(),request(p),p.constraints().coordinates(),
        {"csl.synthesis.strategy-b"},"1",std::nullopt};
    REQUIRE(family.target()==FamilyTarget::candidate_relaxation);
    REQUIRE(std::holds_alternative<CandidateFamily>(family.outcome()));
    CHECK(check_synthesis_result(result,expected).empty());

    auto expect_identity_rejection=[&](SynthesisIdentityExpectation expected) {
        const auto diagnostics=check_synthesis_result(result,expected);
        CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[](const Diagnostic& diagnostic) {
            return diagnostic.code==DiagnosticCode::evidence_mismatch && diagnostic.field=="family.identity";
        }));
        CHECK(family.target()==FamilyTarget::candidate_relaxation);
        CHECK(std::holds_alternative<CandidateFamily>(family.outcome()));
    };

    auto wrong_problem=expected;wrong_problem.problem.value+="-foreign";expect_identity_rejection(wrong_problem);
    auto wrong_request=expected;wrong_request.request.profile+="-foreign";expect_identity_rejection(wrong_request);
    auto wrong_coordinates=expected;++wrong_coordinates.coordinates.horizon;expect_identity_rejection(wrong_coordinates);
    auto wrong_strategy=expected;wrong_strategy.strategy={"csl.synthesis.foreign"};expect_identity_rejection(wrong_strategy);
    auto wrong_version=expected;wrong_version.strategy_version+="-foreign";expect_identity_rejection(wrong_version);
}
TEST_CASE("late extraction materialization stop retains program evidence incumbent and feasible candidate") {
    const auto p=resolve(integrator());auto q=request(p);q.materialization_limit=7;
    const auto r=oracle({0,0.25,1,0.25,0.75},0).solve(p,q,{});
    CHECK(r.termination==Termination::resource_limit);const auto& data=payload(r);REQUIRE(data.optimization);
    CHECK(contains(data.relation,{0,1,2,1,1}));REQUIRE(r.objective.upper);CHECK(r.incumbents.size()==1);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(r.stop));
    CHECK(std::get<ScopedOperationStopped>(r.stop).retained.upper_bound);
    CHECK(std::get<ScopedOperationStopped>(r.stop).retained.partial_or_candidate_family);
}
TEST_CASE("early cancellation and deadline retain their distinct source stop reasons") {
    const auto p=resolve(integrator());auto workspace=oracle({0,0.25,1,0.25,0.75},0);
    std::stop_source stop;stop.request_stop();ExecutionContext cancellation;cancellation.cancellation=stop.get_token();
    const auto cancelled=workspace.solve(p,request(p),cancellation);CHECK(cancelled.termination==Termination::cancelled);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(cancelled.stop));CHECK(std::get<ScopedOperationStopped>(cancelled.stop).stop.reason==StopReason::cancelled);
    CHECK_FALSE(cancelled.family);
    ExecutionContext deadline;deadline.deadline=std::chrono::steady_clock::now();
    const auto expired=workspace.solve(p,request(p),deadline);CHECK(expired.termination==Termination::cancelled);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(expired.stop));CHECK(std::get<ScopedOperationStopped>(expired.stop).stop.reason==StopReason::deadline_expired);
    CHECK_FALSE(expired.family);
    const FamilyIdentity expected{p.identity(),request(p),p.constraints().coordinates(),{"csl.synthesis.strategy-b"},"1",{}};
    CHECK(check_synthesis_result(expired,expected).empty());
}
TEST_CASE("early materialization row limit is a resource stop accepted by the shared boundary") {
    const auto p=resolve(integrator());auto q=request(p);q.materialization_limit=0;
    const auto r=oracle({0,0.25,1,0.25,0.75},0).solve(p,q,{});
    CHECK(r.termination==Termination::resource_limit);CHECK(r.outcome.value==MathematicalOutcome::undetermined);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(r.stop));
    const auto& stop=std::get<ScopedOperationStopped>(r.stop);
    CHECK(stop.stop.reason==StopReason::resource_limit);CHECK(stop.request.port=="strategy");
    CHECK_FALSE(stop.request.request.value.empty());CHECK_FALSE(stop.stop.diagnostics.empty());
    CHECK_FALSE(stop.retained.lower_bound);CHECK_FALSE(stop.retained.upper_bound);
    CHECK(stop.retained.incumbents==0);CHECK_FALSE(stop.retained.partial_or_candidate_family);
    CHECK_FALSE(r.family);CHECK(r.incumbents.empty());CHECK_FALSE(r.objective.upper);
    const FamilyIdentity expected{p.identity(),q,p.constraints().coordinates(),{"csl.synthesis.strategy-b"},"1",{}};
    CHECK(check_synthesis_result(r,expected).empty());
}
TEST_CASE("residual norm keeps the original value rather than its solver square") {
    const auto p=resolve(integrator(ResidualNormTerminal{{1,1,{2}},{7}}));
    const auto program=accepted(build_joint_program(p,request(p)));
    const auto evaluated=accepted(optimization::evaluate_primal(std::get<ConvexProgram>(program.program),Vector{0,1,2,1,1},{1e-8,1e-8},{{"norm-oracle"},"1"}));
    CHECK(evaluated.original_objective==3);CHECK(evaluated.solver_objective==9);
    const auto r=oracle({0,1,2,1,1},3).solve(p,request(p),{});const auto& data=payload(r);
    CHECK(contains(data.relation,{0,1,2,1,1}));CHECK_FALSE(contains(data.relation,{0,0.5,1,0.5,0.5}));
    REQUIRE(r.objective.upper);CHECK(r.objective.upper->value==3);CHECK(r.incumbents[0].witness.original_objective==3);
}
TEST_CASE("zero horizon retains the initial terminal point with no artificial control") {
    auto input=integrator(LinearTerminal{{2},1});input.times={0};input.initial=KnownInitial{{2}};
    input.controls=ContinuousDomain{{}};input.states={UniversalSet{1}};
    const auto p=resolve(input);const auto r=oracle({2},5).solve(p,request(p),{});const auto& data=payload(r);
    CHECK(contains(data.relation,{2}));CHECK_FALSE(contains(data.relation,{1}));
    CHECK(data.construction.coordinates.horizon==0);REQUIRE(r.incumbents.size()==1);
    CHECK(r.incumbents[0].witness.controls.empty());CHECK(r.incumbents[0].witness.states.size()==1);
}
TEST_CASE("native V constraints are rejected instead of silently omitted") {
    auto input=integrator();const auto vertex=accepted(sets::make_v({{"state-vertex"},1,{}},
        {accepted(numeric::snapshot(Matrix{1,1,{0.5}})),accepted(numeric::snapshot(Matrix{0,1,{}}))}));
    input.states[1]=vertex.as_handle();const auto p=resolve(input);
    const auto built=build_joint_program(p,request(p));REQUIRE(std::holds_alternative<Diagnostics>(built));
    const auto r=oracle({0,0.25,1,0.25,0.75},0).solve(p,request(p),{});
    CHECK(r.termination==Termination::operation_rejected);CHECK_FALSE(r.family);
}
TEST_CASE("an infeasible numerical anchor cannot narrow the relation or supply an incumbent") {
    const auto p=resolve(integrator());const auto r=oracle({0,1,1,1,1},0).solve(p,request(p),{});
    const auto& data=payload(r);CHECK(contains(data.relation,{0,1,2,1,1}));
    CHECK(r.incumbents.empty());CHECK_FALSE(r.objective.upper);CHECK(r.outcome.value==MathematicalOutcome::undetermined);
}
TEST_CASE("cancellation after solving retains program evidence and stops original verification") {
    const auto p=resolve(integrator());std::stop_source source;ExecutionContext context;context.cancellation=source.get_token();
    const auto r=oracle({0,0.25,1,0.25,0.75},0,false,false,Termination::completed,&source).solve(p,request(p),context);
    CHECK(r.termination==Termination::cancelled);const auto& data=payload(r);REQUIRE(data.optimization);
    CHECK(contains(data.relation,{0,1,2,1,1}));CHECK(r.incumbents.empty());CHECK_FALSE(r.objective.upper);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(r.stop));CHECK(std::get<ScopedOperationStopped>(r.stop).stop.reason==StopReason::cancelled);
}
TEST_CASE("registered deadline stop survives public result sanitization") {
    const auto p=resolve(integrator());const auto prepared=registered_prepared(p,request(p));
    ExecutionContext context;context.deadline=std::chrono::steady_clock::now()-std::chrono::seconds(1);
    auto workspace=prepared.create();const auto r=accepted(workspace->run(context));
    CHECK(r.termination==Termination::cancelled);REQUIRE(std::holds_alternative<ScopedOperationStopped>(r.stop));
    CHECK(std::get<ScopedOperationStopped>(r.stop).stop.reason==StopReason::deadline_expired);
    CHECK_FALSE(r.family);CHECK(r.incumbents.empty());CHECK(r.outcome.value==MathematicalOutcome::undetermined);
}
TEST_CASE("registered early row-budget stop survives public result sanitization") {
    const auto p=resolve(integrator());auto q=request(p);q.materialization_limit=0;
    const auto prepared=registered_prepared(p,q);auto workspace=prepared.create();const auto r=accepted(workspace->run({}));
    CHECK(r.termination==Termination::resource_limit);REQUIRE(std::holds_alternative<ScopedOperationStopped>(r.stop));
    CHECK(std::get<ScopedOperationStopped>(r.stop).stop.reason==StopReason::resource_limit);
    CHECK_FALSE(r.family);CHECK(r.incumbents.empty());CHECK(r.outcome.value==MathematicalOutcome::undetermined);
}
TEST_CASE("validation failure uses the contract product without a sanitizer replacement") {
    const auto p=resolve(integrator());const auto q=request(p);ExecutionContext context;context.numerical={1e-3,1e-3};
    const auto direct=oracle({0,0.25,1,0.25,0.75},0).solve(p,q,context);
    CHECK(direct.termination==Termination::contract_rejected);REQUIRE(std::holds_alternative<ContractValidationFailure>(direct.stop));
    const SynthesisIdentityExpectation expected{p.identity(),q,p.constraints().coordinates(),
        {"csl.synthesis.strategy-b"},"1",std::nullopt};
    CHECK(check_synthesis_result(direct,expected).empty());
    const auto prepared=registered_prepared(p,q,true);auto workspace=prepared.create();const auto r=accepted(workspace->run({}));
    CHECK(r.termination==Termination::contract_rejected);REQUIRE(std::holds_alternative<ContractValidationFailure>(r.stop));
    const auto& failure=std::get<ContractValidationFailure>(r.stop);REQUIRE_FALSE(failure.diagnostics.empty());
    for(const auto& error:failure.diagnostics) {CHECK(error.code==DiagnosticCode::evidence_mismatch);CHECK(error.field!="result.stop");}
    CHECK(r.incumbents.empty());CHECK(failure.retained.partial_or_candidate_family);
    const auto& data=payload(r);CHECK_FALSE(data.optimization);CHECK(contains(data.relation,{0,1,2,1,1}));
    CHECK(check_synthesis_result(r,expected).empty());
}
