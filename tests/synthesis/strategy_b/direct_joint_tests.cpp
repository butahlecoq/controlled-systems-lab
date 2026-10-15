#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/synthesis/strategy_b/direct_joint.hpp>
#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <csl/synthesis/ts02_constant_integrator.hpp>
#include <csl/optimization/convex_backend.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/geometry/polyhedral_projection.hpp>
#include "compiled_verifiers.hpp"
#include "strategy_b_lineage.hpp"
#include <algorithm>
#include <cmath>
#include <functional>
#include <limits>
#include <string>
#include <type_traits>
#include <vector>
using namespace csl;
using namespace csl::synthesis::strategy_b;
namespace {
bool feasible(const JointProgram&,const Vector&);
bool feasible_without_temporal_rows(const JointProgram&,const Vector&);
class ProposalOnlyWorkspace final:public SynthesisWorkspace {
    CompleteFamilyProposal proposal_;
public:
    explicit ProposalOnlyWorkspace(CompleteFamilyProposal proposal):proposal_(std::move(proposal)){}
    SynthesisResult solve(const problem::ResolvedProblem&,const FamilyRequest&,const ExecutionContext&) override {
        SynthesisResult result;result.termination=Termination::completed;result.complete_proposal=proposal_;return result;
    }
};
registry::StrategyRegistration proposal_only_strategy(CompleteFamilyProposal proposal) {
    registry::StrategyRegistration registration;
    registration.identity={{"csl.synthesis.strategy-b"},"1"};
    registration.capabilities=[](const registry::StrategyRequest&,const registry::Requirements& requirements)->registry::Capability {
        return registry::Offer{requirements.output};
    };
    registration.planner=[proposal=std::move(proposal)](const registry::StrategyRequest&,const registry::Requirements&)->std::variant<registry::StrategyPlan,registry::Rejection> {
        auto checked=registry::check_pipeline();
        return registry::compose_strategy(std::get<registry::CheckedPipeline<>>(std::move(checked)),[proposal](auto,const registry::StrategyRequest&,const registry::Requirements&) {
            return std::make_unique<ProposalOnlyWorkspace>(proposal);
        });
    };
    registration.complete_family_verifier={{"csl.verifier.ts01-analytic"},"1"};
    registration.expected_lineage=[](const registry::StrategyRequest& request) {
        return detail::expected_ts01_lineage(request.problem.identity());
    };
    return registration;
}
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
CompleteFamilyProposal exact_ts01_proposal(const problem::ResolvedProblem& problem,const FamilyRequest& family) {
    const auto coordinates=problem.constraints().coordinates();
    const auto lineage=detail::expected_ts01_lineage(problem.identity());
    const FamilyIdentity identity{problem.identity(),family,coordinates,{"csl.synthesis.strategy-b"},"1",lineage};
    auto payload=accepted(synthesis::strategy_ts01::ExactJointRelation::canonical());
    const SymbolicArgument derivation{"T-S01 exact analytic derivation",
        "x2=u0+u1 and (x2-1)^2>=0; zero is attained exactly when u0+u1=1. With u0,u1 in [0,1], the full canonical optimal history relation is the segment (0,s,1,s,1-s), s in [0,1]."};
    const ClaimEvidence claim{problem.identity(),derivation};
    const ObjectiveBound bound{0,claim};
    CompleteOptimalFamily complete{{coordinates,family.representation,payload},
        {claim,{bound,bound}},
        {identity,RegisteredCompletenessEvidence{{"csl.verifier.ts01-analytic"},"1","TS01-analytic-v1"}},
        Assurance::numerical};
    return {identity,std::move(complete)};
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
TEST_CASE("authored cross-time control equation excludes a stagewise-admissible history") {
    auto input=integrator(LinearTerminal{{0},0});
    input.temporal=TemporalConstraints{
        {1,5,{0,2},{3,4},{1,-1}},{{0.5,0.5}}};
    const auto p=resolve(input);
    const auto q=accepted(build_joint_program(p,request(p)));

    // Canonical joint order is [x0, x1, x2, u0, u1]. Both histories satisfy
    // x1=x0+u0, x2=x1+u1 and the stagewise control boxes [0,1]. The authored
    // temporal row adds u0-u1=0.5: it retains the first history and rejects
    // the second, which a stagewise/Cartesian relaxation would retain.
    const Vector accepted_history{0,0.75,1,0.75,0.25};
    const Vector stagewise_only_history{0,0.25,1,0.25,0.75};
    CHECK(feasible_without_temporal_rows(q,accepted_history));
    CHECK(feasible(q,accepted_history));
    CHECK(feasible_without_temporal_rows(q,stagewise_only_history));
    CHECK_FALSE(feasible(q,stagewise_only_history));

    REQUIRE(q.rows.size()==8);
    const auto& temporal=q.rows.back();
    CHECK(temporal.source==RowSource::temporal);
    CHECK(temporal.stage==0);
    CHECK(temporal.source_row==0);
    CHECK(temporal.program_row==7);
    REQUIRE(q.constraints.row_offsets[7]==11);
    REQUIRE(q.constraints.row_offsets[8]==13);
    CHECK(q.constraints.column_indices[11]==3);
    CHECK(q.constraints.values[11]==1);
    CHECK(q.constraints.column_indices[12]==4);
    CHECK(q.constraints.values[12]==-1);
    REQUIRE(q.bounds.size()==8);
    CHECK(q.bounds[7].lower==0.5);
    CHECK(q.bounds[7].upper==0.5);
    // This only verifies the generated candidate joint relation. It establishes
    // no all-history optimal-family coverage or completeness guarantee.
}
bool feasible(const JointProgram& p,const Vector& x) {
    for(std::size_t i=0;i<p.constraints.rows;++i) {
        double v=0;for(auto j=p.constraints.row_offsets[i];j<p.constraints.row_offsets[i+1];++j)
            v+=p.constraints.values[j]*x[p.constraints.column_indices[j]];
        if(p.bounds[i].lower&&v<*p.bounds[i].lower-1e-10)return false;
        if(p.bounds[i].upper&&v>*p.bounds[i].upper+1e-10)return false;
    }return true;
}
bool feasible_without_temporal_rows(const JointProgram& p,const Vector& x) {
    for(std::size_t i=0;i<p.constraints.rows;++i) {
        if(p.rows[i].source==RowSource::temporal) continue;
        double v=0;for(auto j=p.constraints.row_offsets[i];j<p.constraints.row_offsets[i+1];++j)
            v+=p.constraints.values[j]*x[p.constraints.column_indices[j]];
        if(p.bounds[i].lower&&v<*p.bounds[i].lower-1e-10)return false;
        if(p.bounds[i].upper&&v>*p.bounds[i].upper+1e-10)return false;
    }return true;
}
bool contains(const sets::SetData& set,const Vector& x,double tolerance=1e-10) {
    const auto h=std::get<sets::HRepresentation>(set.representation());
    for(std::size_t i=0;i<h.inequalities.rows();++i) {double v=0;for(std::size_t j=0;j<x.size();++j)v+=h.inequalities(i,j)*x[j];if(v>h.upper_bounds[i]+tolerance)return false;}
    for(std::size_t i=0;i<h.equalities.rows();++i) {double v=0;for(std::size_t j=0;j<x.size();++j)v+=h.equalities(i,j)*x[j];if(std::abs(v-h.equality_values[i])>tolerance)return false;}
    return true;
}
std::size_t equality_rank(const sets::HRepresentation& h) {
    std::vector<Vector> rows(h.equalities.rows(),Vector(h.equalities.cols()));
    for(std::size_t r=0;r<rows.size();++r) {
        double scale=0;
        for(std::size_t c=0;c<rows[r].size();++c)scale=std::max(scale,std::abs(h.equalities(r,c)));
        if(scale>0)for(std::size_t c=0;c<rows[r].size();++c)rows[r][c]=h.equalities(r,c)/scale;
    }
    std::size_t rank=0;
    for(std::size_t c=0;c<h.equalities.cols() && rank<rows.size();++c) {
        auto pivot=rank;while(pivot<rows.size() && std::abs(rows[pivot][c])<1e-10)++pivot;
        if(pivot==rows.size())continue;
        std::swap(rows[rank],rows[pivot]);
        const auto divisor=rows[rank][c];for(std::size_t j=c;j<rows[rank].size();++j)rows[rank][j]/=divisor;
        for(std::size_t r=0;r<rows.size();++r)if(r!=rank) {
            const auto factor=rows[r][c];for(std::size_t j=c;j<rows[r].size();++j)rows[r][j]-=factor*rows[rank][j];
        }
        ++rank;
    }
    return rank;
}
std::pair<double,double> parameter_interval(const sets::HRepresentation& h,
    const Vector& origin,const Vector& direction,double tolerance=1e-7) {
    auto lower=-std::numeric_limits<double>::infinity();
    auto upper=std::numeric_limits<double>::infinity();
    for(std::size_t i=0;i<h.equalities.rows();++i) {
        long double row_scale=std::abs(static_cast<long double>(h.equality_values[i]));
        for(std::size_t j=0;j<origin.size();++j) {
            row_scale=std::max(row_scale,std::abs(static_cast<long double>(h.equalities(i,j))));
        }
        long double at_origin=0,slope=0;
        const auto divisor=row_scale>0?row_scale:1.0L;
        const auto value=static_cast<long double>(h.equality_values[i])/divisor;
        for(std::size_t j=0;j<origin.size();++j) {
            const auto coefficient=static_cast<long double>(h.equalities(i,j))/divisor;
            at_origin+=coefficient*origin[j];slope+=coefficient*direction[j];
        }
        const auto residual=value-at_origin;
        if(slope==0) {
            CHECK(std::abs(residual)<=tolerance);
            continue;
        }
        // Any nonzero equality slope restricts the line to one parameter
        // value, however small that slope is. Do not use a residual tolerance
        // to turn a midpoint-only intersection into a full segment.
        const auto endpoint=residual/slope;
        lower=std::max(lower,static_cast<double>(endpoint));
        upper=std::min(upper,static_cast<double>(endpoint));
    }
    for(std::size_t i=0;i<h.inequalities.rows();++i) {
        long double row_scale=std::abs(static_cast<long double>(h.upper_bounds[i]));
        for(std::size_t j=0;j<origin.size();++j)
            row_scale=std::max(row_scale,std::abs(static_cast<long double>(h.inequalities(i,j))));
        const auto divisor=row_scale>0?row_scale:1.0L;
        long double at_origin=0,slope=0;
        for(std::size_t j=0;j<origin.size();++j) {
            const auto coefficient=static_cast<long double>(h.inequalities(i,j))/divisor;
            at_origin+=coefficient*origin[j];slope+=coefficient*direction[j];
        }
        const auto rhs=static_cast<long double>(h.upper_bounds[i])/divisor-at_origin;
        if(slope==0) {
            CHECK(rhs>=-tolerance);
            continue;
        }
        const auto endpoint=rhs/slope;
        if(slope>0)upper=std::min(upper,static_cast<double>(endpoint));
        else lower=std::max(lower,static_cast<double>(endpoint));
    }
    return {lower,upper};
}
sets::HRepresentation scaled_parameter_interval(double row_scale) {
    const Matrix inequalities{2,5,{0,row_scale,0,0,0,0,-row_scale,0,0,0}};
    const Vector bounds{row_scale,0};
    const auto set=accepted(sets::make_h({{"scaled-parameter-interval"},5,{"x0","x1","x2","u0","u1"}},
        {accepted(numeric::snapshot(inequalities)),accepted(numeric::snapshot_vector(bounds)),
         accepted(numeric::snapshot(Matrix{0,5,{}})),accepted(numeric::snapshot_vector(Vector{}))}));
    return std::get<sets::HRepresentation>(set.representation());
}
sets::HRepresentation midpoint_equality_parameter_interval() {
    const auto set=accepted(sets::make_h({{"midpoint-equality-interval"},5,{"x0","x1","x2","u0","u1"}},
        {accepted(numeric::snapshot(Matrix{2,5,{0,1,0,0,0,0,-1,0,0,0}})),
         accepted(numeric::snapshot_vector(Vector{1,0})),
         accepted(numeric::snapshot(Matrix{1,5,{1,1e-11,0,0,0}})),
         accepted(numeric::snapshot_vector(Vector{5e-12}))}));
    return std::get<sets::HRepresentation>(set.representation());
}
template<class Program,class Base> class OracleWorkspace final:public Base {
    Vector anchor_;double value_;bool wrong_;Termination termination_;std::stop_source* stop_;
    std::function<void()> before_return_;
    ProgramOutcome do_solve(const Program& p,const ExecutionContext&) override {
        auto id=p.identity();if(wrong_)id.program={"foreign"};
        EvidenceSupport support=SymbolicArgument{"literal-joint-oracle","Hand-minimized objective on the authored joint relation."};
        ProgramObjectiveBound bound{value_,{id,support,{}}};
        if(stop_)stop_->request_stop();
        ProgramResult result{termination_,{id,MathematicalOutcome::optimal,support,{}},anchor_,{bound,bound},"independent analytic oracle"};
        if(before_return_)before_return_();
        return result;
    }
public: OracleWorkspace(Vector a,double v,bool wrong,Termination term,std::stop_source* stop,std::function<void()> before_return={}):anchor_(std::move(a)),value_(v),wrong_(wrong),termination_(term),stop_(stop),before_return_(std::move(before_return)){}
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
SynthesisResult run_strategy_a(const problem::ResolvedProblem& p,const FamilyRequest& family) {
    auto lp=accepted(adapters::lp::make_highs_registration());
    auto convex=accepted(adapters::convex::make_highs_registration());
    auto converter=accepted(adapters::polyhedral::make_qhull_registration(lp));
    auto projection=geometry::polyhedral::make_projection_registration();
    auto selected=[]<class Port>(registry::Registration<Port> entry,std::string representation) {
        registry::Registry<Port> providers;
        const registry::Method method{entry.identity.id,entry.identity.version};
        REQUIRE_FALSE(providers.add(std::move(entry)).has_value());
        registry::Requirements required;required.output.representation={std::move(representation)};
        if constexpr(std::is_same_v<Port,registry::GeometryPort> || std::is_same_v<Port,registry::ConversionPort>)
            required.output.relation=SetRelation::equivalent;
        return accepted(registry::prepare_provider(registry::select_provider(providers,method,required)));
    };
    auto affine=geometry::make_affine_sum_registration({
        selected(geometry::make_lp_hull_reducer_registration(),""),
        selected(lp,"csl.program-result.v1"),selected(converter,"csl.polyhedron.v")});
    registry::Registry<registry::GeometryPort> projections,affines;
    registry::Registry<registry::ConversionPort> conversions;
    registry::Registry<registry::LPPort> lps;registry::Registry<registry::ConvexPort> convexes;
    const registry::Method pm{projection.identity.id,projection.identity.version};
    const registry::Method am{affine.identity.id,affine.identity.version};
    const registry::Method cm{converter.identity.id,converter.identity.version};
    const registry::Method lm{lp.identity.id,lp.identity.version};
    const registry::Method qm{convex.identity.id,convex.identity.version};
    REQUIRE_FALSE(projections.add(std::move(projection)).has_value());
    REQUIRE_FALSE(affines.add(std::move(affine)).has_value());
    REQUIRE_FALSE(conversions.add(std::move(converter)).has_value());
    REQUIRE_FALSE(lps.add(std::move(lp)).has_value());
    REQUIRE_FALSE(convexes.add(std::move(convex)).has_value());
    registry::Requirements h,v,program;
    h.output.representation={"csl.polyhedron.h"};h.output.relation=SetRelation::equivalent;
    v.output.representation={"csl.polyhedron.v"};v.output.relation=SetRelation::equivalent;
    program.output.representation={"csl.program-result.v1"};
    auto providers=accepted(registry::check_providers(
        registry::select_provider(projections,pm,h),registry::select_provider(affines,am,v),
        registry::select_provider(conversions,cm,h),registry::select_provider(lps,lm,program),
        registry::select_provider(convexes,qm,program)));
    auto registration=synthesis::strategy_a::make_registration(std::move(providers));
    registry::StrategyRegistry strategies;REQUIRE_FALSE(strategies.add(std::move(registration)).has_value());
    StrategyConfiguration configuration;configuration.strategy={"csl.synthesis.reach-back"};
    registry::StrategyRequest query{p,configuration,family,"1",{}};
    registry::Requirements output;output.output.representation={"csl.polyhedron.h"};
    output.output.family=family.target;output.output.completeness=registry::Completeness::unestablished;
    auto prepared=accepted(strategies.prepare(query,output));auto workspace=prepared.create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    return accepted(workspace->run(context));
}
const sets::SetData& strategy_a_relation(const SynthesisResult& result) {
    REQUIRE(result.family);REQUIRE(result.family->target()==FamilyTarget::candidate_relaxation);
    const auto& candidate=std::get<CandidateFamily>(result.family->outcome());
    const auto* data=dynamic_cast<const synthesis::strategy_a::CandidateHistory*>(candidate.relation.payload.get());
    REQUIRE(data);return data->history.relation;
}
registry::PreparedStrategy registered_prepared(const problem::ResolvedProblem& p,const FamilyRequest& q,
    bool foreign_provider=false,Termination solver_termination=Termination::completed,std::stop_source* stop=nullptr,std::function<void()> before_return={}) {
    registry::Registry<registry::LPPort> lp;registry::Registry<registry::ConvexPort> qp;registry::StrategyRegistry strategies;
    auto linear=accepted(adapters::lp::make_highs_registration());auto convex=accepted(adapters::convex::make_highs_registration());
    if(foreign_provider) {
        registry::Requirements program_requirements;program_requirements.output.representation={"csl.program-result.v1"};
        const auto offer=[=](const auto&,const registry::Requirements&)->registry::Capability{return registry::Offer{program_requirements.output};};
        linear={{{"oracle-lp"},"1"},offer,[](const LinearProgram&){return std::make_unique<OracleWorkspace<LinearProgram,LPWorkspace>>(Vector{0,0.25,1,0.25,0.75},0,true,Termination::completed,nullptr);}};
        convex={{{"oracle-qp"},"1"},offer,[](const ConvexProgram&){return std::make_unique<OracleWorkspace<ConvexProgram,ConvexWorkspace>>(Vector{0,0.25,1,0.25,0.75},0,true,Termination::completed,nullptr);}};
    } else if(solver_termination!=Termination::completed || stop || before_return) {
        registry::Requirements program_requirements;program_requirements.output.representation={"csl.program-result.v1"};
        const auto offer=[=](const auto&,const registry::Requirements&)->registry::Capability{return registry::Offer{program_requirements.output};};
        linear={{{"oracle-lp"},"1"},offer,[=](const LinearProgram&){return std::make_unique<OracleWorkspace<LinearProgram,LPWorkspace>>(Vector{0,0.25,1,0.25,0.75},0,false,solver_termination,stop,before_return);}};
        convex={{{"oracle-qp"},"1"},offer,[=](const ConvexProgram&){return std::make_unique<OracleWorkspace<ConvexProgram,ConvexWorkspace>>(Vector{0,0.25,1,0.25,0.75},0,false,solver_termination,stop,before_return);}};
    }
    const auto lid=linear.identity.id,qid=convex.identity.id;lp.add(std::move(linear));qp.add(std::move(convex));
    CHECK_FALSE(strategies.add(make_registration(lp,qp)));
    StrategyConfiguration configuration;configuration.strategy={"csl.synthesis.strategy-b"};configuration.lp=lid;configuration.convex=qid;
    configuration.representation={"csl.polyhedron.h"};
    registry::Requirements requirements;requirements.output.representation={"csl.polyhedron.h"};
    requirements.output.family=q.target;
    requirements.output.completeness=q.target==FamilyTarget::exact_optimal_relation?
        registry::Completeness::established:registry::Completeness::unestablished;
    return accepted(strategies.prepare({p,configuration,q,"1"},requirements));
}
}
TEST_CASE("row-derived intervals are invariant under positive H-row scaling") {
    const Vector origin{0,0,0.5,0,0.5},direction{0,1,0,1,0};
    for(const double scale:{1e-200,1.0,1e200}) {
        const auto interval=parameter_interval(scaled_parameter_interval(scale),origin,direction);
        CHECK(std::isfinite(interval.first));CHECK(std::isfinite(interval.second));
        CHECK(std::abs(interval.first)<=1e-12);CHECK(std::abs(interval.second-1)<=1e-12);
    }
}
TEST_CASE("a nearly parallel equality collapses the parameter interval") {
    const auto interval=parameter_interval(midpoint_equality_parameter_interval(),
        Vector{0,0,0,0,0},Vector{0,1,0,0,0});
    CHECK(std::isfinite(interval.first));CHECK(std::isfinite(interval.second));
    CHECK(std::abs(interval.first-0.5)<=1e-12);CHECK(std::abs(interval.second-0.5)<=1e-12);
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
    const auto p=resolve(input);const auto q=request(p);
    // Independent full-history derivation: x0=0, x1=u0, x2=u1, and
    // u0,u1 in [0,1]. The objective (x2-1/2)^2 has minimum zero exactly
    // when x2=u1=1/2, leaving u0 free. Thus the full optimal relation is
    // {(0,a,1/2,a,1/2) : 0 <= a <= 1} in (x0,x1,x2,u0,u1) order.
    // Both A stages are zero, so the state matrix is singular.
    auto b_workspace=registered_prepared(p,q).create();
    ExecutionContext b_context;b_context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=accepted(b_workspace->run(b_context));
    CHECK(result.termination==Termination::completed);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    REQUIRE(result.family);CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK_FALSE(result.family->registry_verified());CHECK_FALSE(result.family->partial_registry_verified());
    const auto& data=payload(result);const auto& relation=data.relation;
    const Vector first{0,0,0.5,0,0.5},last{0,1,0.5,1,0.5};
    for(double a:{0.0,0.125,0.25,0.5,0.875,1.0})
        CHECK(contains(relation,{0,a,0.5,a,0.5}));
    CHECK_FALSE(contains(relation,{0,0.25,0.6,0.25,0.5}));
    CHECK_FALSE(contains(relation,{0,0.25,0.5,0.25,0.75}));
    const auto b_h=std::get<sets::HRepresentation>(relation.representation());
    CHECK(equality_rank(b_h)==4);

    // Compare the same resolved profile through Strategy A. Rank four plus
    // the shared endpoints confines each convex H set to the same line;
    // intersecting every H-row with this line must yield the entire interval.
    const auto a_result=run_strategy_a(p,q);const auto& a_relation=strategy_a_relation(a_result);
    const auto a_h=std::get<sets::HRepresentation>(a_relation.representation());
    CHECK(equality_rank(a_h)==4);
    CHECK(contains(relation,first));CHECK(contains(relation,last));
    CHECK(contains(a_relation,first,1e-7));CHECK(contains(a_relation,last,1e-7));
    const Vector direction{0,1,0,1,0};
    const auto b_interval=parameter_interval(b_h,first,direction);
    const auto a_interval=parameter_interval(a_h,first,direction);
    CHECK(std::isfinite(b_interval.first));CHECK(std::isfinite(b_interval.second));
    CHECK(std::abs(b_interval.first)<=1e-7);CHECK(std::abs(b_interval.second-1)<=1e-7);
    CHECK(std::isfinite(a_interval.first));CHECK(std::isfinite(a_interval.second));
    CHECK(std::abs(a_interval.first)<=1e-7);CHECK(std::abs(a_interval.second-1)<=1e-7);
    for(const auto& point:std::vector<Vector>{{0,0.25,0.6,0.25,0.5},{0,0.25,0.5,0.25,0.75}}) {
        CHECK_FALSE(contains(relation,point));CHECK_FALSE(contains(a_relation,point,1e-7));
    }
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
TEST_CASE("registered cancellation after optimization retains candidate and scoped objective evidence") {
    const auto p=resolve(integrator());const auto q=request(p);std::stop_source source;
    const auto prepared=registered_prepared(p,q,false,Termination::completed,&source);
    auto workspace=prepared.create();ExecutionContext context;context.cancellation=source.get_token();
    const auto result=accepted(workspace->run(context));
    CHECK(result.termination==Termination::cancelled);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(result.stop));
    const auto& stop=std::get<ScopedOperationStopped>(result.stop);
    CHECK(stop.stop.reason==StopReason::cancelled);
    CHECK(stop.stop.diagnostics=="Original-problem anchor verification stopped; program evidence and feasible candidate retained.");
    CHECK(stop.request.request==RequestId{"syn04-joint:"+p.identity().value});
    CHECK(stop.request.port=="convex");
    CHECK(result.spans.empty()); // Strategy B emits no timing spans on this path; instrumentation is tracked in #89.
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    REQUIRE(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    const auto& data=payload(result);REQUIRE(data.optimization);
    CHECK(data.optimization->termination==Termination::completed);
    CHECK(contains(data.relation,{0,0.25,1,0.25,0.75}));
    REQUIRE(data.optimization->objective.lower);CHECK(data.optimization->objective.lower->value==0);
    CHECK(data.optimization->objective.lower->evidence.subject==data.optimization->outcome.subject);
    CHECK(std::holds_alternative<SymbolicArgument>(data.optimization->objective.lower->evidence.support));
    REQUIRE(data.optimization->objective.upper);CHECK(data.optimization->objective.upper->value==0);
    CHECK(data.optimization->objective.upper->evidence.subject==data.optimization->outcome.subject);
    CHECK(std::holds_alternative<SymbolicArgument>(data.optimization->objective.upper->evidence.support));
    CHECK(result.incumbents.empty());
    CHECK_FALSE(stop.retained.lower_bound);
    CHECK_FALSE(stop.retained.upper_bound);
    CHECK(stop.retained.incumbents==0);
    CHECK(stop.retained.partial_or_candidate_family);
}

TEST_CASE("registered deadline expiry after optimization retains candidate and scoped objective evidence") {
    const auto p=resolve(integrator());const auto q=request(p);
    ExecutionContext context;
    // A test-only synchronous hook expires the caller-owned context after the
    // optimizer constructs its result. No deadline exists during admission or
    // program construction, so scheduling delays cannot cause pre-solve expiry.
    const auto prepared=registered_prepared(p,q,false,Termination::completed,nullptr,[&context] {
        REQUIRE_FALSE(context.deadline);
        context.deadline=std::chrono::steady_clock::now();
    });
    auto workspace=prepared.create();
    const auto result=accepted(workspace->run(context));
    CHECK(result.termination==Termination::cancelled);
    CHECK(result.outcome.subject==p.identity());
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK(std::holds_alternative<Unestablished>(result.outcome.support));
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(result.stop));
    const auto& stop=std::get<ScopedOperationStopped>(result.stop);
    CHECK(stop.stop.reason==StopReason::deadline_expired);
    CHECK(stop.stop.diagnostics=="Original-problem anchor verification stopped; program evidence and feasible candidate retained.");
    CHECK(stop.request.request==RequestId{"syn04-joint:"+p.identity().value});
    CHECK(stop.request.port=="convex");
    CHECK(result.spans.empty()); // No timing spans are emitted here; instrumentation is tracked in #89.
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK(result.family->identity().request==q);
    REQUIRE(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    CHECK_FALSE(result.family->registry_verified());
    CHECK_FALSE(result.complete_proposal);
    const auto& candidate=std::get<CandidateFamily>(result.family->outcome());
    CHECK(candidate.relation.coordinates==JointCoordinates{{1,1,0},2});
    CHECK(candidate.relation.representation==RepresentationId{"csl.polyhedron.h"});
    CHECK(std::holds_alternative<HeuristicRelationEvidence>(candidate.relation_to_target));
    CHECK(std::holds_alternative<Unestablished>(candidate.feasibility));
    const auto& data=payload(result);REQUIRE(data.optimization);
    REQUIRE(data.diagnostics.size()==1);
    CHECK(data.diagnostics[0].code==DiagnosticCode::unsupported);
    CHECK(data.diagnostics[0].field=="verification");
    CHECK(data.diagnostics[0].explanation=="deadline observed");
    CHECK(data.optimization->termination==Termination::completed);
    CHECK(data.optimization->outcome.value==MathematicalOutcome::optimal);
    CHECK(data.optimization->outcome.subject.problem==p.identity());
    CHECK(data.optimization->outcome.subject.program==ProgramId{"syn04-joint:"+p.identity().value});
    CHECK(data.optimization->primal==std::optional<Vector>{{0,0.25,1,0.25,0.75}});
    CHECK(data.optimization->raw_diagnostics=="independent analytic oracle");
    CHECK(contains(data.relation,{0,0.25,1,0.25,0.75}));
    for(const auto* bound:{&data.optimization->objective.lower,&data.optimization->objective.upper}) {
        REQUIRE(*bound);
        CHECK((*bound)->value==0);
        CHECK((*bound)->evidence.subject.problem==p.identity());
        CHECK((*bound)->evidence.subject.program==ProgramId{"syn04-joint:"+p.identity().value});
        REQUIRE(std::holds_alternative<SymbolicArgument>((*bound)->evidence.support));
        const auto& support=std::get<SymbolicArgument>((*bound)->evidence.support);
        CHECK(support.reference=="literal-joint-oracle");
        CHECK(support.assumptions=="Hand-minimized objective on the authored joint relation.");
    }
    CHECK_FALSE(result.objective.lower);
    CHECK_FALSE(result.objective.upper);
    CHECK(result.incumbents.empty());
    CHECK_FALSE(stop.retained.lower_bound);
    CHECK_FALSE(stop.retained.upper_bound);
    CHECK(stop.retained.incumbents==0);
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

    // The registered workspace is reusable, but runtime evidence belongs to one solve only.
    std::stop_source stop;stop.request_stop();
    auto stopped_context=context;stopped_context.cancellation=stop.get_token();
    const auto stopped=accepted(workspace->run(stopped_context));
    CHECK(stopped.termination==Termination::cancelled);
    CHECK_FALSE(stopped.family);

    const auto rerun=accepted(workspace->run(context));
    REQUIRE(rerun.termination==Termination::completed);
    REQUIRE(rerun.family);
    CHECK(rerun.family->target()==FamilyTarget::exact_optimal_relation);
    CHECK(rerun.family->registry_verified());
    CHECK(rerun.family->identity()==identity);
    CHECK(check_synthesis_result(rerun,identity).empty());

    const auto neighboring=resolve(integrator(QuadraticTerminal{{1,1,{2}},{-1},0.25}));
    auto unsupported=request(neighboring);unsupported.profile=synthesis::strategy_ts01::profile_id;
    unsupported.target=FamilyTarget::exact_optimal_relation;
    CHECK(std::holds_alternative<registry::Rejection>(strategies.prepare({neighboring,configuration,unsupported,"1"},requirements)));
}
TEST_CASE("Strategy B T-S01 rejects a matching self-reported lineage without runtime evidence") {
    const auto p=resolve(integrator());
    auto exact=request(p);exact.profile=synthesis::strategy_ts01::profile_id;exact.target=FamilyTarget::exact_optimal_relation;
    StrategyConfiguration configuration;configuration.strategy={"csl.synthesis.strategy-b"};
    configuration.representation={"csl.polyhedron.h"};
    registry::Requirements requirements;requirements.output.representation={"csl.polyhedron.h"};
    requirements.output.assurance=Assurance::numerical;requirements.output.family=FamilyTarget::exact_optimal_relation;
    requirements.output.completeness=registry::Completeness::established;
    const auto proposal=exact_ts01_proposal(p,exact);
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    registry::StrategyRegistry forged_strategies;
    REQUIRE_FALSE(forged_strategies.add(proposal_only_strategy(proposal)));
    auto forged=forged_strategies.prepare({p,configuration,exact,"1"},requirements);
    REQUIRE(std::holds_alternative<registry::PreparedStrategy>(forged));
    auto forged_workspace=std::get<registry::PreparedStrategy>(std::move(forged)).create();
    const auto rejected=accepted(forged_workspace->run(context));
    CHECK(rejected.termination==Termination::contract_rejected);
    CHECK_FALSE(rejected.family);
    CHECK_FALSE(rejected.complete_proposal);
    REQUIRE(std::holds_alternative<ContractValidationFailure>(rejected.stop));
    CHECK(std::any_of(std::get<ContractValidationFailure>(rejected.stop).diagnostics.begin(),
        std::get<ContractValidationFailure>(rejected.stop).diagnostics.end(),[](const Diagnostic& diagnostic) {
            return diagnostic.code==DiagnosticCode::evidence_mismatch&&diagnostic.field=="family.runtime_receipt";
        }));

    auto reordered=proposal;
    std::reverse(reordered.identity.lineage.begin(),reordered.identity.lineage.end());
    reordered.family.completeness.binding=reordered.identity;
    registry::StrategyRegistry reordered_strategies;
    REQUIRE_FALSE(reordered_strategies.add(proposal_only_strategy(std::move(reordered))));
    auto reordered_prepared=reordered_strategies.prepare({p,configuration,exact,"1"},requirements);
    REQUIRE(std::holds_alternative<registry::PreparedStrategy>(reordered_prepared));
    auto reordered_workspace=std::get<registry::PreparedStrategy>(std::move(reordered_prepared)).create();
    const auto reordered_result=accepted(reordered_workspace->run(context));
    CHECK(reordered_result.termination==Termination::contract_rejected);
    CHECK_FALSE(reordered_result.family);
    REQUIRE(std::holds_alternative<ContractValidationFailure>(reordered_result.stop));
    CHECK(std::any_of(std::get<ContractValidationFailure>(reordered_result.stop).diagnostics.begin(),
        std::get<ContractValidationFailure>(reordered_result.stop).diagnostics.end(),[](const Diagnostic& diagnostic) {
            return diagnostic.code==DiagnosticCode::evidence_mismatch&&diagnostic.field=="family.proposal.binding";
        }));
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
TEST_CASE("registered Strategy B rejects partial-family preparation before creating solver workspaces") {
    const auto p=resolve(integrator());auto q=request(p);q.target=FamilyTarget::partial_relation;
    registry::Registry<registry::LPPort> lp;registry::Registry<registry::ConvexPort> qp;
    registry::StrategyRegistry strategies;
    auto linear=accepted(adapters::lp::make_highs_registration());
    auto convex=accepted(adapters::convex::make_highs_registration());
    const auto lp_id=linear.identity.id,convex_id=convex.identity.id;
    std::size_t lp_factory_calls=0,convex_factory_calls=0;
    const auto lp_factory=linear.factory;
    linear.factory=[&lp_factory_calls,lp_factory](const LinearProgram& program) {
        ++lp_factory_calls;return lp_factory(program);
    };
    const auto convex_factory=convex.factory;
    convex.factory=[&convex_factory_calls,convex_factory](const ConvexProgram& program) {
        ++convex_factory_calls;return convex_factory(program);
    };
    REQUIRE_FALSE(lp.add(std::move(linear)));REQUIRE_FALSE(qp.add(std::move(convex)));
    REQUIRE_FALSE(strategies.add(make_registration(lp,qp)));
    StrategyConfiguration configuration;configuration.strategy={"csl.synthesis.strategy-b"};
    configuration.lp=lp_id;configuration.convex=convex_id;configuration.representation=q.representation;
    registry::Requirements requirements;requirements.output.representation=q.representation;
    requirements.output.assurance=q.assurance;requirements.output.family=q.target;
    requirements.output.completeness=registry::Completeness::unestablished;

    const auto prepared=strategies.prepare({p,configuration,q,"1"},requirements);
    REQUIRE(std::holds_alternative<registry::Rejection>(prepared));
    const auto& rejection=std::get<registry::Rejection>(prepared);
    CHECK(rejection.provenance.port=="strategy");
    CHECK(rejection.provenance.requested.id==ModuleId{"csl.synthesis.strategy-b"});
    CHECK_FALSE(rejection.provenance.requested.version);
    REQUIRE(rejection.provenance.actual);
    CHECK(rejection.provenance.actual->id==ModuleId{"csl.synthesis.strategy-b"});
    CHECK(rejection.provenance.actual->version=="1");
    REQUIRE(rejection.diagnostics.size()==1);
    CHECK(rejection.diagnostics.front().code==DiagnosticCode::unsupported);
    CHECK(rejection.diagnostics.front().field=="joint.coverage");
    CHECK(rejection.diagnostics.front().explanation==
        "Only the exact reviewed T-S01/T-S02 profiles have registered complete-family verifiers; other requests remain candidates.");
    CHECK(lp_factory_calls==0);
    CHECK(convex_factory_calls==0);
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
TEST_CASE("Strategy B registers the exact T-S02 constant-objective history family") {
    const auto p=resolve(integrator(LinearTerminal{{0},3}));
    auto exact=request(p);exact.profile="ts02_constant_integrator";
    exact.target=FamilyTarget::exact_optimal_relation;
    registry::Registry<registry::LPPort> lp;registry::Registry<registry::ConvexPort> qp;
    registry::StrategyRegistry strategies;
    auto linear=accepted(adapters::lp::make_highs_registration());
    auto convex=accepted(adapters::convex::make_highs_registration());
    const auto lp_id=linear.identity.id,convex_id=convex.identity.id;
    REQUIRE_FALSE(lp.add(std::move(linear)));REQUIRE_FALSE(qp.add(std::move(convex)));
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
    REQUIRE(result.termination==Termination::completed);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
    CHECK(result.family->registry_verified());
    CHECK(result.outcome.value==MathematicalOutcome::optimal);
    CHECK(result.outcome.subject==p.identity());
    CHECK(result.family->identity().problem==p.identity());
    CHECK(result.family->identity().request==exact);
    CHECK(result.family->identity().coordinates==p.constraints().coordinates());
    CHECK(result.family->identity().strategy==ModuleId{"csl.synthesis.strategy-b"});
    CHECK(result.family->identity().strategy_version=="1");
    REQUIRE(result.family->identity().lineage.size()==1);
    CHECK(result.family->identity().lineage.front().request==RequestId{"syn04-build:"+p.identity().value});
    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    const auto* proof=std::get_if<RegisteredCompletenessEvidence>(&complete.completeness.support);
    REQUIRE(proof);
    CHECK(proof->verifier==ModuleId{"csl.verifier.ts02-constant-integrator"});
    CHECK(proof->verifier_version=="1");
    CHECK(proof->proof=="TS02-constant-integrator-v1");
    const auto payload=std::dynamic_pointer_cast<const synthesis::Ts02ConstantIntegratorRelation>(complete.relation.payload);
    REQUIRE(payload);
    const auto& metadata=*payload->h_polyhedron().metadata();
    CHECK(metadata.id==SetId{"ts02-optimal-histories"});
    CHECK(metadata.set.dimension==5);
    CHECK(metadata.coordinate_labels==std::vector<std::string>{"x0","x1","x2","u0","u1"});
    CHECK(complete.relation.coordinates==p.constraints().coordinates());
    CHECK(complete.relation.representation==RepresentationId{"csl.polyhedron.h"});

    // Independent public-result oracle: x0=0, x1=x0+u0, x2=x1+u1,
    // 0<=u0,u1<=1. The objective is identically 3, so every point in this
    // feasible H-relation and no other point is optimal. Check every literal
    // row and bound without treating storage order (or equality sign) as
    // semantic; the compiled verifier below is supplemental, not the
    // mathematical oracle for this claim.
    const auto representation=payload->h_polyhedron().representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);
    const Matrix expected_inequalities{4,5,{0,0,0,1,0, 0,0,0,-1,0,
        0,0,0,0,1, 0,0,0,0,-1}};
    const Vector expected_upper{1,0,1,0};
    const Matrix expected_equalities{3,5,{1,0,0,0,0, -1,1,0,-1,0,
        0,-1,1,0,-1}};
    const Vector expected_values{0,0,0};
    REQUIRE(h.inequalities.rows()==expected_inequalities.rows);
    REQUIRE(h.inequalities.cols()==expected_inequalities.cols);
    REQUIRE(h.upper_bounds.size()==expected_upper.size());
    REQUIRE(h.equalities.rows()==expected_equalities.rows);
    REQUIRE(h.equalities.cols()==expected_equalities.cols);
    REQUIRE(h.equality_values.size()==expected_values.size());
    const auto rows_match=[](const auto& actual_matrix,const auto& actual_bounds,
        const Matrix& expected_matrix,const Vector& expected_bounds,bool allow_sign_reversal) {
        if(actual_matrix.rows()!=expected_matrix.rows || actual_matrix.cols()!=expected_matrix.cols ||
            actual_bounds.size()!=expected_bounds.size())return false;
        std::vector<bool> matched(expected_matrix.rows,false);
        for(std::size_t i=0;i<actual_matrix.rows();++i) {
            bool found=false;
            for(std::size_t k=0;k<expected_matrix.rows && !found;++k)if(!matched[k]) {
                for(const double sign:{1.0,-1.0}) {
                    if(sign<0 && !allow_sign_reversal)continue;
                    bool equal=actual_bounds[i]==sign*expected_bounds[k];
                    for(std::size_t j=0;j<actual_matrix.cols() && equal;++j)
                        equal=actual_matrix(i,j)==sign*expected_matrix(k,j);
                    if(equal) {matched[k]=true;found=true;break;}
                }
            }
            if(!found)return false;
        }
        return true;
    };
    CHECK(rows_match(h.inequalities,h.upper_bounds,expected_inequalities,expected_upper,false));
    CHECK(rows_match(h.equalities,h.equality_values,expected_equalities,expected_values,true));
    CHECK(contains(payload->h_polyhedron(),{0,0,0,0,0}));
    CHECK(contains(payload->h_polyhedron(),{0,1,2,1,1}));
    const Vector first_same_terminal_history{0,0.3,1.1,0.3,0.8};
    const Vector second_same_terminal_history{0,0.5,1.1,0.5,0.6};
    CHECK(contains(payload->h_polyhedron(),first_same_terminal_history));
    CHECK(contains(payload->h_polyhedron(),second_same_terminal_history));
    CHECK(first_same_terminal_history[2]==second_same_terminal_history[2]);
    CHECK_FALSE(contains(payload->h_polyhedron(),{0,0,1,1,0}));
    REQUIRE(complete.optimum.bounds.lower);REQUIRE(complete.optimum.bounds.upper);
    CHECK(complete.optimum.bounds.lower->value==3);
    CHECK(complete.optimum.bounds.upper->value==3);
    const registry::StrategyRequest frozen{p,configuration,exact,"1",result.family->identity().lineage};
    CompleteFamilyProposal proposal{result.family->identity(),complete};
    const auto verifier=registry::detail::find_compiled_verifier({synthesis::ts02_constant_integrator_verifier},"1");
    REQUIRE(verifier);
    CHECK(verifier->verify(frozen,proposal).empty());
    auto candidate_request=frozen;candidate_request.family.target=FamilyTarget::candidate_relaxation;
    CHECK_FALSE(verifier->verify(candidate_request,proposal).empty());
    auto wrong_objective=resolve(integrator(LinearTerminal{{0},4}));
    auto wrong_request=frozen;wrong_request.problem=wrong_objective;wrong_request.family.objective=wrong_objective.identity();
    wrong_request.lineage=detail::expected_ts02_lineage(wrong_objective.identity());
    CHECK_FALSE(verifier->verify(wrong_request,proposal).empty());
    auto forged_relation=proposal;
    auto enlarged_upper=expected_upper;enlarged_upper[0]=2;
    const auto inequalities=accepted(numeric::snapshot(expected_inequalities));
    const auto upper=accepted(numeric::snapshot_vector(enlarged_upper));
    const auto equalities=accepted(numeric::snapshot(expected_equalities));
    const auto values=accepted(numeric::snapshot_vector(expected_values));
    auto enlarged=accepted(sets::make_h({{"ts02-optimal-histories"},5,{"x0","x1","x2","u0","u1"}},
        {inequalities,upper,equalities,values}));
    forged_relation.family.relation.payload=std::make_shared<const synthesis::Ts02ConstantIntegratorRelation>(std::move(enlarged));
    CHECK_FALSE(verifier->verify(frozen,forged_relation).empty());
    auto candidate_profile=exact;candidate_profile.target=FamilyTarget::candidate_relaxation;
    registry::Requirements candidate_requirements;candidate_requirements.output.representation={"csl.polyhedron.h"};
    candidate_requirements.output.assurance=Assurance::numerical;
    candidate_requirements.output.family=FamilyTarget::candidate_relaxation;
    candidate_requirements.output.completeness=registry::Completeness::unestablished;
    CHECK(std::holds_alternative<registry::Rejection>(strategies.prepare({p,configuration,candidate_profile,"1"},candidate_requirements)));
}
TEST_CASE("registered Strategy B reports a completed unbounded objective without a finite lower bound") {
    auto input=integrator(LinearTerminal{{-1},0});
    input.controls=ContinuousDomain{{UniversalSet{1},UniversalSet{1}}};
    input.states={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    const auto p=resolve(input);
    const auto q=request(p);
    const auto prepared=registered_prepared(p,q);
    auto workspace=prepared.create();
    ExecutionContext context;
    context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});

    const auto result=accepted(workspace->run(context));

    // Independent ray oracle: x0=0, u0=u1=t, x1=t, x2=2t is feasible
    // for every t>=0 and the authored objective is -x2=-2t, so its infimum
    // is -infinity. Solver termination is successful even though no optimum
    // or complete optimal-history family exists.
    CHECK(result.termination==Termination::completed);
    CHECK(result.outcome.subject==p.identity());
    CHECK(result.outcome.value==MathematicalOutcome::unbounded);
    CHECK(std::holds_alternative<Unestablished>(result.outcome.support));
    const auto generated_program=ProgramId{"syn04-joint:"+p.identity().value};
    CHECK(std::any_of(result.outcome.assumptions.begin(),result.outcome.assumptions.end(),[&](const std::string& assumption) {
        return assumption.find(generated_program.value)!=std::string::npos;
    }));
    CHECK(std::any_of(result.outcome.assumptions.begin(),result.outcome.assumptions.end(),[](const std::string& assumption) {
        return assumption.find("not independently validated")!=std::string::npos;
    }));
    CHECK_FALSE(result.objective.lower);
    CHECK_FALSE(result.complete_proposal);
    CHECK_FALSE(result.partial_proposal);
    CHECK_FALSE(result.family);
}
TEST_CASE("T-S02 verifier admits constant linear quadratic and residual norm objectives") {
    const std::vector<TerminalObjective> objectives{
        QuadraticTerminal{{1,1,{0}},{0},3},ResidualNormTerminal{{1,1,{0}},{3}}};
    for(const auto& objective:objectives) {
        const auto p=resolve(integrator(objective));auto exact=request(p);
        exact.profile=synthesis::ts02_constant_integrator_profile;
        exact.target=FamilyTarget::exact_optimal_relation;
        const auto prepared=registered_prepared(p,exact);auto workspace=prepared.create();
        ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
        context.numerical=exact.numerical;
        const auto result=accepted(workspace->run(context));
        REQUIRE(result.termination==Termination::completed);
        REQUIRE(result.family);CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
        CHECK(result.family->registry_verified());CHECK(result.outcome.value==MathematicalOutcome::optimal);
        REQUIRE(result.objective.lower);REQUIRE(result.objective.upper);
        CHECK(result.objective.lower->value==3);CHECK(result.objective.upper->value==3);
    }
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
TEST_CASE("registered Strategy B preserves its prepared numerical policy in the public result") {
    const auto p=resolve(integrator());auto q=request(p);
    q.assurance=Assurance::numerical;q.numerical={1e-7,2e-7};
    const auto prepared=registered_prepared(p,q);

    auto matching_workspace=prepared.create();
    ExecutionContext matching_context;
    matching_context.numerical={1e-7,2e-7};
    matching_context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=accepted(matching_workspace->run(matching_context));
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK(result.family->identity().request.numerical.absolute_tolerance==1e-7);
    CHECK(result.family->identity().request.numerical.relative_tolerance==2e-7);
    CHECK(result.family->identity().request.numerical==(NumericalPolicy{1e-7,2e-7}));

    auto mismatched_workspace=prepared.create();
    ExecutionContext mismatched_context;
    mismatched_context.numerical={1e-6,2e-7};
    mismatched_context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto unsupported=mismatched_workspace->run(mismatched_context);
    REQUIRE(std::holds_alternative<Unsupported>(unsupported));
    const auto& diagnostics=std::get<Unsupported>(unsupported).diagnostics;
    REQUIRE(diagnostics.size()==1);
    CHECK(diagnostics.front().code==DiagnosticCode::invalid_input);
    CHECK(diagnostics.front().field=="family.numerical");
    CHECK(diagnostics.front().explanation==
        "ExecutionContext numerical policy differs from the prepared family request");
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
