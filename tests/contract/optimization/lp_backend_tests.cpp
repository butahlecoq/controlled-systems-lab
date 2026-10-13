#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/lp_backend.hpp>
#include <csl/registry/registry.hpp>
#include <limits>
#include <stdexcept>
using namespace csl;
using namespace csl::optimization;
using namespace csl::registry;
namespace {
template<class T> T accepted(LPDataResult<T> r) { REQUIRE(std::holds_alternative<T>(r)); return std::get<T>(std::move(r)); }
LinearProgram triangle(double offset=0) { return accepted(make_linear_program({{{"p"},{offset==0?"triangle":"triangle-offset"}},{-1,-2},offset,{1,2,{0,2},{0,1},{1,1}},{{0,{}},{0,{}}},{{{},1}}})); }
ProgramResult candidate(const LinearProgram& p,Termination t=Termination::resource_limit) {
    return {t,{p.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},Vector{0,1},{},"partial"};
}
ProgramObjectiveBound bound(const LinearProgram& p,double value) {
    return {value,{p.identity(),SymbolicArgument{"literal analytic oracle","stated fixture only"},{"binary64 check"}}};
}
void rejected(const Diagnostics& d, DiagnosticCode code) { REQUIRE_FALSE(d.empty()); CHECK(d[0].code == code); }
const Verifier verifier{{"literal-check"},"1"};
const NumericalPolicy policy{1e-9,1e-9};
ExecutionContext context(std::string mode="return") { return {{},{},{},policy,std::move(mode)}; }
// A one-row basis arithmetic fixture, not a general LP solver or pivot kernel.
class LiteralWorkspace final : public LPWorkspace {
public:
    ProgramOutcome do_solve(const LinearProgram& p,const ExecutionContext& c) override {
        if(c.run_id=="throws") throw std::runtime_error("literal exception");
        if(c.run_id=="unsupported") return Unsupported{{{DiagnosticCode::unsupported,"fixture","deliberate"}}};
        auto t=Termination::completed;
        if(c.run_id=="cancel") t=Termination::cancelled;
        if(c.run_id=="limit") t=Termination::resource_limit;
        if(c.run_id=="numerical") t=Termination::numerical_failure;
        return {ProgramResult{t,{p.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},{},{},"fixture"}};
    }
};
class LiteralBasis final : public BasisDiagnostics {
    const LPWorkspace& workspace_;
public:
    explicit LiteralBasis(const LPWorkspace& w):workspace_(w) {}
    BasisCapabilities capabilities() const override { return {true,true,true}; }
    BasisSnapshotResult snapshot() const override {
        const auto& a=workspace_.last_attempt();
        if(!a) return BasisUnavailable{BasisUnavailableReason::not_solved,"no attempt"};
        if(a->state!=SolveAttemptState::returned_result) return BasisUnavailable{BasisUnavailableReason::unavailable_result,"no result"};
        const auto& p=a->stamp.program();
        if(p.constraints().rows()==0) return BasisSnapshot{{a->stamp,0},{},{}};
        const BasisReference before{a->stamp,0},after{a->stamp,1};
        const BasisColumn old=StructuralColumn{0}, entering=StructuralColumn{1};
        return BasisSnapshot{after,{entering},PivotRecord{before,after,{old},entering,old,0,p.constraints()(0,1)/p.constraints()(0,0)}};
    }
    BasisCoordinatesResult coordinates(const BasisReference& ref,std::span<const double> rhs) const override {
        auto result=snapshot();
        if(auto* u=std::get_if<BasisUnavailable>(&result)) return *u;
        auto b=std::get<BasisSnapshot>(result);
        if(ref!=b.reference) return BasisUnavailable{BasisUnavailableReason::stale_reference,"basis changed"};
        if(rhs.size()!=b.columns.size()) return Diagnostics{{DiagnosticCode::invalid_input,"basis.rhs","shape"}};
        if(rhs.empty()) return BasisCoordinates{ref,{}};
        return BasisCoordinates{ref,{rhs[0]/ref.solve.program().constraints()(0,1)}};
    }
};
LinearProgram basis_program(double entering=6) {
    return accepted(make_linear_program({{{"p"},{entering>0?"basis-positive":"basis-negative"}},{0,0},0,{1,2,{0,2},{0,1},{2,entering}},{{{},{}},{{},{}}},{{0,0}}}));
}
LinearProgram improving_ray(double coefficient=-1,double offset=0) {
    return accepted(make_linear_program({{{"p"},{coefficient<0?"min-improving-ray":"normalized-source-max"}},
        {coefficient},offset,{0,1,{0},{},{}},{{0,{}}},{}}));
}
auto plan(const LinearProgram& p,bool with_basis=true) {
    Registry<LPPort> registry;
    Registration<LPPort> r{{{"literal"},"1"},[](const LinearProgram&,const Requirements&)->Capability{return Offer{};},
        [](const LinearProgram&){return std::make_unique<LiteralWorkspace>();}};
    if(with_basis) r.basis_factory=[](const LinearProgram&,LPWorkspace& w){return std::make_unique<LiteralBasis>(w);};
    registry.add(std::move(r));
    Requirements requirements; requirements.basis_diagnostics=with_basis;
    auto prepared=prepare_pipeline(select(registry,Method{{"literal"},{}},p,requirements));
    REQUIRE(std::holds_alternative<PreparedPipeline<LPPort>>(prepared));
    return std::get<PreparedPipeline<LPPort>>(std::move(prepared));
}
}
TEST_CASE("program evidence preserves partial and unestablished outcomes and rejects a different reformulation") {
    const auto p=triangle();
    for(auto t:{Termination::completed,Termination::cancelled,Termination::resource_limit,Termination::numerical_failure}) {
        auto r=candidate(p,t); r.objective.upper=bound(p,-2);
        CHECK(check_program_result(r,p,Assurance::numerical).empty());
        r.outcome.value=MathematicalOutcome::optimal;
        CHECK(check_program_result(r,p,Assurance::numerical).empty());
        CHECK(std::holds_alternative<Unestablished>(r.outcome.support));
        r.objective.upper->evidence.subject.program={"another"};
        rejected(check_program_result(r,p,Assurance::numerical),DiagnosticCode::evidence_mismatch);
    }
    auto r=candidate(p); r.outcome.value=MathematicalOutcome::infeasible;
    CHECK(check_program_result(r,p,Assurance::numerical).empty()); // raw candidate is not a feasible assertion
    r.outcome.support=SymbolicArgument{"contradiction","literal rows"}; r.objective.upper=bound(p,-2);
    rejected(check_program_result(r,p,Assurance::numerical),DiagnosticCode::invalid_claim);
    r=candidate(p); r.outcome={p.identity(),MathematicalOutcome::unbounded,SymbolicArgument{"ray","literal fixture"},{}};
    r.objective.lower=bound(p,-2);
    rejected(check_program_result(r,p,Assurance::numerical),DiagnosticCode::invalid_claim);
    r=candidate(p); r.objective.lower=bound(p,1); r.objective.upper=bound(p,-2);
    rejected(check_program_result(r,p,Assurance::numerical),DiagnosticCode::invalid_claim);
    r=candidate(p); r.objective.upper=bound(p,std::numeric_limits<double>::infinity());
    rejected(check_program_result(r,p,Assurance::numerical),DiagnosticCode::invalid_claim);
    rejected(check_program_result(candidate(p),p,Assurance::validated),DiagnosticCode::unsupported);
}
TEST_CASE("typed residual checks preserve provenance and do not manufacture bounds") {
    const auto p=triangle(); auto r=candidate(p);
    auto e=accepted(evaluate_primal(p,*r.primal,policy,verifier)); r.residuals.primal=e.residuals;
    CHECK(e.objective == -2); CHECK(check_program_result(r,p,Assurance::numerical).empty());
    CHECK_FALSE(r.objective.lower); CHECK_FALSE(r.objective.upper);
    r.residuals.primal->context.subject.program={"other"};
    rejected(check_program_result(r,p,Assurance::numerical),DiagnosticCode::evidence_mismatch);
    r.residuals.primal=e.residuals; r.residuals.primal->rows.scale=-1;
    rejected(check_program_result(r,p,Assurance::numerical),DiagnosticCode::invalid_claim);
}
TEST_CASE("literal dual convention preserves offset and rejects multipliers on absent endpoints") {
    const auto p=triangle(7);
    DualMultipliers multipliers{{0},{2},{1,0},{0,0}};
    const auto d=accepted(evaluate_dual(p,multipliers,policy,verifier));
    CHECK(d.lagrangian_constant == 5); CHECK(d.residuals.stationarity->violation == 0);
    CHECK(d.residuals.signs->violation == 0); CHECK_FALSE(d.residuals.complementarity);
    CHECK(accepted(evaluate_dual(triangle(),multipliers,policy,verifier)).lagrangian_constant == -2);
    multipliers.row_lower[0]=1;
    CHECK(std::holds_alternative<Diagnostics>(evaluate_dual(p,multipliers,policy,verifier)));
    multipliers.row_lower[0]=0; multipliers.variable_upper[0]=1;
    CHECK(std::holds_alternative<Diagnostics>(evaluate_dual(p,multipliers,policy,verifier)));
    multipliers.variable_upper[0]=0; multipliers.variable_lower[0]=-1;
    CHECK(accepted(evaluate_dual(p,multipliers,policy,verifier)).residuals.signs->violation == 1);
}
TEST_CASE("actual bound workspaces independently identify attempts and preserve historical snapshots") {
    auto prepared=plan(basis_program()); auto first=prepared.create(),second=prepared.create();
    auto& w1=*std::get<0>(first); auto& w2=*std::get<0>(second);
    CHECK(w1.workspace_identity()!=w2.workspace_identity());
    CHECK_FALSE(w1.last_attempt());
    CHECK(std::get<BasisUnavailable>(w1.basis()->snapshot()).reason==BasisUnavailableReason::not_solved);
    w1.run(context()); w2.run(context());
    REQUIRE(w1.last_attempt()); REQUIRE(w2.last_attempt());
    auto b1=std::get<BasisSnapshot>(w1.basis()->snapshot()); auto b2=std::get<BasisSnapshot>(w2.basis()->snapshot());
    CHECK(b1.reference.solve.attempt()==1); CHECK(check_basis_snapshot(b1,w1.last_attempt()).empty());
    rejected(check_basis_snapshot(b2,w1.last_attempt()),DiagnosticCode::evidence_mismatch);
    rejected(check_basis_snapshot(b1,{}),DiagnosticCode::evidence_mismatch);
    for(const auto* stop:{"cancel","limit","numerical"}) {
        auto r=std::get<ProgramResult>(w1.run(context(stop)));
        CHECK(r.outcome.value==MathematicalOutcome::undetermined);
        rejected(check_basis_snapshot(b1,w1.last_attempt()),DiagnosticCode::evidence_mismatch);
        CHECK(check_basis_snapshot(std::get<BasisSnapshot>(w1.basis()->snapshot()),w1.last_attempt()).empty());
    }
    CHECK(w1.last_attempt()->stamp.attempt()==4);
    CHECK(std::holds_alternative<Unsupported>(w1.run(context("unsupported"))));
    CHECK(w1.last_attempt()->state==SolveAttemptState::unsupported); CHECK(w1.last_attempt()->stamp.attempt()==5);
    rejected(check_basis_snapshot(b1,w1.last_attempt()),DiagnosticCode::evidence_mismatch);
    CHECK_THROWS_WITH_AS(w1.run(context("throws")),"literal exception",std::runtime_error);
    CHECK(w1.last_attempt()->state==SolveAttemptState::exception); CHECK(w1.last_attempt()->stamp.attempt()==6);
    w1.run(context()); CHECK(w1.last_attempt()->stamp.attempt()==7);
    std::get<0>(first).reset(); std::get<0>(second).reset();
    CHECK(b1.last_pivot->coefficient==3); CHECK(b1.reference.solve.program().constraints()(0,1)==6);
}
TEST_CASE("basis ordering and pre-pivot coefficient have explicit original-row coordinates") {
    for(double entering:{6.0,-6.0}) {
        auto workers=plan(basis_program(entering)).create(); auto& w=*std::get<0>(workers); w.run(context());
        auto b=std::get<BasisSnapshot>(w.basis()->snapshot());
        REQUIRE(b.last_pivot); CHECK(b.last_pivot->coefficient==(entering>0?3:-3));
        CHECK(b.columns==std::vector<BasisColumn>{StructuralColumn{1}});
        CHECK(check_basis_snapshot(b,w.last_attempt()).empty());
        auto z=std::get<BasisCoordinates>(w.basis()->coordinates(b.reference,Vector{12}));
        CHECK(z.values==Vector{entering>0?2.0:-2.0});
        CHECK(check_basis_coordinates(z,b,w.last_attempt()).empty());
        z.values={1,2}; rejected(check_basis_coordinates(z,b,w.last_attempt()),DiagnosticCode::invalid_claim);
        auto wrong=b; wrong.last_pivot->position=1;
        rejected(check_basis_snapshot(wrong,w.last_attempt()),DiagnosticCode::invalid_claim);
        wrong=b; wrong.columns={StructuralColumn{0}};
        rejected(check_basis_snapshot(wrong,w.last_attempt()),DiagnosticCode::invalid_claim);
        wrong=b; wrong.last_pivot->after.iteration=3;
        rejected(check_basis_snapshot(wrong,w.last_attempt()),DiagnosticCode::invalid_claim);
        wrong=b; wrong.last_pivot->coefficient=std::numeric_limits<double>::quiet_NaN();
        rejected(check_basis_snapshot(wrong,w.last_attempt()),DiagnosticCode::invalid_claim);
        w.run(context());
        CHECK(std::get<BasisUnavailable>(w.basis()->coordinates(b.reference,Vector{12})).reason==BasisUnavailableReason::stale_reference);
    }
}
TEST_CASE("generic adapters need no basis and zero rows have an empty basis") {
    const auto p=accepted(make_linear_program({{{"p"},{"zero"}},{1},0,{0,1,{0},{},{}},{{{},{}}},{}}));
    auto generic=plan(p,false).create();
    CHECK(std::get<ProgramResult>(std::get<0>(generic)->run(context())).outcome.value==MathematicalOutcome::undetermined);
    CHECK(std::get<0>(generic)->basis()==nullptr);
    auto workers=plan(p).create(); auto& w=*std::get<0>(workers); w.run(context());
    auto b=std::get<BasisSnapshot>(w.basis()->snapshot()); CHECK(check_basis_snapshot(b,w.last_attempt()).empty());
    auto coordinates=std::get<BasisCoordinates>(w.basis()->coordinates(b.reference,{}));
    CHECK(check_basis_coordinates(coordinates,b,w.last_attempt()).empty());
    coordinates.values={1}; rejected(check_basis_coordinates(coordinates,b,w.last_attempt()),DiagnosticCode::invalid_claim);
    auto wrong_iteration=b; wrong_iteration.reference.iteration=1;
    rejected(check_basis_snapshot(wrong_iteration,w.last_attempt()),DiagnosticCode::invalid_claim);
    b.columns={RowActivityColumn{0}}; rejected(check_basis_snapshot(b,w.last_attempt()),DiagnosticCode::invalid_claim);
}

