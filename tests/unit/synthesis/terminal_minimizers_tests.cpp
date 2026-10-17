#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/synthesis/terminal_minimizers.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/convex/highs.hpp>
using namespace csl;
namespace {
template<class T,class... R> T accepted(std::variant<T,R...> value) { REQUIRE(std::holds_alternative<T>(value)); return std::get<T>(std::move(value)); }
numeric::MatrixView matrix(Matrix m) { return accepted(numeric::snapshot(m)); }
numeric::VectorView vector(Vector v) { return accepted(numeric::snapshot_vector(v)); }
sets::SetData box() { return accepted(sets::make_h({{"terminal-box"},2,{}},{matrix({4,2,{1,0,-1,0,0,1,0,-1}}),vector({1,0,1,0}),matrix({0,2,{}}),vector({})})); }
problem::ResolvedProblem resolved(TerminalObjective objective) {
    Problem p{{"terminal-fixture"},std::make_shared<const SystemModel>(SystemModel{{{2,1,0},TimeDomain::discrete,LinearStage{{2,2,{1,0,0,1}},{2,1,{0,0}},{2,0,{}},{0,0}}},{}}),{0,1},KnownInitial{{0,0}},ContinuousDomain{{Singleton{{0}}}},{UniversalSet{2},UniversalSet{2}},{},{},InformationPattern::nominal_open_loop,std::move(objective)};
    return accepted(problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
synthesis::TerminalOptimizer real_optimizer() {
    registry::Requirements requirements; requirements.output.representation={"csl.program-result.v1"}; registry::Registry<registry::LPPort> lp; auto l=accepted(adapters::lp::make_highs_registration());auto lid=l.identity.id;lp.add(std::move(l));
    registry::Registry<registry::ConvexPort> qp;auto q=accepted(adapters::convex::make_highs_registration());auto qid=q.identity.id;qp.add(std::move(q));
    return {accepted(registry::prepare_provider(registry::select_provider(lp,registry::Method{lid,{}},requirements))),accepted(registry::prepare_provider(registry::select_provider(qp,registry::Method{qid,{}},requirements)))};
}
// Independent analytic optimum port: fixes the literal oracle anchor and value,
// leaving relation construction and nullspace preservation to production code.
template<class Program,class Base> class AnalyticWorkspace final:public Base {
    Vector anchor_; double value_; bool wrong_; MathematicalOutcome outcome_; Termination termination_;
    ProgramOutcome do_solve(const Program& p,const ExecutionContext&) override {
        auto identity=p.identity();if(wrong_)identity.problem={"different"}; const EvidenceSupport proof=outcome_==MathematicalOutcome::optimal?EvidenceSupport{SymbolicArgument{"literal-box-oracle","independently minimized objective on [0,1]^2"}}:EvidenceSupport{Unestablished{}};
        const ProgramObjectiveBound bound{value_,{identity,proof,{}}};
        return ProgramResult{termination_,{identity,outcome_,proof,{}},anchor_,{bound,bound},"analytic fixture"};
    }
public: AnalyticWorkspace(Vector a,double value,bool wrong,MathematicalOutcome outcome,Termination termination):anchor_(std::move(a)),value_(value),wrong_(wrong),outcome_(outcome),termination_(termination){}
};
synthesis::TerminalOptimizer analytic_optimizer(Vector anchor,double value,bool wrong=false,MathematicalOutcome outcome=MathematicalOutcome::optimal,Termination termination=Termination::completed) {
    registry::Registry<registry::LPPort> lp;registry::Registry<registry::ConvexPort> qp;
    registry::Requirements req;req.output.representation={"csl.program-result.v1"};
    const auto offer=[=](const auto&,const registry::Requirements&)->registry::Capability{return registry::Offer{req.output};};
    lp.add({{{"analytic-lp"},"1"},offer,[=](const LinearProgram&){return std::make_unique<AnalyticWorkspace<LinearProgram,LPWorkspace>>(anchor,value,wrong,outcome,termination);}});
    qp.add({{{"analytic-qp"},"1"},offer,[=](const ConvexProgram&){return std::make_unique<AnalyticWorkspace<ConvexProgram,ConvexWorkspace>>(anchor,value,wrong,outcome,termination);}});
    return {accepted(registry::prepare_provider(registry::select_provider(lp,registry::Method{{"analytic-lp"},{}},req))),accepted(registry::prepare_provider(registry::select_provider(qp,registry::Method{{"analytic-qp"},{}},req)))};
}
synthesis::TerminalMinimizers solve(TerminalObjective objective,Vector anchor={0,0},double value=0) {
    auto p=resolved(std::move(objective));FamilyRequest r;r.objective=p.identity();r.profile="nominal-polyhedral";r.representation={"polyhedral-h"};
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    return analytic_optimizer(std::move(anchor),value).solve(p,r,{p.identity(),box()},context);
}bool contains(const sets::SetData& set,Vector x) {
    const auto h=std::get<sets::HRepresentation>(set.representation());
    for(std::size_t i=0;i<h.inequalities.rows();++i) {double a=0;for(std::size_t j=0;j<x.size();++j)a+=h.inequalities(i,j)*x[j];if(a>h.upper_bounds[i]+1e-6)return false;}
    for(std::size_t i=0;i<h.equalities.rows();++i) {double a=0;for(std::size_t j=0;j<x.size();++j)a+=h.equalities(i,j)*x[j];if(std::abs(a-h.equality_values[i])>1e-6)return false;}
    return true;
}
sets::SetData box2() { return accepted(sets::make_h({{"terminal-box-2"},2,{}},{matrix({4,2,{1,0,-1,0,0,1,0,-1}}),vector({2,0,2,0}),matrix({0,2,{}}),vector({})})); }
}
TEST_CASE("linear optimal face retains both ends and interior") {
    auto r=solve(LinearTerminal{{1,0},7},{0,0},7);for(const auto& d:r.diagnostics) MESSAGE(d.field,": ",d.explanation); REQUIRE(r.relation);CHECK(contains(*r.relation,{0,0}));CHECK(contains(*r.relation,{0,0.5}));CHECK(contains(*r.relation,{0,1}));CHECK_FALSE(contains(*r.relation,{1,0}));
    REQUIRE(r.optimum);REQUIRE(r.optimum->bounds.upper);CHECK(r.optimum->bounds.upper->value==doctest::Approx(7));CHECK(std::holds_alternative<Unestablished>(r.construction.support));
}
TEST_CASE("constant objective preserves every terminal point") {
    auto r=solve(LinearTerminal{{0,0},3},{0,0},3);for(const auto& d:r.diagnostics) MESSAGE(d.field,": ",d.explanation); REQUIRE(r.relation);for(Vector x:std::vector<Vector>{{0,0},{1,1},{0.3,0.7}})CHECK(contains(*r.relation,x));CHECK_FALSE(contains(*r.relation,{2,0}));
}
TEST_CASE("semidefinite quadratic retains nullspace with boundary optimum") {
    auto r=solve(QuadraticTerminal{{2,2,{2,0,0,0}},{2,0},0});for(const auto& d:r.diagnostics) MESSAGE(d.field,": ",d.explanation); REQUIRE(r.relation);CHECK(contains(*r.relation,{0,0}));CHECK(contains(*r.relation,{0,1}));CHECK_FALSE(contains(*r.relation,{1,0}));
}
TEST_CASE("rectangular residual map retains every degenerate minimizer") {
    auto r=solve(ResidualNormTerminal{{1,2,{1,0}},{0.5}},{0.5,0},0);for(const auto& d:r.diagnostics) MESSAGE(d.field,": ",d.explanation); REQUIRE(r.relation);CHECK(contains(*r.relation,{0.5,0}));CHECK(contains(*r.relation,{0.5,1}));CHECK_FALSE(contains(*r.relation,{0,0}));
}





TEST_CASE("quadratic linear term restricts a Hessian nullspace") {
    auto r=solve(QuadraticTerminal{{2,2,{0,0,0,2}},{1,0},0});REQUIRE(r.relation);CHECK(contains(*r.relation,{0,0}));CHECK_FALSE(contains(*r.relation,{1,0}));CHECK_FALSE(contains(*r.relation,{0,1}));
}
TEST_CASE("zero residual map retains the whole feasible box") {
    auto r=solve(ResidualNormTerminal{{1,2,{0,0}},{2}},{0,0},2);REQUIRE(r.relation);CHECK(contains(*r.relation,{0,0}));CHECK(contains(*r.relation,{1,1}));CHECK(contains(*r.relation,{0.3,0.9}));
}
TEST_CASE("real HiGHS preserves linear face and honest absent bounds") {
    auto p=resolved(LinearTerminal{{1,0},7});FamilyRequest q;q.objective=p.identity();
    ExecutionContext c;c.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto r=real_optimizer().solve(p,q,{p.identity(),box()},c);REQUIRE(r.relation);CHECK(contains(*r.relation,{0,1}));REQUIRE(r.optimum);CHECK_FALSE(r.optimum->bounds.lower);CHECK_FALSE(r.optimum->bounds.upper);CHECK(std::holds_alternative<Unestablished>(r.construction.support));
}

TEST_CASE("foreign provider result identity cannot become a terminal relation") {
    auto p=resolved(LinearTerminal{{1,0},0});FamilyRequest q;q.objective=p.identity();
    auto r=analytic_optimizer({0,0},0,true).solve(p,q,{p.identity(),box()},{});
    CHECK(r.termination==Termination::contract_rejected);CHECK_FALSE(r.relation);CHECK_FALSE(r.optimization);REQUIRE_FALSE(r.diagnostics.empty());CHECK(r.diagnostics[0].code==DiagnosticCode::evidence_mismatch);
}
TEST_CASE("unattained finite infimum retains bounds without an argmin relation") {
    auto p=resolved(LinearTerminal{{1,0},0});FamilyRequest q;q.objective=p.identity();
    auto r=analytic_optimizer({0,0},0,false,MathematicalOutcome::infimum_not_attained).solve(p,q,{p.identity(),box()},{});
    CHECK(r.outcome==MathematicalOutcome::infimum_not_attained);CHECK_FALSE(r.relation);REQUIRE(r.optimum);REQUIRE(r.optimum->bounds.lower);CHECK(r.optimum->bounds.lower->value==0);
}
TEST_CASE("execution stop remains distinct from supported optimizer evidence") {
    auto p=resolved(LinearTerminal{{1,0},0});FamilyRequest q;q.objective=p.identity();
    auto r=analytic_optimizer({0,0},0,false,MathematicalOutcome::optimal,Termination::resource_limit).solve(p,q,{p.identity(),box()},{});
    CHECK(r.termination==Termination::resource_limit);CHECK(r.outcome==MathematicalOutcome::optimal);REQUIRE(r.relation);REQUIRE(r.optimization);REQUIRE(r.optimum);CHECK(r.optimum->bounds.upper->value==0);
}
TEST_CASE("wrong slice identity and unsupported representation are explicit") {
    auto p=resolved(LinearTerminal{{1,0},0});FamilyRequest q;q.objective=p.identity();auto o=analytic_optimizer({0,0},0);
    auto r=o.solve(p,q,{{"foreign"},box()},{});CHECK(r.termination==Termination::contract_rejected);CHECK_FALSE(r.relation);
    auto v=accepted(sets::make_v({{"vertex-box"},2,{}},{matrix({1,2,{0,0}}),matrix({0,2,{}})}));
    r=o.solve(p,q,{p.identity(),v},{});CHECK(r.termination==Termination::operation_rejected);REQUIRE_FALSE(r.diagnostics.empty());CHECK(r.diagnostics[0].code==DiagnosticCode::unsupported);
    q.assurance=Assurance::validated;r=o.solve(p,q,{p.identity(),box()},{});CHECK(r.termination==Termination::operation_rejected);
}
TEST_CASE("real HiGHS undetermined degenerate QP preserves diagnostics without a relation") {
    auto p=resolved(ResidualNormTerminal{{1,2,{1,0}},{0.5}});FamilyRequest q;q.objective=p.identity();ExecutionContext c;c.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto r=real_optimizer().solve(p,q,{p.identity(),box()},c);CHECK(r.outcome==MathematicalOutcome::undetermined);CHECK_FALSE(r.relation);REQUIRE(r.optimization);CHECK(r.optimization->raw_diagnostics.find("optimality.withheld=")!=std::string::npos);CHECK(r.optimization->raw_diagnostics.find("phase.qp.retry=")==std::string::npos);REQUIRE(r.provider);CHECK(r.provider->actual->id.value!="analytic-qp");
}
TEST_CASE("real HiGHS preserves zero-target degenerate quadratic and residual relations") {
    for(const TerminalObjective objective:std::vector<TerminalObjective>{QuadraticTerminal{{2,2,{2,0,0,0}},{0,0},0},ResidualNormTerminal{{1,2,{1,0}},{0}}}) {
        auto p=resolved(objective);FamilyRequest q;q.objective=p.identity();ExecutionContext c;c.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
        auto r=real_optimizer().solve(p,q,{p.identity(),box()},c);for(const auto& d:r.diagnostics)MESSAGE(d.explanation);CHECK(r.outcome==MathematicalOutcome::optimal);REQUIRE(r.relation);CHECK(contains(*r.relation,{0,0}));CHECK(contains(*r.relation,{0,1}));CHECK_FALSE(contains(*r.relation,{1,0}));CHECK(std::holds_alternative<Unestablished>(r.construction.support));
    }
}
TEST_CASE("program evidence is retained without asserting global problem optimum") {
    auto r=solve(LinearTerminal{{1,0},7},{0,0},7);REQUIRE(r.optimum);REQUIRE(r.optimization);CHECK(std::holds_alternative<Unestablished>(r.optimum->optimum.support));REQUIRE(r.optimum->bounds.upper);CHECK(std::holds_alternative<Unestablished>(r.optimum->bounds.upper->evidence.support));CHECK(std::holds_alternative<SymbolicArgument>(r.optimization->objective.upper->evidence.support));
}

// ---- Issue #69 [TEST-11]: independently designed oracle expansions ----

TEST_CASE("linear cost x on [0,1]^2 gives the whole edge x=0") {
    // Independent oracle: minimize c'x with c=(1,0) on [0,1]^2.
    // Every point with x=0 is optimal; no point with x>0 is optimal.
    auto r=solve(LinearTerminal{{1,0},0},{0,0},0);
    REQUIRE(r.relation);
    CHECK(contains(*r.relation,{0,0}));
    CHECK(contains(*r.relation,{0,0.5}));
    CHECK(contains(*r.relation,{0,1}));
    CHECK_FALSE(contains(*r.relation,{0.5,0}));
    CHECK_FALSE(contains(*r.relation,{1,1}));
    CHECK(r.outcome==MathematicalOutcome::optimal);
}

TEST_CASE("constant cost on [0,1]^2 gives the whole square, not a selected vertex") {
    // Independent oracle: constant objective c=(0,0), offset=5.
    // Every feasible point is a minimizer; the relation must not collapse to a vertex.
    auto r=solve(LinearTerminal{{0,0},5},{0,0},5);
    REQUIRE(r.relation);
    for(Vector x:std::vector<Vector>{{0,0},{1,1},{0,1},{1,0},{0.3,0.7},{0.5,0.5}})
        CHECK(contains(*r.relation,x));
    CHECK_FALSE(contains(*r.relation,{2,0}));
    CHECK(r.outcome==MathematicalOutcome::optimal);
}

TEST_CASE("rank-deficient quadratic (x+y-1)^2 on [0,2]^2 gives segment x+y=1") {
    // Independent oracle: minimize (x+y-1)^2 = x^2+2xy+y^2-2x-2y+1 on [0,2]^2.
    // Q=[[1,1],[1,1]], linear={-2,-2}, offset=1. Hessian H=(Q+Q')/2=[[1,1],[1,1]] (rank 1).
    // The minimizer set is the segment {(x,y): x+y=1, 0<=x<=1, 0<=y<=1}.
    Vector linear{-2,-2};
    auto p=resolved(QuadraticTerminal{{2,2,{1,1,1,1}},linear,1});
    FamilyRequest req;req.objective=p.identity();req.profile="nominal-polyhedral";req.representation={"polyhedral-h"};
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto r=analytic_optimizer({0,1},0).solve(p,req,{p.identity(),box2()},context);
    REQUIRE(r.relation);
    CHECK(contains(*r.relation,{0,1}));
    CHECK(contains(*r.relation,{1,0}));
    CHECK(contains(*r.relation,{0.5,0.5}));
    CHECK_FALSE(contains(*r.relation,{0,0}));
    CHECK_FALSE(contains(*r.relation,{2,2}));
    CHECK(r.outcome==MathematicalOutcome::optimal);
}

TEST_CASE("strictly convex quadratic has analytically unique minimizer") {
    // Independent oracle: minimize (x-0.3)^2+(y-0.7)^2 on [0,1]^2.
    // Q=[[2,0],[0,2]], linear={-0.6,-1.4}, offset=0.58. Unique minimizer at (0.3,0.7).
    // The unique terminal minimizer is distinguished from unique control history.
    Vector linear{-0.6,-1.4};
    auto r=solve(QuadraticTerminal{{2,2,{2,0,0,2}},linear,0.58},{0.3,0.7},0.58);
    REQUIRE(r.relation);
    CHECK(contains(*r.relation,{0.3,0.7}));
    CHECK_FALSE(contains(*r.relation,{0,0}));
    CHECK_FALSE(contains(*r.relation,{1,1}));
    CHECK(r.outcome==MathematicalOutcome::optimal);
}

TEST_CASE("unbounded attainment result is retained without a relation") {
    // Analytic oracle: unbounded outcome on a bounded slice must not produce a relation.
    auto p=resolved(LinearTerminal{{1,0},0});FamilyRequest q;q.objective=p.identity();
    auto r=analytic_optimizer({0,0},0,false,MathematicalOutcome::unbounded).solve(p,q,{p.identity(),box()},{});
    CHECK(r.outcome==MathematicalOutcome::unbounded);
    CHECK_FALSE(r.relation);
}

TEST_CASE("undetermined attainment result is retained without a relation") {
    // Analytic oracle: undetermined outcome must not produce a relation.
    auto p=resolved(LinearTerminal{{1,0},0});FamilyRequest q;q.objective=p.identity();
    auto r=analytic_optimizer({0,0},0,false,MathematicalOutcome::undetermined).solve(p,q,{p.identity(),box()},{});
    CHECK(r.outcome==MathematicalOutcome::undetermined);
    CHECK_FALSE(r.relation);
}

TEST_CASE("objective tolerance does not change exact level-set construction") {
    // The exact level-set {x: c'x=c'a} is independent of numerical tolerances.
    // A relaxed sublevel would be a relaxation, not the exact minimizer relation.
    auto p=resolved(LinearTerminal{{1,0},0});
    FamilyRequest q;q.objective=p.identity();q.profile="nominal-polyhedral";q.representation={"polyhedral-h"};
    q.numerical.absolute_tolerance=1e-3;
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto r=analytic_optimizer({0,0},0).solve(p,q,{p.identity(),box()},context);
    REQUIRE(r.relation);
    CHECK(contains(*r.relation,{0,0}));
    CHECK(contains(*r.relation,{0,1}));
    CHECK_FALSE(contains(*r.relation,{0.5,0}));
    CHECK(std::holds_alternative<Unestablished>(r.construction.support));
}

TEST_CASE("infeasible terminal slice is rejected") {
    // An empty terminal reachability slice must yield infeasible, not an empty relation.
    auto p=resolved(LinearTerminal{{1,0},0});FamilyRequest q;q.objective=p.identity();
    // Create an empty box (infeasible): x <= 1 and -x <= -2 (i.e. x >= 2)
    auto empty_box=accepted(sets::make_h({{"empty-box"},2,{}},{matrix({4,2,{1,0,-1,0,0,1,0,-1}}),vector({1,-2,1,0}),matrix({0,2,{}}),vector({})}));
    auto r=analytic_optimizer({0,0},0,false,MathematicalOutcome::infeasible).solve(p,q,{p.identity(),empty_box},{});
    CHECK(r.outcome==MathematicalOutcome::infeasible);
    CHECK_FALSE(r.relation);
}
