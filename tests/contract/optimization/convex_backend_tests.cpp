#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/convex_backend.hpp>
#include <csl/registry/registry.hpp>
#include <stdexcept>
using namespace csl;
using namespace csl::optimization;
using namespace csl::registry;
namespace {
ConvexProgram program() {
    return std::get<ConvexProgram>(make_convex_program({{{"p"},{"q"}},QuadraticTerminal{{1,1,{2}},{-6},9},{0,1,{0},{},{}},{{0,2}},{},{}}));
}
ConvexProgram normalized_maximum_program() {
    auto made=make_convex_program({{{"p"},{"normalized-source-max"}},LinearTerminal{{-1},-2},
        {0,1,{0},{},{}},{{0,{}}},{},{}});
    REQUIRE(std::holds_alternative<ConvexProgram>(made));
    return std::get<ConvexProgram>(std::move(made));
}
class LiteralWorkspace final : public ConvexWorkspace {
    ProgramOutcome do_solve(const ConvexProgram& p,const ExecutionContext& c) override {
        REQUIRE(last_attempt()->state==SolveAttemptState::running);
        if(c.run_id=="exception") throw std::runtime_error("literal exception");
        if(c.run_id=="unsupported") return Unsupported{{{DiagnosticCode::unsupported,"literal","unsupported"}}};
        return ProgramResult{Termination::resource_limit,{p.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},{},{},"literal"};
    }
};
}
TEST_CASE("convex authoritative attempts advance through return unsupported and exception and retain history") {
    auto history=[] {
        auto p=program(); LiteralWorkspace worker,other;
        CHECK(worker.workspace_identity()!=other.workspace_identity());
        CHECK_FALSE(worker.last_attempt());
        ExecutionContext c;
        worker.solve(p,c);
        auto first=*worker.last_attempt();
        CHECK(first.stamp.attempt()==1);
        CHECK(first.state==SolveAttemptState::returned_result);
        c.run_id="unsupported"; CHECK(std::holds_alternative<Unsupported>(worker.solve(p,c)));
        CHECK(worker.last_attempt()->stamp.attempt()==2);
        CHECK(worker.last_attempt()->state==SolveAttemptState::unsupported);
        c.run_id="exception"; CHECK_THROWS_AS(worker.solve(p,c),std::runtime_error);
        CHECK(worker.last_attempt()->stamp.attempt()==3);
        CHECK(worker.last_attempt()->state==SolveAttemptState::exception);
        return first;
    }();
    CHECK(history.stamp.program().identity().program.value=="q");
    CHECK(history.stamp.program().quadratic_program().hessian()(0,0)==2);
}
TEST_CASE("convex result validation keeps original program evidence subject") {
    auto p=program();
    ProgramResult r{Termination::completed,{p.identity(),MathematicalOutcome::optimal,Unestablished{},{}},Vector{2},{},"literal"};
    CHECK(check_program_result(r,p,Assurance::numerical).empty());
    r.outcome.subject.program={"foreign"};
    auto d=check_program_result(r,p,Assurance::numerical);
    REQUIRE_FALSE(d.empty()); CHECK(d[0].code==DiagnosticCode::evidence_mismatch);
}

TEST_CASE("convex caller validates the same normalized minimization sense for a source maximum") {
    // The convex API accepts minimization objectives. Source max (x + 2) is
    // represented by the convex affine minimization objective -(x + 2).
    const auto p=normalized_maximum_program();
    CHECK(std::get<double>(optimization::evaluate(p.original_objective(),Vector{3}))==-5);
    ProgramResult unbounded{Termination::completed,{p.identity(),MathematicalOutcome::unbounded,
        SymbolicArgument{"x(t)=t, t>=0, normalized objective=-t-2","real scalar t"},{}},{},{} ,"literal analytic report"};
    unbounded.objective.upper=ProgramObjectiveBound{0,{p.identity(),SymbolicArgument{"source lower bound 0 maps to normalized upper bound 0","literal mapping"},{}}};
    CHECK(check_program_result(unbounded,p,Assurance::numerical).empty());
    unbounded.objective.upper.reset();
    unbounded.objective.lower=ProgramObjectiveBound{-5,{p.identity(),SymbolicArgument{"source upper bound 5 maps to normalized lower bound -5","literal mapping"},{}}};
    auto d=check_program_result(unbounded,p,Assurance::numerical);
    REQUIRE_FALSE(d.empty()); CHECK(d[0].code==DiagnosticCode::invalid_claim);
}