TEST_CASE("basis checks reject rank reduction, duplicate identities and malformed auxiliary columns") {
    const auto p=accepted(make_linear_program({{{"p"},{"two-rows"}},{0,0},0,{2,2,{0,1,2},{0,1},{1,1}},{{{},{}},{{},{}}},{{0,0},{0,0}}}));
    LiteralWorkspace w; w.solve(p,context());
    BasisSnapshot b{{w.last_attempt()->stamp,0},{StructuralColumn{0},StructuralColumn{1}},{}};
    CHECK(check_basis_snapshot(b,w.last_attempt()).empty());
    b.columns.pop_back(); rejected(check_basis_snapshot(b,w.last_attempt()),DiagnosticCode::invalid_claim);
    b.columns={StructuralColumn{0},StructuralColumn{0}}; rejected(check_basis_snapshot(b,w.last_attempt()),DiagnosticCode::invalid_claim);
    b.columns={StructuralColumn{0},RowActivityColumn{2}}; rejected(check_basis_snapshot(b,w.last_attempt()),DiagnosticCode::invalid_claim);
    b.columns={AuxiliaryColumn{0,{1,0}},AuxiliaryColumn{1,{0,1}}}; CHECK(check_basis_snapshot(b,w.last_attempt()).empty());
    b.columns[1]=AuxiliaryColumn{0,{0,1}}; rejected(check_basis_snapshot(b,w.last_attempt()),DiagnosticCode::invalid_claim);
    b.columns[1]=AuxiliaryColumn{1,{1}}; rejected(check_basis_snapshot(b,w.last_attempt()),DiagnosticCode::invalid_claim);
    b.columns[1]=AuxiliaryColumn{1,{0,std::numeric_limits<double>::infinity()}};
    rejected(check_basis_snapshot(b,w.last_attempt()),DiagnosticCode::invalid_claim);
}
TEST_CASE("dual residual records reject wrong identities and malformed available checks") {
    const auto p=triangle(); auto r=candidate(p);
    r.residuals.dual=accepted(evaluate_dual(p,{{0},{2},{1,0},{0,0}},policy,verifier)).residuals;
    CHECK(check_program_result(r,p,Assurance::numerical).empty());
    r.residuals.dual->context.subject.program={"wrong"};
    rejected(check_program_result(r,p,Assurance::numerical),DiagnosticCode::evidence_mismatch);
    r.residuals.dual->context.subject=p.identity(); r.residuals.dual->stationarity->violation=-1;
    rejected(check_program_result(r,p,Assurance::numerical),DiagnosticCode::invalid_claim);
}

