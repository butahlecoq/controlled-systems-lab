#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/verification/trajectory.hpp>
#include <algorithm>
#include <limits>
#include <csl/optimization/phase_one.hpp>
using namespace csl;
using namespace csl::verification;
namespace {
template<class T,class... Rest> T accepted(std::variant<T,Rest...> result) {
    REQUIRE(std::holds_alternative<T>(result));return std::get<T>(std::move(result));
}
Problem scalar() {
    return {{"authored"},std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
        LinearStage{{1,1,{0}},{1,1,{1}},{1,0,{}},{0}}},{}}),{0,1},KnownInitial{{2}},
        ContinuousDomain{{Singleton{{3}}}},{UniversalSet{1},UniversalSet{1}},{},{},InformationPattern::nominal_open_loop,LinearTerminal{{1},0}};
}
problem::ResolvedProblem resolve(Problem p) {return accepted(problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));}
TrajectoryRequest request(const problem::ResolvedProblem& p) {TrajectoryRequest r;r.witness={p.identity(),{{2},{3}},{{3}},3};return r;}
const NamedResidual& residual(const TrajectoryReport& r,const std::string& field) {
    auto found=std::find_if(r.residuals.begin(),r.residuals.end(),[&](const auto& x){return x.field==field;});
    REQUIRE(found!=r.residuals.end());return *found;
}
}
TEST_CASE("literal original trajectory passes without a solver success flag") {
    auto p=resolve(scalar());auto r=verify_trajectory(p,request(p));
    CHECK(r.bindings==CheckStatus::numerical_pass);CHECK(r.feasibility==CheckStatus::numerical_pass);
    CHECK(r.objective==CheckStatus::numerical_pass);REQUIRE(r.recomputed_objective);CHECK(*r.recomputed_objective==3);
    CHECK(r.optimality==CheckStatus::unsupported);CHECK(r.completeness==CheckStatus::unsupported);
    CHECK(r.validated==CheckStatus::unsupported);CHECK(r.membership_queries.empty());
}
TEST_CASE("wrong original transition control and cost each have named residuals") {
    auto p=resolve(scalar());auto q=request(p);q.witness.states[1][0]=4;q.witness.controls[0][0]=5;q.witness.original_objective=9;
    auto r=verify_trajectory(p,q);CHECK(r.feasibility==CheckStatus::violation);CHECK(r.objective==CheckStatus::violation);
    CHECK(residual(r,"dynamics[0][0]").measure.violation==1);
    CHECK(residual(r,"controls[0].singleton[0]").measure.violation==2);
    CHECK(residual(r,"objective").measure.violation==5);
}
TEST_CASE("wrong problem and evidence never pass binding") {
    auto p=resolve(scalar());auto q=request(p);q.witness.problem={"wrong"};
    auto r=verify_trajectory(p,q);CHECK(r.bindings==CheckStatus::invalid_input);CHECK(r.feasibility==CheckStatus::not_checked);
    q=request(p);q.bounds.lower=ObjectiveBound{3,{{"wrong"},CertificateReference{"certificate","untrusted"}}};
    r=verify_trajectory(p,q);CHECK(r.bindings==CheckStatus::invalid_input);REQUIRE(r.input.bounds.lower);
    CHECK(r.input.bounds.lower->evidence.problem.value=="wrong");
}
TEST_CASE("two-control unit-box oracle checks each original history without claiming family coverage") {
    auto input=scalar();
    input.times={0,1,2};input.initial=KnownInitial{{0}};
    input.model=std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
        std::vector<LinearStage>{
            {{1,1,{1}},{1,1,{1}},{1,0,{}},{0}},
            {{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}}}, {}});
    const auto unit=accepted(sets::make_h({{"unit-control"},1,{}},
        {accepted(numeric::snapshot(Matrix{2,1,{1,-1}})),
         accepted(numeric::snapshot_vector(Vector{1,0})),
         accepted(numeric::snapshot(Matrix{0,1,{}})),
         accepted(numeric::snapshot_vector(Vector{}))})).as_handle();
    input.controls=ContinuousDomain{{unit,unit}};
    input.states={Singleton{{0}},UniversalSet{1},Singleton{{1}}};
    auto p=resolve(input);TrajectoryRequest q;
    q.witness={p.identity(),{{0},{0.25},{1}},{{0.25},{0.75}},1};
    auto result=verify_trajectory(p,q);
    CHECK(result.feasibility==CheckStatus::numerical_pass);
    CHECK(result.objective==CheckStatus::numerical_pass);
    CHECK(result.completeness==CheckStatus::unsupported);
    q.witness.controls[1][0]=1.25;
    result=verify_trajectory(p,q);
    CHECK(result.feasibility==CheckStatus::violation);
    CHECK_FALSE(residual(result,"controls[1].inequalities[0]").satisfied);
    CHECK_FALSE(residual(result,"dynamics[1][0]").satisfied);
}
TEST_CASE("passive observation maps do not block nominal trajectory checks") {
    auto input=scalar();
    auto model=*input.model;
    model.observations={{ObservationStage{{1,1,{1}},{1,1,{0}},{1,0,{}},{1,0,{}},{0}}, {}}};
    input.model=std::make_shared<const SystemModel>(std::move(model));
    auto p=resolve(input);
    auto r=verify_trajectory(p,request(p));
    CHECK(r.feasibility==CheckStatus::numerical_pass);
    CHECK(r.objective==CheckStatus::numerical_pass);
}

