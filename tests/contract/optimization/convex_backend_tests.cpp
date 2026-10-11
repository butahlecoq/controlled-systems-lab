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
