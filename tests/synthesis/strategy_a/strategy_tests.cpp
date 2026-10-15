#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/contracts.hpp>
#include <csl/synthesis/ts02_constant_integrator.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include "../../../src/registry/compiled_verifiers.hpp"
#include <cmath>
#include <iostream>
#include <limits>

using namespace csl;
using namespace csl::registry;
namespace {
template<class T,class... E> T take(std::variant<T,E...> value) {
    if(!std::holds_alternative<T>(value))std::visit([](const auto& item) {
        if constexpr(requires {item.diagnostics.begin()->field;})
            for(const auto& d:item.diagnostics)std::cerr<<d.field<<": "<<d.explanation<<'\n';
    },value);
    REQUIRE(std::holds_alternative<T>(value));return std::get<T>(std::move(value));
}
template<class T,class V> T alternative(V value) {
    REQUIRE(std::holds_alternative<T>(value));return std::get<T>(std::move(value));
}
SetHandle interval(std::string id,double lo,double hi,std::string label="x") {
    return take(sets::make_h({{std::move(id)},1,{std::move(label)}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}})),take(numeric::snapshot_vector(Vector{hi,-lo})),
         take(numeric::snapshot(Matrix{0,1,{}})),take(numeric::snapshot_vector(Vector{}))})).as_handle();
}
template<class Port> PreparedProvider<Port> selected(Registration<Port> entry,std::string representation) {
    Registry<Port> registry;Method method{entry.identity.id,entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());Requirements requirements;
    requirements.output.representation={std::move(representation)};
    if constexpr(std::is_same_v<Port,GeometryPort> || std::is_same_v<Port,ConversionPort>)
        requirements.output.relation=SetRelation::equivalent;
    return take(prepare_provider(select_provider(registry,method,requirements)));
}
problem::ResolvedProblem integrator(bool constant=false,bool singular=false) {
    QuadraticTerminal objective{};
    objective.Q={1,1,{2}};
    objective.linear={-2};
    objective.offset=1;
    Problem source{{"strategy-a-integrator"},std::make_shared<const SystemModel>(SystemModel{
        {{1,1,0},TimeDomain::discrete,LinearStage{{1,1,{singular?0.0:1.0}},
            {1,1,{1}},{1,0,{}},{0}}}, {}}),{0,1,2},KnownInitial{{0}},
        ContinuousDomain{{interval("u0",0,1,"u"),interval("u1",0,1,"u")}},
        {interval("X0",0,0),interval("X1",0,1),interval("X2",0,2)}, {},{},
        InformationPattern::nominal_open_loop,std::move(objective)};
    if(constant)source.objective=LinearTerminal{{0},7};
    return take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
problem::ResolvedProblem exact_integrator() {
    QuadraticTerminal objective{}; objective.Q={1,1,{2}}; objective.linear={-2}; objective.offset=1;
    Problem source{{"strategy-a-ts01"},std::make_shared<const SystemModel>(SystemModel{
        {{1,1,0},TimeDomain::discrete,LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}}, {}}),
        {0,1,2},KnownInitial{{0}},ContinuousDomain{{interval("u0",0,1,"u"),interval("u1",0,1,"u")}},
        {UniversalSet{1},UniversalSet{1},UniversalSet{1}}, {},{},InformationPattern::nominal_open_loop,
        std::move(objective)};
    return take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
problem::ResolvedProblem exact_ts02_integrator(TerminalObjective objective=LinearTerminal{{0},3},double a=1) {
    Problem source{{"strategy-a-ts02"},std::make_shared<const SystemModel>(SystemModel{
        {{1,1,0},TimeDomain::discrete,LinearStage{{1,1,{a}},{1,1,{1}},{1,0,{}},{0}}}, {}}),
        {0,1,2},KnownInitial{{0}},ContinuousDomain{{interval("u0",0,1,"u"),interval("u1",0,1,"u")}},
        {UniversalSet{1},UniversalSet{1},UniversalSet{1}}, {},{},InformationPattern::nominal_open_loop,
        std::move(objective)};
    return take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
StrategyRequest request(problem::ResolvedProblem problem) {
    FamilyRequest family;family.objective=problem.identity();family.profile="nominal_open_loop";
    family.representation={"csl.polyhedron.h"};
    StrategyConfiguration configuration;configuration.strategy={"csl.synthesis.reach-back"};
    return {std::move(problem),configuration,family,"1",{}};
}
StrategyRequest exact_request(problem::ResolvedProblem problem) {
    FamilyRequest family;family.objective=problem.identity();family.profile=synthesis::strategy_ts01::profile_id;
    family.target=FamilyTarget::exact_optimal_relation;family.assurance=Assurance::numerical;
    family.representation={"csl.polyhedron.h"};
    StrategyConfiguration configuration;configuration.strategy={"csl.synthesis.reach-back"};
    configuration.representation={"csl.polyhedron.h"};
    return {std::move(problem),configuration,family,"1",{}};
}
StrategyRequest exact_ts02_request(problem::ResolvedProblem problem) {
    FamilyRequest family;family.objective=problem.identity();family.profile=synthesis::ts02_constant_integrator_profile;
    family.target=FamilyTarget::exact_optimal_relation;family.assurance=Assurance::numerical;
    family.representation={"csl.polyhedron.h"};
    StrategyConfiguration configuration;configuration.strategy={"csl.synthesis.reach-back"};
    configuration.representation={"csl.polyhedron.h"};
    return {std::move(problem),configuration,family,"1",{}};
}
class CancelAfterTerminal final : public ConvexWorkspace {
    std::unique_ptr<ConvexWorkspace> inner_;
    std::stop_source stop_;
    ProgramOutcome do_solve(const ConvexProgram& program,const ExecutionContext& context) override {
        auto outcome=inner_->solve(program,context);stop_.request_stop();return outcome;
    }
public:
    CancelAfterTerminal(std::unique_ptr<ConvexWorkspace> inner,std::stop_source stop)
        :inner_(std::move(inner)),stop_(std::move(stop)){}
};
class NumericalFailureAfterTerminal final : public ConvexWorkspace {
    std::unique_ptr<ConvexWorkspace> inner_;
    ProgramOutcome do_solve(const ConvexProgram& program,
        const ExecutionContext& context) override {
        auto outcome=inner_->solve(program,context);
        if(auto* solved=std::get_if<ProgramResult>(&outcome)) {
            solved->termination=Termination::numerical_failure;
            solved->raw_diagnostics+="\ninjected terminal numerical failure after real optimizer result";
        }
        return outcome;
    }
public:
    explicit NumericalFailureAfterTerminal(std::unique_ptr<ConvexWorkspace> inner):inner_(std::move(inner)){}
};
class ResourceLimitAfterTerminal final : public ConvexWorkspace {
    std::unique_ptr<ConvexWorkspace> inner_;
    ProgramOutcome do_solve(const ConvexProgram& program,const ExecutionContext& context) override {
        auto outcome=inner_->solve(program,context);
        if(auto* solved=std::get_if<ProgramResult>(&outcome)) {
            solved->termination=Termination::resource_limit;
            solved->raw_diagnostics+="\ninjected terminal resource limit after real optimizer result";
        }
        return outcome;
    }
public:
    explicit ResourceLimitAfterTerminal(std::unique_ptr<ConvexWorkspace> inner):inner_(std::move(inner)){}
};
class DeadlineAfterTerminal final : public ConvexWorkspace {
    std::unique_ptr<ConvexWorkspace> inner_;
    ExecutionContext* caller_context_;
    ProgramOutcome do_solve(const ConvexProgram& program,const ExecutionContext& context) override {
        auto outcome=inner_->solve(program,context);
        if(std::holds_alternative<ProgramResult>(outcome))
            caller_context_->deadline=std::chrono::steady_clock::now();
        return outcome;
    }
public:
    DeadlineAfterTerminal(std::unique_ptr<ConvexWorkspace> inner,ExecutionContext& caller_context)
        :inner_(std::move(inner)),caller_context_(&caller_context){}
};
std::variant<PreparedStrategy,Rejection> admit(const StrategyRequest& request_,bool reject_terminal=false,
    std::optional<std::stop_source> stop_after_terminal={},bool omit_test_verifier=false,
    bool fail_terminal_numerically=false,bool limit_terminal_resources=false,
    ExecutionContext* expire_deadline_after_terminal=nullptr) {
    auto lp=take(adapters::lp::make_highs_registration());
    auto convex=take(adapters::convex::make_highs_registration());
    auto converter=take(adapters::polyhedral::make_qhull_registration(lp));
    auto projection=geometry::polyhedral::make_projection_registration();
    auto affine=geometry::make_affine_sum_registration({
        selected(geometry::make_lp_hull_reducer_registration(),""),selected(lp,"csl.program-result.v1"),
        selected(converter,"csl.polyhedron.v")});
    if(reject_terminal)convex.capabilities=[](const ConvexProgram&,const Requirements&)->Capability {
        return Diagnostics{{DiagnosticCode::unsupported,"test.terminal","terminal provider rejected generated request"}};
    };
    if(stop_after_terminal) {
        const auto factory=convex.factory;const auto stop=*stop_after_terminal;
        convex.factory=[factory,stop](const ConvexProgram& program) {
            return std::make_unique<CancelAfterTerminal>(factory(program),stop);
        };
    }
    if(fail_terminal_numerically) {
        const auto factory=convex.factory;
        convex.factory=[factory](const ConvexProgram& program) {
            return std::make_unique<NumericalFailureAfterTerminal>(factory(program));
        };
    }
    if(limit_terminal_resources) {
        const auto factory=convex.factory;
        convex.factory=[factory](const ConvexProgram& program) {
            return std::make_unique<ResourceLimitAfterTerminal>(factory(program));
        };
    }
    if(expire_deadline_after_terminal) {
        const auto factory=convex.factory;auto* caller_context=expire_deadline_after_terminal;
        convex.factory=[factory,caller_context](const ConvexProgram& program) {
            return std::make_unique<DeadlineAfterTerminal>(factory(program),*caller_context);
        };
    }
    Registry<GeometryPort> projections,affines;Registry<ConversionPort> conversions;
    Registry<LPPort> lps;Registry<ConvexPort> convexes;
    Method pm{projection.identity.id,projection.identity.version},am{affine.identity.id,affine.identity.version};
    Method cm{converter.identity.id,converter.identity.version},lm{lp.identity.id,lp.identity.version};
    Method qm{convex.identity.id,convex.identity.version};
    REQUIRE_FALSE(projections.add(projection));REQUIRE_FALSE(affines.add(affine));
    REQUIRE_FALSE(conversions.add(converter));REQUIRE_FALSE(lps.add(lp));REQUIRE_FALSE(convexes.add(convex));
    Requirements h,v,program;h.output.representation={"csl.polyhedron.h"};h.output.relation=SetRelation::equivalent;
    v.output.representation={"csl.polyhedron.v"};v.output.relation=SetRelation::equivalent;
    program.output.representation={"csl.program-result.v1"};
    auto providers=take(check_providers(select_provider(projections,pm,h),select_provider(affines,am,v),
        select_provider(conversions,cm,h),select_provider(lps,lm,program),select_provider(convexes,qm,program)));
    auto registration=synthesis::strategy_a::make_registration(std::move(providers));
    if(omit_test_verifier)registration.complete_family_verifier={};
    StrategyRegistry strategies;REQUIRE_FALSE(strategies.add(std::move(registration)));
    Requirements output;output.output.representation={"csl.polyhedron.h"};
    output.output.family=request_.family.target;
    if(!omit_test_verifier)output.output.completeness=request_.family.target==FamilyTarget::exact_optimal_relation?
        Completeness::established:Completeness::unestablished;
    return strategies.prepare(request_,output);
}
PreparedStrategy prepare(const StrategyRequest& request_,bool reject_terminal=false) {
    return take(admit(request_,reject_terminal));
}
SynthesisResult run(const StrategyRequest& request_,bool reject_terminal=false,ExecutionContext context={}) {
    if(!context.resources)context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto prepared=prepare(request_,reject_terminal);auto workspace=prepared.create();
    auto result=take(workspace->run(context));
    std::visit([](const auto& stop) {
        if constexpr(requires {stop.diagnostics.begin()->field;})
            for(const auto& d:stop.diagnostics)std::cerr<<d.field<<": "<<d.explanation<<'\n';
    },result.stop);
    return result;
}
const synthesis::strategy_a::CandidateHistory& payload(const SynthesisResult& result) {
    REQUIRE(result.family);REQUIRE(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    const auto& relation=std::get<CandidateFamily>(result.family->outcome()).relation;
    const auto* data=dynamic_cast<const synthesis::strategy_a::CandidateHistory*>(relation.payload.get());
    REQUIRE(data);return *data;
}
bool contains(const sets::SetData& set,const Vector& point) {
    const auto representation=set.representation();const auto& h=std::get<sets::HRepresentation>(representation);
    if(point.size()!=h.equalities.cols())return false;
    for(std::size_t r=0;r<h.inequalities.rows();++r) {
        double lhs=0;for(std::size_t c=0;c<point.size();++c)lhs+=h.inequalities(r,c)*point[c];
        if(lhs>h.upper_bounds[r]+1e-7)return false;
    }
    for(std::size_t r=0;r<h.equalities.rows();++r) {
        double lhs=0;for(std::size_t c=0;c<point.size();++c)lhs+=h.equalities(r,c)*point[c];
        if(std::abs(lhs-h.equality_values[r])>1e-7)return false;
    }
    return true;
}
std::size_t equality_rank(const sets::HRepresentation& h) {
    std::vector<Vector> rows(h.equalities.rows(),Vector(h.equalities.cols()));
    for(std::size_t r=0;r<rows.size();++r)for(std::size_t c=0;c<rows[r].size();++c)rows[r][c]=h.equalities(r,c);
    std::size_t rank=0;
    for(std::size_t c=0;c<h.equalities.cols() && rank<rows.size();++c) {
        auto pivot=rank;while(pivot<rows.size() && std::abs(rows[pivot][c])<1e-8)++pivot;
        if(pivot==rows.size())continue;
        std::swap(rows[rank],rows[pivot]);const auto divisor=rows[rank][c];
        for(auto& value:rows[rank])value/=divisor;
        for(std::size_t r=rank+1;r<rows.size();++r) {
            const auto factor=rows[r][c];for(std::size_t j=c;j<h.equalities.cols();++j)rows[r][j]-=factor*rows[rank][j];
        }
        ++rank;
    }
    return rank;
}
void entire_segment(const sets::SetData& set,const Vector& base,const Vector& direction,double expected_upper=1) {
    // Independent affine-subspace/interval oracle. Rank four fixes the entire
    // 5-D relation to this line; all substituted rows bound its parameter to
    // exactly [0,1]. This tests the locus rather than a witness sample.
    const auto h=std::get<sets::HRepresentation>(set.representation());
    REQUIRE(equality_rank(h)==4);
    for(std::size_t r=0;r<h.equalities.rows();++r) {
        double value=0,slope=0;for(std::size_t c=0;c<5;++c){value+=h.equalities(r,c)*base[c];slope+=h.equalities(r,c)*direction[c];}
        CHECK(value==doctest::Approx(h.equality_values[r]));CHECK(slope==doctest::Approx(0));
    }
    double lower=-std::numeric_limits<double>::infinity(),upper=std::numeric_limits<double>::infinity();
    for(std::size_t r=0;r<h.inequalities.rows();++r) {
        double value=0,slope=0;for(std::size_t c=0;c<5;++c){value+=h.inequalities(r,c)*base[c];slope+=h.inequalities(r,c)*direction[c];}
        const auto rhs=h.upper_bounds[r]-value;
        if(slope>1e-8)upper=std::min(upper,rhs/slope);
        else if(slope<-1e-8)lower=std::max(lower,rhs/slope);
        else CHECK(rhs>=-1e-8);
    }
    CHECK(lower==doctest::Approx(0));CHECK(upper==doctest::Approx(expected_upper));
}
bool has_inequality(const sets::HRepresentation& h,const Vector& coefficients,double bound) {
    const auto pivot=static_cast<std::size_t>(std::find_if(coefficients.begin(),coefficients.end(),
        [](double value){return value!=0;})-coefficients.begin());
    for(std::size_t r=0;r<h.inequalities.rows();++r) {
        const auto factor=h.inequalities(r,pivot)/coefficients[pivot];
        if(factor<=0 || std::abs(h.upper_bounds[r]-factor*bound)>1e-8)continue;
        bool same=true;for(std::size_t c=0;c<5;++c)if(std::abs(h.inequalities(r,c)-factor*coefficients[c])>1e-8)same=false;
        if(same)return true;
    }
    return false;
}
bool has_equality(const sets::HRepresentation& h,const Vector& coefficients,double value) {
    for(std::size_t row=0;row<h.equalities.rows();++row) {
        bool match=std::abs(h.equality_values[row]-value)<1e-8;
        for(std::size_t col=0;col<h.equalities.cols();++col)
            match=match&&std::abs(h.equalities(row,col)-coefficients[col])<1e-8;
        if(match)return true;
    }
    return false;
}
}
TEST_CASE("T-S01 registered candidate retains u0+u1=1 and rejects the marginal product") {
    const auto query=request(integrator());auto result=run(query);CHECK(result.termination==Termination::completed);
    const auto& history=payload(result);CHECK(history.history.coordinates==JointCoordinates{{1,1,0},2});
    CHECK(history.target==synthesis::strategy_a::PreimageTarget::terminal_candidate);
    CHECK(contains(history.history.relation,{0,0,1,0,1}));
    CHECK(contains(history.history.relation,{0,1,1,1,0}));
    CHECK(contains(history.history.relation,{0,.25,1,.25,.75}));
    CHECK_FALSE(contains(history.history.relation,{0,1,2,1,1}));
    entire_segment(history.history.relation,{0,0,1,0,1},{0,1,0,1,-1});
    REQUIRE(history.terminal);REQUIRE(history.terminal->optimization);
    INFO(history.terminal->optimization->raw_diagnostics);
    CHECK_FALSE(history.terminal->optimization->objective.upper);
    REQUIRE(history.terminal->optimization->primal);
    CHECK(take(optimization::evaluate(query.problem.objective(),
        *history.terminal->optimization->primal))==doctest::Approx(0));
    CHECK(std::holds_alternative<Unestablished>(history.terminal->construction.support));
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK_FALSE(result.objective.lower);CHECK_FALSE(result.objective.upper);
    CHECK(result.family->identity().request==query.family);
    CHECK(result.family->identity().lineage.size()==6);
}
TEST_CASE("exact reviewed T-S01 executes registered Strategy A providers and composes the canonical five-coordinate family") {
    const auto query=exact_request(exact_integrator());
    // This test-only registration omits the final compiled verifier so the
    // Strategy A result exposes its actual preimage alongside its proposal.
    // The ordinary registration below must then accept the same proposal.
    auto staged=take(admit(query,false,{},true));
    auto staged_workspace=staged.create();
    auto staged_result=take(staged_workspace->run(ExecutionContext{
        .resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),
        .cancellation={},
        .deadline={},
        .run_id={}}));
    REQUIRE(staged_result.family);
    CHECK(staged_result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK(staged_result.family->identity().request==query.family);
    CHECK(staged_result.family->identity().coordinates==JointCoordinates{{1,1,0},2});
    REQUIRE(staged_result.complete_proposal);
    const auto& proposal=*staged_result.complete_proposal;
    CHECK(proposal.identity.request==query.family);
    CHECK(proposal.identity.coordinates==JointCoordinates{{1,1,0},2});
    CHECK(proposal.identity.lineage==staged_result.family->identity().lineage);
    const auto& staged_history=payload(staged_result);
    entire_segment(staged_history.history.relation,{0,0,1,0,1},{0,1,0,1,-1});
    CHECK_FALSE(contains(staged_history.history.relation,{0,1,2,1,1}));
    const auto& staged_complete=proposal.family;
    const auto* staged_exact=dynamic_cast<const synthesis::strategy_ts01::ExactJointRelation*>(staged_complete.relation.payload.get());
    REQUIRE(staged_exact);
    CHECK(staged_exact->h_polyhedron().metadata()->set.dimension==5);
    CHECK(staged_exact->contains(Vector{0,.25,1,.25,.75}));
    CHECK_FALSE(staged_exact->contains(Vector{0,1,2,1,1}));

    auto result=run(query);
    CHECK(result.termination==Termination::completed);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
    CHECK(result.family->registry_verified());
    CHECK(result.outcome.value==MathematicalOutcome::optimal);
    CHECK(result.family->identity().request==query.family);
    CHECK(result.family->identity().coordinates==JointCoordinates{{1,1,0},2});
    CHECK(result.family->identity().strategy==query.configuration.strategy);
    CHECK(result.family->identity().strategy_version=="1");
    REQUIRE(result.family->identity().lineage.size()==6);
    const auto& lineage=result.family->identity().lineage;
    CHECK(lineage[0].module==query.configuration.strategy);
    CHECK(lineage[1].module==query.configuration.strategy);
    CHECK(lineage[2].module==query.configuration.strategy);
    CHECK(lineage[3].module==ModuleId{"csl.synthesis.control-recovery"});
    CHECK(lineage[4].module==ModuleId{"csl.synthesis.terminal-minimizers"});
    CHECK(lineage[5].module==ModuleId{"csl.synthesis.control-recovery"});
    CHECK(lineage[0].request.value.starts_with("nominal-forward/"));
    CHECK(lineage[0].input.value.ends_with("/initial"));
    CHECK(lineage[0].output==lineage[1].input);
    CHECK(lineage[1].output==lineage[2].input);
    CHECK(lineage[3].request==RequestId{"strategy-a/feasible-preimage"});
    CHECK(lineage[3].input==lineage[2].output);
    CHECK(lineage[4].request.value=="syn02-terminal:"+lineage[2].output.value);
    CHECK(lineage[4].input==lineage[2].output);
    CHECK(lineage[5].input==lineage[4].output);
    REQUIRE(std::holds_alternative<CompleteOptimalFamily>(result.family->outcome()));
    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    const auto* proof=std::get_if<RegisteredCompletenessEvidence>(&complete.completeness.support);
    REQUIRE(proof);
    CHECK(proof->verifier==ModuleId{"csl.verifier.ts01-analytic"});
    CHECK(proof->verifier_version=="1");
    CHECK(proof->proof=="TS01-analytic-v1");
    const auto* exact=dynamic_cast<const synthesis::strategy_ts01::ExactJointRelation*>(complete.relation.payload.get());
    REQUIRE(exact);
    CHECK(exact->h_polyhedron().metadata()->set.dimension==5);
    CHECK(exact->h_polyhedron().metadata()->coordinate_labels==std::vector<std::string>{"x0","x1","x2","u0","u1"});
    // Rank-four affine equalities and substituted H-rows reduce this public relation to
    // the full locus (0,t,1,t,1-t), with the rows bounding t exactly to [0,1].
    entire_segment(exact->h_polyhedron(),{0,0,1,0,1},{0,1,0,1,-1});
    CHECK(exact->contains(Vector{0,0,1,0,1}));
    CHECK(exact->contains(Vector{0,.25,1,.25,.75}));
    CHECK(exact->contains(Vector{0,1,1,1,0}));
    CHECK_FALSE(exact->contains(Vector{0,1,2,1,1}));

}
TEST_CASE("Strategy A rejects validated assurance and the public unverified publisher rejects complete claims") {
    const auto query=exact_request(exact_integrator());

    auto validated=query;
    validated.family.assurance=Assurance::validated;
    CHECK(std::holds_alternative<Rejection>(admit(validated)));

    const auto result=run(query);
    REQUIRE(result.family);
    REQUIRE(result.family->registry_verified());
    REQUIRE(std::holds_alternative<CompleteOptimalFamily>(result.family->outcome()));
    const auto& accepted=std::get<CompleteOptimalFamily>(result.family->outcome());
    const auto& identity=result.family->identity();
    const auto publication=FamilyPublisher::publish(identity,accepted);
    REQUIRE(std::holds_alternative<Diagnostics>(publication));
    const auto& diagnostics=std::get<Diagnostics>(publication);
    CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[](const Diagnostic& diagnostic) {
        return diagnostic.field=="family.completeness";
    }));
}
TEST_CASE("Strategy A exact T-S01 rejects changed profiles and retains candidate on late provider failure") {
    auto query=exact_request(exact_integrator());
    auto wrong=query;wrong.family.profile+="-neighbor";
    CHECK(std::holds_alternative<Rejection>(admit(wrong)));
    auto changed=query;changed.family.objective=integrator(true).identity();
    CHECK(std::holds_alternative<Rejection>(admit(changed)));

    auto result=run(query,true);
    CHECK(result.termination==Termination::operation_rejected);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    CHECK(result.family->identity().request==query.family);
    CHECK(result.family->identity().coordinates==JointCoordinates{{1,1,0},2});
    CHECK(result.family->identity().lineage.size()==4);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK_FALSE(result.objective.lower);CHECK_FALSE(result.objective.upper);
    const auto& history=payload(result);
    CHECK(contains(history.history.relation,{0,1,2,1,1}));
    CHECK_FALSE(result.complete_proposal);
    REQUIRE(std::holds_alternative<ScopedRequestRejection>(result.stop));
    const auto& stop=std::get<ScopedRequestRejection>(result.stop);
    CHECK(stop.retained.partial_or_candidate_family);
    CHECK(stop.completed_lineage==result.family->identity().lineage);
    CHECK(stop.completed_lineage.size()==4);
    CHECK(stop.completed_lineage[0].output==stop.completed_lineage[1].input);
    CHECK(stop.completed_lineage[1].output==stop.completed_lineage[2].input);
    CHECK(stop.completed_lineage[3].input==stop.completed_lineage[2].output);
    CHECK(stop.request.actual_module==ModuleId{"csl.convex.highs"});
}
TEST_CASE("registered Strategy A candidate identity mismatches fail at the caller boundary") {
    const auto query=request(integrator());
    const auto result=run(query);
    REQUIRE(result.family);
    REQUIRE(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    const auto& history=payload(result);
    REQUIRE(history.terminal);
    REQUIRE(history.terminal->relation);
    REQUIRE(history.terminal->optimization);

    std::vector<TransformStepIdentity> lineage;
    for(const auto& stage:history.forward.stages) {
        REQUIRE_FALSE(stage.source_factors.empty());
        lineage.push_back({stage.marginal.evidence.reference.identity.request,
            stage.source_factors.front(),stage.marginal.output.id,
            query.configuration.strategy,query.strategy_version});
    }
    const auto feasible_slice=take(sets::from_handle(history.forward.stages.back().marginal.output));
    const auto feasible_history=take(synthesis::recover_joint_history(query.problem,feasible_slice));
    lineage.push_back({{"strategy-a/feasible-preimage"},feasible_slice.metadata()->id,
        feasible_history.relation.metadata()->id,{"csl.synthesis.control-recovery"},"1"});
    const RequestId terminal_request{history.terminal->optimization->outcome.subject.program.value};
    lineage.push_back({terminal_request,feasible_slice.metadata()->id,
        history.terminal->relation->metadata()->id,{"csl.synthesis.terminal-minimizers"},"1"});
    lineage.push_back({{"strategy-a/terminal-preimage"},history.terminal->relation->metadata()->id,
        history.history.relation.metadata()->id,{"csl.synthesis.control-recovery"},"1"});

    const FamilyIdentity expected{query.problem.identity(),query.family,
        query.problem.constraints().coordinates(),query.configuration.strategy,
        query.strategy_version,std::move(lineage)};
    REQUIRE(expected.lineage.size()==6);
    CHECK(check_synthesis_result(result,expected).empty());

    auto expect_identity_rejection=[&](FamilyIdentity mutated) {
        const auto diagnostics=check_synthesis_result(result,mutated);
        CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[](const Diagnostic& diagnostic) {
            return diagnostic.code==DiagnosticCode::evidence_mismatch && diagnostic.field=="family.identity";
        }));
        CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
        CHECK(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    };

    auto wrong_problem=expected;wrong_problem.problem.value+="-foreign";expect_identity_rejection(wrong_problem);
    auto wrong_request=expected;wrong_request.request.profile+="-foreign";expect_identity_rejection(wrong_request);
    auto wrong_objective=expected;wrong_objective.request.objective=integrator(true).identity();expect_identity_rejection(wrong_objective);
    auto wrong_coordinates=expected;++wrong_coordinates.coordinates.horizon;expect_identity_rejection(wrong_coordinates);
    auto wrong_strategy=expected;wrong_strategy.strategy={"csl.synthesis.foreign"};expect_identity_rejection(wrong_strategy);
    auto wrong_version=expected;wrong_version.strategy_version+="-foreign";expect_identity_rejection(wrong_version);
    auto wrong_lineage=expected;wrong_lineage.lineage.pop_back();expect_identity_rejection(wrong_lineage);
}
TEST_CASE("T-S02 constant objective preserves histories at different terminal points") {
    const auto query=request(integrator(true));auto result=run(query);const auto& history=payload(result);
    CHECK(contains(history.history.relation,{0,0,0,0,0}));
    CHECK(contains(history.history.relation,{0,1,2,1,1}));
    CHECK(contains(history.history.relation,{0,1,1,1,0}));
    CHECK(contains(history.history.relation,{0,0,1,0,1}));
    const auto h=std::get<sets::HRepresentation>(history.history.relation.representation());
    CHECK(equality_rank(h)==3);
    // The four corners span the two-dimensional feasible history plane. Rank
    // three fixes that plane, and these four halfspaces impose exactly [0,1]^2.
    CHECK(has_inequality(h,{0,0,0,1,0},1));CHECK(has_inequality(h,{0,0,0,-1,0},0));
    CHECK(has_inequality(h,{0,0,0,0,1},1));CHECK(has_inequality(h,{0,0,0,0,-1},0));
    CHECK(contains(history.history.relation,{0,.2,.9,.2,.7}));
    CHECK_FALSE(contains(history.history.relation,{0,0,2,0,1}));
    REQUIRE(history.terminal);REQUIRE(history.terminal->optimization);
    CHECK(history.terminal->optimization->outcome.value==MathematicalOutcome::optimal);
    REQUIRE(history.terminal->relation);
    CHECK_FALSE(history.terminal->optimization->objective.upper);
    REQUIRE(history.terminal->optimization->primal);
    CHECK(take(optimization::evaluate(query.problem.objective(),*history.terminal->optimization->primal))==7);
}
TEST_CASE("exact T-S02 selects its analytic verifier and publishes every feasible history") {
    const auto query=exact_ts02_request(exact_ts02_integrator());
    const auto prepared=admit(query);
    REQUIRE(std::holds_alternative<PreparedStrategy>(prepared));
    auto workspace=std::get<PreparedStrategy>(prepared).create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=take(workspace->run(context));
    CHECK(result.termination==Termination::completed);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
    CHECK(result.family->registry_verified());
    CHECK(result.family->identity().request==query.family);
    CHECK(result.family->identity().coordinates==JointCoordinates{{1,1,0},2});
    CHECK(result.family->identity().strategy==query.configuration.strategy);
    CHECK(result.family->identity().lineage.size()==6);
    CHECK(result.outcome.value==MathematicalOutcome::optimal);
    REQUIRE(result.objective.lower);REQUIRE(result.objective.upper);
    CHECK(result.objective.lower->value==3);CHECK(result.objective.upper->value==3);
    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    const auto* exact=dynamic_cast<const synthesis::Ts02ConstantIntegratorRelation*>(complete.relation.payload.get());
    REQUIRE(exact);
    const auto& canonical=exact->h_polyhedron();
    CHECK(canonical.metadata()->id==SetId{"ts02-optimal-histories"});
    CHECK(canonical.metadata()->coordinate_labels==std::vector<std::string>{"x0","x1","x2","u0","u1"});
    CHECK(contains(canonical,{0,0,0,0,0}));
    CHECK(contains(canonical,{0,1,2,1,1}));
    CHECK(contains(canonical,{0,1,1,1,0}));
    CHECK(contains(canonical,{0,0,1,0,1}));
    CHECK(contains(canonical,{0,.2,.9,.2,.7}));
    CHECK(contains(canonical,{0,.4,.9,.4,.5}));
    CHECK_FALSE(contains(canonical,{0,0,2,0,1}));
    CHECK_FALSE(contains(canonical,{1,1,1,0,0}));
    CHECK_FALSE(contains(canonical,{0,-.1,.9,-.1,1}));
    CHECK_FALSE(contains(canonical,{0,1.1,1.1,1.1,0}));
    const auto h=std::get<sets::HRepresentation>(canonical.representation());
    CHECK(equality_rank(h)==3);
    CHECK(has_inequality(h,{0,0,0,1,0},1));CHECK(has_inequality(h,{0,0,0,-1,0},0));
    CHECK(has_inequality(h,{0,0,0,0,1},1));CHECK(has_inequality(h,{0,0,0,0,-1},0));
    CHECK(has_equality(h,{1,0,0,0,0},0));
    CHECK(has_equality(h,{-1,1,0,-1,0},0));
    CHECK(has_equality(h,{0,-1,1,0,-1},0));
    const auto* proof=std::get_if<RegisteredCompletenessEvidence>(&complete.completeness.support);
    REQUIRE(proof);
    CHECK(proof->verifier==ModuleId{synthesis::ts02_constant_integrator_verifier});
    CHECK(proof->verifier_version=="1");
    CHECK(proof->proof==synthesis::ts02_constant_integrator_proof);
}
TEST_CASE("public Strategy A exact T-S02 family equals the analytic feasible-history relation") {
    const auto query=exact_ts02_request(exact_ts02_integrator());
    auto workspace=take(admit(query)).create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=take(workspace->run(context));

    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    const auto* relation=dynamic_cast<const synthesis::Ts02ConstantIntegratorRelation*>(
        complete.relation.payload.get());
    REQUIRE(relation);

    // Independently, the model defines every feasible history by x0=0,
    // x1=u0, x2=x1+u1 and the two control bounds. The objective is the
    // constant 3, so every point in this relation is optimal. These seven
    // rows are the whole relation, rather than a finite set of witnesses.
    const auto polyhedron=relation->h_polyhedron();
    const auto representation=polyhedron.representation();
    const auto& actual=std::get<sets::HRepresentation>(representation);
    REQUIRE(actual.inequalities.rows()==4);
    REQUIRE(actual.equalities.rows()==3);
    CHECK(actual.inequalities.cols()==5);
    CHECK(actual.equalities.cols()==5);
    CHECK(has_inequality(actual,{0,0,0,1,0},1));
    CHECK(has_inequality(actual,{0,0,0,-1,0},0));
    CHECK(has_inequality(actual,{0,0,0,0,1},1));
    CHECK(has_inequality(actual,{0,0,0,0,-1},0));
    CHECK(has_equality(actual,{1,0,0,0,0},0));
    CHECK(has_equality(actual,{-1,1,0,-1,0},0));
    CHECK(has_equality(actual,{0,-1,1,0,-1},0));
    REQUIRE(result.objective.lower);
    REQUIRE(result.objective.upper);
    CHECK(result.objective.lower->value==3);
    CHECK(result.objective.upper->value==3);
}
TEST_CASE("exact T-S02 recovered preimage contains the entire feasible control box") {
    const auto query=exact_ts02_request(exact_ts02_integrator());
    auto workspace=take(admit(query,false,{},true)).create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=take(workspace->run(context));
    const auto& history=payload(result);
    CHECK(history.target==synthesis::strategy_a::PreimageTarget::terminal_candidate);
    REQUIRE(result.complete_proposal);
    const auto h=std::get<sets::HRepresentation>(history.history.relation.representation());
    CHECK(equality_rank(h)==3);
    // Affine rows attaining their maximum on these four vertices admit every
    // point (0,s,s+t,s,t), s,t in [0,1], by convexity. The three dynamics
    // equalities and literal control bounds exclude every other history.
    for(const Vector& point:std::vector<Vector>{{0,0,0,0,0},{0,1,1,1,0},{0,0,1,0,1},{0,1,2,1,1}})
        CHECK(contains(history.history.relation,point));
    CHECK(has_equality(h,{1,0,0,0,0},0));
    CHECK(has_equality(h,{-1,1,0,-1,0},0));
    CHECK(has_equality(h,{0,-1,1,0,-1},0));
    CHECK(has_inequality(h,{0,0,0,1,0},1));CHECK(has_inequality(h,{0,0,0,-1,0},0));
    CHECK(has_inequality(h,{0,0,0,0,1},1));CHECK(has_inequality(h,{0,0,0,0,-1},0));
}
TEST_CASE("exact T-S02 rejects requests outside its reviewed model and objective at admission") {
    for(const auto& problem:std::vector<problem::ResolvedProblem>{
        exact_ts02_integrator(LinearTerminal{{0},7}),
        exact_ts02_integrator(LinearTerminal{{1},3}),
        exact_ts02_integrator(LinearTerminal{{0},3},0)}) {
        const auto admitted=admit(exact_ts02_request(problem));
        REQUIRE(std::holds_alternative<Rejection>(admitted));
        CHECK_FALSE(std::get<Rejection>(admitted).diagnostics.empty());
    }
}
TEST_CASE("exact T-S02 verifier rejects altered Strategy A bindings and payloads") {
    const auto query=exact_ts02_request(exact_ts02_integrator());
    const auto result=run(query);
    REQUIRE(result.family);
    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    const CompleteFamilyProposal proposal{result.family->identity(),complete};
    auto frozen=query;frozen.lineage=result.family->identity().lineage;
    const auto verifier=registry::detail::find_compiled_verifier({synthesis::ts02_constant_integrator_verifier},"1");
    REQUIRE(verifier);
    CHECK(verifier->verify(frozen,proposal).empty());
    const auto rejected=[&](const StrategyRequest& request,const CompleteFamilyProposal& altered,std::string field) {
        const auto diagnostics=verifier->verify(request,altered);
        CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[&](const Diagnostic& diagnostic) {
            return diagnostic.field==field;
        }));
    };
    auto wrong_lineage=frozen;wrong_lineage.lineage.pop_back();
    rejected(wrong_lineage,proposal,"ts02.verifier.profile");
    auto wrong_model=frozen;wrong_model.problem=exact_ts02_integrator(LinearTerminal{{0},3},0);
    rejected(wrong_model,proposal,"ts02.verifier.profile");
    auto wrong_objective=frozen;wrong_objective.problem=exact_ts02_integrator(LinearTerminal{{0},4});
    rejected(wrong_objective,proposal,"ts02.verifier.profile");
    auto wrong_binding=proposal;wrong_binding.identity.lineage.front().output={"foreign-output"};
    rejected(frozen,wrong_binding,"ts02.verifier.binding");
    auto wrong_bounds=proposal;wrong_bounds.family.optimum.bounds.upper->value=4;
    rejected(frozen,wrong_bounds,"ts02.verifier.optimum");
    auto wrong_payload=proposal;wrong_payload.family.relation.payload=std::make_shared<const JointRelationPayload>();
    rejected(frozen,wrong_payload,"ts02.verifier.relation");
    const auto* exact=dynamic_cast<const synthesis::Ts02ConstantIntegratorRelation*>(complete.relation.payload.get());
    REQUIRE(exact);
    auto h=std::get<sets::HRepresentation>(exact->h_polyhedron().representation());
    h.upper_bounds=take(numeric::snapshot_vector(Vector{2,0,1,0}));
    auto enlarged=take(sets::make_h({{"ts02-optimal-histories"},5,{"x0","x1","x2","u0","u1"}},h));
    wrong_payload.family.relation.payload=std::make_shared<const synthesis::Ts02ConstantIntegratorRelation>(std::move(enlarged));
    rejected(frozen,wrong_payload,"ts02.verifier.relation");
}
TEST_CASE("exact T-S02 preserves the reviewed constant quadratic and residual norm objectives") {
    for(const auto& objective:std::vector<TerminalObjective>{
        QuadraticTerminal{{1,1,{0}},{0},3},ResidualNormTerminal{{1,1,{0}},{3}}}) {
        const auto result=run(exact_ts02_request(exact_ts02_integrator(objective)));
        REQUIRE(result.termination==Termination::completed);
        REQUIRE(result.family);
        CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
        CHECK(result.family->registry_verified());
        REQUIRE(result.objective.lower);REQUIRE(result.objective.upper);
        CHECK(result.objective.lower->value==3);CHECK(result.objective.upper->value==3);
    }
}
TEST_CASE("exact T-S02 freezes the selected registration version during preparation") {
    auto query=exact_ts02_request(exact_ts02_integrator());query.strategy_version.clear();
    const auto result=run(query);
    REQUIRE(result.termination==Termination::completed);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
    CHECK(result.family->registry_verified());
    CHECK(result.family->identity().strategy_version=="1");
}
TEST_CASE("T-S03 singular A keeps free earlier controls with a unique terminal minimizer") {
    // Reproduce an ordinary preceding Strategy A call that exits at the late
    // terminal provider boundary, then exercise the real T-S03 user result.
    const auto rejected=run(request(integrator()),true);
    CHECK(rejected.termination==Termination::operation_rejected);
    REQUIRE(rejected.family);
    const auto& rejected_history=payload(rejected);
    CHECK(contains(rejected_history.history.relation,{0,1,2,1,1}));
    auto result=run(request(integrator(false,true)));const auto& history=payload(result);
    CHECK(result.termination==Termination::completed);
    CHECK(contains(history.history.relation,{0,0,1,0,1}));
    CHECK(contains(history.history.relation,{0,1,1,1,1}));
    CHECK_FALSE(contains(history.history.relation,{0,1,0,1,0}));
    entire_segment(history.history.relation,{0,0,1,0,1},{0,1,0,1,0});
}
TEST_CASE("late terminal admission rejection retains a feasible candidate and scoped lineage") {
    auto result=run(request(integrator()),true);
    CHECK(result.termination==Termination::operation_rejected);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK_FALSE(result.objective.lower);CHECK_FALSE(result.objective.upper);
    CHECK(result.incumbents.empty());CHECK_FALSE(result.complete_proposal);CHECK_FALSE(result.partial_proposal);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK_FALSE(result.family->registry_verified());CHECK_FALSE(result.family->partial_registry_verified());
    const auto& history=payload(result);CHECK(contains(history.history.relation,{0,1,2,1,1}));
    REQUIRE(history.terminal);
    const SetId final_slice{"nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward2/project/output"};
    CHECK(history.terminal->construction.feasible_slice==final_slice);
    const auto generated_request=RequestId{"syn02-terminal:nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward2/project/output"};
    REQUIRE(std::holds_alternative<ScopedRequestRejection>(result.stop));
    const auto& stop=std::get<ScopedRequestRejection>(result.stop);
    CHECK(stop.request.request==generated_request);
    CHECK(stop.request.port=="convex");
    CHECK(stop.request.requested_module==ModuleId{"csl.convex.highs"});
    CHECK(stop.request.requested_version==std::optional<std::string>{"1.0.0+highs.1.11.0"});
    CHECK(stop.request.actual_module==ModuleId{"csl.convex.highs"});
    CHECK(stop.request.actual_version==std::optional<std::string>{"1.0.0+highs.1.11.0"});
    CHECK_FALSE(stop.retained.lower_bound);CHECK_FALSE(stop.retained.upper_bound);
    CHECK(stop.retained.incumbents==0);CHECK(stop.retained.partial_or_candidate_family);
    const SetId initial{"nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward0/initial"};
    const SetId reachable0{"nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward0/project/output"};
    const SetId reachable1{"nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward1/project/output"};
    const SetId reachable2{"nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward2/project/output"};
    const SetId recovered{"recovery/joint-history/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf9142:nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward2/project/output"};
    const std::vector<TransformStepIdentity> expected_lineage{
        {{"nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward0/stage"},initial,reachable0,{"csl.synthesis.reach-back"},"1"},
        {{"nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward1/stage"},reachable0,reachable1,{"csl.synthesis.reach-back"},"1"},
        {{"nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward2/stage"},reachable1,reachable2,{"csl.synthesis.reach-back"},"1"},
        {{"strategy-a/feasible-preimage"},reachable2,recovered,{"csl.synthesis.control-recovery"},"1"}};
    CHECK(stop.completed_lineage==expected_lineage);
    CHECK(stop.completed_lineage==result.family->identity().lineage);
    REQUIRE(stop.diagnostics.size()==1);
    CHECK(stop.diagnostics[0].code==DiagnosticCode::unsupported);
    CHECK(stop.diagnostics[0].field=="test.terminal");
    CHECK(stop.diagnostics[0].explanation=="terminal provider rejected generated request");
    CHECK(history.terminal->construction.feasible_slice==history.forward.stages.back().marginal.output.id);
}
TEST_CASE("post-terminal cancellation keeps scoped optimizer and completed terminal lineage") {
    const auto query=request(integrator());std::stop_source stop_source;
    auto prepared=take(admit(query,false,stop_source));auto workspace=prepared.create();
    ExecutionContext context;context.cancellation=stop_source.get_token();
    context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto result=take(workspace->run(context));
    CHECK(result.termination==Termination::cancelled);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK_FALSE(result.objective.lower);CHECK_FALSE(result.objective.upper);
    CHECK(result.incumbents.empty());CHECK_FALSE(result.complete_proposal);CHECK_FALSE(result.partial_proposal);
    REQUIRE(result.family);CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK_FALSE(result.family->registry_verified());CHECK_FALSE(result.family->partial_registry_verified());
    REQUIRE(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    const auto& candidate=std::get<CandidateFamily>(result.family->outcome());
    REQUIRE(std::holds_alternative<HeuristicRelationEvidence>(candidate.relation_to_target));
    CHECK(std::get<HeuristicRelationEvidence>(candidate.relation_to_target).method==
        "binary64 feasible-history preimage of forward terminal slice; objective has not restricted this candidate");
    CHECK(std::holds_alternative<Unestablished>(candidate.feasibility));
    const auto& history=payload(result);REQUIRE(history.terminal);REQUIRE(history.terminal->relation);
    CHECK(history.target==synthesis::strategy_a::PreimageTarget::forward_terminal_slice);
    CHECK(contains(*history.terminal->relation,{1.0}));
    CHECK_FALSE(contains(*history.terminal->relation,{0.0}));
    CHECK_FALSE(contains(*history.terminal->relation,{2.0}));
    CHECK(std::holds_alternative<Unestablished>(history.terminal->construction.support));
    REQUIRE(history.terminal->optimum);
    CHECK(history.terminal->optimum->optimum.problem==query.problem.identity());
    CHECK(std::holds_alternative<Unestablished>(history.terminal->optimum->optimum.support));
    CHECK_FALSE(history.terminal->optimum->bounds.lower);CHECK_FALSE(history.terminal->optimum->bounds.upper);
    REQUIRE(history.terminal->optimization);
    CHECK(history.terminal->optimization->termination==Termination::completed);
    CHECK(history.terminal->optimization->outcome.value==MathematicalOutcome::optimal);
    CHECK_FALSE(history.terminal->optimization->objective.lower);
    CHECK_FALSE(history.terminal->optimization->objective.upper);
    CHECK(history.terminal->optimization->raw_diagnostics.find("bounds=unavailable")!=std::string::npos);
    CHECK(contains(history.history.relation,{0,1,2,1,1})); // unrecovered feasible candidate stays correctly scoped
    const auto& lineage=result.family->identity().lineage;
    REQUIRE(lineage.size()==5);
    CHECK(lineage.back().output==history.terminal->relation->metadata()->id);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(result.stop));
    const auto& stop=std::get<ScopedOperationStopped>(result.stop);
    CHECK(stop.stop.reason==StopReason::cancelled);
    CHECK(stop.stop.diagnostics=="Cancelled between Strategy A phases.");
    CHECK(stop.request.request==RequestId{"strategy-a/terminal-preimage"});
    CHECK(stop.request.port=="strategy");
    CHECK(stop.request.requested_module==ModuleId{"csl.synthesis.reach-back"});
    CHECK(stop.request.requested_version=="1");
    CHECK(stop.request.actual_module==ModuleId{"csl.synthesis.reach-back"});
    CHECK(stop.request.actual_version=="1");
    CHECK_FALSE(stop.retained.lower_bound);CHECK_FALSE(stop.retained.upper_bound);
    CHECK(stop.retained.incumbents==0);CHECK(stop.retained.partial_or_candidate_family);
    // Strategy A publishes no caller-visible timing spans on this stop; timing evidence remains a #89 dependency.
    CHECK(result.spans.empty());
}
TEST_CASE("post-terminal deadline expiry retains the completed slice and unestablished candidate") {
    const auto query=request(integrator());
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto prepared=take(admit(query,false,{},false,false,false,&context));auto workspace=prepared.create();
    auto result=take(workspace->run(context));
    CHECK(result.termination==Termination::cancelled);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK_FALSE(result.objective.lower);CHECK_FALSE(result.objective.upper);
    CHECK(result.incumbents.empty());CHECK_FALSE(result.complete_proposal);CHECK_FALSE(result.partial_proposal);
    REQUIRE(result.family);CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK_FALSE(result.family->registry_verified());CHECK_FALSE(result.family->partial_registry_verified());
    REQUIRE(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    const auto& candidate=std::get<CandidateFamily>(result.family->outcome());
    REQUIRE(std::holds_alternative<HeuristicRelationEvidence>(candidate.relation_to_target));
    CHECK(std::get<HeuristicRelationEvidence>(candidate.relation_to_target).method==
        "binary64 feasible-history preimage of forward terminal slice; objective has not restricted this candidate");
    CHECK(std::holds_alternative<Unestablished>(candidate.feasibility));
    const auto& history=payload(result);CHECK(history.target==synthesis::strategy_a::PreimageTarget::forward_terminal_slice);
    CHECK(contains(history.history.relation,{0,1,2,1,1}));
    REQUIRE(history.terminal);REQUIRE(history.terminal->relation);
    CHECK(contains(*history.terminal->relation,{1.0}));
    CHECK_FALSE(contains(*history.terminal->relation,{0.0}));
    CHECK_FALSE(contains(*history.terminal->relation,{2.0}));
    CHECK(std::holds_alternative<Unestablished>(history.terminal->construction.support));
    REQUIRE(history.terminal->optimum);
    CHECK(history.terminal->optimum->optimum.problem==query.problem.identity());
    CHECK(std::holds_alternative<Unestablished>(history.terminal->optimum->optimum.support));
    CHECK_FALSE(history.terminal->optimum->bounds.lower);CHECK_FALSE(history.terminal->optimum->bounds.upper);
    REQUIRE(history.terminal->optimization);
    CHECK(history.terminal->termination==Termination::completed);
    CHECK(history.terminal->optimization->termination==Termination::completed);
    CHECK(history.terminal->optimization->outcome.value==MathematicalOutcome::optimal);
    CHECK_FALSE(history.terminal->optimization->objective.lower);
    CHECK_FALSE(history.terminal->optimization->objective.upper);
    CHECK(history.terminal->optimization->outcome.subject.problem==query.problem.identity());
    CHECK(history.terminal->optimization->outcome.subject.program.value==
        "syn02-terminal:nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward2/project/output");
    const auto& lineage=result.family->identity().lineage;
    REQUIRE(lineage.size()==5);
    CHECK(lineage.back().output==history.terminal->relation->metadata()->id);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(result.stop));
    const auto& stop=std::get<ScopedOperationStopped>(result.stop);
    CHECK(stop.stop.reason==StopReason::deadline_expired);
    CHECK(stop.stop.diagnostics=="Deadline expired between Strategy A phases.");
    CHECK(stop.request.request==RequestId{"strategy-a/terminal-preimage"});
    CHECK(stop.request.port=="strategy");
    CHECK(stop.request.requested_module==ModuleId{"csl.synthesis.reach-back"});
    CHECK(stop.request.requested_version=="1");
    CHECK(stop.request.actual_module==ModuleId{"csl.synthesis.reach-back"});
    CHECK(stop.request.actual_version=="1");
    CHECK_FALSE(stop.retained.lower_bound);CHECK_FALSE(stop.retained.upper_bound);
    CHECK(stop.retained.incumbents==0);CHECK(stop.retained.partial_or_candidate_family);
    // Strategy A emits no caller-visible timing spans on this stop; timing coverage remains a #89 dependency.
    CHECK(result.spans.empty());
}
TEST_CASE("registered terminal resource limit retains only the unestablished feasible candidate") {
    const auto query=request(integrator());
    auto prepared=take(admit(query,false,{},false,false,true));auto workspace=prepared.create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=take(workspace->run(context));
    CHECK(result.termination==Termination::resource_limit);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK_FALSE(result.objective.lower);CHECK_FALSE(result.objective.upper);
    CHECK(result.incumbents.empty());CHECK_FALSE(result.complete_proposal);CHECK_FALSE(result.partial_proposal);
    REQUIRE(result.family);CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK_FALSE(result.family->registry_verified());CHECK_FALSE(result.family->partial_registry_verified());
    REQUIRE(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    const auto& candidate=std::get<CandidateFamily>(result.family->outcome());
    REQUIRE(std::holds_alternative<HeuristicRelationEvidence>(candidate.relation_to_target));
    CHECK(std::get<HeuristicRelationEvidence>(candidate.relation_to_target).method==
        "binary64 feasible-history preimage of forward terminal slice; objective has not restricted this candidate");
    CHECK(std::holds_alternative<Unestablished>(candidate.feasibility));
    const auto& history=payload(result);
    CHECK(history.target==synthesis::strategy_a::PreimageTarget::forward_terminal_slice);
    CHECK(contains(history.history.relation,{0,1,2,1,1}));
    REQUIRE(history.terminal);REQUIRE(history.terminal->relation);
    CHECK(contains(*history.terminal->relation,{1.0}));
    CHECK_FALSE(contains(*history.terminal->relation,{0.0}));
    CHECK_FALSE(contains(*history.terminal->relation,{2.0}));
    CHECK(std::holds_alternative<Unestablished>(history.terminal->construction.support));
    REQUIRE(history.terminal->optimum);
    CHECK(std::holds_alternative<Unestablished>(history.terminal->optimum->optimum.support));
    CHECK_FALSE(history.terminal->optimum->bounds.lower);CHECK_FALSE(history.terminal->optimum->bounds.upper);
    REQUIRE(history.terminal->optimization);
    CHECK(history.terminal->termination==Termination::resource_limit);
    CHECK(history.terminal->optimization->termination==Termination::resource_limit);
    CHECK(history.terminal->optimization->outcome.value==MathematicalOutcome::optimal);
    CHECK(history.terminal->optimization->raw_diagnostics.find(
        "injected terminal resource limit after real optimizer result")!=std::string::npos);
    CHECK_FALSE(history.terminal->optimization->objective.lower);
    CHECK_FALSE(history.terminal->optimization->objective.upper);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(result.stop));
    const auto& stop=std::get<ScopedOperationStopped>(result.stop);
    CHECK(stop.stop.reason==StopReason::resource_limit);
    CHECK(stop.stop.diagnostics=="Terminal optimization stopped; slice-scoped evidence retained.");
    CHECK(stop.request.port=="convex");
    CHECK(stop.request.request==RequestId{"syn02-terminal:"+history.terminal->construction.feasible_slice.value});
    CHECK(stop.request.requested_module==ModuleId{"csl.convex.highs"});
    CHECK(stop.request.actual_module==ModuleId{"csl.convex.highs"});
    CHECK(stop.request.actual_version==std::optional<std::string>{"1.0.0+highs.1.11.0"});
    CHECK_FALSE(stop.retained.lower_bound);CHECK_FALSE(stop.retained.upper_bound);
    CHECK(stop.retained.incumbents==0);CHECK(stop.retained.partial_or_candidate_family);
    // Strategy A emits no caller-visible timing spans on this stop; timing coverage remains a #89 dependency.
    CHECK(result.spans.empty());
}
TEST_CASE("registered terminal numerical failure retains the feasible candidate and scoped optimizer evidence") {
    const auto query=request(integrator());
    auto prepared=take(admit(query,false,{},false,true));auto workspace=prepared.create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=take(workspace->run(context));
    CHECK(result.termination==Termination::numerical_failure);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK_FALSE(result.objective.lower);CHECK_FALSE(result.objective.upper);
    CHECK(result.incumbents.empty());CHECK_FALSE(result.complete_proposal);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    REQUIRE(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    const auto& candidate=std::get<CandidateFamily>(result.family->outcome());
    CHECK(std::holds_alternative<HeuristicRelationEvidence>(candidate.relation_to_target));
    CHECK(std::holds_alternative<Unestablished>(candidate.feasibility));
    const auto& history=payload(result);
    CHECK(history.target==synthesis::strategy_a::PreimageTarget::forward_terminal_slice);
    CHECK(contains(history.history.relation,{0,1,2,1,1}));
    REQUIRE(history.terminal);REQUIRE(history.terminal->relation);
    CHECK(history.terminal->relation->metadata()->id.value==
        history.terminal->construction.feasible_slice.value+":terminal-candidate");
    CHECK(std::holds_alternative<Unestablished>(history.terminal->construction.support));
    CHECK(contains(*history.terminal->relation,{1.0}));
    CHECK_FALSE(contains(*history.terminal->relation,{0.0}));
    CHECK_FALSE(contains(*history.terminal->relation,{2.0}));
    REQUIRE(history.terminal->optimization);
    CHECK(history.terminal->optimization->termination==Termination::numerical_failure);
    CHECK(history.terminal->optimization->raw_diagnostics.find(
        "injected terminal numerical failure after real optimizer result")!=std::string::npos);
    CHECK(history.terminal->optimization->outcome.value==MathematicalOutcome::optimal);
    const auto& optimizer=*history.terminal->optimization;
    CHECK(optimizer.outcome.subject.problem==query.problem.identity());
    CHECK(optimizer.outcome.subject.program.value==
        "syn02-terminal:"+history.terminal->construction.feasible_slice.value);
    CHECK(std::holds_alternative<Unestablished>(optimizer.outcome.support));
    CHECK_FALSE(optimizer.objective.lower);CHECK_FALSE(optimizer.objective.upper);
    CHECK(optimizer.raw_diagnostics.find("bounds=unavailable")!=std::string::npos);
    REQUIRE(optimizer.residuals.primal);
    CHECK(optimizer.residuals.primal->context.subject==optimizer.outcome.subject);
    CHECK(optimizer.residuals.primal->context.verifier.id==ModuleId{"csl.convex.highs.primal"});
    CHECK(optimizer.residuals.primal->context.verifier.version=="1");
    CHECK(optimizer.residuals.primal->context.absolute_tolerance==query.family.numerical.absolute_tolerance);
    CHECK(optimizer.residuals.primal->context.relative_tolerance==query.family.numerical.relative_tolerance);
    REQUIRE(optimizer.primal);
    REQUIRE(optimizer.primal->size()==1);
    const auto terminal_state=optimizer.primal->front();
    const auto primal_tolerance=optimizer.residuals.primal->context.absolute_tolerance+
        optimizer.residuals.primal->context.relative_tolerance;
    CHECK(std::abs(terminal_state-1.0)<=primal_tolerance);
    CHECK(terminal_state>=0.0);CHECK(terminal_state<=2.0);
    CHECK(optimizer.residuals.primal->rows.violation<=
        optimizer.residuals.primal->context.absolute_tolerance+
        optimizer.residuals.primal->context.relative_tolerance*optimizer.residuals.primal->rows.scale);
    CHECK(optimizer.residuals.primal->rows.scale==doctest::Approx(2.0));
    CHECK(optimizer.residuals.primal->variables.violation<=
        optimizer.residuals.primal->context.absolute_tolerance+
        optimizer.residuals.primal->context.relative_tolerance*optimizer.residuals.primal->variables.scale);
    CHECK(optimizer.residuals.primal->variables.scale==1.0);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(result.stop));
    const auto& stop=std::get<ScopedOperationStopped>(result.stop);
    CHECK(stop.stop.reason==StopReason::numerical_failure);
    CHECK(stop.stop.diagnostics=="Terminal optimization stopped; slice-scoped evidence retained.");
    CHECK(stop.request.port=="convex");
    CHECK(stop.request.actual_module==ModuleId{"csl.convex.highs"});
    CHECK_FALSE(stop.retained.lower_bound);CHECK_FALSE(stop.retained.upper_bound);
    CHECK(stop.retained.incumbents==0);CHECK(stop.retained.partial_or_candidate_family);
    CHECK(result.spans.empty());
}
TEST_CASE("coverage and materialization requests fail closed at strategy preparation") {
    auto query=request(integrator());
    for(auto target:{FamilyTarget::exact_optimal_relation,FamilyTarget::partial_relation}) {
        query.family.target=target;const auto rejected=alternative<Rejection>(admit(query));
        CHECK(rejected.diagnostics[0].field=="strategy_a.coverage");
        CHECK(rejected.provenance.actual->id==ModuleId{"csl.synthesis.reach-back"});
    }
    query.family.target=FamilyTarget::candidate_relaxation;query.family.materialization_limit=20;
    CHECK(alternative<Rejection>(admit(query)).diagnostics[0].field=="strategy_a.capacity");
    query.family.materialization_limit.reset();query.family.assurance=Assurance::validated;
    CHECK(alternative<Rejection>(admit(query)).diagnostics[0].field=="family");
}
TEST_CASE("registered Strategy A preserves its prepared numerical policy in the public result") {
    auto query=request(integrator());
    query.family.assurance=Assurance::numerical;
    query.family.numerical={1e-7,2e-7};
    auto prepared=prepare(query);

    auto matching_workspace=prepared.create();
    ExecutionContext matching_context;
    matching_context.numerical={1e-7,2e-7};
    matching_context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=take(matching_workspace->run(matching_context));
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK(result.family->identity().request.numerical.absolute_tolerance==1e-7);
    CHECK(result.family->identity().request.numerical.relative_tolerance==2e-7);
    CHECK(result.family->identity().request.numerical==(NumericalPolicy{1e-7,2e-7}));

    auto mismatched_workspace=prepared.create();
    ExecutionContext mismatched_context;
    mismatched_context.numerical={1e-6,2e-7};
    mismatched_context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto& unsupported=alternative<Unsupported>(mismatched_workspace->run(mismatched_context));
    REQUIRE(unsupported.diagnostics.size()==1);
    CHECK(unsupported.diagnostics.front().code==DiagnosticCode::invalid_input);
    CHECK(unsupported.diagnostics.front().field=="family.numerical");
    CHECK(unsupported.diagnostics.front().explanation==
        "ExecutionContext numerical policy differs from the prepared family request");
}
TEST_CASE("stage constraints restrict the joint locus without separating histories") {
    auto source=*integrator().description();source.states[1]=interval("restricted-X1",0,.5);
    auto problem=take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    auto result=run(request(problem));const auto& history=payload(result);
    entire_segment(history.history.relation,{0,0,1,0,1},{0,1,0,1,-1},.5);
    CHECK_FALSE(contains(history.history.relation,{0,1,1,1,0}));
}
TEST_CASE("cancellation and deadline retain distinct scoped stops and no mathematical claim") {
    const auto query=request(integrator());std::stop_source source;source.request_stop();
    ExecutionContext context;context.cancellation=source.get_token();auto cancelled=run(query,false,context);
    CHECK(cancelled.termination==Termination::cancelled);
    CHECK(cancelled.outcome.value==MathematicalOutcome::undetermined);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(cancelled.stop));
    CHECK(std::get<ScopedOperationStopped>(cancelled.stop).stop.reason==StopReason::cancelled);
    context={};context.deadline=std::chrono::steady_clock::now();auto expired=run(query,false,context);
    CHECK(expired.termination==Termination::cancelled);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(expired.stop));
    CHECK(std::get<ScopedOperationStopped>(expired.stop).stop.reason==StopReason::deadline_expired);
    CHECK(std::get<ScopedOperationStopped>(expired.stop).stop.diagnostics.find("deadline")!=std::string::npos);
}
TEST_CASE("unsupported authored finite controls and declared temporal coupling reject in preparation") {
    auto source=*integrator().description();source.controls=FiniteDomain{1,{{0},{1}}};
    auto problem=take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    CHECK(alternative<Rejection>(admit(request(problem))).diagnostics[0].field=="controls");
    source=*integrator().description();source.temporal=TemporalConstraints{{0,5,{0},{},{}},{}};
    problem=take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    CHECK(alternative<Rejection>(admit(request(problem))).diagnostics[0].field=="strategy_a.temporal");
}

TEST_CASE("empty reachable stage stays undetermined without authored infeasibility evidence") {
    auto source=*integrator().description();
    source.states[2]=interval("impossible-X2",3,4);
    const auto problem=take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));

    const auto result=run(request(problem));

    CHECK(result.termination==Termination::completed);
    CHECK(result.outcome.subject==problem.identity());
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK(std::holds_alternative<Unestablished>(result.outcome.support));
    REQUIRE(result.outcome.assumptions.size()==2);
    CHECK(result.outcome.assumptions[0]==
        "forward recurrence, terminal construction and joint-history coverage remain unestablished");
    CHECK(result.outcome.assumptions[1]==
        "forward stage 2 compiled empty; authored infeasibility is not independently established");
    CHECK_FALSE(result.family);
    CHECK_FALSE(result.objective.lower);
    CHECK_FALSE(result.objective.upper);
    CHECK(result.incumbents.empty());
    CHECK(std::holds_alternative<std::monostate>(result.stop));
}