namespace {
numeric::MatrixView matrix(Matrix m) {return accepted(numeric::snapshot(m));}
numeric::VectorView vector(Vector v) {return accepted(numeric::snapshot_vector(v));}
SetHandle interval_h() {return accepted(sets::make_h({{"interval"},1,{}},
    {matrix({2,1,{1,-1}}),vector({4,0}),matrix({0,1,{}}),vector({})})).as_handle();}
SetHandle segment_v() {return accepted(sets::make_v({{"segment"},1,{}},
    {matrix({2,1,{0,4}}),matrix({0,1,{}})})).as_handle();}
Problem ltv() {
    auto p=scalar();p.times={0,0.5,2,9};p.initial=KnownInitial{{1,2}};
    p.model=std::make_shared<const SystemModel>(SystemModel{{{2,1,1},TimeDomain::discrete,std::vector<LinearStage>{
        {{2,2,{0,0,0,0}},{2,1,{1,2}},{2,1,{2,-1}},{1,-1}},
        {{2,2,{1,0,0,0}},{2,1,{-1,3}},{2,1,{0,1}},{0,2}},
        {{2,2,{0,1,0,0}},{2,1,{2,1}},{2,1,{1,0}},{-1,0}}}}, {}});
    p.controls=ContinuousDomain{{Singleton{{2}},Singleton{{-1}},Singleton{{3}}}};
    p.states={Singleton{{1,2}},Singleton{{9,0}},Singleton{{10,3}},Singleton{{6,3}}};
    p.external=KnownExternalSequence{{{3},{4},{-2}}};
    p.objective=LinearTerminal{{2,-1},4};
    p.temporal=TemporalConstraints{{1,11,{0,4},{0,6,8,10},{1,1,1,-1}},{{6,6}}};return p;
}
TrajectoryRequest ltv_request(const problem::ResolvedProblem& p) {
    TrajectoryRequest r;r.witness={p.identity(),{{1,2},{9,0},{10,3},{6,3}},{{2},{-1},{3}},13};return r;
}
class Membership final:public LPWorkspace {
    int mode_;
public:explicit Membership(int mode):mode_(mode){}
    ProgramOutcome do_solve(const LinearProgram& p,const ExecutionContext&) override {
        ProgramResult r{Termination::completed,{p.identity(),MathematicalOutcome::optimal,Unestablished{},{}},Vector{0.25,0.75},{},"literal barycentric answer"};
        if(mode_==1)r.primal=Vector{0.75,0.25};
        if(mode_==2)r.outcome.subject.program={"wrong"};
        if(mode_==3)r.termination=Termination::resource_limit;
        if(mode_==4)r.outcome.support=NumericalCheck{-1,0,0,{"bad"}};
        if(mode_==5)r.objective.lower=ProgramObjectiveBound{0,{{p.identity().problem,{"other-program"}},Unestablished{},{}}};
        if(mode_==6) {r.outcome.value=MathematicalOutcome::infeasible;r.primal.reset();}
        return r;
    }
};
registry::PreparedProvider<registry::LPPort> provider(int mode,std::shared_ptr<int> factories=std::make_shared<int>(0)) {
    registry::Registry<registry::LPPort> registry;
    REQUIRE(!registry.add({{{"membership-literal"},"1"},
        [mode](const LinearProgram&,const registry::Requirements&)->registry::Capability {
            if(mode==7)return Diagnostics{{DiagnosticCode::unsupported,"membership","literal rejection"}};
            return registry::Offer{};
        },[mode,factories](const LinearProgram&){++*factories;return std::make_unique<Membership>(mode);}}));
    return accepted(registry::prepare_provider(registry::select_provider(registry,{{"membership-literal"},"1"})));
}
}
TEST_CASE("three-stage singular rectangular LTV uses prescribed external sequence and full history") {
    auto p=resolve(ltv());auto q=ltv_request(p);auto r=verify_trajectory(p,q);
    CHECK(r.feasibility==CheckStatus::numerical_pass);CHECK(r.recomputed_objective==13);
    CHECK(residual(r,"temporal[0].lower").measure.violation==0);
    CHECK(residual(r,"dynamics[2][0]").measure.violation==0);
    for(std::size_t i=0;i<4;++i) {auto changed=q;changed.witness.states[i][1]+=1;auto bad=verify_trajectory(p,changed);
        CHECK(bad.feasibility==CheckStatus::violation);CHECK_FALSE(residual(bad,"states["+std::to_string(i)+"].singleton[1]").satisfied);}
    for(std::size_t i=0;i<3;++i) {auto changed=q;changed.witness.controls[i][0]+=1;auto bad=verify_trajectory(p,changed);
        CHECK(bad.feasibility==CheckStatus::violation);CHECK_FALSE(residual(bad,"controls["+std::to_string(i)+"].singleton[0]").satisfied);}
    q.witness.controls[0].push_back(3);CHECK(verify_trajectory(p,q).feasibility==CheckStatus::invalid_input);
}
TEST_CASE("original quadratic and residual norm costs are not squared or replaced") {
    auto input=ltv();input.objective=QuadraticTerminal{{2,2,{2,0,0,4}},{1,-1},5};
    auto p=resolve(input);auto q=ltv_request(p);q.witness.original_objective=62;
    CHECK(verify_trajectory(p,q).recomputed_objective==62);CHECK(verify_trajectory(p,q).objective==CheckStatus::numerical_pass);
    input.objective=ResidualNormTerminal{{1,2,{1,2}},{2}};p=resolve(input);q=ltv_request(p);q.witness.original_objective=100;
    auto r=verify_trajectory(p,q);CHECK(r.recomputed_objective==10);CHECK(r.objective==CheckStatus::violation);
    CHECK(residual(r,"objective").measure.violation==90);
}
TEST_CASE("direct H inequalities and equalities include initial and terminal domains") {
    auto input=scalar();input.states={interval_h(),accepted(sets::make_h({{"eq"},1,{}},
        {matrix({0,1,{}}),vector({}),matrix({1,1,{2}}),vector({6})})).as_handle()};
    input.controls=ContinuousDomain{{interval_h()}};auto p=resolve(input);auto q=request(p);
    CHECK(verify_trajectory(p,q).feasibility==CheckStatus::numerical_pass);
    q.witness.states[0][0]=5;q.witness.states[1][0]=4;q.witness.controls[0][0]=-1;
    auto r=verify_trajectory(p,q);CHECK(residual(r,"states[0].inequalities[0]").measure.violation==1);
    CHECK(residual(r,"states[1].equalities[0]").measure.violation==2);
    CHECK(residual(r,"controls[0].inequalities[1]").measure.violation==1);
    CHECK(residual(r,"initial[0]").measure.violation==3);
}
TEST_CASE("empty universal singleton zero ports and zero horizon preserve their meanings") {
    auto input=scalar();input.states[1]=EmptySet{1};auto p=resolve(input);CHECK(verify_trajectory(p,request(p)).feasibility==CheckStatus::violation);
    input=scalar();input.times={0};input.controls=ContinuousDomain{{}};input.states={UniversalSet{1}};
    p=resolve(input);auto q=request(p);q.witness.states={{2}};q.witness.controls={};q.witness.original_objective=2;
    CHECK(verify_trajectory(p,q).feasibility==CheckStatus::numerical_pass);
    input.model=std::make_shared<const SystemModel>(SystemModel{{{0,0,0},TimeDomain::discrete,LinearStage{{0,0,{}},{0,0,{}},{0,0,{}},{}}},{}});
    input.initial=KnownInitial{{}};input.states={Singleton{{}}};input.objective=LinearTerminal{{},7};
    p=resolve(input);q.witness={p.identity(),{{}},{},7};auto r=verify_trajectory(p,q);
    CHECK(r.feasibility==CheckStatus::numerical_pass);CHECK(r.recomputed_objective==7);
}
TEST_CASE("explicit numerical thresholds and finite arithmetic do not certify validated accuracy") {
    auto p=resolve(scalar());auto q=request(p);q.witness.original_objective=3.125;
    ExecutionContext c;c.numerical={0.125,0};auto r=verify_trajectory(p,q,c);
    CHECK(r.objective==CheckStatus::numerical_pass);CHECK(residual(r,"objective").tolerance==0.125);
    c.numerical={0.124,0};CHECK(verify_trajectory(p,q,c).objective==CheckStatus::violation);
    c.numerical={-1,0};CHECK(verify_trajectory(p,q,c).feasibility==CheckStatus::invalid_input);
    q.assurance=Assurance::validated;r=verify_trajectory(p,q);CHECK(r.feasibility==CheckStatus::unsupported);
    CHECK(r.validated==CheckStatus::unsupported);
    q=request(p);q.witness.states[0][0]=std::numeric_limits<double>::quiet_NaN();CHECK(verify_trajectory(p,q).feasibility==CheckStatus::invalid_input);
}
TEST_CASE("stops and count limits retain supplied evidence and checked prefixes") {
    auto p=resolve(scalar());auto q=request(p);q.bounds.lower=ObjectiveBound{2,{p.identity(),CertificateReference{"retained","external"}}};
    std::stop_source stop;stop.request_stop();ExecutionContext c;c.cancellation=stop.get_token();
    auto r=verify_trajectory(p,q,c);CHECK(r.termination==Termination::cancelled);CHECK(r.feasibility==CheckStatus::not_checked);REQUIRE(r.input.bounds.lower);
    CHECK(std::get<CertificateReference>(r.input.bounds.lower->evidence.support).artifact=="retained");
    c={};c.deadline=std::chrono::steady_clock::time_point::min();CHECK(verify_trajectory(p,q,c).termination==Termination::resource_limit);
    q.limits.residuals=1;r=verify_trajectory(p,q);CHECK(r.termination==Termination::resource_limit);CHECK(r.residuals.size()==1);
    CHECK(r.feasibility!=CheckStatus::numerical_pass);
}
TEST_CASE("unsupported rich profiles are never silently dropped") {
    auto input=scalar();input.controls=FiniteDomain{1,{{3}}};auto p=resolve(input);CHECK(verify_trajectory(p,request(p)).feasibility==CheckStatus::unsupported);
    input=scalar();input.initial=InitialSet{Singleton{{2}},SetQuantifier::existential};p=resolve(input);
    CHECK(verify_trajectory(p,request(p)).feasibility==CheckStatus::unsupported);
    input=scalar();input.information=InformationPattern::feedback;p=resolve(input);CHECK(verify_trajectory(p,request(p)).feasibility==CheckStatus::unsupported);
    input=ltv();input.external=ExogenousExternalInput{{Singleton{{3}},Singleton{{4}},Singleton{{-2}}},SetQuantifier::universal};p=resolve(input);
    CHECK(verify_trajectory(p,ltv_request(p)).feasibility==CheckStatus::unsupported);
}
TEST_CASE("published candidate and claimed optimum never establish family coverage") {
    auto p=resolve(scalar());auto q=request(p);ClaimEvidence claim{p.identity(),NumericalCheck{0,0,0,{"backend"}}};
    q.outcome=SynthesisOutcomeClaim{p.identity(),MathematicalOutcome::optimal,claim.support,{"backend assumption"}};
    q.backend_bounds={ProgramObjectiveEvidence{ProgramObjectiveBound{3,{{p.identity(),{"original-program"}},claim.support,{"preserved assumption"}}},{}}};
    const auto coordinates=p.constraints().coordinates();
    const FamilyRequest effective{"nominal",p.identity(),FamilyTarget::candidate_relaxation,
        {1e-8,1e-8},Assurance::numerical,{"opaque-family"},{}};
    const FamilyIdentity identity{p.identity(),effective,coordinates,{"candidate-strategy"},"1",{}};
    const JointRelation relation{coordinates,effective.representation,{}};
    q.family=accepted(FamilyPublisher::publish(identity,CandidateFamily{relation,
        HeuristicRelationEvidence{"literal candidate"},WitnessFeasibilityEvidence{q.witness,claim}}));
    auto r=verify_trajectory(p,q);
    CHECK(r.bindings==CheckStatus::numerical_pass);CHECK(r.feasibility==CheckStatus::numerical_pass);
    CHECK(r.optimality==CheckStatus::unsupported);CHECK(r.completeness==CheckStatus::unsupported);
    CHECK(r.validated==CheckStatus::unsupported);
    CHECK(r.input.family->target()==FamilyTarget::candidate_relaxation);
    CHECK(r.input.backend_bounds[0].lower->evidence.subject.program.value=="original-program");
    CHECK(r.input.backend_bounds[0].lower->evidence.assumptions==std::vector<std::string>{"preserved assumption"});
    CHECK(std::holds_alternative<Diagnostics>(FamilyPublisher::publish(identity,CandidateFamily{relation,
        FeasibleCandidateEvidence{claim},WitnessFeasibilityEvidence{q.witness,claim}})));
    auto wrong_coordinates=coordinates;wrong_coordinates.horizon=7;
    auto wrong_identity=identity;wrong_identity.coordinates=wrong_coordinates;
    q.family=accepted(FamilyPublisher::publish(wrong_identity,CandidateFamily{
        JointRelation{wrong_coordinates,effective.representation,{}},HeuristicRelationEvidence{"literal candidate"},Unestablished{}}));
    CHECK(verify_trajectory(p,q).bindings==CheckStatus::invalid_input);
    auto wrong_problem=identity;wrong_problem.problem={"other-resolved-problem"};
    wrong_problem.request.objective=wrong_problem.problem;
    q.family=accepted(FamilyPublisher::publish(wrong_problem,CandidateFamily{relation,
        HeuristicRelationEvidence{"literal candidate"},Unestablished{}}));
    CHECK(verify_trajectory(p,q).bindings==CheckStatus::invalid_input);
    q.family.reset();q.outcome->subject={"wrong"};CHECK(verify_trajectory(p,q).bindings==CheckStatus::invalid_input);
}
TEST_CASE("published synthesis family bindings match only an independent expected synthesis identity") {
    auto p=resolve(scalar());
    auto q=request(p);
    ClaimEvidence claim{p.identity(),NumericalCheck{0,0,0,{"backend"}}};
    const auto coordinates=p.constraints().coordinates();
    const FamilyRequest effective{"nominal",p.identity(),FamilyTarget::candidate_relaxation,
        {1e-8,1e-8},Assurance::numerical,{"opaque-family"},{}};
    const std::vector<TransformStepIdentity> lineage{
        {{"transform/1"},{"source/set"},{"intermediate/set"},{"converter"},"2"},
        {{"transform/2"},{"intermediate/set"},{"family/set"},{"projector"},"3"}};
    const ModuleId strategy{"candidate-strategy"};
    const std::string strategy_version="1";
    const ExpectedSynthesisBinding expected{effective,strategy,strategy_version,lineage};
    const auto family=[&](const FamilyRequest& family_request,const ModuleId& family_strategy,
                          const std::string& family_version,
                          const std::vector<TransformStepIdentity>& family_lineage) {
        const FamilyIdentity identity{p.identity(),family_request,coordinates,family_strategy,family_version,family_lineage};
        const JointRelation relation{coordinates,family_request.representation,{}};
        return accepted(FamilyPublisher::publish(identity,CandidateFamily{relation,
            HeuristicRelationEvidence{"literal candidate"},WitnessFeasibilityEvidence{q.witness,claim}}));
    };
    q.family=family(effective,strategy,strategy_version,lineage);
    CHECK(verify_trajectory(p,q).bindings==CheckStatus::invalid_input);

    q.expected_synthesis=expected;
    auto report=verify_trajectory(p,q);
    CHECK(report.bindings==CheckStatus::numerical_pass);
    CHECK(report.feasibility==CheckStatus::numerical_pass);
    CHECK(report.optimality==CheckStatus::unsupported);
    CHECK(report.completeness==CheckStatus::unsupported);
    CHECK(report.validated==CheckStatus::unsupported);

    auto wrong_request=effective;
    wrong_request.profile="different-effective-request";
    q.family=family(wrong_request,strategy,strategy_version,lineage);
    CHECK(verify_trajectory(p,q).bindings==CheckStatus::invalid_input);

    auto wrong_strategy=strategy;
    wrong_strategy.value="different-strategy";
    q.family=family(effective,wrong_strategy,strategy_version,lineage);
    CHECK(verify_trajectory(p,q).bindings==CheckStatus::invalid_input);

    q.family=family(effective,strategy,"2",lineage);
    CHECK(verify_trajectory(p,q).bindings==CheckStatus::invalid_input);

    auto wrong_lineage=lineage;
    std::reverse(wrong_lineage.begin(),wrong_lineage.end());
    q.family=family(effective,strategy,strategy_version,wrong_lineage);
    CHECK(verify_trajectory(p,q).bindings==CheckStatus::invalid_input);

    q.family.reset();
    q.expected_synthesis.reset();
    CHECK(verify_trajectory(p,q).bindings==CheckStatus::numerical_pass);
    CHECK(verify_trajectory(p,q).optimality==CheckStatus::unsupported);
    CHECK(verify_trajectory(p,q).completeness==CheckStatus::unsupported);
}
TEST_CASE("V membership checks actual original rows and retains registered provenance") {
    auto input=scalar();input.states[1]=segment_v();auto p=resolve(input);auto q=request(p);
    CHECK(verify_trajectory(p,q).feasibility==CheckStatus::unsupported);
    auto r=verify_trajectory(p,q,{},provider(0));CHECK(r.feasibility==CheckStatus::numerical_pass);
    REQUIRE(r.membership_queries.size()==1);const auto& call=std::get<registry::LPQueryCompleted>(r.membership_queries[0]);
    CHECK(call.request==call.returned_subject);CHECK(call.provider.actual->id.value=="membership-literal");
    CHECK(residual(r,"states[1].reconstruction[0]").measure.violation==0);
    q.witness.states[1][0]=1;auto other=verify_trajectory(p,q,{},provider(1));
    CHECK(std::get<registry::LPQueryCompleted>(other.membership_queries[0]).request!=call.request);
}
TEST_CASE("malformed or ambiguous membership evidence cannot pass and stopped queries stay stopped") {
    auto input=scalar();input.states[1]=segment_v();auto p=resolve(input);auto q=request(p);
    for(int mode:{1,2,4,5,6}) {auto r=verify_trajectory(p,q,{},provider(mode));INFO("mode ",mode);CHECK(r.feasibility==CheckStatus::unsupported);CHECK(r.membership_queries.size()==1);}
    auto r=verify_trajectory(p,q,{},provider(3));CHECK(r.termination==Termination::resource_limit);CHECK(r.feasibility!=CheckStatus::numerical_pass);
    q.bounds.lower=ObjectiveBound{0,{p.identity(),CertificateReference{"retained-bound","unverified"}}};
    auto count=std::make_shared<int>(0);r=verify_trajectory(p,q,{},provider(7,count));
    CHECK(r.termination==Termination::completed);CHECK(r.feasibility==CheckStatus::unsupported);CHECK(*count==0);
    REQUIRE(r.input.bounds.lower);CHECK(r.input.bounds.lower->value==0);
    CHECK(residual(r,"initial[0]").satisfied);
    q.limits.membership_queries=0;r=verify_trajectory(p,q,{},provider(0));CHECK(r.termination==Termination::resource_limit);CHECK(r.membership_queries.empty());
}
TEST_CASE("actual registered phase one supplies numerical V membership with no native backend dependency") {
    auto provider_owner=[] {
        registry::Registry<registry::LPPort> registry;auto registration=accepted(optimization::phase_one::make_registration());
        const auto method=registry::Method{registration.identity.id,registration.identity.version};
        REQUIRE(!registry.add(std::move(registration)));
        registry::Requirements requirements;
        requirements.output.representation={"csl.program-result.v1"};
        return accepted(registry::prepare_provider(registry::select_provider(registry,method,requirements)));
    }();
    auto input=scalar();input.states[1]=segment_v();auto p=resolve(input);auto r=verify_trajectory(p,request(p),{},provider_owner);
    CHECK(r.feasibility==CheckStatus::numerical_pass);REQUIRE(r.membership_queries.size()==1);
    CHECK(std::get<registry::LPQueryCompleted>(r.membership_queries[0]).provider.actual->id.value=="phase-one-bland");
}
