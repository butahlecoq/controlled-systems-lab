#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/verification/trajectory.hpp>
#include <algorithm>
#include <limits>
#include <csl/optimization/phase_one.hpp>
#include <csl/optimization/linear_infeasibility_certificate.hpp>
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
    q.verification=VerificationRequest{{0.125,0.03125},Assurance::numerical};
    ExecutionContext c;
    auto r=verify_trajectory(p,q,c);CHECK(r.feasibility==CheckStatus::violation);CHECK(r.objective==CheckStatus::violation);
    CHECK(residual(r,"dynamics[0][0]").measure.violation==1);
    CHECK(residual(r,"dynamics[0][0]").tolerance==0.28125);
    CHECK(residual(r,"controls[0].singleton[0]").measure.violation==2);
    CHECK(residual(r,"controls[0].singleton[0]").tolerance==0.28125);
    CHECK(residual(r,"objective").measure.violation==5);
    CHECK(residual(r,"objective").tolerance==0.40625);
}
TEST_CASE("positive-horizon witnesses reject truncated and extended state and control histories") {
    const auto p=resolve(scalar());
    const auto reject_shape=[&](TrajectoryRequest q,const std::string& expected_field) {
        const auto report=verify_trajectory(p,q);
        CHECK(report.bindings==CheckStatus::numerical_pass);
        CHECK(report.feasibility==CheckStatus::invalid_input);
        CHECK(report.objective==CheckStatus::invalid_input);
        CHECK(std::any_of(report.diagnostics.begin(),report.diagnostics.end(),[&](const auto& diagnostic) {
            return diagnostic.code==DiagnosticCode::invalid_input&&diagnostic.field==expected_field;
        }));
    };
    auto q=request(p);q.witness.states.pop_back();reject_shape(q,"witness.states");
    q=request(p);q.witness.states.push_back({4});reject_shape(q,"witness.states");
    q=request(p);q.witness.controls.pop_back();reject_shape(q,"witness.controls");
    q=request(p);q.witness.controls.push_back({3});reject_shape(q,"witness.controls");
}
TEST_CASE("wrong problem and evidence never pass binding") {
    auto p=resolve(scalar());auto q=request(p);q.witness.problem={"wrong"};
    auto r=verify_trajectory(p,q);CHECK(r.bindings==CheckStatus::invalid_input);CHECK(r.feasibility==CheckStatus::not_checked);
    q=request(p);q.bounds.lower=ObjectiveBound{3,{{"wrong"},CertificateReference{"certificate","untrusted"}}};
    r=verify_trajectory(p,q);CHECK(r.bindings==CheckStatus::invalid_input);REQUIRE(r.input.bounds.lower);
    CHECK(r.input.bounds.lower->evidence.problem.value=="wrong");
}
TEST_CASE("mismatched outcome and objective-bound identities are rejected with evidence retained") {
    const auto p=resolve(scalar());
    const auto retained=CertificateReference{"retained-certificate","external-reference-only"};
    {
        auto q=request(p);
        q.outcome=SynthesisOutcomeClaim{{"other-problem"},MathematicalOutcome::optimal,retained,{"caller assumption"}};
        const auto r=verify_trajectory(p,q);
        CHECK(r.bindings==CheckStatus::invalid_input);
        CHECK(r.feasibility==CheckStatus::not_checked);
        REQUIRE(r.input.outcome);
        CHECK(r.input.outcome->subject.value=="other-problem");
        CHECK(r.input.outcome->value==MathematicalOutcome::optimal);
        REQUIRE(std::holds_alternative<CertificateReference>(r.input.outcome->support));
        CHECK(std::get<CertificateReference>(r.input.outcome->support).artifact==retained.artifact);
        CHECK(std::get<CertificateReference>(r.input.outcome->support).verifier==retained.verifier);
        CHECK(r.input.outcome->assumptions==std::vector<std::string>{"caller assumption"});
    }
    {
        auto q=request(p);
        q.bounds.lower=ObjectiveBound{2,{{"other-problem"},retained}};
        const auto r=verify_trajectory(p,q);
        CHECK(r.bindings==CheckStatus::invalid_input);
        CHECK(r.feasibility==CheckStatus::not_checked);
        REQUIRE(r.input.bounds.lower);
        CHECK(r.input.bounds.lower->value==2);
        CHECK(r.input.bounds.lower->evidence.problem.value=="other-problem");
        REQUIRE(std::holds_alternative<CertificateReference>(r.input.bounds.lower->evidence.support));
        CHECK(std::get<CertificateReference>(r.input.bounds.lower->evidence.support).artifact==retained.artifact);
        CHECK(std::get<CertificateReference>(r.input.bounds.lower->evidence.support).verifier==retained.verifier);
    }
    {
        auto q=request(p);
        const ProgramIdentity subject{{"other-problem"},{"reported-backend-program"}};
        q.backend_bounds.push_back({ProgramObjectiveBound{2,{subject,retained,{"backend assumption"}}},std::nullopt});
        const auto r=verify_trajectory(p,q);
        CHECK(r.bindings==CheckStatus::invalid_input);
        CHECK(r.feasibility==CheckStatus::not_checked);
        REQUIRE(r.input.backend_bounds.size()==1);
        REQUIRE(r.input.backend_bounds[0].lower);
        CHECK(r.input.backend_bounds[0].lower->value==2);
        CHECK(r.input.backend_bounds[0].lower->evidence.subject==subject);
        REQUIRE(std::holds_alternative<CertificateReference>(r.input.backend_bounds[0].lower->evidence.support));
        CHECK(std::get<CertificateReference>(r.input.backend_bounds[0].lower->evidence.support).artifact==retained.artifact);
        CHECK(std::get<CertificateReference>(r.input.backend_bounds[0].lower->evidence.support).verifier==retained.verifier);
        CHECK(r.input.backend_bounds[0].lower->evidence.assumptions==std::vector<std::string>{"backend assumption"});
    }
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
    q.verification=VerificationRequest{{0.125,0.03125},Assurance::numerical};
    ExecutionContext c;
    auto result=verify_trajectory(p,q,c);
    CHECK(result.feasibility==CheckStatus::numerical_pass);
    CHECK(result.objective==CheckStatus::numerical_pass);
    CHECK(result.completeness==CheckStatus::unsupported);
    q.witness.controls[1][0]=1.25;
    result=verify_trajectory(p,q,c);
    CHECK(result.feasibility==CheckStatus::violation);
    CHECK_FALSE(residual(result,"controls[1].inequalities[0]").satisfied);
    CHECK(residual(result,"controls[1].inequalities[0]").measure.scale==1.25);
    CHECK(residual(result,"controls[1].inequalities[0]").tolerance==0.1640625);
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
class CancelAfterMembership final:public LPWorkspace {
    std::stop_source& stop_;
public:
    explicit CancelAfterMembership(std::stop_source& stop):stop_(stop){}
    ProgramOutcome do_solve(const LinearProgram& p,const ExecutionContext&) override {
        stop_.request_stop();
        return ProgramResult{Termination::completed,
            {p.identity(),MathematicalOutcome::optimal,Unestablished{},{}},Vector{0.25,0.75},{},"literal barycentric answer"};
    }
};
registry::PreparedProvider<registry::LPPort> cancel_after_membership_provider(std::stop_source& stop) {
    registry::Registry<registry::LPPort> registry;
    REQUIRE(!registry.add({{{"cancel-after-membership"},"1"},
        [](const LinearProgram&,const registry::Requirements&)->registry::Capability{return registry::Offer{};},
        [&stop](const LinearProgram&){return std::make_unique<CancelAfterMembership>(stop);}}));
    return accepted(registry::prepare_provider(registry::select_provider(registry,{{"cancel-after-membership"},"1"})));
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
    input.objective=ResidualNormTerminal{{1,2,{1,2}},{7}};p=resolve(input);q=ltv_request(p);
    q.witness.original_objective=5;
    auto r=verify_trajectory(p,q);CHECK(r.recomputed_objective==5);CHECK(r.objective==CheckStatus::numerical_pass);
    q.witness.original_objective=25;r=verify_trajectory(p,q);
    CHECK(r.recomputed_objective==5);CHECK(r.objective==CheckStatus::violation);
    CHECK(residual(r,"objective").measure.violation==20);
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
TEST_CASE("injected temporal bounds are recomputed over the original joint history") {
    auto input=scalar();
    // The verifier's independent coordinate order is x0, x1, u0. These rows
    // evaluate to x1 + u0 = 6 (above 5) and x0 - u0 = -1 (below 0).
    input.temporal=TemporalConstraints{
        {2,3,{0,2,4},{1,2,0,2},{1,1,1,-1}},
        {{std::nullopt,5.0},{0.0,std::nullopt}}};
    const auto p=resolve(input);
    const auto r=verify_trajectory(p,request(p));
    CHECK(r.feasibility==CheckStatus::violation);
    CHECK(r.objective==CheckStatus::numerical_pass);
    CHECK(residual(r,"temporal[0].upper").measure.violation==1);
    CHECK(residual(r,"temporal[1].lower").measure.violation==1);
    CHECK(r.optimality==CheckStatus::unsupported);
    CHECK(r.completeness==CheckStatus::unsupported);
    CHECK(r.validated==CheckStatus::unsupported);
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
    q.verification=VerificationRequest{{0.125,0},Assurance::numerical};auto r=verify_trajectory(p,q);
    CHECK(r.objective==CheckStatus::numerical_pass);CHECK(residual(r,"objective").tolerance==0.125);
    q.verification=VerificationRequest{{0.124,0},Assurance::numerical};CHECK(verify_trajectory(p,q).objective==CheckStatus::violation);
    q.verification=VerificationRequest{{-1,0},Assurance::numerical};CHECK(verify_trajectory(p,q).feasibility==CheckStatus::invalid_input);
    q.verification=VerificationRequest{{1e-8,1e-8},Assurance::validated};r=verify_trajectory(p,q);CHECK(r.feasibility==CheckStatus::unsupported);
    CHECK(r.validated==CheckStatus::unsupported);
    q=request(p);q.witness.states[0][0]=std::numeric_limits<double>::quiet_NaN();CHECK(verify_trajectory(p,q).feasibility==CheckStatus::invalid_input);
}
TEST_CASE("relative tolerances use the reported objective scale at exact boundaries") {
    auto p=resolve(scalar());auto q=request(p);
    q.verification=VerificationRequest{{0.5,0.125},Assurance::numerical};
    q.witness.original_objective=4;
    auto report=verify_trajectory(p,q);
    CHECK(report.objective==CheckStatus::numerical_pass);
    CHECK(report.verification==*q.verification);
    CHECK(report.numerical==q.verification->numerical);
    CHECK(residual(report,"objective").measure.scale==4);
    CHECK(residual(report,"objective").measure.violation==1);
    CHECK(residual(report,"objective").tolerance==1);

    q.verification=VerificationRequest{{0.5,0.0625},Assurance::numerical};report=verify_trajectory(p,q);
    CHECK(report.objective==CheckStatus::violation);
    CHECK(residual(report,"objective").tolerance==0.75);

    q.witness.original_objective=8;
    q.verification=VerificationRequest{{0.5,0.5625},Assurance::numerical};report=verify_trajectory(p,q);
    CHECK(report.objective==CheckStatus::numerical_pass);
    CHECK(report.verification==*q.verification);
    CHECK(residual(report,"objective").measure.scale==8);
    CHECK(residual(report,"objective").measure.violation==5);
    CHECK(residual(report,"objective").tolerance==5);
    q.verification=VerificationRequest{{0.5,0.5},Assurance::numerical};report=verify_trajectory(p,q);
    CHECK(report.objective==CheckStatus::violation);
    CHECK(residual(report,"objective").tolerance==4.5);
}
TEST_CASE("infinite witness values and numerical tolerances are invalid inputs") {
    const auto p=resolve(scalar());auto q=request(p);
    q.witness.states[1][0]=std::numeric_limits<double>::infinity();
    auto report=verify_trajectory(p,q);
    CHECK(report.feasibility==CheckStatus::invalid_input);
    CHECK(std::any_of(report.diagnostics.begin(),report.diagnostics.end(),[](const auto& diagnostic) {
        return diagnostic.field=="witness.states[1]"&&diagnostic.code==DiagnosticCode::invalid_input;
    }));

    q=request(p);q.witness.original_objective=std::numeric_limits<double>::infinity();
    report=verify_trajectory(p,q);
    CHECK(report.objective==CheckStatus::invalid_input);
    CHECK(std::any_of(report.diagnostics.begin(),report.diagnostics.end(),[](const auto& diagnostic) {
        return diagnostic.field=="witness.original_objective"&&diagnostic.code==DiagnosticCode::invalid_input;
    }));

    q=request(p);q.verification=VerificationRequest{{std::numeric_limits<double>::infinity(),0},Assurance::numerical};
    report=verify_trajectory(p,q);
    CHECK(report.feasibility==CheckStatus::invalid_input);
    CHECK(report.verification==*q.verification);
    CHECK(std::any_of(report.diagnostics.begin(),report.diagnostics.end(),[](const auto& diagnostic) {
        return diagnostic.field=="numerical"&&diagnostic.code==DiagnosticCode::invalid_input;
    }));
}
TEST_CASE("unknown assurance values are rejected instead of downgraded to numerical verification") {
    const auto p=resolve(scalar());
    auto q=request(p);
    q.verification=VerificationRequest{{1e-8,1e-8},static_cast<Assurance>(127)};

    const auto report=verify_trajectory(p,q);
    CHECK(report.termination==Termination::completed);
    CHECK(report.bindings==CheckStatus::numerical_pass);
    CHECK(report.feasibility==CheckStatus::invalid_input);
    CHECK(report.objective==CheckStatus::invalid_input);
    CHECK(report.optimality==CheckStatus::unsupported);
    CHECK(report.completeness==CheckStatus::unsupported);
    CHECK(report.validated==CheckStatus::unsupported);
    CHECK(std::any_of(report.diagnostics.begin(),report.diagnostics.end(),[](const auto& diagnostic) {
        return diagnostic.field=="assurance" && diagnostic.code==DiagnosticCode::invalid_input;
    }));
}
TEST_CASE("stops and count limits retain supplied evidence and checked prefixes") {
    auto p=resolve(scalar());auto q=request(p);q.bounds.lower=ObjectiveBound{2,{p.identity(),CertificateReference{"retained","external"}}};
    std::stop_source stop;stop.request_stop();ExecutionContext c;c.cancellation=stop.get_token();
    auto r=verify_trajectory(p,q,c);CHECK(r.termination==Termination::cancelled);CHECK(r.feasibility==CheckStatus::not_checked);REQUIRE(r.input.bounds.lower);
    CHECK(std::get<CertificateReference>(r.input.bounds.lower->evidence.support).artifact=="retained");
    c={};c.deadline=std::chrono::steady_clock::time_point::min();CHECK(verify_trajectory(p,q,c).termination==Termination::deadline_expired);
    q.limits.residuals=1;r=verify_trajectory(p,q);CHECK(r.termination==Termination::resource_limit);CHECK(r.residuals.size()==1);
    CHECK(r.feasibility!=CheckStatus::numerical_pass);
}
TEST_CASE("Farkas evidence must bind the exact generated program or remain unpromoted") {
    const auto p=resolve(scalar());
    auto published=optimization::make_linear_program({{p.identity(),{"farkas/first"}},{0},0,
        {2,1,{0,1,2},{0,0},{1,1}},{{{},{}}},{{1,{}},{{},0}}});
    REQUIRE(std::holds_alternative<LinearProgram>(published));
    const auto first=std::get<LinearProgram>(std::move(published));
    const LinearInfeasibilityCertificate certificate{first.identity(),{1,0},{0,1},{0},{0}};
    auto checked=optimization::verify_linear_infeasibility_certificate(first,certificate);
    REQUIRE(std::holds_alternative<ExactFarkasEvidence>(checked));
    const auto proof=std::get<ExactFarkasEvidence>(std::move(checked));

    auto q=request(p);
    q.backend_bounds.push_back({ProgramObjectiveBound{0,{first.identity(),proof,{}}},std::nullopt});
    CHECK(verify_trajectory(p,q).bindings==CheckStatus::invalid_input);

    auto foreign=first.identity();foreign.program={"farkas/foreign"};
    q.backend_bounds[0].lower->evidence.subject=foreign;
    CHECK(verify_trajectory(p,q).bindings==CheckStatus::invalid_input);

    q=request(p);
    q.bounds.lower=ObjectiveBound{0,{p.identity(),proof}};
    CHECK(verify_trajectory(p,q).bindings==CheckStatus::invalid_input);
}
TEST_CASE("late cancellation after registered membership retains evidence without completing claims") {
    auto input=scalar();input.states[1]=segment_v();auto p=resolve(input);auto q=request(p);
    q.bounds.lower=ObjectiveBound{2,{p.identity(),CertificateReference{"retained","external"}}};
    std::stop_source stop;ExecutionContext c;c.cancellation=stop.get_token();
    auto r=verify_trajectory(p,q,c,cancel_after_membership_provider(stop));
    CHECK(r.termination==Termination::cancelled);
    CHECK(r.bindings==CheckStatus::numerical_pass);
    CHECK(r.feasibility==CheckStatus::not_checked);CHECK(r.objective==CheckStatus::not_checked);
    CHECK(r.optimality==CheckStatus::unsupported);CHECK(r.completeness==CheckStatus::unsupported);
    CHECK(r.validated==CheckStatus::unsupported);
    REQUIRE(r.input.bounds.lower);
    CHECK(r.input.bounds.lower->value==2);
    CHECK(std::get<CertificateReference>(r.input.bounds.lower->evidence.support).artifact=="retained");
    CHECK(residual(r,"initial[0]").satisfied);
    CHECK(r.membership_queries.size()==1);
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
    q.expected_synthesis=ExpectedSynthesisBinding{effective,{"candidate-strategy"},"1",{}};
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
TEST_CASE("candidate-family witness cannot borrow feasibility from a different checked trajectory") {
    auto p=resolve(scalar());
    auto q=request(p);
    const ClaimEvidence claim{p.identity(),NumericalCheck{0,0,0,{"backend"}}};
    const auto coordinates=p.constraints().coordinates();
    const FamilyRequest effective{"nominal",p.identity(),FamilyTarget::candidate_relaxation,
        {1e-8,1e-8},Assurance::numerical,{"candidate-family"},{}};
    const ModuleId strategy{"candidate-strategy"};
    q.expected_synthesis=ExpectedSynthesisBinding{effective,strategy,"1",{}};
    const FamilyIdentity identity{p.identity(),effective,coordinates,strategy,"1",{}};
    const auto relation=JointRelation{coordinates,effective.representation,{}};

    auto forged=q.witness;
    forged.states[1][0]=99;
    q.family=accepted(FamilyPublisher::publish(identity,CandidateFamily{relation,
        HeuristicRelationEvidence{"literal candidate"},WitnessFeasibilityEvidence{forged,claim}}));

    const auto report=verify_trajectory(p,q);
    CHECK(report.bindings==CheckStatus::invalid_input);
    CHECK(report.feasibility==CheckStatus::not_checked);
}
TEST_CASE("sampled relaxed and symbolic candidate metadata never establish family coverage") {
    const auto p=resolve(scalar());auto q=request(p);
    const ClaimEvidence numerical{p.identity(),NumericalCheck{0,0,0,{"candidate backend"}}};
    const auto coordinates=p.constraints().coordinates();
    const FamilyRequest effective{"nominal",p.identity(),FamilyTarget::candidate_relaxation,
        {1e-8,1e-8},Assurance::numerical,{"candidate-family"},{}};
    const ModuleId strategy{"candidate-strategy"};
    q.expected_synthesis=ExpectedSynthesisBinding{effective,strategy,"1",{}};
    const auto publish=[&](FamilyRelationToTarget relation_evidence) {
        const FamilyIdentity identity{p.identity(),effective,coordinates,strategy,"1",{}};
        const JointRelation relation{coordinates,effective.representation,{}};
        return accepted(FamilyPublisher::publish(identity,CandidateFamily{relation,
            std::move(relation_evidence),WitnessFeasibilityEvidence{q.witness,numerical}}));
    };
    q.outcome=SynthesisOutcomeClaim{p.identity(),MathematicalOutcome::optimal,
        SymbolicArgument{"floating-point-completeness-claim","unvalidated symbolic argument"},
        {"backend success metadata"}};
    q.backend_bounds={ProgramObjectiveEvidence{ProgramObjectiveBound{3,
        {{p.identity(),{"original-program"}},SymbolicArgument{"backend-bound","floating-point"},{}}},{}}};

    const auto check_nonpromotion=[&]() {
        const auto report=verify_trajectory(p,q);
        CHECK(report.bindings==CheckStatus::numerical_pass);
        CHECK(report.feasibility==CheckStatus::numerical_pass);
        CHECK(report.optimality==CheckStatus::unsupported);
        CHECK(report.completeness==CheckStatus::unsupported);
        CHECK(report.validated==CheckStatus::unsupported);
        REQUIRE(report.input.family);
        CHECK(report.input.family->target()==FamilyTarget::candidate_relaxation);
        REQUIRE(report.input.outcome);
        CHECK(std::holds_alternative<SymbolicArgument>(report.input.outcome->support));
        REQUIRE(report.input.backend_bounds.size()==1);
        REQUIRE(report.input.backend_bounds[0].lower);
        CHECK(std::holds_alternative<SymbolicArgument>(report.input.backend_bounds[0].lower->evidence.support));
        return report;
    };

    q.family=publish(HeuristicRelationEvidence{"finite sampled witness cloud"});
    const auto sampled_report=check_nonpromotion();
    CHECK(std::get<HeuristicRelationEvidence>(std::get<CandidateFamily>(sampled_report.input.family->outcome()).relation_to_target).method
        =="finite sampled witness cloud");

    q.family=publish(OuterCandidateEvidence{numerical});
    const auto relaxed_report=check_nonpromotion();
    const auto& relaxed_evidence=std::get<OuterCandidateEvidence>(
        std::get<CandidateFamily>(relaxed_report.input.family->outcome()).relation_to_target).enclosure;
    CHECK(relaxed_evidence.problem==numerical.problem);
    REQUIRE(std::holds_alternative<NumericalCheck>(relaxed_evidence.support));
    CHECK(std::get<NumericalCheck>(relaxed_evidence.support).absolute_tolerance==0);
    CHECK(std::get<NumericalCheck>(relaxed_evidence.support).relative_tolerance==0);
    CHECK(std::get<NumericalCheck>(relaxed_evidence.support).max_residual==0);
    CHECK(std::get<NumericalCheck>(relaxed_evidence.support).verifier.value=="candidate backend");

    const ClaimEvidence symbolic{p.identity(),SymbolicArgument{"symbolic-relaxation","floating-point only"}};
    q.family=publish(OuterCandidateEvidence{symbolic});
    const auto symbolic_report=check_nonpromotion();
    const auto& symbolic_evidence=std::get<SymbolicArgument>(std::get<OuterCandidateEvidence>(
        std::get<CandidateFamily>(symbolic_report.input.family->outcome()).relation_to_target).enclosure.support);
    CHECK(symbolic_evidence.reference=="symbolic-relaxation");
    CHECK(symbolic_evidence.assumptions=="floating-point only");
}
TEST_CASE("validated verification cannot promote numerical candidate completeness claims") {
    const auto p=resolve(scalar());auto q=request(p);
    const ClaimEvidence numerical{p.identity(),NumericalCheck{0,0,0,{"numerical candidate"}}};
    const auto coordinates=p.constraints().coordinates();
    const FamilyRequest effective{"nominal",p.identity(),FamilyTarget::candidate_relaxation,
        {1e-8,1e-8},Assurance::numerical,{"candidate-family"},{}};
    const ModuleId strategy{"candidate-strategy"};
    const FamilyIdentity identity{p.identity(),effective,coordinates,strategy,"1",{}};
    const JointRelation relation{coordinates,effective.representation,{}};
    q.expected_synthesis=ExpectedSynthesisBinding{effective,strategy,"1",{}};
    q.family=accepted(FamilyPublisher::publish(identity,CandidateFamily{relation,
        OuterCandidateEvidence{numerical},WitnessFeasibilityEvidence{q.witness,numerical}}));
    q.verification=VerificationRequest{{1e-8,1e-8},Assurance::validated};

    const auto report=verify_trajectory(p,q);
    CHECK(report.bindings==CheckStatus::numerical_pass);
    CHECK(report.verification==*q.verification);
    CHECK(report.feasibility==CheckStatus::unsupported);
    CHECK(report.objective==CheckStatus::unsupported);
    CHECK(report.optimality==CheckStatus::unsupported);
    CHECK(report.completeness==CheckStatus::unsupported);
    CHECK(report.validated==CheckStatus::unsupported);
    REQUIRE(report.input.family);
    CHECK(report.input.family->target()==FamilyTarget::candidate_relaxation);
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
TEST_CASE("separate verification policy leaves the prepared solve family identity unchanged") {
    auto p=resolve(scalar());auto q=request(p);
    q.witness.original_objective=3.125;
    ClaimEvidence claim{p.identity(),NumericalCheck{0,0,0,{"backend"}}};
    auto solve_request=FamilyRequest{"nominal",p.identity(),FamilyTarget::candidate_relaxation,
        {1e-7,2e-7},Assurance::numerical,{"opaque-family"},{}};
    const auto coordinates=p.constraints().coordinates();
    const ModuleId strategy{"candidate-strategy"};
    q.expected_synthesis=ExpectedSynthesisBinding{solve_request,strategy,"1",{}};
    const FamilyIdentity family_identity{p.identity(),solve_request,coordinates,strategy,"1",{}};
    const JointRelation relation{coordinates,solve_request.representation,{}};
    q.family=accepted(FamilyPublisher::publish(family_identity,CandidateFamily{relation,
        HeuristicRelationEvidence{"literal candidate"},WitnessFeasibilityEvidence{q.witness,claim}}));

    const VerificationRequest verification{{0.1,0},Assurance::numerical};
    q.verification=verification;
    ExecutionContext context;context.numerical={0.5,0};
    const auto report=verify_trajectory(p,q,context);
    const NumericalPolicy solve_policy{1e-7,2e-7};

    CHECK(report.bindings==CheckStatus::numerical_pass);
    CHECK(report.feasibility==CheckStatus::numerical_pass);
    CHECK(report.objective==CheckStatus::violation);
    CHECK(residual(report,"objective").measure.violation==0.125);
    CHECK(residual(report,"objective").tolerance==0.1);
    CHECK(report.verification==verification);
    CHECK(report.input.verification==verification);
    CHECK(report.numerical==verification.numerical);
    REQUIRE(report.input.family.has_value());
    CHECK(report.input.family->identity().request.numerical==solve_policy);
    REQUIRE(report.input.expected_synthesis.has_value());
    CHECK(report.input.expected_synthesis->request.numerical==solve_policy);
    CHECK(q.family->identity().request.numerical==solve_policy);
    CHECK(q.expected_synthesis->request.numerical==solve_policy);
}
TEST_CASE("legacy positional trajectory request aggregate remains source compatible") {
    auto p=resolve(scalar());
    const auto witness=request(p).witness;
    TrajectoryRequest legacy{witness,Assurance::numerical,std::nullopt,std::nullopt,{}, {}, {}};
    const auto report=verify_trajectory(p,legacy);
    CHECK(report.bindings==CheckStatus::numerical_pass);
    CHECK(report.feasibility==CheckStatus::numerical_pass);
    CHECK(report.optimality==CheckStatus::unsupported);
    CHECK(report.completeness==CheckStatus::unsupported);
}
TEST_CASE("legacy positional trajectory report aggregate remains source compatible") {
    const auto p=resolve(scalar());
    const NumericalPolicy legacy_policy{0.125,0.25};
    const TrajectoryReport report{p.identity(),request(p),Verifier{{"csl.trajectory.original"},"1"},legacy_policy};
    CHECK(report.numerical==legacy_policy);
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
    const ClaimEvidence family_claim{p.identity(),NumericalCheck{0,0,0,{"retained candidate"}}};
    const FamilyRequest family_request{"nominal",p.identity(),FamilyTarget::candidate_relaxation,
        {1e-8,1e-8},Assurance::numerical,{"retained-candidate-family"},{}};
    const auto coordinates=p.constraints().coordinates();
    const ModuleId strategy{"candidate-strategy"};
    const FamilyIdentity family_identity{p.identity(),family_request,coordinates,strategy,"1",{}};
    const JointRelation family_relation{coordinates,family_request.representation,{}};
    q.expected_synthesis=ExpectedSynthesisBinding{family_request,strategy,"1",{}};
    q.family=accepted(FamilyPublisher::publish(family_identity,CandidateFamily{family_relation,
        HeuristicRelationEvidence{"retained candidate relation"},WitnessFeasibilityEvidence{q.witness,family_claim}}));
    auto count=std::make_shared<int>(0);r=verify_trajectory(p,q,{},provider(7,count));
    CHECK(r.termination==Termination::completed);CHECK(r.feasibility==CheckStatus::unsupported);CHECK(*count==0);
    CHECK(r.bindings==CheckStatus::numerical_pass);
    REQUIRE(r.input.bounds.lower);CHECK(r.input.bounds.lower->value==0);
    REQUIRE(std::holds_alternative<CertificateReference>(r.input.bounds.lower->evidence.support));
    CHECK(std::get<CertificateReference>(r.input.bounds.lower->evidence.support).artifact=="retained-bound");
    REQUIRE(r.input.family);CHECK(r.input.family->identity()==family_identity);
    CHECK(r.input.family->target()==FamilyTarget::candidate_relaxation);
    CHECK(std::holds_alternative<CandidateFamily>(r.input.family->outcome()));
    const auto& retained_candidate=std::get<CandidateFamily>(r.input.family->outcome());
    CHECK(std::get<HeuristicRelationEvidence>(retained_candidate.relation_to_target).method=="retained candidate relation");
    REQUIRE(std::holds_alternative<WitnessFeasibilityEvidence>(retained_candidate.feasibility));
    const auto& retained_witness=std::get<WitnessFeasibilityEvidence>(retained_candidate.feasibility);
    CHECK(retained_witness.witness.problem==q.witness.problem);
    CHECK(retained_witness.witness.states==q.witness.states);
    CHECK(retained_witness.witness.controls==q.witness.controls);
    CHECK(retained_witness.witness.original_objective==q.witness.original_objective);
    CHECK(retained_witness.support.problem==p.identity());
    REQUIRE(std::holds_alternative<NumericalCheck>(retained_witness.support.support));
    const auto& retained_check=std::get<NumericalCheck>(retained_witness.support.support);
    CHECK(retained_check.absolute_tolerance==0);
    CHECK(retained_check.relative_tolerance==0);
    CHECK(retained_check.max_residual==0);
    CHECK(retained_check.verifier.value=="retained candidate");
    CHECK(r.optimality==CheckStatus::unsupported);CHECK(r.completeness==CheckStatus::unsupported);
    CHECK(r.validated==CheckStatus::unsupported);
    REQUIRE(r.membership_queries.size()==1);
    CHECK(std::holds_alternative<registry::LPQueryRejected>(r.membership_queries[0]));
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