TEST_CASE("contradictory rows and an improving ray remain distinct supported reports without manufactured finite bounds") {
    const auto infeasible=accepted(make_linear_program({{{"p"},{"contradiction"}},{0},0,{2,1,{0,1,2},{0,0},{1,1}},{{{},{}}},{{{},0},{1,{}}}}));
    const auto ray=accepted(make_linear_program({{{"p"},{"improving-ray"}},{-1},0,{0,1,{0},{},{}},{{0,{}}},{}}));
    ProgramResult empty{Termination::completed,{infeasible.identity(),MathematicalOutcome::infeasible,
        SymbolicArgument{"x<=0 and x>=1 contradict","real scalar x"},{}},{},{},"literal analytic report"};
    CHECK(check_program_result(empty,infeasible,Assurance::numerical).empty());
    rejected(check_program_result(empty,ray,Assurance::numerical),DiagnosticCode::evidence_mismatch);
    ProgramResult unbounded{Termination::completed,{ray.identity(),MathematicalOutcome::unbounded,
        SymbolicArgument{"x(t)=t, t>=0, cost=-t","nonnegative scalar t"},{}},{},{},"literal analytic report"};
    CHECK(check_program_result(unbounded,ray,Assurance::numerical).empty());
    CHECK(accepted(evaluate_primal(ray,Vector{10},policy,verifier)).objective==-10);
    unbounded.objective.lower=bound(ray,0);
    rejected(check_program_result(unbounded,ray,Assurance::numerical),DiagnosticCode::invalid_claim);
}

TEST_CASE("minimization bounds distinguish supported unboundedness from finite upper evidence") {
    const auto p=improving_ray();
    ProgramResult unbounded{Termination::completed,{p.identity(),MathematicalOutcome::unbounded,
        SymbolicArgument{"x(t)=t, t>=0, objective=-t","real scalar t"},{}},{},{} ,"literal analytic report"};
    unbounded.objective.lower=bound(p,-1);
    rejected(check_program_result(unbounded,p,Assurance::numerical),DiagnosticCode::invalid_claim);

    unbounded.objective.lower.reset();
    unbounded.objective.upper=bound(p,0);
    CHECK(check_program_result(unbounded,p,Assurance::numerical).empty());
}

TEST_CASE("source maximization bounds map through an explicitly normalized minimization program") {
    // Source max (x + 2) is represented by min (-x - 2); no maximize API is implied.
    const auto normalized=improving_ray(-1,-2);
    CHECK(accepted(evaluate_primal(normalized,Vector{3},policy,verifier)).objective==-5);

    ProgramResult unbounded{Termination::completed,{normalized.identity(),MathematicalOutcome::unbounded,
        SymbolicArgument{"x(t)=t, t>=0, normalized objective=-t-2","real scalar t"},{}},{},{} ,"literal analytic report"};
    // lower(max f)=0 maps to upper(min -f)=0.
    unbounded.objective.upper=bound(normalized,0);
    CHECK(check_program_result(unbounded,normalized,Assurance::numerical).empty());

    // upper(max f)=5 maps to lower(min -f)=-5, contradicting unboundedness below.
    unbounded.objective.upper.reset();
    unbounded.objective.lower=bound(normalized,-5);
    rejected(check_program_result(unbounded,normalized,Assurance::numerical),DiagnosticCode::invalid_claim);
}

TEST_CASE("unsupported outcome or bound evidence does not create an unboundedness contradiction") {
    const auto p=improving_ray();
    ProgramResult r{Termination::completed,{p.identity(),MathematicalOutcome::unbounded,
        Unestablished{},{}},{},{} ,"literal candidate"};
    r.objective.lower=bound(p,0);
    CHECK(check_program_result(r,p,Assurance::numerical).empty());

    r.outcome.support=SymbolicArgument{"improving ray","x(t)=t"};
    r.objective.lower=ProgramObjectiveBound{0,{p.identity(),Unestablished{},{}}};
    CHECK(check_program_result(r,p,Assurance::numerical).empty());
}

TEST_CASE("undetermined minimization outcome may retain a supported finite bound") {
    const auto p=improving_ray();
    ProgramResult r{Termination::resource_limit,{p.identity(),MathematicalOutcome::undetermined,
        Unestablished{},{}},{},{} ,"literal candidate"};
    r.objective.upper=bound(p,0);
    CHECK(check_program_result(r,p,Assurance::numerical).empty());
}
